"""换货 / 退款提交前的独立审查（docs/claude/spec_2026-10-15-1448_independent-review.md）。

审查模型用 FakeChatModel 脚本代替，不发网络请求。
"""

from datetime import date

import pytest
from haike_contracts.common import WarrantyDecision

from app.actions import review as review_mod
from app.actions.review import ReviewCase, ReviewJudgment, judge
from app.actions.runtime import configure
from app.models.config import ModelsConfig
from app.models.fake import FakeChatModel
from app.models.registry import ModelRegistry
from app.models.router import ModelRouter
from app.models.runtime import set_model_router
from app.sessions import l3

ASK = "My S1 Pro stopped mopping after the update and it still won't work. I want a replacement."
SN = "Serial number is AK7RCN1E15600379"
# Anker002 有两行：S1 Pro 主机与配件包，产品前提才有得比
LINES = (("T2080GA1", "eufy Robot Vacuum and Mop, S1 Pro Omni"), ("T29C2001", "EUFY S1 PRO REPLACEMENT ACCESSORY KIT"))
WARRANTY = WarrantyDecision(
    status="in_warranty", basis="order", as_of=date(2026, 10, 8), order_no="Anker002",
    warranty_end=date(2027, 9, 13), reason="订单 Anker002 质保至 2027-09-13",
).model_dump(mode="json")


def case(kind="replace", texts=(ASK, SN), basis=None, lines=LINES, sku="T2080GA1"):
    return ReviewCase(
        kind=kind, sku=sku, order_no="Anker002", order_lines=lines, customer_texts=texts, basis=basis,
        requested_remedy=kind, warranty=WARRANTY, evidence={"order_or_receipt": "order:Anker002"},
    )


def judgment(**overrides):
    return ReviewJudgment.model_validate(
        {"customer_request": "replace", "request_quote": "I want a replacement", "fault_unresolved": True,
         "fault_quote": "it still won't work", "order_line_sku": "T2080GA1", "counter_evidence": []} | overrides
    )


def premise(result, name):
    return next(p for p in result.premises if p["premise"] == name)


def test_consistent_request_fault_and_product_pass():
    result = judge(case(), judgment())
    assert result.problems == [] and result.dropped_quotes == 0
    assert premise(result, "request")["source"] == "customer:I want a replacement"
    assert premise(result, "fault")["bound"] and premise(result, "product")["bound"]
    # 质保与证据由闸门前两项判，这里只记档
    assert premise(result, "warranty") == {"premise": "warranty", "bound": True,
                                           "source": "订单 Anker002 质保至 2027-09-13", "judged_by": "gate"}


def test_customer_asked_refund_but_candidate_is_replace():
    texts = ("The S1 Pro still won't work. I just want my money back.",)
    result = judge(case(texts=texts), judgment(customer_request="refund", request_quote="I just want my money back"))
    assert result.problems == ["审查读到客户诉求是退款，候选是换货：「I just want my money back」"]
    # 未绑定的前提也留下核实过的原话，后台对照面板据此显示依据
    assert premise(result, "request") == {
        "premise": "request", "bound": False, "source": "customer:I just want my money back", "judged_by": "review"}


def test_other_remedy_is_a_mismatch():
    # 2026-10-09 实测：改订单诉求被 requested_type 兜底成换货单
    texts = ("Please hold my order, I am moving next week.",)
    result = judge(case(texts=texts), judgment(customer_request="other_remedy", request_quote="Please hold my order"))
    assert result.problems[0].startswith("审查读到客户诉求是其他诉求")


def test_system_offered_replacement_binds_to_troubleshooting_basis():
    texts = ("The S1 Pro still won't mop after all the steps.",)
    silent = judgment(customer_request="none", request_quote=None, fault_quote="still won't mop")
    passed = judge(case(texts=texts, basis="guide_exhausted"), silent)
    assert passed.problems == [] and premise(passed, "request")["source"] == "basis:guide_exhausted"
    assert judge(case(texts=texts), silent).problems == [
        "客户原话里没有提出换货，也没有排障走完或官方指引判定硬件故障的依据"
    ]
    # 退款没有系统路径：客户没提就不能提交退款单
    assert judge(case(kind="refund", texts=texts, basis="guide_exhausted"), silent).problems == [
        "退款只能由客户提出，审查未在客户原话中读到退款诉求"
    ]


