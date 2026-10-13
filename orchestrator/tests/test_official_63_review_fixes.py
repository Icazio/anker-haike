"""官方 63 单 2026-10-13 全量复评的 4 处系统修改（docs/planning/2026-10-13-1058_official-63-full-review/）。

T50 / T53：候选讲充电关系、客户没说过充电问题时不追问「哪个部件充不了电」；「does work」被改写成否定时还原。
T57：bp-0164 收 App 版本用问题卡，没拿到版本不算指南走完。
T34：卡上说了「资料不覆盖旧地图、未解决由同事核查」，指南走完按资料缺口交人工，不进质保收订单。
T48：单张照片不说灯常亮 / 闪烁。
"""

from __future__ import annotations

import pytest

from app.conversation.interpret import FactCandidate, normal_operation_is_uncertain
from app.conversation.product_questions import PHOTO_ANSWER_RULES
from app.diagnose.charging import mentions_charging
from app.diagnose.synthesize import filter_hypotheses
from app.knowledge.runtime import set_knowledge_adapter
from app.official.models import OfficialData
from app.plans.qa import qa_plan_library
from tests.conversation_runtime import conversation as base_conversation_fixture
from tests.fake_qa import QAHitAdapter
from tests.test_conversation_l3 import act
from tests.test_conversation_l3 import l3_runtime as l3_runtime_fixture

base_conversation = base_conversation_fixture
l3_runtime = l3_runtime_fixture
TICKETS = {t.id: t.body for t in OfficialData().tickets}
LIB = qa_plan_library()
BP_0127 = "qa_bp_0127"  # 「charging case not charging one side」


@pytest.fixture
async def conversation(l3_runtime, base_conversation):
    yield base_conversation


def _charging_case_hypothesis(symptom: str, confidence: float = 0.62) -> dict:
    return {"plan_id": BP_0127, "confidence": confidence, "evidence_ids": ["e1"], "applicability": "supported",
            "supported_symptoms": [symptom]}


# ---- T50 / T53：没说过充电问题，不被充电条目带去问充电 ----

def test_t53_charged_but_will_not_turn_on_is_not_asked_which_part_is_not_charging():
    """T53 主轮：「一侧停机，充了很多次还是开不了机」被 bp-0127 带去问「Which part is not charging」。
    客户的现象是停机；充电是做过的操作（action_taken），不是「充不进电」。"""
    symptom = "One side of the pump stoped working"
    facts = [{"kind": "symptom", "status": "active", "value": symptom, "quote": symptom + "."},
             {"kind": "action_taken", "status": "active", "value": "tried to charge it over and over again but it stoped turning on",
              "quote": "I tried to charge it over and over again but it stoped turning on."}]
    kept, dropped, clarifications = filter_hypotheses(
        [_charging_case_hypothesis(symptom)], allowed={BP_0127: LIB.get(BP_0127)}, evidence_ids={"e1"},
        symptoms={symptom}, facts=facts, max_n=3)
    assert kept == [] and clarifications == []
    assert f"charging_not_reported:{BP_0127}" in dropped


def test_charging_symptom_without_a_clear_recipient_still_asks_which_part():
    """客户说了充不进电、但没说是谁：仍按原规则问是哪个部件（不影响 B11 / T52 的充电对象核验）。"""
    symptom = "it will not charge"
    facts = [{"kind": "symptom", "status": "active", "value": symptom, "quote": symptom}]
    kept, dropped, clarifications = filter_hypotheses(
        [_charging_case_hypothesis(symptom, 0.9)], allowed={BP_0127: LIB.get(BP_0127)}, evidence_ids={"e1"},
        symptoms={symptom}, facts=facts, max_n=3)
    assert kept == [] and f"charging_recipient_unknown:{BP_0127}" in dropped
    assert clarifications[0]["question"].startswith("Which part")


def test_t50_rewritten_negation_does_not_count_as_a_charging_report():
    """T50 主轮：模型把「does work」改写成 value「left side does not work」；判断有没有说过充电只看原话。"""
    assert not mentions_charging(["the left one does work"])
    assert mentions_charging(["laadt niet op"]) and mentions_charging(["lädt nicht"]) and mentions_charging(["no carga"])
    assert mentions_charging(["can't get past critical low battery"])


def test_t50_normal_operation_marked_negated_is_restored_to_the_quote():
    """T50 主轮：「the left one does work」抽成 negated「left side does not work」，与原话意思相反。
    改成 uncertain 并还原 value，由服务端问哪一侧、什么问题。"""
    fact = FactCandidate(kind="symptom", value="left side does not work", quote="the left one does work", polarity="negated")
    fixed = normal_operation_is_uncertain([fact])[0]
    assert (fixed.polarity, fixed.value) == ("uncertain", "the left one does work")
    real = FactCandidate(kind="symptom", value="left one not working", quote="the left one does not work", polarity="negated")
    assert normal_operation_is_uncertain([real])[0] == real


# ---- T57：收 App 版本用问题卡 ----

