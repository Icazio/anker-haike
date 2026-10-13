"""客户否定事实的补抽与极性校正（docs/claude/spec_2026-10-12-1823_negated-facts.md）。

T41（会话 2d5b2267 / 24f5e167 / 016757a0）：「we have not run mop cycles and thus havent needed any mop drying」
3 次里 2 次整句漏抽、1 次抽成 action_taken affirmed「not run mop cycles」。前提核对没有否定事实可比，
rv-0146（拖布没烘干）判「前提未知」，去追问客户已经回答过的事，之后让客户「跑一次拖地」。
"""

from __future__ import annotations

import pytest

from app.conversation.interpret import (
    DENIED_ACTION,
    FactCandidate,
    TurnInterpretation,
    complete_problem_facts,
    negation_polarity,
    uncovered_denials,
)
from app.knowledge.runtime import set_knowledge_adapter
from app.models.runtime import get_model_router
from app.official.message import parse_message
from tests.conversation_runtime import conversation as base_conversation_fixture
from tests.fake_qa import QAHitAdapter
from tests.test_conversation_l3 import l3_runtime as l3_runtime_fixture
from tests.test_problem_description_recovery import source_state

base_conversation = base_conversation_fixture
l3_runtime = l3_runtime_fixture

T41 = ("Product Name: Omni E28\nProduct PN: T2352\nProblem Type: Issue\nProblem Description: This is the second time Ive "
       "received this error message related to failed drying. As the water injection is still malfunctioning we have not "
       "run mop cycles and thus havent needed any mop drying so im not sure what is triggering this.")
DRYING = FactCandidate(value="received error message related to failed drying",
                       quote="This is the second time Ive received this error message related to failed drying.")
INJECTION = FactCandidate(value="water injection is still malfunctioning", quote="As the water injection is still malfunctioning")


@pytest.fixture
async def conversation(l3_runtime, base_conversation):
    yield base_conversation


@pytest.mark.parametrize("text, denied", [
    ("we have not run mop cycles", True),
    ("thus havent needed any mop drying", True),
    ("I've never used the mop", True),
    ("I still haven't tried the app", True),
    ("Water tray will not empty", False),
    ("pump not suctioning", False),
    ("It clicks but does not suction", False),
    ("insured the hose is not pinched", False),  # T29：否定的是状态，客户做了检查
    ("I have not received this vacuum", False),   # 物流，由 NEVER_ARRIVED 处理
    ("I had not known I can put in a claim", False),
    ("the WiFi is fine", False),
])
def test_denied_action(text, denied):
    assert bool(DENIED_ACTION.search(text)) is denied


@pytest.mark.parametrize("fact, polarity, value", [
    # 016757a0 原样
    (FactCandidate(kind="action_taken", value="not run mop cycles", quote="we have not run mop cycles"), "negated", "run mop cycles"),
    (FactCandidate(kind="action_taken", value="run mop cycles", quote="we have not run mop cycles"), "negated", "run mop cycles"),
    (FactCandidate(kind="observation", value="havent needed mop drying", quote="havent needed any mop drying"), "negated", "needed mop drying"),
    (FactCandidate(kind="action_taken", value="insured the hose is not pinched", quote="insured the hose is not pinched"),
     "affirmed", "insured the hose is not pinched"),
    (FactCandidate(kind="observation", value="no lights appear", quote="no lights appear"), "affirmed", "no lights appear"),
    (FactCandidate(kind="symptom", value="will not empty", quote="Water tray will not empty"), "affirmed", "will not empty"),
    (FactCandidate(kind="action_taken", value="cleaned it", quote="I have already cleaned it"), "affirmed", "cleaned it"),
])
def test_negation_polarity(fact, polarity, value):
    [out] = negation_polarity([fact])
    assert (out.polarity, out.value) == (polarity, value)


def test_only_t41_has_uncovered_denials_among_official_tickets():
    from app.official.models import OfficialData

    hits = [t.id for t in OfficialData().tickets if uncovered_denials(parse_message(t.body).description or t.body, [])]
    assert hits == ["T41"]


