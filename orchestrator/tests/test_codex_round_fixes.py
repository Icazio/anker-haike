"""Codex 2026-10-12 20:25 复测 12 个非语言问题的修复（docs/claude/spec_2026-10-12-2217_codex-12-fixes.md）。

每条用官方原始工单（data/official/tickets.yaml）加同义 / 否定 / 对象互换的对照样本，不按案例号硬编码答案。
"""

from __future__ import annotations

import pytest

from app.conversation.interpret import (
    FactCandidate,
    TurnInterpretation,
    complete_problem_facts,
    device_failure_is_affirmed,
    uncovered_checks,
)
from app.conversation.product_questions import observation_terms, question_observations
from app.diagnose.synthesize import filter_hypotheses
from app.diagnose.vision import _instruction
from app.escalation.summary import r5_boundary
from app.knowledge.runtime import set_knowledge_adapter
from app.models.runtime import get_model_router
from app.official.message import parse_message
from app.official.models import OfficialData
from app.plans.qa import customer_text, qa_plan_library
from tests.conversation_runtime import conversation as base_conversation_fixture
from tests.fake_qa import QAHitAdapter
from tests.test_conversation_l3 import act
from tests.test_conversation_l3 import l3_runtime as l3_runtime_fixture
from tests.test_problem_description_recovery import source_state

base_conversation = base_conversation_fixture
l3_runtime = l3_runtime_fixture
TICKETS = {t.id: t.body for t in OfficialData().tickets}
LIB = qa_plan_library()


@pytest.fixture
async def conversation(l3_runtime, base_conversation):
    yield base_conversation


# ---- T27：跨行的问题描述与已做检查补抽 ----

def test_problem_description_spans_lines_until_the_next_form_field():
    """T27 的「Problem Description: Rolling Mop Blockage. Please clean.」下一行才是客户写的已做检查；只取第一行时
    补抽看不到这些句子。63 单里 7 单跨行。"""
    t27 = parse_message(TICKETS["T27"]).description
    assert t27.startswith("Rolling Mop Blockage. Please clean.") and "no blockage seen. roller mop area is clear." in t27
    assert "Problem Upload Images" not in t27
    assert parse_message(TICKETS["T41"]).description.endswith("is there an update on their arrival?")
    assert "Prodcut SN" not in parse_message(TICKETS["T29"]).description


def test_uncovered_checks_finds_the_stated_checks_until_they_are_extracted():
    t27 = parse_message(TICKETS["T27"]).description
    assert uncovered_checks(t27, []) == [
        "tried the suggestion solution but error still persist.", "no blockage seen.", "roller mop area is clear."]
    extracted = [FactCandidate(kind="action_taken", value="tried suggestion", quote="tried the suggestion solution"),
                 FactCandidate(kind="observation", value="no blockage", quote="no blockage seen. roller mop area is clear.")]
    assert uncovered_checks(t27, extracted) == []
    # 症状事实的原话不算覆盖：它说的是故障，不是已做检查
    symptom = [FactCandidate(value="mop blocked", quote="Rolling Mop Blockage. Please clean. tried the suggestion solution")]
    assert uncovered_checks(t27, symptom)
    # 同义 / 荷兰语
    assert uncovered_checks("Slang in tank is in orde. Rubbers zijn in orde.", []) == ["Slang in tank is in orde.", "Rubbers zijn in orde."]
    assert uncovered_checks("The robot keeps beeping when docked.", []) == []


async def test_t27_missed_checks_are_recovered_even_with_an_error_code(conversation):
    """T27 带 3212 错误码：之前有码就整个不补抽；已做检查与有没有码无关。"""
    model = conversation.models["intake"]
    model.script = [{"facts": [
        {"kind": "observation", "value": "no blockage, roller area clear", "quote": "no blockage seen. roller mop area is clear."},
        {"kind": "action_taken", "value": "tried suggested solution", "quote": "tried the suggestion solution"},
        {"kind": "symptom", "value": "invented", "quote": "not in the text"},
    ]}]
    symptom = FactCandidate(value="Rolling Mop Blockage", quote="Rolling Mop Blockage. Please clean.")
    meaning = TurnInterpretation(primary_intent="report_problem", facts=[symptom])
    result, trace = await complete_problem_facts(get_model_router(), meaning, source_state(TICKETS["T27"]), lane="domestic")
    assert len(model.calls) == 1 and trace["checks"] == 3
    assert [(f.kind, f.quote) for f in result.facts[1:]] == [
        ("observation", "no blockage seen. roller mop area is clear."), ("action_taken", "tried the suggestion solution")]


