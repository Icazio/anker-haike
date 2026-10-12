"""条件步骤先对事实（2026-10-10 多轮复现 P2 / P3），客户自述只标注不消费步骤（2026-10-12 T21）。

- T22：rv-0106 两步都是条件建议。用户说「平地持续报错、没卡在楼梯或家具」→ s1 条件否定、s2 条件成立，直接发 s2（重启）。
- 客户说做过的操作、原话里像是答过的问句都不跳卡：卡照发，首卡引用客户原话说明可能重叠（T16 T21 T29 T36 T37 T46 T51）。
模型只给条件判定和引文；服务端校验引文逐字出自用户原话。模型与知识库均为假。
"""

from __future__ import annotations

import pytest

from app.guide.fact_check import StepCheck, _skips, _steps_text, accept, candidates
from app.guide.steps import reported_quotes
from app.knowledge.runtime import set_knowledge_adapter
from app.plans.qa import qa_plan_library, step_condition
from tests.conversation_runtime import conversation as base_conversation_fixture
from tests.fake_qa import QAHitAdapter
from tests.test_conversation_l3 import act
from tests.test_conversation_l3 import l3_runtime as l3_runtime_fixture

base_conversation = base_conversation_fixture
l3_runtime = l3_runtime_fixture
LIB = qa_plan_library()
FLAT = "This happens continuously on an open, flat floor. It has not been stuck at stairs or furniture."


@pytest.fixture
async def conversation(l3_runtime, base_conversation):
    yield base_conversation


@pytest.mark.parametrize(("text", "condition"), [
    ("If the robot is often stuck on the edge of stairs or furniture and triggers this warning, it is recommended to set a no-go zone.",
     "the robot is often stuck on the edge of stairs or furniture and triggers this warning"),
    ("If the robot continues to display errors on flat ground, please try restarting the robot.",
     "the robot continues to display errors on flat ground"),
    ("If the error persists after restarting, please try unplugging the base station.", None),
    ("If heating still fails, try placing the speaker covers crosswise.", None),
    ("Restart the robot and try again.", None),
])
def test_step_condition_keeps_scenarios_and_skips_follow_ups(text, condition):
    assert step_condition(text) == condition


def test_only_condition_steps_are_checked_and_quotes_must_be_the_customers():
    plan = LIB.get("qa_rv_0106")
    assert [s.step_id for s in candidates(plan, {})] == ["s1", "s2"]
    # 没有条件步骤的计划不调用核对：操作与问句由卡片反馈处理（T21 rv-0113 / T46 bp-0123）
    assert candidates(LIB.get("qa_rv_0113"), {}) == []
    assert candidates(LIB.get("qa_bp_0123"), {}) == []
    steps = candidates(plan, {})
    out = accept(steps, [
        StepCheck(step_id="s1", status="negated", quote="It has not been stuck at stairs or furniture"),
        StepCheck(step_id="s2", status="satisfied", quote="it happens on the floor"),  # 引文不在原话里
        StepCheck(step_id="s9", status="negated", quote="has not been stuck"),  # 不是候选步骤
    ], [FLAT])
    assert out == {"s1": {"status": "negated", "quote": "It has not been stuck at stairs or furniture"}}


BOTH = {"s1", "s2"}


def test_sibling_condition_satisfied_skips_the_earlier_unknown_one():
    plan = LIB.get("qa_rv_0106")
    assert _skips(plan, {"s2": {"status": "satisfied", "quote": "flat floor"}}, BOTH) == {
        "s1": {"status": "unknown", "skip": True}, "s2": {"status": "satisfied", "quote": "flat floor"}}
    assert _skips(plan, {"s1": {"status": "negated", "quote": "not been stuck"}}, BOTH)["s1"]["skip"] is True
    assert "s2" not in _skips(plan, {"s1": {"status": "negated", "quote": "not been stuck"}}, BOTH)
    assert _skips(plan, {"s1": {"status": "satisfied", "quote": "stuck on stairs"}}, BOTH) == {
        "s1": {"status": "satisfied", "quote": "stuck on stairs"}}


