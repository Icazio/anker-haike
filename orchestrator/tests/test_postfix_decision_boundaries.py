"""官方复测 R1–R5：异常不能授权操作，状态与事实不能被模型猜测替代。"""

from types import SimpleNamespace

import pytest

from app.cases.service import CaseService
from app.context import budget as context_budget
from app.context.runtime import turn_context
from app.conversation.interpret import TurnInterpretation
from app.conversation.reduce import reduce_turn
from app.diagnose.decision import explanation
from app.diagnose.synthesize import filter_hypotheses, synthesize
from app.models.runtime import get_model_router
from app.plans.qa import qa_plan_library
from app.sessions import graph, l3
from app.sessions.clarify import fixed_question
from tests.conversation_runtime import conversation as conversation_fixture

conversation = conversation_fixture
LIBRARY = qa_plan_library()


async def run_synthesis(router, *, evidence=None, state=None, allowed=None):
    return await synthesize(
        router, state=state or {"symptoms": ["滚刷缠头发"]},
        allowed=allowed or [LIBRARY.get("qa_rv_0272")],
        evidence=evidence if evidence is not None else [{
            "evidence_id": "c12", "doc_id": "rv-0272", "source": "kb_qa",
            "snippet": "The roller brush is tangled with hair.",
        }], observations=[], budget_ms=3000, max_hypotheses=3,
        session_id=None, lane="domestic",
    )


@pytest.mark.parametrize("with_evidence", [True, False])
async def test_unavailable_judgment_never_authorizes_retrieval_order(with_evidence):
    result = await run_synthesis(None, evidence=None if with_evidence else [])
    assert result["plans_ranked"] == []
    assert result["degraded"] in {"no_evidence", "router_unavailable"}


async def test_failed_model_never_authorizes_a_plan(conversation):
    conversation.models["diagnose.synthesize"].script = [RuntimeError("provider failed")]
    result = await run_synthesis(get_model_router())
    assert result["plans_ranked"] == []
    assert result["degraded"].startswith("model:")


async def test_final_context_budget_drops_tail_candidates_and_their_evidence(conversation, monkeypatch):
    config = context_budget.conversation_config().model_copy(update={
        "input_budgets": {"diagnose.synthesize": 6000},  # 输出 schema 约 1.7k、提示约 2k token；仍远小于 UNIQUE_TAIL 尾段
    })
    monkeypatch.setattr(context_budget, "conversation_config", lambda: config)
    model = conversation.models["diagnose.synthesize"]
    model.script = [{"hypotheses": [
        {"plan_id": "qa_rv_0272", "confidence": 0.9, "evidence_ids": ["c12"],
         "applicability": "supported", "supported_symptoms": ["滚刷缠头发"]},
        {"plan_id": "qa_rv_0271", "confidence": 0.95, "evidence_ids": ["tail"],
         "applicability": "supported", "supported_symptoms": ["滚刷缠头发"]},
    ]}]
    state = {"input_id": "i", "at": "2026-10-09T12:00:00Z", "symptoms": ["滚刷缠头发"]}
    token = turn_context.set(state)
    try:
        result = await run_synthesis(get_model_router(), state=state, allowed=[
            LIBRARY.get("qa_rv_0272"), LIBRARY.get("qa_rv_0271"),
        ], evidence=[
            {"evidence_id": "c12", "doc_id": "rv-0272", "source": "kb_qa", "snippet": "Roller brush tangled"},
            {"evidence_id": "tail", "doc_id": "rv-0271", "source": "kb_qa", "context_text": "UNIQUE_TAIL " * 5000},
        ])
    finally:
        turn_context.reset(token)
    assert len(model.calls) == 1
    assert [item["plan_id"] for item in result["plans_ranked"]] == ["qa_rv_0272"]
    assert result["plans_ranked"][0]["source"] == "synthesize"
    prompt = str(model.calls[0]["messages"])
    assert "UNIQUE_TAIL" not in prompt and "qa_rv_0271" not in prompt
    assert any(item.startswith("budget:") for item in result["dropped"])


