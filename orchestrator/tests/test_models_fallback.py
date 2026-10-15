"""票 11：降级链、同模型重试、退避、预算、能力跳过、跨通道标注（全部用假 provider 注入故障）。"""

from __future__ import annotations

import json

import httpx
import openai
import pytest
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel

from app.models.config import load_models_config
from app.models.fake import FakeChatModel
from app.models.registry import ModelRegistry
from app.models.router import (
    ModelInvokeError,
    ModelRouter,
    backoff_seconds,
    classify_exception,
)

CONFIG = """
version: t
default_lane: domestic
providers:
  cn1: {sdk: openai, api_key_env: K1}
  cn2: {sdk: openai, api_key_env: K2}
  us:  {sdk: anthropic, api_key_env: K3, lane: overseas}
models:
  a: {provider: cn1, id: a1, structured: json_object, vision: false, timeout_s: 5}
  b: {provider: cn2, id: b1, structured: json_object, vision: true,  timeout_s: 5}
  c: {provider: us,  id: c1, structured: json_object, vision: true,  timeout_s: 5}
  emb: {provider: cn1, id: e, kind: embedding}
  rr:  {provider: cn1, id: r, kind: rerank}
lanes:
  domestic:
    intake:               {chain: [a, b, c]}
    disambiguate.clarify: {chain: [a]}
    diagnose.vision:      {chain: [b, c], needs_vision: true}
    diagnose.synthesize:  {chain: [a, b]}
    guide.step:           {chain: [a]}
    reply.stream:         {chain: [a], stream: true}
    escalate.summary:     {chain: [a]}
    warranty.receipt_ocr: {chain: [b], needs_vision: true}
retry: {same_model_max: 1, rate_limit_max: 1, chain_max: 3, sdk_max_retries: 0}
concurrency: {max_in_flight: 50}
"""
KEYS = {"K1": "x", "K2": "x", "K3": "x"}


class Out(BaseModel):
    v: int


OK = json.dumps({"v": 1})
MSGS = [("human", "hi")]


def _resp(status: int) -> httpx.Response:
    return httpx.Response(status, request=httpx.Request("POST", "http://x"))


def rate_limited() -> Exception:
    return openai.RateLimitError("429 slow down", response=_resp(429), body=None)


def server_error() -> Exception:
    return openai.InternalServerError("502 bad gateway", response=_resp(502), body=None)


def refusal_msg() -> AIMessage:
    return AIMessage(content="", response_metadata={"stop_reason": "refusal"})


class FakeClock:
    """每次调用假模型推进 step 秒；now() 可读。"""

    def __init__(self, step: float = 0.0):
        self.t = 0.0
        self.step = step

    def __call__(self) -> float:
        return self.t


@pytest.fixture
def cfg(tmp_path):
    p = tmp_path / "models.yaml"
    p.write_text(CONFIG, encoding="utf-8")
    return load_models_config(p)


def build(cfg, scripts: dict[str, list], *, env=None, clock=None, per_call_s: float = 0.0):
    clock = clock or FakeClock()
    sleeps: list[float] = []

    class TickingFake(FakeChatModel):
        def _next(self, messages, run_manager, kwargs):
            clock.t += per_call_s
            return super()._next(messages, run_manager, kwargs)

    fakes = {a: TickingFake(script=list(s), name_for_trace=a) for a, s in scripts.items()}

    async def sleep(s: float) -> None:
        sleeps.append(s)
        clock.t += s

    reg = ModelRegistry(cfg, env=env if env is not None else KEYS)
    router = ModelRouter(
        reg,
        model_factory=lambda r, route: fakes[r.alias],
        clock=clock,
        sleep=sleep,
        rng=lambda: 0.5,
    )
    return router, fakes, sleeps