def test_negated_verdict_alone_cannot_exhaust_the_plan():
    """T22 复测 B06-r2：s1 已反馈，只剩 s2；模型把平地条件误判 negated。最后一个可发步骤照发，不因一次判定转人工。"""
    plan = LIB.get("qa_rv_0106")
    kept = _skips(plan, {"s2": {"status": "negated", "quote": "x"}}, {"s2"})
    assert kept["s2"]["skip"] is False
    both = _skips(plan, {"s1": {"status": "negated", "quote": "a"}, "s2": {"status": "negated", "quote": "b"}}, BOTH)
    assert both["s1"]["skip"] is True and both["s2"]["skip"] is False


def test_handled_sibling_conditions_are_shown_as_reference():
    """只剩一条条件时把已处理的兄弟条件作对照给模型，模型才分得清原话里的否定句针对哪个场景。"""
    plan = LIB.get("qa_rv_0106")
    state = {"step_attempts": [{"plan_id": "qa_rv_0106", "step_id": "s1", "instruction_src": "evidence:rv-0106#s1",
                                "kind": "action", "feedback": "not_solved"}]}
    steps = candidates(plan, state)
    assert [s.step_id for s in steps] == ["s2"]
    text = _steps_text(steps, LIB, [s for s in plan.steps if s.condition and s not in steps])
    assert "s1 [reference] the robot is often stuck on the edge of stairs" in text
    assert "s2 [condition] the robot continues to display errors on flat ground" in text
    # 模型即便输出了对照步骤的判定，也不采纳
    assert accept(steps, [StepCheck(step_id="s1", status="negated", quote="has not been stuck")],
                  ["It has not been stuck at stairs or furniture."]) == {}


T22 = ("Productnaam: X10 Pro Omni\nProduct-PN: T2351\nProbleemtype: WARNING\nProbleemcode: 7002-De robot zweeft in de lucht.\n"
       "Probleempush: Wiel raakt de grond niet, verplaats de robot naar een nieuwe positie.\n"
       "Probleembeschrijving: Wiel raakt de grond niet.\n")


async def test_t22_flat_floor_goes_straight_to_the_restart_branch(conversation):
    """T22 首封就说平地持续报错：精确错误码命中 rv-0106 后不发楼梯 / 家具禁区卡，直接发 s2。"""
    set_knowledge_adapter(QAHitAdapter("rv-0106"))
    conversation.models["guide.step"].script = [{"steps": [
        {"step_id": "s1", "status": "negated", "quote": "It has not been stuck at stairs or furniture"},
        {"step_id": "s2", "status": "satisfied", "quote": "This happens continuously on an open, flat floor"},
    ]}]
    events = await conversation.send(T22 + FLAT, {
        "primary_intent": "report_problem", "device_relation": "current", "product_hints": ["X10 Pro Omni"],
        "facts": [{"value": "Wiel raakt de grond niet", "quote": "Wiel raakt de grond niet"},
                  {"value": "Happens continuously on an open, flat floor", "quote": "This happens continuously on an open, flat floor"}],
    })
    card = next(e for e in events if e["type"] == "step_card")
    assert card["step"]["step_id"] == "s2"
    state = await conversation.state()
    assert state["step_checks"]["qa_rv_0106"]["steps"]["s1"]["skip"] is True
    assert any(t.get("event") == "fact_check" for t in state["guide_trace"])


async def test_t22_second_turn_feedback_and_condition_both_advance(conversation):
    """T22 两轮：首卡 s1；用户回「平地持续」→ 反馈记到 s1，下一张是 s2，不重发 s1。"""
    set_knowledge_adapter(QAHitAdapter("rv-0106"))
    conversation.models["guide.step"].script = [{"steps": []}]
    events = await conversation.send(T22, {
        "primary_intent": "report_problem", "device_relation": "current", "product_hints": ["X10 Pro Omni"],
        "facts": [{"value": "Wiel raakt de grond niet", "quote": "Wiel raakt de grond niet"}],
    })
    assert next(e for e in events if e["type"] == "step_card")["step"]["step_id"] == "s1"
    events = await conversation.send(FLAT, {
        "primary_intent": "step_feedback", "device_relation": "current", "feedback": "not_solved", "feedback_quote": FLAT,
        "facts": [{"value": "Happens continuously on an open, flat floor", "quote": "This happens continuously on an open, flat floor"}],
    })
    assert next(e for e in events if e["type"] == "step_card")["step"]["step_id"] == "s2"