async def test_required_facts_cannot_be_dropped_to_make_a_plan_fit(conversation):
    state = {
        "input_id": "i", "at": "2026-10-09T12:00:00Z", "active_issue_id": "issue",
        "issues": {"issue": {"facts": [{"kind": "symptom", "status": "active", "value": "FACT " * 20000}]}},
    }
    token = turn_context.set(state)
    try:
        result = await run_synthesis(get_model_router(), state=state)
    finally:
        turn_context.reset(token)
    assert not conversation.models["diagnose.synthesize"].calls
    assert result["plans_ranked"] == []
    assert "budget" in result["degraded"]
    assert len(state["issues"]["issue"]["facts"][0]["value"]) == 100000


@pytest.mark.parametrize("with_query", [False, True])
async def test_closed_unresolved_case_finishes_current_task_truthfully(monkeypatch, with_query):
    cases = CaseService()
    row = await cases.open("session", "issue", {})
    await cases.transition(row["case_id"], "proposing", "review")
    await cases.transition(row["case_id"], "closed_unresolved", "out of warranty")
    events = []
    monkeypatch.setattr(l3, "require_services", lambda: SimpleNamespace(cases=cases))
    monkeypatch.setattr(l3, "writer", lambda: events.append)
    state = {
        "session_id": "session", "input_id": "i", "active_issue_id": "issue", "base_version": 1,
        "case_id": row["case_id"], "case_status": "closed_unresolved", "stage": "context",
        "issues": {"issue": {"title": "battery problem"}}, "requested_remedy": "replace",
        "task_queue": [{"task_id": "diagnose", "intent": "report_problem", "status": "active", "quote": "help"}],
    }
    if with_query:
        state["task_queue"].append({"task_id": "query", "intent": "order_query", "status": "pending", "quote": "order date"})
    update = await l3.propose(state)
    text = " ".join(event.get("delta", "") for event in events)
    assert "closed" in text and "not resolved" in text
    assert "waiting to be processed" not in text
    assert update["completed_task_intent"] == "report_problem"
    advanced = await l3.advance_tasks({**state, **update})
    assert advanced["task_queue"][0]["status"] == "done"
    assert advanced["l3_route"] == ("consult" if with_query else "commit_issue")
    saved = await cases.store.get(row["case_id"])
    assert saved["status"] == "closed_unresolved"
    assert not any(event["type"] == "handoff_summary" for event in saved["events"])


async def test_actual_approval_wait_is_not_treated_as_closed(monkeypatch):
    cases = CaseService()
    row = await cases.open("session", "issue", {})
    await cases.transition(row["case_id"], "proposing", "review")
    await cases.transition(row["case_id"], "awaiting_approval", "human review")
    events = []
    monkeypatch.setattr(l3, "require_services", lambda: SimpleNamespace(cases=cases))
    monkeypatch.setattr(l3, "writer", lambda: events.append)
    update = await l3.propose({"case_id": row["case_id"], "input_id": "i"})
    assert update["l3_route"] == "commit_issue"
    assert "closed" not in " ".join(event.get("delta", "") for event in events)
    assert (await cases.store.get(row["case_id"]))["status"] == "awaiting_approval"


def reduce_form(text, facts):
    return reduce_turn(
        {"session_id": "session", "input_id": "input", "at": "2026-10-09T12:00:00Z", "text": text},
        TurnInterpretation(primary_intent="report_problem", device_relation="current", facts=facts),
    )