async def test_timeout_moves_to_the_next_model_without_waiting(cfg):
    """2026-10-13：主位 deepseek-v4-pro 并发时超时，同模型再等一次（9 s + 退避 + 9 s）吃光预算、轮不到兜底。"""
    router, fakes, sleeps = build(cfg, {"a": [TimeoutError(), OK], "b": [OK]})
    res = await router.invoke("intake", MSGS, Out, budget_ms=10_000)
    assert [(a.alias, a.outcome) for a in res.attempts] == [("a", "timeout"), ("b", "ok")]
    assert len(fakes["a"].calls) == 1 and sleeps == []


async def test_429_twice_moves_to_next_model(cfg):
    router, fakes, sleeps = build(cfg, {"a": [rate_limited(), rate_limited()], "b": [OK]})
    res = await router.invoke("intake", MSGS, Out, budget_ms=10_000)
    assert [(a.alias, a.outcome) for a in res.attempts] == [
        ("a", "rate_limited"),
        ("a", "rate_limited"),
        ("b", "ok"),
    ]
    assert sleeps == [1.25]  # 同模型只退避一次；换家不等待
    assert len(fakes["a"].calls) == 2


async def test_5xx_is_retried_and_refusal_is_not(cfg):
    router, fakes, sleeps = build(
        cfg, {"a": [server_error(), refusal_msg()], "b": [refusal_msg()], "c": [OK]}
    )
    res = await router.invoke("intake", MSGS, Out, budget_ms=10_000)
    assert [(a.alias, a.outcome) for a in res.attempts] == [
        ("a", "server_error"),
        ("a", "refusal"),
        ("b", "refusal"),
        ("c", "ok"),
    ]
    assert len(fakes["b"].calls) == 1  # 拒答不重试
    assert res.lane == "overseas" and [a.lane for a in res.attempts][-1] == "overseas"
    assert sleeps == [1.25]


async def test_schema_error_sequence_then_timeout_mix(cfg):
    router, fakes, _ = build(cfg, {"a": ["garbage", TimeoutError()], "b": [OK]})
    res = await router.invoke("intake", MSGS, Out, budget_ms=10_000)
    assert [(a.alias, a.outcome) for a in res.attempts] == [
        ("a", "schema_error"),
        ("a", "timeout"),
        ("b", "ok"),
    ]
    assert isinstance(fakes["a"].calls[1]["messages"][-1], HumanMessage)


async def test_budget_exhausted_stops_without_trying_remaining(cfg):
    """429 退避后剩余不足 1 s 再调一次：不再尝试任何模型，返回 budget exhausted。"""
    clock = FakeClock()
    router, fakes, sleeps = build(
        cfg, {"a": [rate_limited()], "b": [OK], "c": [OK]}, clock=clock, per_call_s=0.9
    )
    with pytest.raises(ModelInvokeError) as ei:
        await router.invoke("intake", MSGS, Out, budget_ms=1_500)
    assert ei.value.reason == "budget exhausted"
    assert [(a.alias, a.outcome) for a in ei.value.attempts] == [("a", "rate_limited")]
    assert fakes["b"].calls == [] and fakes["c"].calls == [] and sleeps == []


async def test_timeout_uses_the_remaining_budget_on_the_next_model(cfg):
    """超时直接换家：剩余预算交给下一家，而不是退避后放弃。"""
    clock = FakeClock()
    router, _fakes, _ = build(cfg, {"a": [TimeoutError()], "b": [OK]}, clock=clock, per_call_s=0.9)
    res = await router.invoke("intake", MSGS, Out, budget_ms=1_500)
    assert [(a.alias, a.outcome) for a in res.attempts] == [("a", "timeout"), ("b", "ok")]


async def test_budget_zero_returns_last_error_shape(cfg):
    router, fakes, _ = build(cfg, {"a": [OK]})
    with pytest.raises(ModelInvokeError, match="budget exhausted"):
        await router.invoke("intake", MSGS, Out, budget_ms=0)
    assert fakes["a"].calls == []