async def test_checks_already_extracted_do_not_call_the_model(conversation):
    meaning = TurnInterpretation(primary_intent="report_problem", facts=[
        FactCandidate(value="Rolling Mop Blockage", quote="Rolling Mop Blockage. Please clean."),
        FactCandidate(kind="action_taken", value="tried suggestion", quote="tried the suggestion solution but error still persist."),
        FactCandidate(kind="observation", value="no blockage", quote="no blockage seen."),
        FactCandidate(kind="observation", value="area clear", quote="roller mop area is clear."),
    ])
    result, trace = await complete_problem_facts(get_model_router(), meaning, source_state(TICKETS["T27"]), lane="domestic")
    assert result == meaning and trace["outcome"] == "not_needed" and not conversation.models["intake"].calls


# ---- T61：设备做不到的「否定」现象、时机冲突不追问、交人工列出全部症状 ----

@pytest.mark.parametrize("quote, affirmed", [
    ("the cleans are not being recorded", True),       # T61
    ("now it doesn't swap water", True),               # T42
    ("The robot no longer charges", True),
    ("no smoke", False),
    ("it is not leaking", False),
    ("we have not run mop cycles", False),             # 客户没做过，不是现象
])
def test_device_failure_negation_is_the_anomaly_itself(quote, affirmed):
    [fact] = device_failure_is_affirmed([FactCandidate(value=quote, quote=quote, polarity="negated")])
    assert (fact.polarity == "affirmed") is affirmed


def test_opposite_timing_is_dropped_without_a_question():
    facts = [{"kind": "symptom", "value": "starts 2 hours early", "quote": "it's going off 2 hours before",
              "subject": "schedule", "polarity": "affirmed", "timing": "2 hours before", "status": "active"}]
    plan = LIB.get("qa_rv_0551")
    kept, dropped, clar = filter_hypotheses(
        [{"plan_id": "qa_rv_0551", "confidence": 0.35, "evidence_ids": ["e1"], "applicability": "supported",
          "supported_symptoms": ["starts 2 hours early"],
          "conflict": {"kind": "direction", "customer_quote": "it's going off 2 hours before", "candidate_quote": "failed to start"}}],
        allowed={"qa_rv_0551": plan}, evidence_ids={"e1"}, symptoms={"starts 2 hours early"}, facts=facts,
        error_codes=[], said=["it's going off 2 hours before"], max_n=3)
    assert kept == [] and clar == [] and dropped == ["conflict_direction:qa_rv_0551"]


def test_r5_boundary_names_every_reported_symptom():
    facts = [{"kind": "symptom", "status": "active", "polarity": "affirmed", "value": "starts early", "quote": "it's going off 2 hours before"},
             {"kind": "symptom", "status": "active", "polarity": "affirmed", "value": "no records", "quote": "the cleans are not being recorded"},
             {"kind": "observation", "status": "active", "value": "x", "quote": "ignored"}]
    text = r5_boundary({"active_issue_id": "i", "issues": {"i": {"facts": facts}}})
    assert '"it\'s going off 2 hours before"' in text and '"the cleans are not being recorded"' in text
    single = r5_boundary({"active_issue_id": "i", "issues": {"i": {"facts": facts[:1]}}})
    assert single == "I couldn't confirm official troubleshooting guidance for this issue. "