def test_t57_app_version_is_collected_with_a_question_card():
    steps = LIB.get("qa_bp_0164").steps
    assert [(s.step_id, s.kind) for s in steps] == [("s2", "statement"), ("s3", "question")]
    assert "Which version of the Anker eufy app" in steps[1].title


async def test_t57_unanswered_version_does_not_finish_the_guide(conversation, l3_runtime):
    """T57 主轮：两张「是否解决」卡点两次未解决就说官方排查已完成、收订单，版本号从没拿到。
    现在第一张就是问版本的问题卡（附 5.0 以上已知问题说明），不接受「解决 / 未解决」。"""
    set_knowledge_adapter(QAHitAdapter("bp-0164"))
    conversation.models["diagnose.synthesize"].script = [{"hypotheses": [{
        "plan_id": "qa_bp_0164", "confidence": 0.8, "evidence_ids": ["chunk-bp-0164"],
        "applicability": "supported", "supported_symptoms": ["cameras are not working"],
    }]}]
    events = await conversation.send(TICKETS["T57"], {
        "primary_intent": "report_problem", "device_relation": "current", "product_hints": ["SoloCam S340"],
        "facts": [{"value": "cameras are not working", "quote": "All of the cameras are not working except one"}],
    })
    card = next(e for e in events if e["type"] == "step_card")["step"]
    assert (card["step_id"], card["kind"]) == ("s3", "question")
    assert "5.0 or higher" in card["context"]
    rejected = await act(conversation.client, conversation.sid, "step_feedback", {"feedback": "not_solved"})
    assert (rejected.status_code, rejected.json()["code"]) == (409, "not_allowed_now")
    conversation.check(await act(conversation.client, conversation.sid, "step_feedback",
                                 {"answer": {"option": None, "text": "5.2.1", "unavailable": False}}))
    state = await conversation.state()
    assert any(f.get("quote") == "5.2.1" for f in state["issues"][state["active_issue_id"]]["facts"])


# ---- T34：资料不覆盖客户要的结果，走完按资料缺口交人工 ----

async def test_t34_old_map_request_is_handed_to_a_colleague_not_to_warranty(conversation, l3_runtime):
    set_knowledge_adapter(QAHitAdapter("rv-0312"))
    conversation.models["diagnose.synthesize"].script = [{"hypotheses": [{
        "plan_id": "qa_rv_0312", "confidence": 0.9, "evidence_ids": ["chunk-rv-0312"],
        "applicability": "supported", "supported_symptoms": ["lost the maps"],
    }]}]
    events = await conversation.send(TICKETS["T34"], {
        "primary_intent": "report_problem", "device_relation": "current",
        "facts": [{"value": "lost the maps", "quote": "siscovered i had lost the maps."}],
    })
    card = next(e for e in events if e["type"] == "step_card")["step"]
    assert "a colleague will check" in card["context"]
    texts = []
    for _ in range(3):
        events = conversation.check(await act(conversation.client, conversation.sid, "step_feedback", {"feedback": "not_solved"}))
        texts += [e.get("delta") or "" for e in events if e["type"] == "message"]
        if not any(e["type"] == "step_card" for e in events):
            break
    said = "".join(texts)
    assert "only covers the steps you tried" in said
    assert "order number" not in said and "after-sales review" not in said
    summary = next(e for e in events if e["type"] == "escalation_summary")["summary"]
    assert summary["reason"]["rule_id"] == "R5" and summary["reason"]["cause"] == "outcome_beyond_source"


async def test_map_loss_without_asking_for_the_old_map_keeps_the_warranty_route(conversation, l3_runtime):
    """没说要找回旧地图（scope_note 未命中）时，rv-0312 走完仍按指南走完进质保。"""
    set_knowledge_adapter(QAHitAdapter("rv-0312"))
    conversation.models["diagnose.synthesize"].script = [{"hypotheses": [{
        "plan_id": "qa_rv_0312", "confidence": 0.9, "evidence_ids": ["chunk-rv-0312"],
        "applicability": "supported", "supported_symptoms": ["robot keeps asking to remap"],
    }]}]
    events = await conversation.send("Product PN: T2080A\nProblem Description: robot keeps asking to remap every day", {
        "primary_intent": "report_problem", "device_relation": "current",
        "facts": [{"value": "robot keeps asking to remap", "quote": "robot keeps asking to remap every day"}],
    })
    card = next(e for e in events if e["type"] == "step_card")["step"]
    assert "colleague will check" not in (card.get("context") or "")
    texts = []
    for _ in range(3):
        events = conversation.check(await act(conversation.client, conversation.sid, "step_feedback", {"feedback": "not_solved"}))
        texts += [e.get("delta") or "" for e in events if e["type"] == "message"]
        if not any(e["type"] == "step_card" for e in events):
            break
    assert "after-sales review" in "".join(texts)


# ---- T48：单张照片不说常亮 / 闪烁 ----

def test_t48_photo_answer_does_not_claim_solid_or_flashing():
    assert "不要写常亮" in PHOTO_ANSWER_RULES and "常亮还是闪烁" in PHOTO_ANSWER_RULES
