"""官方 63 单 2026-10-13 全量复评的 4 处系统修改（docs/planning/2026-10-13-1058_official-63-full-review/）。

T50 / T53：候选讲的现象客户没说过（模型判 conflict=not_reported）时不追问「哪个部件充不了电」；
「does work」被改写成否定时还原。
T57：bp-0164 收 App 版本用问题卡，没拿到版本不算指南走完。
T34：卡上说了「资料不覆盖旧地图、未解决由同事核查」，指南走完按资料缺口交人工，不进质保收订单。
T48：单张照片不说灯常亮 / 闪烁。
"""

from __future__ import annotations

import pytest

from app.conversation.interpret import FactCandidate, normal_operation_is_uncertain
from app.conversation.product_questions import PHOTO_ANSWER_RULES
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


# ---- T50 / T53：客户没说过的现象，不被充电条目带去问充电 ----
# 是不是同一件事由模型判断（conflict），原先是充电句式解析加多语言词表；这里只测服务端怎样处理模型的判断。

T53_SAID = ("Problem Description: One side of the pump stoped working. I tried to charge it over and over again "
            "but it stoped turning on.")


def _bp0127(conflict=None, confidence=0.62):
    return filter_hypotheses(
        [{"plan_id": BP_0127, "confidence": confidence, "evidence_ids": ["e1"], "applicability": "supported",
          "supported_symptoms": ["One side of the pump stoped working"], "conflict": conflict}],
        allowed={BP_0127: LIB.get(BP_0127)}, evidence_ids={"e1"}, symptoms={"One side of the pump stoped working"},
        facts=[], said=[T53_SAID], max_n=3)


def test_t53_not_reported_drops_the_charging_candidate():
    """T53 主轮：「一侧停机，充了很多次还是开不了机」被 bp-0127 带去问「Which part is not charging」。"""
    kept, dropped, clarifications = _bp0127({"kind": "not_reported", "candidate_quote": "charging case not charging one side"})
    assert kept == [] and clarifications == [] and f"conflict_not_reported:{BP_0127}" in dropped


def test_object_conflict_asking_about_a_part_the_customer_never_named_is_not_asked():
    """模型说对象不同、要问 charging case，可 T53 客户从没说过充电盒：引文核对不过，只丢弃不追问。"""
    kept, dropped, clarifications = _bp0127({"kind": "object", "customer_quote": "My charging case will not charge",
                                             "candidate_quote": "charging case not charging one side", "ask_about": "charging case"})
    assert kept == [] and clarifications == [] and f"conflict_object:{BP_0127}" in dropped


def test_no_conflict_keeps_the_candidate():
    """模型认为就是这件事（不填 conflict）：服务端不用词表二次否决。"""
    kept, _, _ = _bp0127(None, confidence=0.9)
    assert [k["plan_id"] for k in kept] == [BP_0127]


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
    assert [(s.step_id, s.kind) for s in steps] == [("s1", "question"), ("s2", "statement"), ("s3", "handoff")]
    assert "Which version of the Anker eufy app" in steps[0].title
    # 选方案时模型把「先确认 App 版本」当前提：它指出就是计划第 s1 步（问题卡），不另发追问
    #（2026-10-13 复测 2/8 次、3/6 次问了两遍版本）
    hyp = {"plan_id": "qa_bp_0164", "confidence": 0.62, "evidence_ids": ["e1"], "applicability": "needs_confirmation",
           "supported_symptoms": ["cameras are not working"], "missing_fact": "Check the version of the Anker eufy app",
           "clarification_question": "Which version of the Anker eufy app are you currently using?", "plan_step": "s1"}
    kept, dropped, clar = filter_hypotheses([hyp], allowed={"qa_bp_0164": LIB.get("qa_bp_0164")}, evidence_ids={"e1"},
                                            symptoms={"cameras are not working"}, facts=[], max_n=3)
    assert [k["plan_id"] for k in kept] == ["qa_bp_0164"] and clar == []
    assert "precondition_in_plan:qa_bp_0164:s1" in dropped


async def test_t57_unanswered_version_does_not_finish_the_guide(conversation, l3_runtime):
    """T57 主轮：两张「是否解决」卡点两次未解决就说官方排查已完成、收订单，版本号从没拿到。
    现在第一张就是问版本的问题卡，不接受「解决 / 未解决」；答了版本才给 5.0 以上已知问题说明。"""
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
    assert (card["step_id"], card["kind"]) == ("s1", "question")
    rejected = await act(conversation.client, conversation.sid, "step_feedback", {"feedback": "not_solved"})
    assert (rejected.status_code, rejected.json()["code"]) == (409, "not_allowed_now")
    events = conversation.check(await act(conversation.client, conversation.sid, "step_feedback",
                                          {"answer": {"option": None, "text": "5.2.1", "unavailable": False}}))
    assert "5.0 or higher" in "".join(e.get("delta") or "" for e in events if e["type"] == "message")
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