async def test_t61_hands_off_with_both_symptoms_instead_of_repeating_the_customer(conversation, l3_runtime):
    set_knowledge_adapter(QAHitAdapter("rv-0551", "rv-0522"))
    conversation.models["diagnose.synthesize"].script = [{"hypotheses": [
        {"plan_id": "qa_rv_0551", "confidence": 0.35, "evidence_ids": ["chunk-rv-0551"], "applicability": "supported",
         "supported_symptoms": ["going off 2 hours before schedule"],
         "conflict": {"kind": "direction", "customer_quote": "it’s going off 2 hours before", "candidate_quote": "failed to start"}},
    ]}]
    events = await conversation.send(TICKETS["T61"], {
        "primary_intent": "report_problem", "device_relation": "current", "product_hints": ["omni c20"],
        "facts": [{"value": "going off 2 hours before schedule", "quote": "it’s going off 2 hours before", "timing": "2 hours before"},
                  {"value": "cleans are not being recorded", "quote": "the cleans are not being recorded", "polarity": "negated"}],
    })
    text = "".join(e.get("delta", "") for e in events)
    assert "Is that right" not in text
    assert "the cleans are not being recorded" in text and "it’s going off 2 hours before" in text
    state = await conversation.state()
    assert state["escalate_reason"] == "R5"
    issue = state["issues"][state["active_issue_id"]]
    assert all(f["polarity"] == "affirmed" for f in issue["facts"] if f["kind"] == "symptom")


# ---- T37 / T34：资料覆盖边界说明 ----

@pytest.mark.parametrize("qa_id, removed", [
    ("rv-0021", "normal protective mechanism"),   # 本轮复测主轮与 repeat-2 选中的是这条
    ("rv-0112", "simply a notification"),
])
def test_other_low_water_entries_drop_the_it_is_normal_sentence(qa_id, removed):
    plan = LIB.get("qa_" + qa_id.replace("-", "_"))
    assert [s.kind for s in plan.steps] == ["action", "handoff"] and plan.steps[0].scope_note
    rendered = customer_text(LIB.evidence[f"{qa_id}#s1"].snippet)
    assert removed not in rendered and "in most cases" not in rendered.lower()


def test_full_tank_entry_no_longer_says_it_is_only_a_low_water_notice():
    steps = LIB.get("qa_rv_0111").steps
    assert [(s.step_id, s.kind) for s in steps] == [("s1", "action"), ("s1c", "handoff")]
    rendered = customer_text(LIB.evidence["rv-0111#s1"].snippet)
    assert "simply a notification" not in rendered and "in most cases" not in rendered
    assert "refill it and restart the cleaning task" in rendered


async def test_t37_full_tank_card_says_how_to_continue(conversation, l3_runtime):
    set_knowledge_adapter(QAHitAdapter("rv-0111"))
    conversation.models["diagnose.synthesize"].script = [{"hypotheses": [{
        "plan_id": "qa_rv_0111", "confidence": 0.85, "evidence_ids": ["chunk-rv-0111"],
        "applicability": "supported", "supported_symptoms": ["add water warning while tank is full"],
    }]}]
    events = await conversation.send(TICKETS["T37"], {
        "primary_intent": "report_problem", "device_relation": "current", "product_hints": ["Omni E28"],
        "facts": [{"value": "add water warning while tank is full", "quote": "Terwijl de schoonwater tank nog vol is."},
                  {"kind": "observation", "value": "hose ok", "quote": "Slang in tank is in orde."},
                  {"kind": "observation", "value": "rubbers ok", "quote": "Rubbers zijn in orde."}],
    })
    card = next(e for e in events if e["type"] == "step_card")["step"]
    assert (card["plan_id"], card["step_id"]) == ("qa_rv_0111", "s1")
    assert "You said the tank is already full" in card["context"] and '"Slang in tank is in orde."' in card["context"]
    assert card["context"].count("mark it as not solved") == 1  # 两段说明不重复反馈方式
    assert "simply a notification" not in card["instruction"]
    # 未解决 → 原文的「仍报错请联系我们」是交人工段，不再发第二张卡
    events = conversation.check(await act(conversation.client, conversation.sid, "step_feedback", {"feedback": "not_solved"}))
    assert not any(e["type"] == "step_card" for e in events)