@pytest.mark.parametrize("label", ["Problem Description", "Probleembeschrijving", "Problembeschreibung"])
def test_structured_problem_survives_action_only_extraction(label):
    description = "Water tray will not empty. I cleaned the hose and the dirty water tank is empty."
    state = reduce_form(f"Product PN: T2351\n{label}: {description}", [
        {"kind": "action_taken", "value": "cleaned the hose", "quote": "cleaned the hose"},
    ])
    assert state["symptoms"] == []
    facts = state["issues"][state["active_issue_id"]]["facts"]
    assert not any(fact["kind"] == "symptom" for fact in facts)
    assert state["unparsed_problem"] == {"text": description, "source_entry_ids": ["input"], "status": "unparsed"}
    assert any(fact["kind"] == "action_taken" for fact in facts)


@pytest.mark.parametrize("polarity", ["affirmed", "negated", "uncertain"])
def test_explicit_symptom_polarity_is_not_overwritten_by_raw_form(polarity):
    state = reduce_form("Product PN: T2351\nProblem Description: The tray is not blocked.", [
        {"value": "tray blocked", "quote": "The tray is not blocked", "polarity": polarity},
    ])
    facts = state["issues"][state["active_issue_id"]]["facts"]
    assert len(facts) == 1 and facts[0]["polarity"] == polarity


def test_free_email_and_metadata_do_not_become_symptoms():
    for text in ["I cleaned the hose. My order number is Anker029.", "Product PN: T2351\nCountry: NL"]:
        assert reduce_form(text, [])["symptoms"] == []


def test_unparsed_problem_does_not_invent_semantic_polarity():
    state = reduce_form("Product PN: T2351\nProblem Description: The left one does work.", [])
    facts = state["issues"][state["active_issue_id"]]["facts"]
    assert facts == [] and state["symptoms"] == []
    assert state["unparsed_problem"]["text"] == "The left one does work."


def test_full_description_misclassified_as_action_still_preserves_the_problem():
    description = "The tray will not empty after I cleaned the hose."
    state = reduce_form(f"Product PN: T2351\nProblem Description: {description}", [
        {"kind": "action_taken", "value": description, "quote": description},
    ])
    assert state["symptoms"] == [] and state["unparsed_problem"]["text"] == description


def test_later_grounded_fact_can_resolve_the_unparsed_description():
    description = "The tray will not empty."
    first = reduce_form(f"Product PN: T2351\nProblem Description: {description}", [])
    second = reduce_turn(
        {**first, "session_id": "session", "input_id": "confirmation", "at": "2026-10-09T12:01:00Z", "text": description},
        TurnInterpretation(primary_intent="report_problem", facts=[{"value": description, "quote": description}]),
    )
    facts = second["issues"][second["active_issue_id"]]["facts"]
    assert [f["polarity"] for f in facts if f["kind"] == "symptom" and f["status"] == "active"] == ["affirmed"]
    assert second["unparsed_problem"]["status"] == "interpreted"
    assert second["unparsed_problem"]["source_entry_ids"] == ["input"]
    assert first["unparsed_problem"]["status"] == "unparsed"


def test_closed_unresolved_explanation_does_not_claim_resolution():
    text = explanation({"stage": "done", "case_status": "closed_unresolved"})
    assert "marked as resolved" not in text
    assert "closed" in text and "not resolved" in text


@pytest.mark.parametrize("reason", ["R3", "R4"])
async def test_new_human_request_or_safety_risk_reopens_closed_case(monkeypatch, reason):
    cases = CaseService()
    row = await cases.open("session", "issue", {})
    await cases.transition(row["case_id"], "proposing", "review")
    await cases.transition(row["case_id"], "closed_unresolved", "out of warranty")
    events = []
    monkeypatch.setattr(graph, "get_services", lambda: SimpleNamespace(cases=cases))
    monkeypatch.setattr(graph, "get_stream_writer", lambda: events.append)
    monkeypatch.setattr(graph, "get_model_router", lambda: None)
    state = {
        "session_id": "session", "run_id": "r", "input_id": "i", "input_seq": 1,
        "at": "2026-10-09T12:00:00Z", "active_issue_id": "issue", "base_version": 1,
        "case_id": row["case_id"], "escalate_reason": reason,
        "text": "Please transfer me to a human" if reason == "R3" else "The battery is smoking",
        "issues": {"issue": {"facts": [], "handoff": {"status": "not_requested"}}},
        "task_queue": [{"task_id": "a", "intent": "report_problem", "status": "active"}],
    }
    result = await graph.summarize(state)
    assert result["stage"] == "awaiting_human"
    assert (await cases.store.get(row["case_id"]))["status"] == "awaiting_approval"
    assert next(e for e in events if e["type"] == "escalation_summary")["handoff_status"] == "requested"