async def test_per_call_timeout_is_min_of_model_and_remaining(cfg):
    seen: list[float] = []
    router, _fakes, _ = build(cfg, {"a": [OK]})
    orig = router._call

    async def spy(runnable, msgs, config, timeout_s, method, schema):
        seen.append(timeout_s)
        return await orig(runnable, msgs, config, timeout_s, method, schema)

    router._call = spy  # type: ignore[method-assign]
    await router.invoke("intake", MSGS, Out, budget_ms=2_000)
    assert seen == [2.0]  # 模型 timeout_s=5，剩余 2 s → 取小
    router2, _, _ = build(cfg, {"a": [OK]})
    seen.clear()
    router2._call = spy  # type: ignore[method-assign]
    await router2.invoke("intake", MSGS, Out, budget_ms=60_000)
    assert seen == [5.0]


async def test_vision_capability_skipped_before_routing(cfg):
    image_msg = HumanMessage(
        content=[
            {"type": "text", "text": "看图"},
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,xx"}},
        ]
    )
    router, fakes, _ = build(cfg, {"a": [OK], "b": [OK]})
    res = await router.invoke("diagnose.synthesize", [image_msg], Out, budget_ms=5_000)
    assert [(a.alias, a.outcome) for a in res.attempts] == [("a", "skipped"), ("b", "ok")]
    assert res.attempts[0].error == "no vision capability"
    assert fakes["a"].calls == []


async def test_unconfigured_alias_skipped_not_counted_as_retry(cfg):
    router, _fakes, sleeps = build(cfg, {"a": [OK], "b": [OK]}, env={"K2": "x"})
    res = await router.invoke("intake", MSGS, Out, budget_ms=5_000)
    assert [(a.alias, a.outcome) for a in res.attempts] == [("a", "skipped"), ("b", "ok")]
    assert "missing env K1" in res.attempts[0].error and sleeps == []


async def test_whole_chain_fails_reports_all_attempts(cfg):
    router, _fakes, sleeps = build(
        cfg,
        {
            "a": [TimeoutError(), TimeoutError()],
            "b": [rate_limited(), server_error()],
            "c": ["nope", "nope"],
        },
    )
    with pytest.raises(ModelInvokeError) as ei:
        await router.invoke("intake", MSGS, Out, budget_ms=60_000)
    assert len(ei.value.attempts) == 5  # 超时直接换家，其余 (1 + same_model_max)
    assert [a.outcome for a in ei.value.attempts] == [
        "timeout",
        "rate_limited",
        "server_error",
        "schema_error",
        "schema_error",
    ]
    assert len(sleeps) == 1  # 只有 b 的 429 退避；超时换家与 c 的 schema 重试不等待


@pytest.fixture
def cooldown_cfg(tmp_path):
    p = tmp_path / "models.yaml"
    p.write_text(CONFIG.replace("sdk_max_retries: 0}", "sdk_max_retries: 0, cooldown_s: 30}"), encoding="utf-8")
    return load_models_config(p)


async def test_full_timeout_moves_model_to_chain_end_across_tasks_until_cooldown_ends(cooldown_cfg):
    """2026-10-15 官方 63 单 T58：intake 主位超时、备用接住后，同一轮 synthesize 主位再等满超时，备用只剩约 4 s。
    超时的模型在冷却期内对所有任务排到链尾；冷却结束恢复原顺序，再成功一次清除冷却。"""
    clock = FakeClock()
    router, fakes, _ = build(cooldown_cfg, {"a": [TimeoutError(), OK, OK], "b": [OK, OK]}, clock=clock)
    res = await router.invoke("intake", MSGS, Out, budget_ms=60_000)
    assert [(a.alias, a.outcome) for a in res.attempts] == [("a", "timeout"), ("b", "ok")]
    clock.t += 10
    res = await router.invoke("diagnose.synthesize", MSGS, Out, budget_ms=60_000)
    assert [(a.alias, a.outcome) for a in res.attempts] == [("b", "ok")]
    clock.t += 30
    res = await router.invoke("diagnose.synthesize", MSGS, Out, budget_ms=60_000)
    assert [(a.alias, a.outcome) for a in res.attempts] == [("a", "ok")]
    assert len(fakes["a"].calls) == 2


