"""问句先对事实（2026-10-10 第 3 项）。

- T53 第十轮：用户已说「stoped turning on」，bp-0114 仍让在「无法开机 / 加热故障」里二选一。
  模型核实现象属于哪个小节（matched_section），服务端校验它逐字等于首问的选项后替用户记一条回答，直接发该小节首步。
- T41 第十轮：用户已说「we have not run mop cycles」，模型 needs_confirmation 还问「不跑拖地是否也报错」。
  模型给出要确认的前提（missing_fact），服务端与事实比对：否定事实覆盖 → 不适用也不问；肯定的已做 / 已观察 → 当作成立。
不加同义词表，不按 QA 编号判断。
"""

from __future__ import annotations

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


def _hyp(pid, **extra):
    return {"plan_id": pid, "confidence": 0.9, "evidence_ids": ["e1"], "applicability": "supported",
            "supported_symptoms": ["stoped turning on"], **extra}


def _run(hyps, facts=(), symptoms=("stoped turning on",), said=()):
    return filter_hypotheses(hyps, allowed={"qa_bp_0114": LIB.get("qa_bp_0114"), "qa_rv_0146": LIB.get("qa_rv_0146")},
                             evidence_ids={"e1"}, symptoms=set(symptoms), facts=list(facts), said=list(said), max_n=3)


# ---- matched_section ----

def test_verified_section_is_kept_and_unverified_is_dropped():
    kept, dropped, _ = _run([_hyp("qa_bp_0114", matched_section="Breast pump cannot be turned on")])
    assert kept[0]["matched_section"] == "Breast pump cannot be turned on"
    kept, dropped, _ = _run([_hyp("qa_bp_0114", matched_section="cannot be turned on")])  # 不逐字
    assert "matched_section" not in kept[0] and "section_unverified:qa_bp_0114" in dropped


def test_section_on_a_plan_without_branches_is_ignored():
    kept, dropped, _ = _run([_hyp("qa_rv_0146", matched_section="Anything")])
    assert "matched_section" not in kept[0] and "section_unverified:qa_rv_0146" in dropped


# ---- 前提客户已经说过：模型判断并引原话，服务端只核对引文出处（原先按词干重叠猜，T41 / T37）----

T41_SAID = ("This is the second time Ive received this error message related to failed drying. As the water injection "
            "is still malfunctioning we have not run mop cycles and thus havent needed any mop drying")


def _mop_hyp(known=None, **extra):
    return _hyp("qa_rv_0146", applicability="needs_confirmation", supported_symptoms=["failed drying"],
                clarification_question="Does the drying error appear even when no mop cycle has been run?",
                missing_fact="perform a new mopping task", precondition_known=known, **extra)


def test_negated_precondition_drops_without_asking():
    """T41 第十轮：客户已说没跑过拖地，仍被问「不跑拖地是否也报错」。"""
    known = {"answer": "no", "customer_quote": "we have not run mop cycles"}
    kept, dropped, clar = _run([_mop_hyp(known)], symptoms=("failed drying",), said=[T41_SAID])
    assert kept == [] and clar == [] and "precondition_negated:qa_rv_0146" in dropped


def test_known_precondition_promotes_to_supported():
    known = {"answer": "yes", "customer_quote": "I ran a mop cycle yesterday"}
    kept, dropped, clar = _run([_mop_hyp(known)], symptoms=("failed drying",), said=["I ran a mop cycle yesterday and it still says failed drying"])
    assert [k["plan_id"] for k in kept] == ["qa_rv_0146"] and clar == []
    assert "precondition_known:qa_rv_0146" in dropped


def test_precondition_quote_must_be_the_customers_words():
    """模型说前提已知却编了一句客户没说过的话（T37：「水管正常」不能证明「App 显示水量不准」）：不采信，照常追问。"""
    known = {"answer": "yes", "customer_quote": "the water level in the app is wrong"}
    kept, dropped, clar = _run([_mop_hyp(known)], symptoms=("failed drying",), said=["Slang in tank is in orde."])
    assert kept == [] and clar[0]["question"].startswith("Does the drying error")
    assert not any(d.startswith("precondition_") for d in dropped)


def test_answer_to_an_earlier_question_counts_as_customer_words():
    """客户在追问后答了 no：引文可以取自 answered_preconditions 的回答。"""
    known = {"answer": "no", "customer_quote": "no"}
    answered = [{"plan_id": "qa_bp_0114", "question": "Is it the left side?", "answer": "no"}]
    kept, dropped, clar = filter_hypotheses(
        [_mop_hyp(known)], allowed={"qa_rv_0146": LIB.get("qa_rv_0146")}, evidence_ids={"e1"},
        symptoms={"failed drying"}, facts=[], answered=answered, said=[], max_n=3)
    assert kept == [] and clar == [] and "precondition_negated:qa_rv_0146" in dropped


def test_unknown_precondition_still_asks():
    hyp = _hyp("qa_rv_0146", applicability="needs_confirmation", supported_symptoms=["mop still damp"],
               clarification_question="Have you run a mopping task since the update?", missing_fact="perform a new mopping task")
    kept, _, clar = _run([hyp], facts=[], symptoms=("mop still damp",))
    assert kept == [] and clar[0]["question"].startswith("Have you run")


# ---- HTTP：T53 直落小节首步 ----

T53 = ("Order No: Anker015\nProduct Name: eufy Wearable Breast Pump S1 Pro\nProblem Description: One side of the pump "
       "stoped working. I tried to charge it over and over again but it stoped turning on. I hope you can fix it.")


async def test_t53_known_fault_skips_the_section_question(conversation):
    set_knowledge_adapter(QAHitAdapter("bp-0114"))
    conversation.models["diagnose.synthesize"].script = [{"hypotheses": [{
        "plan_id": "qa_bp_0114", "confidence": 0.9, "evidence_ids": ["chunk-bp-0114"],
        "applicability": "supported", "supported_symptoms": ["stoped turning on"],
        "matched_section": "Breast pump cannot be turned on",
    }]}]
    events = await conversation.send(T53, {
        "primary_intent": "report_problem", "device_relation": "current", "product_hints": ["S1 Pro breast pump"],
        "facts": [{"value": "stoped turning on", "quote": "it stoped turning on", "subject": "it"}],
    })
    card = next(e["step"] for e in events if e["type"] == "step_card")
    assert card["plan_id"] == "qa_bp_0114" and card["step_id"] == "s2" and card["kind"] == "action"
    state = await conversation.state()
    recorded = [s for s in state["step_attempts"] if s["step_id"] == "select_scope"]
    assert recorded and recorded[0]["answer"] == {"option": "Breast pump cannot be turned on", "source": "fact"}
    assert (state.get("counters") or {}).get("executed", 0) == 0
    assert any(t.get("event") == "question_answered_from_facts" for t in state["guide_trace"])


async def test_t53_without_verified_section_still_asks(conversation):
    set_knowledge_adapter(QAHitAdapter("bp-0114"))
    conversation.models["diagnose.synthesize"].script = [{"hypotheses": [{
        "plan_id": "qa_bp_0114", "confidence": 0.9, "evidence_ids": ["chunk-bp-0114"],
        "applicability": "supported", "supported_symptoms": ["stoped working"],
    }]}]
    events = await conversation.send("My S1 Pro breast pump stoped working", {
        "primary_intent": "report_problem", "device_relation": "current", "product_hints": ["S1 Pro breast pump"],
        "facts": [{"value": "stoped working", "quote": "stoped working"}],
    })
    card = next(e["step"] for e in events if e["type"] == "step_card")
    assert card["step_id"] == "select_scope" and card["kind"] == "question"