async def test_t46_question_mentioned_in_text_is_still_asked_on_the_card(conversation):
    """T46：首封说了「continuous, during breast pumping」。原话推出的答案不替客户点选：问句照发，客户在卡上确认；
    计划没有条件步骤，不调用核对模型。"""
    set_knowledge_adapter(QAHitAdapter("bp-0123"))
    text = "My S1 Pro breast pump motor is making abnormal noise. The noise is continuous, during breast pumping."
    conversation.models["diagnose.synthesize"].script = [{"hypotheses": [{
        "plan_id": "qa_bp_0123", "confidence": 0.9, "evidence_ids": ["chunk-bp-0123"],
        "applicability": "supported", "supported_symptoms": ["motor making abnormal noise"],
    }]}]
    events = await conversation.send(text, {
        "primary_intent": "report_problem", "device_relation": "current", "product_hints": ["S1 Pro breast pump"],
        "facts": [{"value": "motor making abnormal noise", "quote": "motor is making abnormal noise", "subject": "motor"}],
    })
    card = next(e for e in events if e["type"] == "step_card")
    assert (card["step"]["step_id"], card["step"]["kind"]) == ("s2", "question")
    state = await conversation.state()
    assert not state.get("step_attempts")
    assert not conversation.models["guide.step"].calls


async def test_fact_check_failure_falls_back_to_the_first_step(conversation):
    """判定不可用（脚本耗尽 = 模型失败）时照常从首步发卡，不阻塞排障。"""
    set_knowledge_adapter(QAHitAdapter("rv-0106"))
    conversation.models["guide.step"].script = []
    events = await conversation.send(T22 + FLAT, {
        "primary_intent": "report_problem", "device_relation": "current", "product_hints": ["X10 Pro Omni"],
        "facts": [{"value": "Happens continuously on an open, flat floor", "quote": "This happens continuously on an open, flat floor"}],
    })
    assert next(e for e in events if e["type"] == "step_card")["step"]["step_id"] == "s1"


async def test_t22_feedback_then_misjudged_restart_condition_still_sends_restart(conversation):
    """T22 复测 B06-r2：第二轮模型同时给反馈（s1 记 not_solved），条件判定又把 s2 判 negated；仍发 s2，不进质保。"""
    set_knowledge_adapter(QAHitAdapter("rv-0106"))
    events = await conversation.send(T22, {
        "primary_intent": "report_problem", "device_relation": "current", "product_hints": ["X10 Pro Omni"],
        "facts": [{"value": "Wiel raakt de grond niet", "quote": "Wiel raakt de grond niet"}],
    })
    assert next(e for e in events if e["type"] == "step_card")["step"]["step_id"] == "s1"
    conversation.models["guide.step"].script = [{"steps": [{"step_id": "s2", "status": "negated", "quote": FLAT}]}]
    events = await conversation.send(FLAT, {
        "primary_intent": "report_problem", "secondary_intents": ["step_feedback"], "device_relation": "current",
        "feedback": "not_solved", "feedback_quote": FLAT,
        "facts": [{"value": "Happens continuously on an open, flat floor", "quote": "This happens continuously on an open, flat floor"}],
    })
    assert next(e for e in events if e["type"] == "step_card")["step"]["step_id"] == "s2"
    state = await conversation.state()
    assert state["stage"] == "guide" and not state.get("escalate_reason")
    assert state["step_checks"]["qa_rv_0106"]["steps"]["s2"]["kept"] == "last_step"
    prompt = str(conversation.models["guide.step"].calls[-1])
    assert "s1 [reference]" in prompt


def test_app_report_with_error_code_is_never_a_product_question():
    """T22 复跑：带 7002 的 App 报错表单被判 product_question，走产品咨询不发卡。带码表单一律按故障。"""
    from app.conversation.interpret import TurnInterpretation, device_code_report

    meaning = TurnInterpretation(primary_intent="product_question", secondary_intents=["report_problem", "logistics_query"])
    fixed = device_code_report(meaning, T22)
    assert fixed.primary_intent == "report_problem" and fixed.secondary_intents == ["logistics_query"]
    question = TurnInterpretation(primary_intent="product_question")
    assert device_code_report(question, "How do I set a no-go zone on my X10 Pro Omni?").primary_intent == "product_question"
    # 接在模型输出与降级规则共用的纠正入口上
    from app.conversation.interpret import logistics_correction
    assert logistics_correction(meaning, T22).primary_intent == "report_problem"


