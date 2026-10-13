"""适用性核对用结构化事实（2026-10-09 官方 63 单 I2 / I3：T18 T30 T50 T52 T61）。

模型与知识库均为假；检查的是服务端对候选方案的确定性核对，不是模型自觉。
"""

import pytest

from app.diagnose.synthesize import filter_hypotheses
from app.knowledge.runtime import set_knowledge_adapter
from app.plans.qa import qa_plan_library
from tests.conversation_runtime import conversation as base_conversation_fixture
from tests.fake_qa import QAHitAdapter
from tests.test_conversation_l3 import l3_runtime as l3_runtime_fixture

base_conversation = base_conversation_fixture
l3_runtime = l3_runtime_fixture
LIB = qa_plan_library()


@pytest.fixture
async def conversation(l3_runtime, base_conversation):
    yield base_conversation


T18 = (
    "Productnaam: Omni E28\nProduct-PN: T2352\nProbleemtype: WARNING\nProbleemcode: 3212-De mop is vastgezet.\n"
    "Probleempush: De mop met rol is verstopt, gelieve schoon te maken.\n"
    "Probleembeschrijving: Nieuw uit de doos. Toch de melding mop obstructed. Hoe los ik dit op?\n"
)


async def test_exact_steps_code_skips_model_applicability(conversation):
    """T18 / T30：同型号同错误码精确命中步骤类 Q&A → 直接发该方案首步，不再让模型判适用性，也不追问错误码。"""
    set_knowledge_adapter(QAHitAdapter("rv-0148"))
    model = conversation.models["diagnose.synthesize"]
    model.script = [{"hypotheses": []}]
    events = await conversation.send(T18, {
        "primary_intent": "report_problem", "device_relation": "current", "product_hints": ["Omni E28"],
        "facts": [{"value": "mop obstructed", "quote": "mop obstructed"}],
    })
    card = next(e for e in events if e["type"] == "step_card")
    assert card["step"]["plan_id"] == "qa_rv_0147"
    assert model.calls == []
    state = await conversation.state()
    assert state["plans_ranked"][0]["source"] == "exact_code"
    assert state["error_codes"] == ["3212"]
    assert state["retrieval_trace"][0]["status"] == "exact_code_steps"


def _allowed(*ids):
    return {pid: LIB.get(pid) for pid in ids}


def _hyp(pid, **extra):
    return {"plan_id": pid, "confidence": 0.9, "evidence_ids": ["e1"], "applicability": "supported",
            "supported_symptoms": ["the left one does work"], **extra}


def test_uncertain_polarity_forces_clarification():
    """T50：唯一症状的极性不确定 → 不能 supported，澄清问哪一侧、什么现象。"""
    facts = [{"kind": "symptom", "value": "the left one does work", "quote": "the left one does work",
              "subject": "left pump", "polarity": "uncertain", "status": "active"}]
    kept, dropped, clar = filter_hypotheses(
        [_hyp("qa_bp_0020")], allowed=_allowed("qa_bp_0020"), evidence_ids={"e1"},
        symptoms={"the left one does work"}, facts=facts, error_codes=[], max_n=3,
    )
    assert kept == [] and "polarity_uncertain:qa_bp_0020" in dropped
    assert clar and "Which side or part" in clar[0]["question"] and "the left one does work" in clar[0]["question"]


T52_SAID = "My charging case will not charge therefore I cannot charge my pump motors."


def test_uncertain_observation_alone_also_forces_clarification():
    """2026-10-13 deepseek-v4-pro：「the left one does work」被记成 observation 而非 symptom，选方案以 0.9 判可执行发了 5 张卡。
    唯一的客户陈述只是哪部分正常，不论记成现象还是观察，都先问哪一侧、什么问题。"""
    facts = [{"kind": "observation", "value": "the left one does work", "quote": "the left one does work",
              "polarity": "uncertain", "status": "active"}]
    kept, dropped, clar = filter_hypotheses(
        [_hyp("qa_bp_0020", supported_symptoms=["I have a S1 pump, the left one does work"])], allowed=_allowed("qa_bp_0020"),
        evidence_ids={"e1"}, symptoms={"I have a S1 pump, the left one does work"}, facts=facts, error_codes=[], max_n=3,
    )
    assert kept == [] and "polarity_uncertain:qa_bp_0020" in dropped
    assert "Which side or part" in clar[0]["question"]