async def test_scope_note_only_appears_when_the_customer_said_it(conversation, l3_runtime):
    set_knowledge_adapter(QAHitAdapter("rv-0111"))
    conversation.models["diagnose.synthesize"].script = [{"hypotheses": [{
        "plan_id": "qa_rv_0111", "confidence": 0.85, "evidence_ids": ["chunk-rv-0111"],
        "applicability": "supported", "supported_symptoms": ["6011 add water"],
    }]}]
    events = await conversation.send("Product PN: T2352\nProblem Description: 6011 add water message keeps showing", {
        "primary_intent": "report_problem", "device_relation": "current",
        "facts": [{"value": "6011 add water", "quote": "6011 add water message keeps showing"}],
    })
    card = next(e for e in events if e["type"] == "step_card")["step"]
    assert "already full" not in (card.get("context") or "")


async def test_t34_map_card_states_what_the_source_cannot_confirm(conversation, l3_runtime):
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
    assert card["step_id"] == "s1"
    assert "I couldn't find official information on restoring a map after a repair" in card["context"]
    assert "cannot be retrieved" not in card["context"]  # 不借用 E28 的结论


# ---- T52：one side 是泵位（检查规则见 test_p2_wording_and_objects.py）；T32：无依据的效果与换新前提 ----

def test_temporary_fix_card_drops_the_replacement_premise_and_success_rate():
    rendered = customer_text(LIB.evidence["rv-0061#s1"].snippet)
    assert "Before arranging a replacement" not in rendered and "success rate" not in rendered
    assert "We have a simple temporary solution that you might want to try." in rendered
    assert "slight misalignment of the detection sensor" in rendered


# ---- T48：提问随附照片的观察进入产品问答 ----

def test_question_observations_come_only_from_the_question_input():
    facts = [{"kind": "observation", "status": "active", "source_kind": "image_observation", "quote": "指示灯亮绿色与黄色",
              "source_entry_ids": ["q1"]},
             {"kind": "observation", "status": "active", "source_kind": "image_observation", "quote": "旧照片里的滚刷",
              "source_entry_ids": ["old"]},
             {"kind": "observation", "status": "active", "source_kind": "user_report", "quote": "客户说的", "source_entry_ids": ["q1"]}]
    facts.append({"kind": "observation", "status": "active", "source_kind": "image_observation",
                  "quote": "画面主体：耳机充电盒", "source_entry_ids": ["q1"]})
    state = {"active_issue_id": "i", "issues": {"i": {"facts": facts}}}
    # 产品已确认时不把图里可能认错的物体名交给回答（T48 吸奶器主机被叫成耳机充电盒），只留灯与外观
    assert question_observations(state, {"source_input_id": "q1"}) == ["指示灯亮绿色与黄色"]
    assert observation_terms(["指示灯亮绿色与黄色"]) == "indicator light LED green yellow"
    assert observation_terms(["白色圆形小家电主机"]) == "white"


async def test_t48_photo_observations_reach_the_product_answer(conversation):
    """T48：拍指示灯问「这个绿灯是什么意思」。读图看到的灯色进检索词和回答输入，回答规则要求以确认的产品为准、
    证据没覆盖时说明缺口并给下一步；不把别的颜色的灯规则当答案。"""
    from app.conversation.product_questions import answer_product_question
    from app.sessions.cards import get_catalog

    captured = {}

    class Recorder:
        async def ensure(self):
            return None

    state = {"text": "The product is S1 Pro breast pump, model T8D04.", "input_id": "q2", "session_id": "s", "run_id": "r",
             "turn_decision": {"primary_intent": "supplement"}, "active_issue_id": "i",
             "product_question": {"question": "What does this green light mean", "source_input_id": "q1",
                                  "status": "awaiting_product", "candidate_skus": []},
             "issues": {"i": {"facts": [{"kind": "observation", "status": "active", "source_kind": "image_observation",
                                         "quote": "指示灯亮绿色与黄色", "source_entry_ids": ["q1"]}]}}}

    async def fake_search(adapter, query, scope, k, **kwargs):
        captured["query"] = query
        raise TimeoutError

    import app.conversation.product_questions as pq
    original = pq.search_round
    pq.search_round = fake_search
    try:
        await answer_product_question(state, writer=lambda e: None, catalog=get_catalog(), adapter=Recorder(),
                                      router=None, rules=None, lane="domestic")
    finally:
        pq.search_round = original
    assert captured["query"] == "What does this green light mean indicator light LED green yellow"