B11_SAID = "My charging case will not charge therefore I cannot charge my pump motors. I am an exclusive pumper"


@pytest.mark.parametrize("plan_id", ["qa_bp_0067", "qa_bp_0039", "qa_bp_0122"])
def test_failed_power_source_is_asked_before_the_pump_guide(plan_id):
    """B11 / T52：盒子自身不进电，泵充不上只是下游。模型判定对象冲突并引客户原话，追问盒子自身的状态，不发泵受电指南。"""
    conflict = {"kind": "object", "customer_quote": "My charging case will not charge",
                "candidate_quote": "not charging the pump", "ask_about": "charging case"}
    kept, dropped, clarifications = filter_hypotheses([
        {"plan_id": plan_id, "confidence": 0.9, "evidence_ids": ["e1"], "applicability": "supported",
         "supported_symptoms": ["cannot charge pump motors"], "conflict": conflict},
    ], allowed={plan_id: LIBRARY.get(plan_id)}, evidence_ids={"e1"}, symptoms={"cannot charge pump motors"},
        facts=[], said=[B11_SAID], max_n=3)
    assert kept == [] and f"conflict_object:{plan_id}" in dropped
    assert "charging case" in clarifications[0]["question"] and "pump" not in clarifications[0]["question"]


@pytest.mark.parametrize("plan_id", ["qa_bp_0067", "qa_bp_0039"])
def test_internal_device_charging_still_matches_official_plan(plan_id):
    """泵在盒里充不上：模型不报冲突，泵受电条目照常可执行。"""
    symptom = "The pumps are not charging in the case"
    kept, dropped, _ = filter_hypotheses([
        {"plan_id": plan_id, "confidence": 0.9, "evidence_ids": ["e1"], "applicability": "supported",
         "supported_symptoms": [symptom]},
    ], allowed={plan_id: LIBRARY.get(plan_id)}, evidence_ids={"e1"}, symptoms={symptom}, facts=[
        {"kind": "symptom", "status": "active", "value": symptom, "quote": symptom, "subject": "pump motors"},
    ], said=[symptom], max_n=3)
    assert [item["plan_id"] for item in kept] == [plan_id], dropped


def test_symptom_question_is_category_neutral():
    text = fixed_question("symptom", {"category": "security_camera"})
    assert "3212" not in text and "E41" not in text
    assert "code" in text and "doing" in text


def test_not_reported_conflict_drops_without_asking():
    """T53：客户只说充过电仍开不了机，候选讲充不进电。模型判定客户没说过这个现象：丢弃，不追问「哪个部件充不了电」。"""
    plan = LIBRARY.get("qa_bp_0127")
    kept, dropped, clarifications = filter_hypotheses([
        {"plan_id": plan.plan_id, "confidence": 0.62, "evidence_ids": ["e1"], "applicability": "supported",
         "supported_symptoms": ["One side of the pump stoped working"],
         "conflict": {"kind": "not_reported", "candidate_quote": "charging case not charging one side"}},
    ], allowed={plan.plan_id: plan}, evidence_ids={"e1"}, symptoms={"One side of the pump stoped working"}, facts=[],
        said=["One side of the pump stoped working. I tried to charge it over and over again but it stoped turning on."], max_n=3)
    assert kept == [] and clarifications == [] and "conflict_not_reported:qa_bp_0127" in dropped