def test_quotes_must_be_verbatim_customer_words():
    result = judge(case(), judgment(request_quote="Please replace my robot", fault_quote="it is broken"))
    assert result.problems == ["审查读到客户要换货，但给出的依据不是客户原话", "审查未在客户原话中找到故障仍未解决的依据"]
    assert result.dropped_quotes == 2
    # 编出来的反证不采信，不算反证
    made_up = judge(case(), judgment(counter_evidence=[{"quote": "it works now", "against": "fault"}]))
    assert made_up.problems == [] and made_up.counter_evidence == [] and made_up.dropped_quotes == 1


def test_fault_already_resolved():
    texts = ("I want a replacement. Actually after the reset it works fine now.",)
    result = judge(case(texts=texts), judgment(fault_unresolved=False, fault_quote="after the reset it works fine now"))
    assert result.problems == ["审查读到故障已经解决：「after the reset it works fine now」"]
    fault = premise(result, "fault")
    assert fault["bound"] is False and fault["source"] == "customer:after the reset it works fine now"


def test_product_on_another_order_line():
    texts = ("The accessory kit side brush is broken, I want a replacement.",)
    picked = judgment(fault_quote="side brush is broken", order_line_sku="t29c2001")
    assert judge(case(texts=texts), picked).problems == ["审查读到客户说的是订单行 T29C2001，候选是 T2080GA1"]
    # 订单行之外的 SKU 不采信；单行订单不比
    assert judge(case(texts=texts), judgment(fault_quote="side brush is broken", order_line_sku="T9999")).problems == []
    assert premise(judge(case(lines=LINES[:1]), judgment(order_line_sku="T29C2001")), "product")["bound"] is None


def test_verified_counter_evidence_fails_review():
    texts = (ASK, "Or maybe just refund me, I don't care.")
    counter = [{"quote": "Or maybe just refund me", "against": "request", "note": "诉求在换货和退款之间摇摆"}]
    result = judge(case(texts=texts), judgment(counter_evidence=counter))
    assert result.problems == ["反证（诉求）：「Or maybe just refund me」（诉求在换货和退款之间摇摆）"]
    assert result.counter_evidence[0]["quote"] == "Or maybe just refund me"


def test_snapshot_hash_changes_with_worker_claims():
    first = review_mod.snapshot_hash(review_mod.snapshot(case()))
    assert first == review_mod.snapshot_hash(review_mod.snapshot(case()))
    assert first != review_mod.snapshot_hash(review_mod.snapshot(case(basis="guide_exhausted")))


def fake_router(*script):
    model = FakeChatModel(script=list(script), name_for_trace="reviewer")
    cfg = ModelsConfig.model_validate({
        "version": "review-test",
        "default_lane": "domestic",
        "providers": {"r": {"sdk": "openai", "api_key_env": "R_KEY"}},
        "models": {"reviewer": {"provider": "r", "id": "reviewer", "structured": "native"}},
        "lanes": {"domestic": {"remedy.review": {"chain": ["reviewer"]}}},
        "retry": {"same_model_max": 0, "rate_limit_max": 0, "chain_max": 1},
    })
    return ModelRouter(ModelRegistry(cfg, env={"R_KEY": "x"}), model_factory=lambda resolved, route: model), model


async def test_review_skips_model_when_not_applicable():
    router, model = fake_router()
    for kwargs, detail in [
        ({"case": case(), "human_approved": True}, "人工已批准，不再审查"),
        ({"case": case(kind="reship"), "human_approved": False}, "物流类方案由包裹状态决定，不经独立审查"),
    ]:
        outcome = await review_mod.review(kwargs["case"], router, human_approved=kwargs["human_approved"], session_id="s")
        assert outcome.check.passed and outcome.check.detail == detail and outcome.event is None
    disabled = await review_mod.review(case(), None, human_approved=False, session_id="s")
    assert disabled.check.passed and disabled.check.detail == "独立审查未启用（模型全局关闭）"
    assert model.calls == []


async def test_review_fails_closed_when_the_model_call_fails():
    router, _ = fake_router(TimeoutError("upstream timeout"))
    outcome = await review_mod.review(case(), router, human_approved=False, session_id="s")
    assert not outcome.check.passed and outcome.check.detail == "独立审查模型不可用，需人工复核"
    assert outcome.event["outcome"] == "unavailable" and outcome.event["snapshot_hash"]