def test_photo_facts_group_lights_damage_and_details_for_the_answer():
    """T48 2026-10-13 复测：十几条平铺观察交给回答，模型三次都只照做「查说明书」，没复述灯位与裂纹。
    按用途分组（灯 / 外观异常 / 主体细节），背景物体不给。"""
    from app.conversation.product_questions import PHOTO_ANSWER_RULES, photo_facts

    obs = ["裂纹：机身左侧充电触点上方边缘处", "绿色灯：面板中央电源键左侧，一颗亮起", "主体细节：米色圆角机身",
           "背景有白色毛巾", "外壳破损"]
    assert photo_facts(obs) == {"lights": ["绿色灯：面板中央电源键左侧，一颗亮起"],
                                "visible_damage": ["裂纹：机身左侧充电触点上方边缘处"], "device_details": ["米色圆角机身"]}
    assert "1. 先复述照片" in PHOTO_ANSWER_RULES and "常亮还是闪烁" in PHOTO_ANSWER_RULES


# ---- T30 / T42：读图主体判据（真实识别效果需真实模型复测）----

def test_vision_prompt_gives_visible_cues_for_body_base_and_handheld_parts():
    text = _instruction()
    assert "手里拿着的东西是主体" in text and "layer（手持 / 前景 / 中景 / 背景）" in text
    assert "底部有轮子、边刷" in text and "带水箱或尘袋仓" in text
    # 细节只归到它真正所在的物体；分不清就不写（T42 金属片、标签被归到配件或基站上）
    assert "只归到它真正所在的那个物体上" in text and "anomalies" in text


# ---- 本轮复测（round3）新发现：低置信候选的追问、现象事实漏抽时的有效症状兜底 ----

def test_low_confidence_candidate_does_not_get_to_question_the_customer():
    """T61 round3 主轮：两个时机冲突候选丢弃后，0.25 的「重复清扫」条目去问「历史里有没有重复路径」。
    低于换方案门槛（0.3）的候选，客户答「是」也不会被执行，不该拿来追问。"""
    facts = [{"kind": "symptom", "value": "cleans not recorded", "quote": "the cleans are not being recorded",
              "polarity": "affirmed", "status": "active"}]
    hyp = {"plan_id": "qa_rv_0542", "confidence": 0.25, "evidence_ids": ["e1"], "applicability": "needs_confirmation",
           "supported_symptoms": ["cleans not recorded"], "clarification_question": "Does the app show repeated cleaning?",
           "missing_fact": "Repeated cleaning/Overlapping cleaning paths"}
    allowed = {"qa_rv_0542": LIB.get("qa_rv_0542")}
    _, _, clar = filter_hypotheses([hyp], allowed=allowed, evidence_ids={"e1"}, symptoms={"cleans not recorded"},
                                   facts=facts, error_codes=[], max_n=3)
    assert clar == []
    _, _, clar = filter_hypotheses([{**hyp, "confidence": 0.55}], allowed=allowed, evidence_ids={"e1"},
                                   symptoms={"cleans not recorded"}, facts=facts, error_codes=[], max_n=3)
    assert [c["plan_id"] for c in clar] == ["qa_rv_0542"]