def test_a_covered_denial_is_not_asked_again():
    description = parse_message(T41).description
    assert uncovered_denials(description, [DRYING, INJECTION])
    covered = FactCandidate(kind="action_taken", value="run mop cycles", quote="we have not run mop cycles", polarity="negated")
    needed = FactCandidate(kind="observation", value="needed mop drying", quote="havent needed any mop drying", polarity="negated")
    assert uncovered_denials(description, [DRYING, INJECTION, covered, needed]) == []


async def test_t41_missed_denial_is_recovered(conversation):
    model = conversation.models["intake"]
    model.script = [{"facts": [
        # 模型给了 affirmed：仍以原话「we have not run」校正
        {"kind": "action_taken", "value": "run mop cycles", "quote": "we have not run mop cycles", "subject": "mop cycles"},
        {"kind": "symptom", "value": "invented", "quote": "not in the text"},
    ]}]
    meaning = TurnInterpretation(primary_intent="report_problem", facts=[DRYING, INJECTION])
    result, trace = await complete_problem_facts(get_model_router(), meaning, source_state(T41), lane="domestic")
    assert len(model.calls) == 1 and trace["denials"] == 2
    added = result.facts[2:]
    assert [(f.kind, f.polarity, f.value) for f in added] == [("action_taken", "negated", "run mop cycles")]
    assert "we have not run mop cycles" in str(model.calls[0]["messages"])


async def test_symptoms_present_and_no_denial_does_not_call_the_model(conversation):
    meaning = TurnInterpretation(primary_intent="report_problem", facts=[
        FactCandidate(value="Water tray will not empty", quote="Water tray will not empty"),
        FactCandidate(kind="action_taken", value="insured the hose is not pinched", quote="I insured the hose is not pinched")])
    text = "Product PN: T2351\nProblem Description: Water tray will not empty. I insured the hose is not pinched."
    result, trace = await complete_problem_facts(get_model_router(), meaning, source_state(text), lane="domestic")
    assert result == meaning and trace["outcome"] == "not_needed" and not conversation.models["intake"].calls


async def test_t41_negated_fact_drops_the_drying_plan_without_asking(conversation):
    """HTTP 链路：intake 漏抽，补抽给出否定事实；synthesize 把 rv-0146 判待确认「跑一次拖地」并指出客户已否定 → 不追问。"""
    set_knowledge_adapter(QAHitAdapter("rv-0146"))
    conversation.models["intake"].script = [
        {"primary_intent": "report_problem", "device_relation": "current", "product_hints": ["T2352"], "facts": [
            DRYING.model_dump(), INJECTION.model_dump()]},
        {"facts": [{"kind": "action_taken", "value": "run mop cycles", "quote": "we have not run mop cycles",
                    "subject": "mop cycles", "polarity": "negated"}]},
    ]
    question = "Does the failed drying error appear during or right after a mop/roller drying cycle?"
    conversation.models["diagnose.synthesize"].script = [{"hypotheses": [{
        "plan_id": "qa_rv_0146", "confidence": 0.6, "evidence_ids": ["chunk-rv-0146"],
        "applicability": "needs_confirmation", "supported_symptoms": [DRYING.value],
        "clarification_question": question, "missing_fact": "perform a new mopping task",
        # 是否已被客户原话否定由模型判断并引原话（原先按词干重叠猜）；服务端核对引文出自这封工单
        "precondition_known": {"answer": "no", "customer_quote": "we have not run mop cycles"},
    }]}]
    snapshot = await conversation.snapshot()
    response = await conversation.client.post(f"/sessions/{conversation.sid}/messages", data={
        "input_id": "t41-input", "expected_version": snapshot["version"], "text": T41})
    events = conversation.check(response)
    assert question not in "".join(e.get("delta", "") for e in events)
    assert not any(e["type"] == "step_card" for e in events)
    state = await conversation.state()
    facts = state["issues"][state["active_issue_id"]]["facts"]
    assert any(f["kind"] == "action_taken" and f["polarity"] == "negated" and f["value"] == "run mop cycles" for f in facts)
    assert any("precondition_negated:qa_rv_0146" in str(t.get("dropped")) for t in state["retrieval_trace"]
               if t.get("event") == "synthesize")
