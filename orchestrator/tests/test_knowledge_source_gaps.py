"""An unavailable referenced instruction is a coverage gap, not a complete answer."""

import pytest

from app.guide.steps import prepare_step
from app.knowledge.runtime import set_knowledge_adapter
from app.official.models import QAEntry
from app.official.qa_index import QAIndex, build_guide
from app.plans.qa import qa_plan_library
from app.rules import RulesService
from app.settings import REPO_ROOT
from tests.conversation_runtime import conversation as conversation_fixture
from tests.fake_qa import QAHitAdapter
from tests.test_conversation_l3 import act

conversation = conversation_fixture


@pytest.mark.parametrize("content,gap", [
    ("Suggested troubleshooting steps can be found at:", True),
    ("The instructions are available at:", True),
    ("The instructions are listed below:", True),
    ("The instructions are available at:\nhttps://example.test/guide", False),
    ("The instructions are listed below:\nRestart the device.", False),
    ("The device will return to the station when power is low.", False),
])
def test_only_explicitly_dangling_source_references_are_marked(content, gap):
    guide = build_guide(QAEntry(id="test-1", sheet="test", directory=["QA", "Robot"], title="Example",
                               content=content, visible=True, pn=["T2080"], pdt=""), {})
    assert guide.steps[0].source_gap is gap
    assert guide.answer == content.replace("https://example.test/guide", "").strip()


@pytest.mark.parametrize("lead", ["", "1. The device may consume fluid gradually.\n2. ", "1. Check the tank.\n2. "])
async def test_source_gap_preserves_evidence_without_an_operation(lead):
    guide = build_guide(QAEntry(id="test-1", sheet="test", directory=["QA", "Robot"], title="Example",
        content=lead + "Further instructions can be found at:", visible=True, pn=["T2080"], pdt=""), {})
    step_id = "s2" if "Check" in lead else "s1"
    result = await prepare_step(
        state={"plan_cursor": {"plan_id": guide.plan_id, "step_id": step_id},
               "category": "robot_vacuum", "product_confirmed": {"sku": "T2080"}},
        library=qa_plan_library(QAIndex(guides={guide.qa_id: guide}, version="test")),
        rules=RulesService(REPO_ROOT / "config/rules/safety_terms.yaml", hot_reload=False),
        router=None, lane="domestic", session_id="source-gap",
    )
    assert result.outcome == "source_gap" and result.step is None and result.card_id is None
    assert "does not include them or a link" in result.explanation and result.evidence
    assert result.dropped[-1]["reason"] == "source_reference_missing"


async def test_http_incomplete_official_source_is_not_marked_answered(conversation):
    set_knowledge_adapter(QAHitAdapter("rv-0371"))
    conversation.models["diagnose.synthesize"].script = [{"hypotheses": [{
        "plan_id": "qa_rv_0371", "confidence": 0.9, "evidence_ids": ["chunk-rv-0371"],
        "applicability": "supported", "supported_symptoms": ["cleaning solution stays at 660ml"],
    }]}]
    events = await conversation.send("Product PN: T2080\nProblem Description: cleaning solution stays at 660ml", {
        "primary_intent": "report_problem", "device_relation": "current",
        "facts": [{"value": "cleaning solution stays at 660ml", "quote": "cleaning solution stays at 660ml"}],
    })
    state = await conversation.state()
    assert not state["consult_answered"] and not state["steps_executed"]
    assert state["escalate_reason"] == "R5"
    assert any(t["event"] == "knowledge_source_gap" for t in state["guide_trace"])
    text = "".join(e.get("delta", "") for e in events)
    assert "does not include them or a link" in text and "found at:" not in text
    assert not any(e["type"] == "step_card" for e in events)