def test_customer_text_is_the_symptom_when_no_symptom_fact_was_extracted():
    """T40 round3 主轮：长邮件里一条现象事实都没抽到，所有候选因「没覆盖任何有效症状」被丢弃。"""
    from app.diagnose.synthesize import active_symptoms

    assert active_symptoms({"symptoms": [], "query": "floor detergent level has barely moved"}, []) == [
        "floor detergent level has barely moved"]
    assert active_symptoms({"symptoms": ["not dispensing"], "query": "long email"}, ["指示灯亮"]) == ["not dispensing", "指示灯亮"]
    # T60 round4：愿望被抽成否定现象，不能用原文把愿望重新当成现象
    wish = {"symptoms": [], "query": "This app is shit . I just want my hoover to clean with out all this bullshit",
            "active_issue_id": "i", "issues": {"i": {"facts": [
                {"kind": "symptom", "status": "active", "polarity": "negated", "value": "hoover not cleaning",
                 "quote": "I just want my hoover to clean with out all this bullshit"}]}}}
    assert active_symptoms(wish, []) == []
    assert active_symptoms({**wish, "issues": {"i": {"facts": []}}}, []) == []  # 原文本身是愿望
    # 2026-10-13 deepseek-v4-pro：T40 的现象被记成观察，没有现象事实时客户自己说的肯定观察也可选；否定观察与有现象事实时不算
    seen = {"symptoms": [], "query": "", "active_issue_id": "i", "issues": {"i": {"facts": [
        {"kind": "observation", "status": "active", "polarity": "affirmed", "value": "floor detergent level has barely moved"},
        {"kind": "observation", "status": "active", "polarity": "negated", "value": "not dispensing"}]}}}
    assert active_symptoms(seen, []) == ["floor detergent level has barely moved"]
    with_symptom = {**seen, "issues": {"i": {"facts": [*seen["issues"]["i"]["facts"],
                                                        {"kind": "symptom", "status": "active", "value": "won't dispense"}]}}}
    assert active_symptoms(with_symptom, []) == []


async def test_recovery_also_runs_when_troubleshooting_is_the_secondary_request(conversation):
    """T41 round4 主轮：模型把「配件到了没」排为主诉求、「烘干报错」排第二，补抽被跳过，「没跑过拖地」漏掉后
    又问「是不是在烘干之后出现」。排障是次诉求也要补。"""
    model = conversation.models["intake"]
    model.script = [{"facts": [{"kind": "action_taken", "value": "run mop cycles", "quote": "we have not run mop cycles",
                                "polarity": "negated"}]}]
    drying = FactCandidate(value="failed drying error", quote="This is the second time Ive received this error message related to failed drying.")
    meaning = TurnInterpretation(primary_intent="logistics_query", secondary_intents=["report_problem"], facts=[drying])
    result, trace = await complete_problem_facts(get_model_router(), meaning, source_state(TICKETS["T41"]), lane="domestic")
    assert len(model.calls) == 1 and trace["denials"] == 2
    assert any(f.kind == "action_taken" and f.polarity == "negated" for f in result.facts)
    only_logistics = TurnInterpretation(primary_intent="logistics_query", facts=[drying])
    _, trace = await complete_problem_facts(get_model_router(), only_logistics, source_state(TICKETS["T41"]), lane="domestic")
    assert trace["outcome"] == "not_needed"


async def test_first_message_correction_without_a_target_is_not_a_correction(conversation):
    """T27 final repeat-1：首封消息里模型把「no blockage seen. roller mop area is clear.」写成 corrections（fact_id 填现象原文），
    补抽因「有更正」被跳过，首卡没有承接已做检查。没有可更正的旧事实时它不是更正，照常补抽。"""
    model = conversation.models["intake"]
    model.script = [{"facts": [{"kind": "observation", "value": "no blockage", "quote": "no blockage seen."}]}]
    meaning = TurnInterpretation(primary_intent="report_problem", facts=[
        FactCandidate(value="mop blocked", quote="Rolling Mop Blockage. Please clean.")],
        corrections=[{"fact_id": "Rolling Mop Blockage", "value": "no blockage seen. roller mop area is clear.",
                      "quote": "no blockage seen. roller mop area is clear."}])
    result, trace = await complete_problem_facts(get_model_router(), meaning, source_state(TICKETS["T27"]), lane="domestic")
    assert len(model.calls) == 1 and trace["checks"] == 3
    assert any(f.kind == "observation" for f in result.facts)


# ---- T61 2026-10-13 08:05 复测：不相关候选的追问（docs/claude/spec_2026-10-13-1041_t61-unrelated-clarify.md）----