async def test_error_code_from_an_earlier_turn_still_hits_the_official_guide(conversation):
    """首轮表单没进排障（意图被读成别的）；第二轮只报现象，错误码仍从本问题首轮原话取，精确命中 rv-0106。"""
    set_knowledge_adapter(QAHitAdapter("rv-0106"))
    conversation.models["guide.step"].script = [{"steps": [
        {"step_id": "s1", "status": "negated", "quote": "It has not been stuck at stairs or furniture"},
        {"step_id": "s2", "status": "satisfied", "quote": "This happens continuously on an open, flat floor"},
    ]}]
    await conversation.send(T22, {
        "primary_intent": "history_query", "device_relation": "current", "product_hints": ["X10 Pro Omni"],
        "facts": [{"value": "Wiel raakt de grond niet", "quote": "Wiel raakt de grond niet"}],
    })
    conversation.models["diagnose.synthesize"].script = []
    events = await conversation.send(FLAT, {
        "primary_intent": "report_problem", "device_relation": "current",
        "facts": [{"value": "Happens continuously on an open, flat floor", "quote": "This happens continuously on an open, flat floor"}],
    })
    card = next(e for e in events if e["type"] == "step_card")
    assert (card["step"]["plan_id"], card["step"]["step_id"]) == ("qa_rv_0106", "s2")
    state = await conversation.state()
    assert state["error_codes"] == ["7002"] and state["plans_ranked"][0]["source"] == "exact_code"
    assert not conversation.models["diagnose.synthesize"].calls


# ---- 客户自述做过的操作：卡照发，首卡说明（2026-10-12 T21；取代 10-10 的 done / partial 跳卡）----

T16 = ("Product Name: X10 Pro Omni\nProduct PN: T2351\nProduct SN:\nProblem Type: WARNING\n"
       "Problem Code: 2310-The dust box or filter is not in place.\nProblem Push: Please insert dustbin and filter.\n"
       "Problem Description: The dustbin or filter is not installed. It is fully installed and clean\nProblem Upload Images: []")


async def test_t16_installed_filter_is_still_checked_on_the_first_card(conversation):
    """T16：表单写「It is fully installed and clean」。首卡仍查滤网安装（s1）；s2 的条件「装好了」成立不跳 s1。"""
    set_knowledge_adapter(QAHitAdapter("rv-0056"))
    conversation.models["guide.step"].script = [{"steps": [
        {"step_id": "s2", "status": "satisfied", "quote": "It is fully installed and clean"},
    ]}]
    events = await conversation.send(T16, {
        "primary_intent": "report_problem", "device_relation": "current", "product_hints": ["X10 Pro Omni"],
        "facts": [{"value": "dustbin or filter not installed warning while fully installed",
                   "quote": "The dustbin or filter is not installed. It is fully installed and clean"}],
    })
    card = next(e for e in events if e["type"] == "step_card")
    assert (card["step"]["plan_id"], card["step"]["step_id"]) == ("qa_rv_0056", "s1")
    state = await conversation.state()
    assert not state["step_checks"]["qa_rv_0056"]["steps"]["s2"].get("skip")


async def test_form_with_only_the_device_push_does_not_call_the_check(conversation):
    """描述字段只是推送原文时没有客户自己的话，不调用核对，照常从首步发卡。"""
    set_knowledge_adapter(QAHitAdapter("rv-0056"))
    text = T16.replace("The dustbin or filter is not installed. It is fully installed and clean", "Please insert dustbin and filter.")
    events = await conversation.send(text, {
        "primary_intent": "report_problem", "device_relation": "current", "product_hints": ["X10 Pro Omni"],
        "facts": [{"value": "insert dustbin and filter", "quote": "Please insert dustbin and filter."}],
    })
    assert next(e for e in events if e["type"] == "step_card")["step"]["step_id"] == "s1"
    assert not conversation.models["guide.step"].calls


T37 = ("Productnaam: Omni E28\nProduct-PN: T2352\nProbleemtype: issue\nProbleemomschrijving: Ik krijg steeds de melding in de app "
       "“voeg water toe” als de dweil wordt gewassen. Terwijl de schoonwater tank nog vol is. De robot gaat vervolgens over op alleen vegen.\n\n"
       "Slang in tank is in orde. Rubbers zijn in orde. Hoe op te lossen?\nGeüploade afbeeldingen van het probleem: []")


