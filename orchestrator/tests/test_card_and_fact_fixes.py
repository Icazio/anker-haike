"""官方 63 单 2026-10-12 19:09 复测的卡片说明、事实承接与资料覆写修正（docs/claude/spec_2026-10-12-1951_card-and-fact-fixes.md）。"""

from __future__ import annotations

import pytest

from app.conversation.interpret import (
    FactCandidate,
    TurnInterpretation,
    logistics_correction,
    negation_polarity,
    uncovered_denials,
    wish_sentence_quotes,
)
from app.diagnose.decision import concrete
from app.diagnose.synthesize import _stems, precondition_status
from app.diagnose.vision import _instruction
from app.guide.steps import REPORTED_ANSWER, reported_note
from app.knowledge.runtime import set_knowledge_adapter
from app.official.message import parse_message
from app.official.models import OfficialData
from app.plans.qa import qa_plan_library
from tests.conversation_runtime import conversation as base_conversation_fixture
from tests.fake_qa import QAHitAdapter
from tests.test_conversation_l3 import l3_runtime as l3_runtime_fixture

base_conversation = base_conversation_fixture
l3_runtime = l3_runtime_fixture
TICKETS = {t.id: t.body for t in OfficialData().tickets}


@pytest.fixture
async def conversation(l3_runtime, base_conversation):
    yield base_conversation


# ---- C1 / C2：首卡说明按卡片类型、引用症状 ----

@pytest.mark.parametrize("kind", ["action", "question", "material_request"])
def test_reported_note_matches_the_card_kind(kind):
    """T36：rv-0341 首张是问题卡（只有选项和短答），说明却让客户「mark it as not solved」。"""
    note = reported_note(["Alle filters en borstels zijn vervangen"], kind)
    assert note.endswith(REPORTED_ANSWER[kind])
    assert ("not solved" in note) is (kind == "action")


def test_reported_note_quotes_the_symptom_once():
    """T37：「水箱满」在症状里，只引「软管、胶圈正常」时客户看不出这张卡针对的是自己的情况。"""
    note = reported_note(["Slang in tank is in orde."], "action", ["Terwijl de schoonwater tank nog vol is.", "Slang in tank is in orde."])
    assert note.startswith('You described: "Terwijl de schoonwater tank nog vol is.". You mentioned: "Slang in tank is in orde."')
    assert note.count("Slang in tank") == 1
    assert not reported_note(["x"], "action").startswith("You described")


T36 = TICKETS["T36"]


async def test_t36_question_card_note_does_not_offer_not_solved(conversation, l3_runtime):
    set_knowledge_adapter(QAHitAdapter("rv-0341"))
    conversation.models["diagnose.synthesize"].script = [{"hypotheses": [{
        "plan_id": "qa_rv_0341", "confidence": 0.8, "evidence_ids": ["chunk-rv-0341"],
        "applicability": "supported", "supported_symptoms": ["loud noise while vacuuming"],
    }]}]
    replaced = "Alle filters en borstels zijn vervangen en alles is schoongemaakt"
    events = await conversation.send(T36, {
        "primary_intent": "report_problem", "device_relation": "current", "product_hints": ["S1 Pro"],
        "facts": [{"value": "loud noise while vacuuming", "quote": "Tijdens het stofzuigen maakt de stofzuiger enorm veel geluid."},
                  {"kind": "action_taken", "value": "filters and brushes replaced", "quote": replaced}],
    })
    card = next(e for e in events if e["type"] == "step_card")["step"]
    assert card["kind"] == "question" and replaced in card["context"]
    assert "not solved" not in card["context"] and REPORTED_ANSWER["question"] in card["context"]
    assert '"Tijdens het stofzuigen maakt de stofzuiger enorm veel geluid."' in card["context"]


# ---- C3：T41 否定事实 ----

T41 = parse_message(TICKETS["T41"]).description
INJECTION_SENTENCE = "As the water injection is still malfunctioning we have not run mop cycles"