T61_FACTS = [
    {"kind": "symptom", "value": "going off 2 hours before schedule", "quote": "it's going off 2 hours before",
     "polarity": "affirmed", "timing": "2 hours before", "status": "active"},
    {"kind": "symptom", "value": "cleans are not being recorded", "quote": "the cleans are not being recorded",
     "polarity": "affirmed", "status": "active"},
]


def _t61_hyps(extra):
    return [
        {"plan_id": "qa_rv_0522", "confidence": 0.35, "evidence_ids": ["e1"], "applicability": "needs_confirmation",
         "supported_symptoms": ["going off 2 hours before schedule"],
         "conflict": {"kind": "direction", "customer_quote": "it's going off 2 hours before", "candidate_quote": "failed to start scheduled cleaning"},
         "clarification_question": "Is another task running?", "missing_fact": "other tasks not completed"},
        {"plan_id": "qa_rv_0565", "confidence": 0.3, "evidence_ids": ["e1"], "applicability": "needs_confirmation",
         "supported_symptoms": ["cleans are not being recorded"], "missing_fact": "inaccurate mapping",
         "clarification_question": "Does the app show an inaccurate or wrong map for your home?", **extra},
    ]


def _run(hyps, facts, symptoms):
    allowed = {h["plan_id"]: LIB.get(h["plan_id"]) for h in hyps}
    return filter_hypotheses(hyps, allowed=allowed, evidence_ids={"e1"}, symptoms=symptoms, facts=facts, error_codes=[], max_n=3)


def test_t61_question_about_a_different_problem_is_not_asked():
    """Codex repeat-1：时机冲突的两条丢弃后，只覆盖「清扫不记录」的 rv-0565（0.3）问「地图准不准」。
    文档讲的是另一个问题，不追问；没有可执行方案就按知识缺口交人工。"""
    symptoms = {f["value"] for f in T61_FACTS}
    kept, dropped, clar = _run(_t61_hyps({"question_targets": ["cleans are not being recorded"],
                                          "question_relation": "different_problem"}), T61_FACTS, symptoms)
    assert kept == [] and clar == []
    assert "conflict_direction:qa_rv_0522" in dropped and "clarify_unrelated:qa_rv_0565" in dropped
    # 自报 narrows 却指不出逐字的有效症状，同样不问
    _, dropped, clar = _run(_t61_hyps({"question_targets": ["map is wrong"], "question_relation": "narrows"}), T61_FACTS, symptoms)
    assert clar == [] and "clarify_unrelated:qa_rv_0565" in dropped


def test_t62_question_that_narrows_the_symptom_is_still_asked():
    """T62「not cleaning in a straight line」：rv-0542 问「是否反复清扫同一区域」是在细分客户的症状，Codex 判合理。"""
    facts = [{"kind": "symptom", "value": "not cleaning in a straight line", "quote": "not cleaning in a straight line",
              "polarity": "affirmed", "status": "active"}]
    hyp = {"plan_id": "qa_rv_0542", "confidence": 0.35, "evidence_ids": ["e1"], "applicability": "needs_confirmation",
           "supported_symptoms": ["not cleaning in a straight line"], "missing_fact": "Repeated cleaning/Overlapping cleaning paths",
           "clarification_question": "Does the robot clean the same area repeatedly?",
           "question_targets": ["not cleaning in a straight line"], "question_relation": "narrows"}
    _, _, clar = _run([hyp], facts, {"not cleaning in a straight line"})
    assert [c["plan_id"] for c in clar] == ["qa_rv_0542"]


def test_without_a_relation_the_confidence_floor_still_applies():
    """旧回放或模型漏填关系时不判相关性，回到 0.3 门槛：0.3 照问，0.25 不问。"""
    symptoms = {f["value"] for f in T61_FACTS}
    _, _, clar = _run(_t61_hyps({}), T61_FACTS, symptoms)
    assert [c["plan_id"] for c in clar] == ["qa_rv_0565"]
    low = _t61_hyps({})
    low[1]["confidence"] = 0.25
    assert _run(low, T61_FACTS, symptoms)[2] == []