async def test_t37_full_tank_still_gets_the_tank_card(conversation, l3_runtime):
    """T37：客户说水箱是满的。唯一一步（查水箱）照发，由客户在卡上确认；不再因自述直接耗尽计划进质保。"""
    set_knowledge_adapter(QAHitAdapter("rv-0021"))
    conversation.models["diagnose.synthesize"].script = [{"hypotheses": [{
        "plan_id": "qa_rv_0021", "confidence": 0.8, "evidence_ids": ["chunk-rv-0021"],
        "applicability": "supported", "supported_symptoms": ["add water warning while clean water tank is full"],
    }]}]
    events = await conversation.send(T37, {
        "primary_intent": "report_problem", "device_relation": "current", "product_hints": ["Omni E28"],
        "facts": [{"value": "add water warning while clean water tank is full",
                   "quote": "Terwijl de schoonwater tank nog vol is"}],
    })
    card = next(e for e in events if e["type"] == "step_card")["step"]
    assert (card["plan_id"], card["step_id"]) == ("qa_rv_0021", "s1")
    state = await conversation.state()
    assert "qa_rv_0021" not in (state.get("exhausted_plans") or [])


T36 = ("Productnaam: S1 Pro\nProduct-PN: T2080A\nProbleemtype: Probleem met het toestel\nProbleemomschrijving: Tijdens het "
       "stofzuigen maakt de stofzuiger enorm veel geluid. Alle filters en borstels zijn vervangen en alles is schoongemaakt maar "
       "het harde geluid blijft. Ik ben bang dat de stofzuigermotor kapot gaat.\nGeüploade afbeeldingen van het probleem: []")


async def test_t36_replaced_filters_are_quoted_once_and_every_card_is_sent(conversation, l3_runtime):
    """T36：客户已换全部滤网和刷子并清洁过。rv-0316 四项逐张发；首卡引用客户原话说明可能重叠，之后的卡不再重复。"""
    set_knowledge_adapter(QAHitAdapter("rv-0316"))
    conversation.models["diagnose.synthesize"].script = [{"hypotheses": [{
        "plan_id": "qa_rv_0316", "confidence": 0.8, "evidence_ids": ["chunk-rv-0316"],
        "applicability": "supported", "supported_symptoms": ["loud noise while vacuuming"],
    }]}]
    replaced = "Alle filters en borstels zijn vervangen en alles is schoongemaakt"
    events = await conversation.send(T36, {
        "primary_intent": "report_problem", "device_relation": "current", "product_hints": ["S1 Pro"],
        "facts": [{"value": "loud noise while vacuuming", "quote": "Tijdens het stofzuigen maakt de stofzuiger enorm veel geluid."},
                  {"kind": "action_taken", "value": "filters and brushes replaced, everything cleaned", "quote": replaced}],
    })
    first = next(e for e in events if e["type"] == "step_card")["step"]
    assert first["step_id"] == "s1"
    assert "You mentioned:" in first["context"] and replaced in first["context"]
    events = conversation.check(await act(conversation.client, conversation.sid, "step_feedback", {"feedback": "not_solved"}))
    second = next(e for e in events if e["type"] == "step_card")["step"]
    assert second["step_id"] == "s2" and "You mentioned:" not in (second.get("context") or "")
    assert not conversation.models["guide.step"].calls


T32 = ("Product Name: Omni E25\nProduct PN: T2353\nProblem Type: ERROR\nProblem Code: 3021-The sewage tank of the robot is not in place.\n"
       "Problem Description: The robot keeps saying remove and install the dirty water tank. I took out the water tank and reinstalled it. "
       "It stopped then started going off again. Went back and reinstalled it again seemed fine\nProblem Upload Images: []")


async def test_t32_reinstalling_the_tank_does_not_skip_the_tape_fix(conversation, l3_runtime):
    """T32：rv-0061 是整段客服邮件，拆成问候说明 + 胶带操作卡 + 交售后。胶带卡照发、带图示；
    客户自述的重装水箱原样引用。"""
    set_knowledge_adapter(QAHitAdapter("rv-0061"))
    conversation.models["guide.step"].script = [{"steps": [{"step_id": "s1b", "status": "unknown"}]}]
    events = await conversation.send(T32, {
        "primary_intent": "report_problem", "device_relation": "current", "product_hints": ["Omni E25"],
        "facts": [{"value": "dirty water tank not in place error", "quote": "The robot keeps saying remove and install the dirty water tank."},
                  {"kind": "action_taken", "value": "reinstalled the water tank", "quote": "I took out the water tank and reinstalled it."}],
    })
    card = next(e for e in events if e["type"] == "step_card")["step"]
    assert (card["plan_id"], card["step_id"]) == ("qa_rv_0061", "s1b")
    assert "tape" in card["instruction"] and card["media"]
    # 问候与原因作为说明附在卡上（官方原文）；客户自述原样引用
    assert "slight misalignment of the detection sensor" in card["context"]
    assert "I took out the water tank and reinstalled it." in card["context"]