def test_direction_conflict_drops_without_asking():
    """T61：「提前两小时启动」对「无法按时启动（7051）」方向相反。候选不对不是信息不足，不追问「你说的是提前吗」
    （重复客户原话，Fable D1）。是否相反由模型判断（conflict），原先是 before / early 对 failed to start 的词表。"""
    conflict = {"kind": "direction", "customer_quote": "going off 2 hours before", "candidate_quote": "failed to start scheduled cleaning"}
    kept, dropped, clar = filter_hypotheses(
        [_hyp("qa_rv_0522", supported_symptoms=["starts 2 hours before schedule"], conflict=conflict)],
        allowed=_allowed("qa_rv_0522"), evidence_ids={"e1"}, symptoms={"starts 2 hours before schedule"},
        facts=[], error_codes=[], said=["omni c20 isn't following my schedule, it's going off 2 hours before"], max_n=3,
    )
    assert kept == [] and clar == [] and "conflict_direction:qa_rv_0522" in dropped


def test_object_conflict_asks_about_the_customers_part():
    """T52：客户说盒子自身充不进电，候选讲泵在盒子里充不上电。追问盒子自身的状态。"""
    conflict = {"kind": "object", "customer_quote": "My charging case will not charge", "candidate_quote": "not charging in the case",
                "ask_about": "charging case"}
    kept, dropped, clar = filter_hypotheses(
        [_hyp("qa_bp_0067", supported_symptoms=["charging case will not charge"], conflict=conflict)],
        allowed=_allowed("qa_bp_0067"), evidence_ids={"e1"}, symptoms={"charging case will not charge"},
        facts=[], error_codes=[], said=[T52_SAID], max_n=3,
    )
    assert kept == [] and "conflict_object:qa_bp_0067" in dropped
    assert "charging case itself" in clar[0]["question"]


@pytest.mark.parametrize("conflict", [
    # 客户原话里没有这句：模型不能替客户添对象
    {"kind": "object", "customer_quote": "my charging hub is broken", "candidate_quote": "x", "ask_about": "charging hub"},
    # 引文是真的，但追问的部件不在引文里
    {"kind": "object", "customer_quote": "My charging case will not charge", "candidate_quote": "x", "ask_about": "pump hub"},
])
def test_object_conflict_without_grounded_quote_drops_without_asking(conflict):
    kept, dropped, clar = filter_hypotheses(
        [_hyp("qa_bp_0067", supported_symptoms=["charging case will not charge"], conflict=conflict)],
        allowed=_allowed("qa_bp_0067"), evidence_ids={"e1"}, symptoms={"charging case will not charge"},
        facts=[], error_codes=[], said=[T52_SAID], max_n=3,
    )
    assert kept == [] and clar == [] and "conflict_object:qa_bp_0067" in dropped


def test_different_code_same_model_is_not_applicable():
    facts = [{"kind": "symptom", "value": "mop obstructed", "quote": "x", "polarity": "affirmed", "status": "active"}]
    kept, dropped, clar = filter_hypotheses(
        [_hyp("qa_rv_0522", supported_symptoms=["mop obstructed"], applicability="needs_confirmation",
              clarification_question="Does the app show 7051?")],
        allowed=_allowed("qa_rv_0522"), evidence_ids={"e1"}, symptoms={"mop obstructed"},
        facts=facts, error_codes=["3212"], max_n=3,
    )
    assert kept == [] and "code_mismatch:qa_rv_0522" in dropped and clar == []