def test_symptom_quote_containing_the_denial_does_not_cover_it():
    """T41 repeat-2：症状事实的整句 quote 含「we have not run」，补抽不触发，事实里一条否定都没有。"""
    symptom = FactCandidate(value="water injection is still malfunctioning", quote=INJECTION_SENTENCE)
    assert uncovered_denials(T41, [symptom])
    denied = FactCandidate(kind="action_taken", value="run mop cycles", quote="we have not run mop cycles", polarity="negated")
    needed = FactCandidate(kind="observation", value="needed mop drying", quote="havent needed any mop drying", polarity="negated")
    assert uncovered_denials(T41, [symptom, denied, needed]) == []


def test_observation_before_the_denial_keeps_its_polarity():
    """T41 主轮：观察「注水仍异常」的 quote 是整句，被整条翻成 negated，意思反了。"""
    injection = FactCandidate(kind="observation", value="water injection is still malfunctioning", quote=INJECTION_SENTENCE)
    denied = FactCandidate(kind="action_taken", value="not run mop cycles", quote=INJECTION_SENTENCE)
    out = negation_polarity([injection, denied])
    assert [(f.polarity, f.value) for f in out] == [("affirmed", injection.value), ("negated", "run mop cycles")]


def test_dried_and_drying_share_a_stem():
    assert _stems("Mop not dried") == _stems("mop drying") == {"mop", "dry"}
    assert _stems("carries") == {"carry"} and _stems("emptied") == {"empty"}


def test_alternatives_in_a_precondition_are_matched_separately():
    """rv-0146 的前提「roller not dried /Mop not dried」：客户说没需要烘干拖布，任一备选被覆盖即前提被否定。"""
    fact = {"kind": "observation", "polarity": "negated", "status": "active",
            "value": "needed mop drying", "quote": "havent needed any mop drying"}
    assert precondition_status("roller not dried /Mop not dried", [fact])[0] == "negated"
    assert precondition_status("roller not dried", [fact])[0] == "unknown"


# ---- C4：T60 愿望句 ----

T60 = TICKETS["T60"]


def test_truncated_wish_quote_is_widened_to_its_sentence():
    """T60 主轮：「I just want my hoover to clean…」被截成「my hoover to clean…」，愿望被当成具体症状。"""
    fact = FactCandidate(value="hoover not cleaning properly", quote="my hoover to clean with out all this bullshit")
    [widened] = wish_sentence_quotes([fact], T60)
    assert widened.quote == "I just want my hoover to clean with out all this bullshit"
    assert not concrete(widened.model_dump())
    meaning = logistics_correction(TurnInterpretation(primary_intent="report_problem", facts=[fact]), T60)
    assert not concrete(meaning.facts[0].model_dump())


@pytest.mark.parametrize("text, quote", [
    ("The robot stops after 5 minutes. I want it to clean the whole floor.", "The robot stops after 5 minutes"),
    ("Water tray will not empty. I have already cleaned it.", "Water tray will not empty"),
])
def test_symptoms_outside_a_wish_sentence_are_unchanged(text, quote):
    fact = FactCandidate(value="x", quote=quote)
    assert wish_sentence_quotes([fact], text) == [fact]


# ---- C5：读图主体 ----

def test_vision_prompt_asks_for_the_main_subject_first():
    """T30：前景机器人 4 轮都被写成「扫地机器人基站」：提示词只要求写品类，词表里能指扫地机整机的只有基站。"""
    text = _instruction()
    # 2026-10-13 起主体单独成字段 subject（不再是「第一条观察」），由代码放到观察的第一条
    assert "subject：画面主体" in text and "扫地机器人本体" in text and "主机" in text


# ---- C6 / D1–D3：资料覆写 ----

LIB = qa_plan_library()


@pytest.mark.parametrize("plan_id", ["qa_rv_0473", "qa_rv_0363"])
def test_factory_reset_card_warns_about_the_map(plan_id):
    """T31：恢复出厂卡没提示会删地图；同型号 rv-0312 写明长按红键超过 5 秒会删除地图。"""
    steps = {s.step_id: s for s in LIB.get(plan_id).steps}
    assert "remove your saved map" in (steps["s4"].caution or "")
    assert all(not steps[s].caution for s in ("s1", "s2", "s3"))


def test_battery_heading_is_not_a_card():
    """T51：bp-0111「Check Battery Power」是小标题，单独出了一张四个词的卡。"""
    steps = {s.step_id: s for s in LIB.get("qa_bp_0111").steps}
    assert steps["s5"].kind == "statement" and steps["s6"].kind == "action"