async def test_angry_first_turn_that_only_gets_a_card_is_acknowledged_once(conversation, l3_runtime):
    """首轮直接出步骤卡、没有文字时，情绪致歉单独一条发在卡前；卡片正文不带致歉。"""
    set_knowledge_adapter(QAHitAdapter("rv-0056"))
    text = T16.replace("It is fully installed and clean", "It is fully installed and clean. I'm sick of this")
    events = await conversation.send(text, {
        "primary_intent": "report_problem", "device_relation": "current", "product_hints": ["X10 Pro Omni"],
        "emotion_level": "angry", "emotion_cues": ["I'm sick of this"],
        "facts": [{"value": "insert dustbin and filter", "quote": "Please insert dustbin and filter."}],
    })
    said = [e["delta"] for e in events if e["type"] == "message"]
    assert said.count("I'm sorry about the frustration.") == 1
    card = next(e for e in events if e["type"] == "step_card")["step"]
    assert "sorry" not in (card.get("context") or "").casefold()


def test_app_fault_form_without_code_is_not_a_product_question():
    """T43「Tipo de problema: Problema / El robot está desconectado」无错误码，4 次里 1 次判 product_question，
    答成一串无关报码就结束。App 反馈表单的问题类型不是咨询类就是在报故障；Ask Us / App usage issue 不约束（T31 / T34）。"""
    from app.conversation.interpret import TurnInterpretation, device_code_report
    from app.official.models import OfficialData

    tickets = {t.id: t.body for t in OfficialData().tickets}
    question = TurnInterpretation(primary_intent="product_question")
    for tid in ("T43", "T20", "T21", "T35"):
        assert device_code_report(question, tickets[tid]).primary_intent == "report_problem", tid
    for tid in ("T31", "T34"):
        assert device_code_report(question, tickets[tid]).primary_intent == "product_question", tid


async def test_t29_cleaned_tray_is_quoted_and_the_grille_card_is_sent(conversation, l3_runtime):
    """T29：客户说清洁盘洗过了。第 2 步「查格栅并清洗清洁盘」照发；首卡已引用过客户原话，第二张不再重复。"""
    set_knowledge_adapter(QAHitAdapter("rv-0254"))
    conversation.models["diagnose.synthesize"].script = [{"hypotheses": [{
        "plan_id": "qa_rv_0254", "confidence": 0.8, "evidence_ids": ["chunk-rv-0254"],
        "applicability": "supported", "supported_symptoms": ["water tray will not empty"],
    }]}]
    text = "Product PN: T2351\nProblem Description: Water tray will not empty. I have already cleaned it."
    events = await conversation.send(text, {
        "primary_intent": "report_problem", "device_relation": "current",
        "facts": [{"value": "water tray will not empty", "quote": "Water tray will not empty"},
                  {"kind": "action_taken", "value": "cleaned the water tray", "quote": "I have already cleaned it"}],
    })
    first = next(e for e in events if e["type"] == "step_card")["step"]
    assert first["step_id"] == "s1" and '"I have already cleaned it"' in first["context"]
    await act(conversation.client, conversation.sid, "step_feedback", {"feedback": "not_solved"})
    state = await conversation.state()
    card = state["pending_card"]["payload"]["step"]
    assert card["step_id"] == "s2" and "grille is blocked" in card["instruction"]
    assert "You mentioned:" not in (card.get("context") or "")


T21 = ("Nom du produit : X10 Pro Omni\nRéférence produit :T2351\nType de problème : Autre problème\n"
       "Description du problème : Bonjour depuis 2 semaines je réussi pas à faire fonctionne mon aspirateur il dit tjrs la même chose "
       "capteur laser bloquer . Nous avons nettoyé et repartit aspirateur a plusieurs reprise et le même message erreur revient toujours.\n"
       "Images téléchargées pour le problème : null")
