"""官方 63 单复测 P2：措辞不预设事实、材料请求与操作反馈分开、缺资料不是查询。

充电盒对象不被换成泵（T52 / B11）改由模型判断冲突，见 test_applicability_facts.py 与 test_postfix_decision_boundaries.py。

模型与知识库均为假；只检查服务端的确定性约束与客户可见文案。
"""

from datetime import date

import pytest

from app.backends import logistics
from app.conversation.interpret import TurnInterpretation
from app.conversation.reply import fallback_reply
from app.conversation.request_constraints import ground_additional_queries
from app.guide.steps import step_media
from app.official.models import OfficialData
from app.plans.qa import ACTION_WITH_MATERIAL_EXPECTED, EXPECTED, qa_plan_library
from app.sessions.l3 import HARDWARE_BASIS

LIB = qa_plan_library()


def test_t9_presale_with_pending_hold_does_not_promise_shipping():
    """T9：暂缓已交人工后仍说「It will be sent on the expected ship date」。"""
    order = next(o for o in OfficialData().orders if o.order_no == "Anker008")
    as_of = date(2026, 10, 10)
    assert "It will be sent" in logistics.sop_text(order, as_of)
    held = logistics.sop_text(order, as_of, change_pending=True)
    assert "will be sent" not in held and "original expected ship date" in held and "colleague" in held


def test_t14_hardware_basis_does_not_confirm_warranty():
    for text in HARDWARE_BASIS.values():
        assert "covered by warranty service" not in text and "depends on the check below" in text


def _complaint_state(**extra):
    return {"turn_decision": {"primary_intent": "complaint", "allowed_operations": True}, "input_id": "i1", **extra}


def test_t58_first_message_complaint_does_not_imply_earlier_service():
    """T58：首封只有一句抱怨，没有排障或案件，不说「we haven't solved this yet」。"""
    text = fallback_reply(_complaint_state())
    assert "haven't solved" not in text and "what it is doing" in text


def test_complaint_after_tried_steps_keeps_the_unresolved_wording():
    attempts = [{"plan_id": "p", "step_id": "s1", "card_id": "c1", "kind": "action", "feedback": "not_solved"}]
    assert fallback_reply(_complaint_state(step_attempts=attempts)).startswith("I'm sorry we haven't solved this yet.")


def test_t40_action_with_material_request_says_they_are_separate():
    """操作卡里顺带要照片 / 视频（rv-0272「若松动请拍照」），卡上说明两件事分开，点「未解决」不等于交了材料。"""
    assert LIB.get("qa_rv_0272").steps[0].expected_result == ACTION_WITH_MATERIAL_EXPECTED
    assert LIB.get("qa_rv_0147").steps[0].expected_result == EXPECTED


def test_t40_article_check_is_its_own_card_with_the_link():
    """官方 63 单 T40（2026-10-12 复测）：rv-0073 只出一张带外链的卡，一个「未解决」就算官方排查走完，
    文章里的检查做没做无从知道。审核拆成装瓶 → 是否已按文章检查（还没看可重发）→ 照片 / 视频，链接挂在文章那张。"""
    steps = LIB.get("qa_rv_0073").steps
    assert [(s.step_id, s.kind) for s in steps] == [("s1", "action"), ("s1b", "question"), ("s1c", "material_request")]
    assert steps[0].expected_result == EXPECTED
    assert steps[1].retry_options == ["I haven't tried them yet"]
    assert step_media("qa_rv_0073", "s1") == [] and step_media("qa_rv_0073", "s1c") == []
    assert step_media("qa_rv_0073", "s1b") == [
        {"url": "https://support.eufy.com/s/article/How-do-I-use-eufy-cleaning-solution-with-my-S1-Pro", "kind": "link"}]


@pytest.mark.parametrize("quote,kept", [
    ("I don't have my receipt right now.", False),            # B17
    ("I don't have my order number, can you find it?", True),  # 真在问
    ("What did I order?", True),
])
def test_b17_saying_material_is_missing_is_not_an_order_query(quote, kept):
    text = "Do not submit any replacement request yet. " + quote
    meaning = TurnInterpretation(
        primary_intent="replacement_request", secondary_intents=["order_query"],
        request_quotes={"replacement_request": "Do not submit any replacement request yet.", "order_query": quote},
        answer_request={"fields": ["order_no", "sku"], "quote": quote},
    )
    result, rejected = ground_additional_queries(meaning, text)
    assert ("order_query" in result.secondary_intents) is kept
    if not kept:
        assert rejected == [{"intent": "order_query", "reason": "lacks_material_not_query"}]