async def test_cooling_model_is_still_tried_last(cooldown_cfg):
    """冷却只调顺序不移除：排到前面的备用也失败时，冷却中的模型照样有机会。"""
    router, _fakes, _ = build(cooldown_cfg, {"a": [server_error(), server_error(), OK], "b": [OK, TimeoutError()]})
    res = await router.invoke("diagnose.synthesize", MSGS, Out, budget_ms=60_000)
    assert [(a.alias, a.outcome) for a in res.attempts] == [("a", "server_error"), ("a", "server_error"), ("b", "ok")]
    res = await router.invoke("diagnose.synthesize", MSGS, Out, budget_ms=60_000)
    assert [(a.alias, a.outcome) for a in res.attempts] == [("b", "timeout"), ("a", "ok")]


async def test_budget_truncated_timeout_does_not_cool_the_model(cooldown_cfg):
    """只剩 2 s 时的超时是预算不够，不是模型慢：下一次照常先试它。"""
    router, _fakes, _ = build(cooldown_cfg, {"a": [TimeoutError(), OK], "b": [OK]})
    with pytest.raises(ModelInvokeError):
        await router.invoke("disambiguate.clarify", MSGS, Out, budget_ms=2_000)
    res = await router.invoke("intake", MSGS, Out, budget_ms=60_000)
    assert [(a.alias, a.outcome) for a in res.attempts] == [("a", "ok")]


def test_sdk_max_retries_is_zero_in_repo_config_and_instances():
    from app.settings import REPO_ROOT

    cfg = load_models_config(REPO_ROOT / "config" / "models.yaml")
    assert cfg.retry.sdk_max_retries == 0
    reg = ModelRegistry(cfg, env={"DEEPSEEK_API_KEY": "x", "ANTHROPIC_API_KEY": "x"})
    assert reg.build("deepseek").max_retries == 0
    assert reg.build("sonnet").max_retries == 0


def test_backoff_table():
    assert backoff_seconds("rate_limited", 0, lambda: 0.0) == 1.0
    assert backoff_seconds("rate_limited", 1, lambda: 0.0) == 2.0
    assert backoff_seconds("rate_limited", 2, lambda: 0.0) == 4.0
    assert backoff_seconds("rate_limited", 9, lambda: 0.0) == 4.0
    assert backoff_seconds("timeout", 0, lambda: 0.0) == 1.0
    assert backoff_seconds("server_error", 3, lambda: 0.999) == pytest.approx(1.4995)
    for _ in range(50):
        w = backoff_seconds("timeout", 0)
        assert 1.0 <= w < 1.5


def test_classify_exception_table():
    assert classify_exception(TimeoutError()) == "timeout"
    assert (
        classify_exception(openai.APITimeoutError(request=httpx.Request("POST", "http://x")))
        == "timeout"
    )
    assert classify_exception(rate_limited()) == "rate_limited"
    assert classify_exception(server_error()) == "server_error"
    assert (
        classify_exception(openai.APIStatusError("503", response=_resp(503), body=None))
        == "server_error"
    )
    assert (
        classify_exception(
            openai.BadRequestError("data_inspection_failed", response=_resp(400), body=None)
        )
        == "refusal"
    )
    assert (
        classify_exception(openai.BadRequestError("bad json", response=_resp(400), body=None))
        == "error"
    )
    assert classify_exception(ValueError("x")) == "error"


def test_langchain_openai_connection_error_wrapper_is_retryable():
    """票 42 实测：langchain-openai 1.6 把连接失败包成 OpenAIConnectionError，名字不含 APIConnectionError。"""

    class OpenAIConnectionError(Exception):
        pass

    assert classify_exception(OpenAIConnectionError("Connection error.")) == "server_error"
    assert (
        classify_exception(openai.APIConnectionError(request=httpx.Request("GET", "http://x")))
        == "server_error"
    )