def test_clarification_never_asks_a_known_code():
    facts = [{"kind": "symptom", "value": "mop obstructed", "quote": "x", "polarity": "affirmed", "status": "active"}]
    _, _, clar = filter_hypotheses(
        [_hyp("qa_rv_0147", supported_symptoms=["mop obstructed"], applicability="needs_confirmation",
              clarification_question="Does the app show 3212 or 3202?")],
        allowed=_allowed("qa_rv_0147"), evidence_ids={"e1"}, symptoms={"mop obstructed"},
        facts=facts, error_codes=["3212"], max_n=3,
    )
    assert clar == []


# ---- §3 首轮 operation_update 不绕过检索（T31）；§4 no_match 先澄清再交接（T60）----

T31 = (
    "Product Name: S1 Pro\nProduct PN: T2080A\nProblem Type: Ask Us\n"
    "Problem Description: The robot won't charge when it is at the base station despite wiping clean the electrical connections "
    "and the robot can't get past critical low battery\n"
)


async def test_first_turn_operation_phrase_still_retrieves(conversation):
    """T31：模型把「despite wiping clean」读成操作条件变更；从未排障的问题不能因此跳过检索直接 R2。"""
    set_knowledge_adapter(QAHitAdapter("rv-0364"))
    conversation.models["diagnose.synthesize"].script = [{"hypotheses": [{
        "plan_id": "qa_rv_0364", "confidence": 0.9, "evidence_ids": ["chunk-rv-0364"],
        "applicability": "supported", "supported_symptoms": ["won't charge at the base station"],
    }]}]
    events = await conversation.send(T31, {
        "primary_intent": "report_problem", "device_relation": "current",
        "facts": [{"value": "won't charge at the base station", "quote": "The robot won't charge when it is at the base station"}],
        "operation_update": {"signal": "device_ready", "quote": "The robot won't charge when it is at the base station"},
    })
    assert any(e["type"] == "step_card" for e in events)
    state = await conversation.state()
    assert state["escalate_reason"] is None
    assert any(t.get("event") == "context_selected" for t in state["retrieval_trace"])


class NoMatch:
    async def hybrid_search(self, kb, query, top_k, allow):
        from app.knowledge.adapter import ToolResult
        return ToolResult("no_match", [], kb=kb, query=query)


async def test_no_match_without_symptom_fact_asks_before_handoff(conversation):
    """T60：只有情绪和「想让它正常清扫」、没有现象也没有错误码，知识库无命中 → 先问现象，两次无效后才交人工。"""
    set_knowledge_adapter(NoMatch())
    text = "This app is shit . I just want my X10 Pro Omni to clean with out all this bullshit"
    # 真实模型会把愿望改写成一条泛化现象（2026-10-10 复跑 3/3），不是零条事实；改写句不算客户报告的具体现象
    meaning = {"primary_intent": "report_problem", "device_relation": "current", "product_hints": ["X10 Pro Omni"],
               "emotion_level": "angry", "emotion_cues": ["shit"],
               "facts": [{"value": "X10 Pro Omni not cleaning properly", "quote": "I just want my X10 Pro Omni to clean"}]}
    first = await conversation.send(text, meaning)
    assert not any(e["type"] == "escalation_summary" for e in first)
    assert "describe what the device is doing" in "".join(e.get("delta", "") for e in first)
    second = await conversation.send("it just doesn't work", {**meaning, "primary_intent": "answer_pending"})
    assert not any(e["type"] == "escalation_summary" for e in second)
    third = await conversation.send("I told you, it doesn't work", {**meaning, "primary_intent": "answer_pending"})
    assert any(e["type"] == "escalation_summary" for e in third)
    assert (await conversation.state())["escalate_reason"] == "R5"


async def test_no_match_with_a_real_symptom_still_hands_off(conversation):
    set_knowledge_adapter(NoMatch())
    events = await conversation.send("X10 Pro Omni keeps spinning in circles and never docks", {
        "primary_intent": "report_problem", "device_relation": "current", "product_hints": ["X10 Pro Omni"],
        "facts": [{"value": "spins in circles and never docks", "quote": "keeps spinning in circles and never docks"}],
    })
    assert any(e["type"] == "escalation_summary" for e in events)