async def test_reviewer_sees_customer_words_and_order_lines_only():
    router, model = fake_router(judgment().model_dump())
    outcome = await review_mod.review(case(basis="guide_exhausted"), router, human_approved=False, session_id="s")
    assert outcome.check.passed and outcome.event["outcome"] == "passed"
    sent = "\n".join(str(m.content) for m in model.calls[0]["messages"])
    assert ASK in sent and "S1 PRO REPLACEMENT ACCESSORY KIT" in sent
    # 上下文隔离：Worker 的诉求判断与系统依据不进审查模型的输入
    assert "guide_exhausted" not in sent and "requested_remedy" not in sent


@pytest.fixture
def services():
    yield configure(memory=True)
    configure(None)
    set_model_router(None)


async def opened_case(services):
    row = await services.cases.open("s1", "i1", {"sku": "T2080GA1", "category": "robot_vacuum"})
    await services.cases.transition(row["case_id"], "proposing", "按 SOP 生成服务单方案")
    row = await services.cases.transition(row["case_id"], "awaiting_confirmation", "等待客户确认提交")
    return row["case_id"]


def authorize_state(case_id):
    option = {"option_id": "replace", "type": "replace", "title": "Submit a replacement request", "detail": "", "source": "sop"}
    return {
        "session_id": "s1", "active_issue_id": "i1", "case_id": case_id, "entry": "action", "input_id": "in-1",
        "case_order_no": "Anker002", "requested_remedy": "replace", "warranty": WARRANTY,
        "proposal": {"options": [option], "chosen_option_id": "replace", "user_confirmed": True, "status": "confirmed"},
        "risk_cases": [], "turn_decision": {"allowed_operations": True},
        "product_confirmed": {"sku": "T2080GA1"},
        "receipt": {"status": "order_verified", "verified_facts": {"order_no": "Anker002", "address": "AnkerDirect"}},
        "image_refs": [{"image_id": "img-1", "purpose": "fault"}],
        "history": [{"role": "user", "text": t, "issue_id": "i1"} for t in (ASK, SN)],
    }


@pytest.fixture
def emitted(monkeypatch):
    events = []
    monkeypatch.setattr(l3, "writer", lambda: events.append)
    return events


async def test_authorize_sends_a_mismatch_to_human_with_the_difference(services, emitted):
    case_id = await opened_case(services)
    router, _ = fake_router(judgment(customer_request="refund", request_quote="I want a replacement").model_dump())
    set_model_router(router)
    state = authorize_state(case_id)
    update = await l3.authorize(state)
    # 等审查模型时进度已推到办理
    assert emitted == [{"type": "progress", "stage": "execute"}]
    assert update["l3_route"] == "await_human"
    review = next(c for c in update["gate_result"]["checks"] if c["name"] == "review")
    assert not review["passed"] and "审查读到客户诉求是退款，候选是换货" in review["detail"]
    row = await services.cases.store.get(case_id)
    event = next(e for e in row["events"] if e["type"] == "review_completed")
    assert event["payload"]["outcome"] == "mismatch"
    assert event["payload"]["snapshot"]["reviewer_input"]["customer_texts"] == [ASK, SN]
    # 交接原因直接写差异，坐席不用再翻事件
    assert l3.handoff_reason({**state, **update}, row).startswith("提交条件未满足：独立审查不一致：审查读到客户诉求是退款")


async def test_authorize_submits_when_review_agrees(services, emitted):
    case_id = await opened_case(services)
    router, _ = fake_router(judgment().model_dump())
    set_model_router(router)
    update = await l3.authorize(authorize_state(case_id))
    assert update["l3_route"] == "execute" and update["gate_result"]["passed"]
    row = await services.cases.store.get(case_id)
    assert [e["payload"]["outcome"] for e in row["events"] if e["type"] == "review_completed"] == ["passed"]


async def test_human_approval_is_not_reviewed_again(services, emitted):
    # 审查不一致转人工 → 人工批准 → apply_human_decision 回到 authorize：不能再被审查送回人工
    case_id = await opened_case(services)
    row = await services.cases.transition(
        case_id, "awaiting_approval", "需要人工审核", proposal=authorize_state(case_id)["proposal"]
    )
    await services.cases.decide(case_id, decision_id="d1", decision="approve", actor="agent:desk",
                                expected_revision=row["revision"], note="已电话核实", option_id="replace")
    router, model = fake_router()
    set_model_router(router)
    update = await l3.authorize(authorize_state(case_id))
    assert update["l3_route"] == "execute" and model.calls == [] and emitted == []