T21_DONE = "Nous avons nettoyé et repartit aspirateur a plusieurs reprise"


async def test_t21_cleaned_and_restarted_is_quoted_and_all_radar_cards_are_sent(conversation, l3_runtime):
    """官方 63 单 T21（2026-10-12 复测）：客户说多次清洁并重启。rv-0113 三张卡照发、首卡说明客户已做的事；
    三张都反馈未解决后照常进质保判断。"""
    set_knowledge_adapter(QAHitAdapter("rv-0113"))
    conversation.models["diagnose.synthesize"].script = [{"hypotheses": [{
        "plan_id": "qa_rv_0113", "confidence": 0.8, "evidence_ids": ["chunk-rv-0113"],
        "applicability": "supported", "supported_symptoms": ["capteur laser bloquer"],
    }]}]
    events = await conversation.send(T21, {
        "primary_intent": "report_problem", "device_relation": "current", "product_hints": ["X10 Pro Omni"],
        "facts": [{"value": "capteur laser bloquer", "quote": "il dit tjrs la même chose capteur laser bloquer"},
                  {"kind": "action_taken", "value": "nettoyé et repartit aspirateur a plusieurs reprise", "quote": T21_DONE}],
    })
    cards = [next(e for e in events if e["type"] == "step_card")["step"]]
    assert f'"{T21_DONE}"' in cards[0]["context"] and "mark it as not solved" in cards[0]["context"]
    for _ in range(2):
        events = conversation.check(await act(conversation.client, conversation.sid, "step_feedback", {"feedback": "not_solved"}))
        cards.append(next(e for e in events if e["type"] == "step_card")["step"])
    assert [c["step_id"] for c in cards] == ["s1", "s2", "s3"]
    assert all("You mentioned:" not in (c.get("context") or "") for c in cards[1:])
    await act(conversation.client, conversation.sid, "step_feedback", {"feedback": "not_solved"})
    state = await conversation.state()
    assert state["next_action"]["reason"] == "guide_exhausted"
    assert not conversation.models["guide.step"].calls


async def test_t51_charged_pump_still_gets_the_fully_charged_card(conversation, l3_runtime):
    """官方 63 单 T51：「I've charged my pump」不等于已充满，bp-0111「Ensure the device is fully charged」照发。"""
    set_knowledge_adapter(QAHitAdapter("bp-0111"))
    conversation.models["diagnose.synthesize"].script = [{"hypotheses": [{
        "plan_id": "qa_bp_0111", "confidence": 0.8, "evidence_ids": ["chunk-bp-0111"],
        "applicability": "supported", "supported_symptoms": ["pump stops working intermittently"],
    }]}]
    events = await conversation.send("My S1 Pro pump stops working intermittently. I've charged my pump.", {
        "primary_intent": "report_problem", "device_relation": "current", "product_hints": ["S1 Pro breast pump"],
        "facts": [{"value": "pump stops working intermittently", "quote": "pump stops working intermittently"},
                  {"kind": "action_taken", "value": "charged the pump", "quote": "I've charged my pump"}],
    })
    cards = [next(e for e in events if e["type"] == "step_card")["step"]]
    events = conversation.check(await act(conversation.client, conversation.sid, "step_feedback", {"feedback": "not_solved"}))
    cards.append(next(e for e in events if e["type"] == "step_card")["step"])
    assert [c["step_id"] for c in cards] == ["s5", "s6"]
    assert "fully charged" in cards[1]["instruction"]


@pytest.mark.parametrize(("extra", "kept"), [
    ({}, True), ({"kind": "observation"}, True), ({"polarity": "negated"}, False), ({"polarity": "uncertain"}, False),
    ({"status": "superseded"}, False), ({"source_kind": "model"}, False), ({"source": "assistant"}, False), ({"kind": "symptom"}, False),
])
def test_only_active_affirmed_customer_actions_and_checks_are_quoted(extra, kept):
    fact = {"kind": "action_taken", "status": "active", "value": "cleaned the contacts", "quote": "I cleaned the contacts", **extra}
    state = {"active_issue_id": "i", "issues": {"i": {"facts": [fact]}, "old": {"facts": [
        {"kind": "action_taken", "status": "active", "value": "replaced the filter", "quote": "I replaced the filter"}]}}}
    assert reported_quotes(state) == (["I cleaned the contacts"] if kept else [])