async def test_source_gap_switches_silently_to_the_complete_candidate(conversation):
    """官方 63 单 T40（Codex 2026-10-12 20:25 主轮）：synthesize 把缺链接的 rv-0371 判可执行、rv-0073 判待确认「瓶子装好没」，
    客户先听到「官方资料缺后续说明」，再收到一句无卡片的自由文本追问。rv-0073 首步就是查清洁液瓶（前提即计划内检查，
    按可执行处理），rv-0371 碰到缺口按耗尽、静默换到 rv-0073 出卡（Fable D3）；缺口只记内部轨迹。"""
    set_knowledge_adapter(QAHitAdapter("rv-0371", "rv-0073"))
    question = "Is the cleaning solution bottle installed correctly in your S1 Pro?"
    conversation.models["diagnose.synthesize"].script = [{"hypotheses": [
        {"plan_id": "qa_rv_0371", "confidence": 0.72, "evidence_ids": ["chunk-rv-0371"],
         "applicability": "supported", "supported_symptoms": ["cleaning solution stays at 660ml"]},
        {"plan_id": "qa_rv_0073", "confidence": 0.6, "evidence_ids": ["chunk-rv-0073"],
         "applicability": "needs_confirmation", "supported_symptoms": ["cleaning solution stays at 660ml"],
         "clarification_question": question, "missing_fact": "the cleaning solution bottle is installed correctly",
         "plan_step": "s1"},
    ]}]
    events = await conversation.send("Product PN: T2080\nProblem Description: cleaning solution stays at 660ml", {
        "primary_intent": "report_problem", "device_relation": "current",
        "facts": [{"value": "cleaning solution stays at 660ml", "quote": "cleaning solution stays at 660ml"}],
    })
    state = await conversation.state()
    text = "".join(e.get("delta", "") for e in events)
    assert "does not include them or a link" not in text and question not in text
    card = next(e for e in events if e["type"] == "step_card")["step"]
    assert (card["plan_id"], card["step_id"]) == ("qa_rv_0073", "s1")
    assert not state.get("escalate_reason")
    assert any(t["event"] == "knowledge_source_gap" and t.get("plan_id") == "qa_rv_0371" for t in state["guide_trace"])


async def test_source_gap_with_only_a_precondition_candidate_still_asks(conversation):
    """待确认候选的前提不是它自己的步骤时（这里是「是否用过第三方清洁液」），仍如实告知缺口后先问一次，不交人工。"""
    set_knowledge_adapter(QAHitAdapter("rv-0371", "rv-0073"))
    question = "Have you used a third-party cleaning solution?"
    conversation.models["diagnose.synthesize"].script = [{"hypotheses": [
        {"plan_id": "qa_rv_0371", "confidence": 0.72, "evidence_ids": ["chunk-rv-0371"],
         "applicability": "supported", "supported_symptoms": ["cleaning solution stays at 660ml"]},
        {"plan_id": "qa_rv_0073", "confidence": 0.6, "evidence_ids": ["chunk-rv-0073"],
         "applicability": "needs_confirmation", "supported_symptoms": ["cleaning solution stays at 660ml"],
         "clarification_question": question, "missing_fact": "third-party cleaning solution used"},
    ]}]
    events = await conversation.send("Product PN: T2080\nProblem Description: cleaning solution stays at 660ml", {
        "primary_intent": "report_problem", "device_relation": "current",
        "facts": [{"value": "cleaning solution stays at 660ml", "quote": "cleaning solution stays at 660ml"}],
    })
    state = await conversation.state()
    text = "".join(e.get("delta", "") for e in events)
    assert "does not include them or a link" in text and question in text
    assert not state.get("escalate_reason") and state["stage"] != "awaiting_human"
    assert (state["diagnose_outcome"] or {}).get("plan_id") == "qa_rv_0073"


async def test_gap_plan_does_not_count_as_a_finished_guide(conversation):
    """T40 本轮复测 repeat-2：rv-0371 与 rv-0073 都判可执行、rv-0371 排第一。缺链接的 rv-0371 按耗尽换到 rv-0073 后，
    它被计入「已走完一条指南」，rv-0073 第一张卡点未解决就说「官方排查已完成」进质保，文章确认卡没发出来。
    原文缺口的计划客户什么也没做，不算走完。"""
    set_knowledge_adapter(QAHitAdapter("rv-0371", "rv-0073"))
    conversation.models["diagnose.synthesize"].script = [{"hypotheses": [
        {"plan_id": "qa_rv_0371", "confidence": 0.9, "evidence_ids": ["chunk-rv-0371"],
         "applicability": "supported", "supported_symptoms": ["cleaning solution stays at 660ml"]},
        {"plan_id": "qa_rv_0073", "confidence": 0.85, "evidence_ids": ["chunk-rv-0073"],
         "applicability": "supported", "supported_symptoms": ["cleaning solution stays at 660ml"]},
    ]}]
    events = await conversation.send("Product PN: T2080\nProblem Description: cleaning solution stays at 660ml", {
        "primary_intent": "report_problem", "device_relation": "current",
        "facts": [{"value": "cleaning solution stays at 660ml", "quote": "cleaning solution stays at 660ml"}],
    })
    first = next(e for e in events if e["type"] == "step_card")["step"]
    assert (first["plan_id"], first["step_id"]) == ("qa_rv_0073", "s1")
    events = conversation.check(await act(conversation.client, conversation.sid, "step_feedback", {"feedback": "not_solved"}))
    second = next(e for e in events if e["type"] == "step_card")["step"]
    assert (second["plan_id"], second["step_id"], second["kind"]) == ("qa_rv_0073", "s1b", "question")
    assert second["media"] and "official troubleshooting for this issue is complete" not in "".join(e.get("delta", "") for e in events)
