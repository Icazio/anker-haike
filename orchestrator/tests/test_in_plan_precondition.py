"""计划内检查不是入口前提（T29，2026-10-12 复测）。

rv-0254 第 1 步就是「检查污水箱门扣是否扣紧」，模型把它填成 needs_confirmation 的 missing_fact，
先发一句「门扣扣紧了吗」，客户答 yes 后才出卡并跳过第 1 步；3 次复测 2 次走问句、1 次直接出卡。
2026-10-13 起由模型在 plan_step 指出前提就是计划第一张卡（原先按「check / verify」句首加词干重叠猜）；
服务端只核对它确实是这个计划第一张会发出的卡、是操作或问题卡、不带适用条件，就按 supported 继续。
场景前提（In multi-floor tasks …）不填 plan_step，仍先问。
"""

from __future__ import annotations

import pytest

from app.diagnose.synthesize import filter_hypotheses, plan_step_of
from app.knowledge.runtime import set_knowledge_adapter
from app.plans.runtime import get_plan_library
from tests.conversation_runtime import conversation as base_conversation_fixture
from tests.fake_qa import QAHitAdapter
from tests.test_conversation_l3 import l3_runtime as l3_runtime_fixture

base_conversation = base_conversation_fixture
l3_runtime = l3_runtime_fixture

LATCH = "Check whether the door latch of the dirty water tank is fastened"
QUESTION = "Is the door latch of the dirty water tank fastened securely?"
SYMPTOM = "Water tray will not empty"


@pytest.fixture
async def conversation(l3_runtime, base_conversation):
    yield base_conversation


def _hyp(pid="qa_rv_0254", **extra):
    return {"plan_id": pid, "confidence": 0.62, "evidence_ids": ["e1"], "applicability": "needs_confirmation",
            "supported_symptoms": [SYMPTOM], "clarification_question": QUESTION, "missing_fact": LATCH,
            "plan_step": "s1", **extra}


def _run(hyps, facts=(), symptoms=(SYMPTOM,)):
    lib = get_plan_library()
    allowed = {pid: lib.get(pid) for pid in ("qa_rv_0254", "qa_rv_0050")}
    return filter_hypotheses(hyps, allowed=allowed, evidence_ids={"e1"}, symptoms=set(symptoms), facts=list(facts), max_n=3)


@pytest.mark.parametrize("plan_id, step_id, expected", [
    ("qa_rv_0254", "s1", "s1"),
    ("qa_rv_0254", "s2", None),           # 后面的步骤：第 1 张卡已默认前提成立，仍先问
    ("qa_bp_0067", "s3", None),           # 2026-10-13 复测 T52：「确认充电盒自身有电」在第 3 步
    ("qa_rv_0254", "s99", None),          # 计划里没有这一步：模型编的步骤号不采信
    ("qa_bp_0164", "s1", "s1"),           # T57：问题卡问的就是 App 版本
    ("qa_bp_0164", "s2", None),           # 说明段不是检查
    ("qa_rv_0254", None, None),
])
def test_plan_step_must_be_a_real_check_in_this_plan(plan_id, step_id, expected):
    assert plan_step_of(get_plan_library().get(plan_id), step_id) == expected


def test_t29_in_plan_check_is_supported_without_asking():
    kept, dropped, clar = _run([_hyp()])
    assert [k["plan_id"] for k in kept] == ["qa_rv_0254"] and clar == []
    assert "precondition_in_plan:qa_rv_0254:s1" in dropped


def test_t29_latch_not_fastened_keeps_the_plan():
    """客户说门扣没扣紧：原先按「前提被否定」丢掉 rv-0254，可这正是第 1 步要处理的原因。plan_step 优先于前提已知。"""
    loose = {"kind": "observation", "value": "the door latch of the dirty water tank is not fastened",
             "quote": "the latch is not fastened", "subject": "door latch of the dirty water tank",
             "polarity": "negated", "status": "active"}
    known = {"answer": "no", "customer_quote": "the latch is not fastened"}
    kept, dropped, clar = _run([_hyp(precondition_known=known)], facts=[loose])
    assert [k["plan_id"] for k in kept] == ["qa_rv_0254"] and clar == []
    assert not any(d.startswith("precondition_negated") for d in dropped)


def test_in_plan_check_without_covered_symptom_still_asks():
    kept, dropped, clar = _run([_hyp(supported_symptoms=[])])
    assert kept == [] and clar[0]["question"] == QUESTION
    assert "not_supported:qa_rv_0254" in dropped


def test_scene_precondition_still_asks():
    hyp = _hyp("qa_rv_0050", missing_fact="In multi-floor tasks", plan_step=None,
               clarification_question="Was the robot running a multi-floor task?")
    kept, _, clar = _run([hyp])
    assert kept == [] and clar[0]["plan_id"] == "qa_rv_0050"


def test_not_applicable_is_still_dropped():
    kept, dropped, clar = _run([_hyp(applicability="not_applicable")])
    assert kept == [] and clar == [] and "not_supported:qa_rv_0254" in dropped


T29 = ("Product Name: eufy X10 Pro Omni Robot Vacuum and Mop Combo\nProblem Description: Water tray will not empty. "
       "I have already cleaned it, insured the hose is not pinched and insured that the connector under the dirty water "
       "tank is not pushed down. The dirty water tank is also empty. What else can I do?")


async def test_t29_first_turn_sends_the_latch_card(conversation):
    set_knowledge_adapter(QAHitAdapter("rv-0254"))
    conversation.models["diagnose.synthesize"].script = [{"hypotheses": [{
        **_hyp(), "evidence_ids": ["chunk-rv-0254"]}]}]
    events = await conversation.send(T29, {
        "primary_intent": "report_problem", "device_relation": "current", "product_hints": ["X10 Pro Omni"],
        "facts": [{"value": SYMPTOM, "quote": "Water tray will not empty.", "subject": "Water tray"}],
    })
    card = next(e["step"] for e in events if e["type"] == "step_card")
    assert card["plan_id"] == "qa_rv_0254" and card["step_id"] == "s1"
    assert QUESTION not in "".join(e.get("delta", "") for e in events)
    state = await conversation.state()
    assert not state.get("precondition_answers")


def test_t52_precondition_in_a_later_step_still_asks():
    """2026-10-13 复测 T52：盒子自身不进电，模型把 bp-0067 的前提指到 s3「确认充电盒自身有电」。按可执行处理会从 s1
    「对准泵与盒内触点」发起（首卡禁止项）。前提不在第一张卡上就先问。"""
    lib = get_plan_library()
    hyp = {"plan_id": "qa_bp_0067", "confidence": 0.7, "evidence_ids": ["e1"], "applicability": "needs_confirmation",
           "supported_symptoms": ["charging case will not charge"], "plan_step": "s3",
           "clarification_question": "Is the charging case itself fully charged?",
           "missing_fact": "Ensure the charging case itself has sufficient charge"}
    kept, dropped, clar = filter_hypotheses([hyp], allowed={"qa_bp_0067": lib.get("qa_bp_0067")}, evidence_ids={"e1"},
                                            symptoms={"charging case will not charge"}, facts=[], max_n=3)
    assert kept == [] and clar[0]["question"] == "Is the charging case itself fully charged?"
    assert not any(d.startswith("precondition_in_plan") for d in dropped)
