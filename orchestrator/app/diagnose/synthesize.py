"""diagnose.synthesize（03 §1.4 步骤 3；09 §3.2）：强推理档、tag=internal，输出最多 3 个假设。

每个假设必须引用当前允许集合内的 plan_id（枚举由 PlanLibrary.allowed_for 决定）与状态里已有的 evidence_ids；
不在枚举内的 plan_id 丢弃并记录，无效 evidence_id 剔除。无证据或判断不可用时不产生可执行方案。
"""

from __future__ import annotations

import logging
from typing import Annotated, Any, Literal, get_args

from langchain_core.messages import convert_to_messages
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, ValidationError, create_model

from app.context.budget import context_input_budget, measure_input
from app.context.builder import ContextBudgetExceeded
from app.context.runtime import prepare_messages
from app.conversation.quotes import normalize, quoted
from app.diagnose.decision import SWITCH_CONFIDENCE, concrete
from app.guide.fact_check import user_corpus
from app.knowledge.context import render_evidence
from app.models.queue import CapacityExceeded
from app.models.router import ModelInvokeError, ModelRouter
from app.plans.models import Plan
from app.prompts import compose_system_prompt, wrap_data

log = logging.getLogger("diagnose.synthesize")


def _clip(limit: int):
    """自由说明字段超长就截断，不让整批假设作废（2026-10-10 B25：deepseek 中文 rationale 超 80 字，两次重试全部 schema_error，
    第一轮直接 R5 转人工）。上限仍写在 schema 里提示模型；plan_id / applicability 等判定字段照旧严格校验。"""
    return BeforeValidator(lambda v: v[:limit] if isinstance(v, str) else v)


Rationale = Annotated[str, _clip(80)]
# 追问与客户症状的关系（T61 2026-10-13：两个时机冲突候选丢弃后，只覆盖「清扫不记录」的 0.3 候选拿「地图准不准」
# 去追问）。表外的值当作没给，回到置信度门槛，不让整次选方案因一个字段作废
QuestionRelationName = Literal["narrows", "different_problem"]
QuestionRelation = Annotated[
    QuestionRelationName | None, BeforeValidator(lambda v: v if v in get_args(QuestionRelationName) else None)]


class Conflict(BaseModel):
    """候选讲的问题与客户说的问题不是同一件事。原先是三套英文词表（部件名、提前 / 没启动、充电句式），换个说法、
    换种语言就漏（2026-10-13 复评：「won't take a charge」「se descarga」「laadt niet op」）。现在由模型判断并
    逐字引两边原话；服务端只核对引文确实出自客户原话与候选原文，不再用词表猜意思。"""

    model_config = ConfigDict(extra="forbid")
    kind: Literal["object", "direction", "not_reported"] = Field(
        description="object = 候选针对的部件 / 受电方与客户说的不同（充电盒自身不进电 vs 盒给泵充电）；"
                    "direction = 时机或结果相反（提前启动 vs 无法启动）；"
                    "not_reported = 候选讲的现象客户根本没说过（客户只说充过电仍开不了机，候选讲充不进电），"
                    "或候选只是用法 / 规格说明而客户报的是故障（客户说充电盒充不进电，候选讲充满要多久）")
    customer_quote: str | None = Field(
        default=None, max_length=200,
        description="object / direction：从 customer_original 逐字摘录客户描述该问题的那一句；not_reported 留空")
    candidate_quote: str = Field(max_length=200, description="从候选标题或检索片段逐字摘录它讲的对象 / 时机 / 现象")
    ask_about: str | None = Field(
        default=None, max_length=80,
        description="object：客户说的那个部件或对象（如 charging case），用来追问它自身的状态；其余留空")


class KnownPrecondition(BaseModel):
    """needs_confirmation 的前提，客户其实已经说过（原先按词干重叠猜，「Mop not dried」对「havent needed any mop drying」
    要靠去词尾规则对上，换种说法就漏）。由模型判断并逐字引客户原话，服务端只核对引文出处。"""

    model_config = ConfigDict(extra="forbid")
    answer: Literal["yes", "no"] = Field(description="yes = 客户原话说明前提成立；no = 客户原话说明前提不成立 / 没做过")
    customer_quote: str = Field(max_length=200, description="从 customer_original 或 answered_preconditions 的回答逐字摘录")


class Hypothesis(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plan_id: str = Field(description="只能是允许列表中的计划 id")
    confidence: float = Field(ge=0, le=1)
    applicability: Literal["supported", "needs_confirmation", "not_applicable"] = Field(
        description="证据是否支持用户的实际现象和必要条件；同型号或关键词接近不算支持"
    )
    supported_symptoms: list[str] = Field(description="逐字选择本次有效症状中该方案能解释的项目，未覆盖的不填")
    evidence_ids: list[str] = Field(
        default_factory=list, description="支撑该假设的证据 id，取自提供的片段"
    )
    rationale: Rationale = Field(default="", max_length=80)
    clarification_question: str | None = Field(
        default=None, max_length=300,
        description="needs_confirmation 时用一句英文询问文档要求但尚未知的入口前提；只确认事实，不要求执行操作",
    )
    matched_section: str | None = Field(default=None, max_length=120, description="候选列出多个故障小节时，用户现象对应的小节标题逐字；不能确定留空")
    missing_fact: str | None = Field(default=None, max_length=120, description="needs_confirmation 时，clarification_question 要确认的那个前提，摘自候选原文")
    question_targets: list[str] = Field(default_factory=list, description="needs_confirmation 时，这个追问在区分哪条有效症状（逐字）")
    question_relation: QuestionRelation = Field(
        default=None, description="needs_confirmation 时：narrows = 前提是该症状的一种具体表现或发生条件；different_problem = 文档讲的是另一个问题")
    conflict: Conflict | None = Field(default=None, description="候选与客户的问题不是同一件事时填写；同一件事留空")
    plan_step: str | None = Field(
        default=None, max_length=20,
        description="needs_confirmation 时：要确认的前提正是计划第一步本身要检查或要问的事，填该步 step_id；否则留空")
    precondition_known: KnownPrecondition | None = Field(
        default=None, description="needs_confirmation 时：客户已经说过这个前提成立或不成立就填，并逐字引原话；没说过留空")


class PlansRanked(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hypotheses: list[Hypothesis] = Field(default_factory=list, max_length=5)


def _schema_with_enum(plan_ids: list[str]) -> type[BaseModel]:
    """把 plan_id 收窄为枚举（09 §3.2）。"""
    if not plan_ids:
        return PlansRanked
    lit = Literal[tuple(plan_ids)]  # type: ignore[valid-type]
    hyp = create_model(
        "HypothesisEnum",
        __config__=ConfigDict(extra="forbid"),
        plan_id=(lit, Field(description="只能是允许列表中的计划 id")),
        confidence=(float, Field(ge=0, le=1)),
        applicability=(Literal["supported", "needs_confirmation", "not_applicable"], Field()),
        supported_symptoms=(list[str], Field()),
        evidence_ids=(list[str], Field(default_factory=list)),
        rationale=(Rationale, Field(default="", max_length=80)),
        clarification_question=(str | None, Field(default=None, max_length=300)),
        matched_section=(str | None, Field(default=None, max_length=120)),
        missing_fact=(str | None, Field(default=None, max_length=120)),
        question_targets=(list[str], Field(default_factory=list)),
        question_relation=(QuestionRelation, Field(default=None)),
        conflict=(Conflict | None, Field(default=None)),
        plan_step=(str | None, Field(default=None, max_length=20)),
        precondition_known=(KnownPrecondition | None, Field(default=None)),
    )
    return create_model(
        "PlansRankedEnum",
        __config__=ConfigDict(extra="forbid"),
        hypotheses=(list[hyp], Field(default_factory=list, max_length=5)),
    )  # type: ignore[valid-type]


def unrelated_question(h: dict[str, Any], symptoms: set[str]) -> bool:
    """追问不是在细分客户的某条症状：模型自报 different_problem，或说 narrows 却指不出逐字的有效症状。
    没给关系（旧回放、模型漏填）时不判，交给置信度门槛（T61 两次失败都是 0.2–0.3 的候选；T62 对同一条 rv-0542 的
    「是否反复清扫」追问是在细分「不走直线」，0.35 也合理，只靠门槛分不开）。"""
    relation = h.get("question_relation")
    if relation is None:
        return False
    if relation == "different_problem":
        return True
    targets = [t for t in h.get("question_targets") or [] if t]
    return not targets or not all(t in symptoms for t in targets)


def plan_step_of(plan: Plan, step_id: str | None) -> str | None:
    """模型说要确认的前提就是计划第一张卡本身（T29 rv-0254 第 1 步查门扣、T57 bp-0164 首卡问 App 版本）：由这张卡
    按官方顺序查，不另起追问。只认第一张会发出的卡（跳过说明段）：前提落在后面某步时（2026-10-13 复测 T52：bp-0067
    s3「确认充电盒自身有电」），前面的卡已默认它成立，照样先问。原先按「check / verify」句首与词干比对来认。"""
    first = next((s for s in plan.steps if s.kind != "statement"), None)
    if first is None or first.step_id != step_id or first.kind not in {"action", "question"} or first.condition:
        return None
    return first.step_id


def stated(quote: str | None, said: list[str]) -> bool:
    """引文确实是客户原话的片段（容忍空白、引号形态与边缘一个词的错字，见 quoted）。"""
    return bool(quote) and any(quoted(quote, text) for text in said)


def asked_before(h: dict[str, Any], answered: list[dict[str, Any]]) -> bool:
    """同一候选的同一句追问或同一前提原话已经问过、客户答过。只比相等，不比词义（原先比词干重叠）。"""
    def same(a: str | None, b: str | None) -> bool:
        return bool(a and b) and normalize(a).casefold() == normalize(b).casefold()

    return any(item.get("plan_id") == h.get("plan_id")
               and (same(h.get("clarification_question"), item.get("question")) or same(h.get("missing_fact"), item.get("missing_fact")))
               for item in answered)


CLARIFY_TEMPLATES = {
    "polarity_uncertain": 'You mentioned "{quote}". Which side or part has the problem, and what exactly is it doing?',
    "object_conflict": "Is the problem with the {subject} itself (for example its own charging light or power input), or with how it works together with other parts?",
}


def filter_hypotheses(
    raw: list[dict[str, Any]], *, allowed: dict[str, Plan], evidence_ids: set[str], symptoms: set[str],
    facts: list[dict[str, Any]] = (), error_codes: list[str] = (), answered: list[dict[str, Any]] = (),
    said: list[str] = (), max_n: int,
) -> tuple[list[dict[str, Any]], list[str], list[dict[str, Any]]]:
    """模型的假设先过服务端核对，再决定可执行 / 待澄清 / 丢弃。

    返回 (kept, dropped, clarifications)。意思由模型判断（conflict / plan_step / precondition_known），服务端只核对
    模型给的东西真实存在：计划 id、证据 id、错误码、逐字引文出自 said（本问题的客户原话）、步骤 id 属于该计划。
    不信模型对 applicability 的自评：同型号、关键词相近都不等于适用（T50 / T52 / T61）。
    """
    kept: list[dict[str, Any]] = []
    dropped: list[str] = []
    clarifications: list[dict[str, Any]] = []
    seen: set[str] = set()
    by_value = {f.get("value"): f for f in facts if f.get("kind") == "symptom" and f.get("status", "active") == "active"}
    codes = {c.upper() for c in error_codes}
    # 唯一的「现象」只是哪部分正常（T50「the left one does work」）：模型不把它列进 supported_symptoms 时，
    # 会转而用 needs_confirmation 自拟追问，替客户假定另一侧的故障（T50 右侧吸力、B10 反转成左侧没吸力）。
    # 没有任何确定现象与错误码时，每个候选都只能先问哪里有问题。理解阶段把这句记成观察而非现象时同样算
    #（2026-10-13 deepseek-v4-pro：observation「the left one does work」uncertain，选方案以 0.9 判可执行发了 5 张卡）
    stated_facts = [f for f in facts if f.get("kind") in {"symptom", "observation"} and f.get("status", "active") == "active"
                    and f.get("source_kind", "user_report") == "user_report"]
    only_uncertain = None if codes or not stated_facts or any(f.get("polarity", "affirmed") != "uncertain" for f in stated_facts) \
        else stated_facts[0]

    def clarify(h, reason, question):
        ev = [e for e in (h.get("evidence_ids") or []) if e in evidence_ids]
        if not ev or not question:
            return
        if codes and any(code.casefold() in question.casefold() for code in codes):
            return  # 不问用户已经告诉我们的错误码（T18）
        if float(h.get("confidence", 0) or 0) < SWITCH_CONFIDENCE:
            # 低于换方案门槛的候选，即使客户答「是」也不会被选中执行：问了只是把一个不相干的条目拿来盘问客户
            #（T61 本轮复测：两个时机冲突候选丢弃后，0.25 的「重复清扫」条目问「历史里有没有重复路径」）
            return
        clarifications.append({"plan_id": h["plan_id"], "question": question.strip(), "evidence_ids": ev,
                               "confidence": float(h.get("confidence", 0)), "reason": reason,
                               **({"missing_fact": h["missing_fact"]} if h.get("missing_fact") else {})})

    for h in raw:
        pid = h.get("plan_id")
        if pid not in allowed:
            dropped.append(f"plan_id:{pid}")
            continue
        if pid in seen:
            dropped.append(f"duplicate:{pid}")
            continue
        seen.add(pid)
        plan = allowed[pid]
        if codes and plan.symptom_codes and not codes.intersection(c.upper() for c in plan.symptom_codes):
            dropped.append(f"code_mismatch:{pid}")  # 同型号异码不是候选，也不值得追问
            continue
        covered = list(dict.fromkeys(s for s in h.get("supported_symptoms", []) if s in symptoms))
        covered_facts = [by_value[s] for s in covered if s in by_value]
        if covered_facts and len(covered_facts) == len(covered) and not any(concrete(f) for f in covered_facts) and not codes:
            # 覆盖的「现象」全是客户的愿望（T60「I just want my hoover to clean」）或评价（T58「cameras suck」）：
            # 不是可判定的故障，不能据此选方案，交给检索落空的追问（missing_for_retrieval 同样不算作现象）
            dropped.append(f"not_concrete:{pid}")
            continue
        uncertain = next((f for f in covered_facts if f.get("polarity") == "uncertain"), None) or only_uncertain
        if uncertain:
            dropped.append(f"polarity_uncertain:{pid}")
            clarify(h, "polarity_uncertain", CLARIFY_TEMPLATES["polarity_uncertain"].format(quote=uncertain.get("quote") or uncertain["value"]))
            continue
        conflict = h.get("conflict") or None
        if conflict:
            # 模型判定候选讲的不是客户这件事（对象不同 / 方向相反 / 客户没说过）：否决只需模型自己认定，直接丢弃；
            # 追问客户的部件则要引文核对出自原话，模型不能替客户添对象（T52 盒子自身不进电对 bp-0039 盒给泵充电、
            # T61 提前启动对 rv-0551 无法启动、T53「充过电仍开不了机」对 bp-0127 充不进电）
            kind = conflict.get("kind") or "object"
            dropped.append(f"conflict_{kind}:{pid}")
            subject = conflict.get("ask_about")
            quote = conflict.get("customer_quote")
            if kind == "object" and subject and stated(quote, said) and normalize(subject).casefold() in normalize(quote).casefold():
                clarify(h, "object_conflict", CLARIFY_TEMPLATES["object_conflict"].format(subject=subject))
            continue
        if h.get("applicability") != "supported":
            step_id = plan_step_of(plan, h.get("plan_step")) if h.get("applicability") == "needs_confirmation" else None
            known = h.get("precondition_known") or {}
            heard = [*said, *(str(a.get("answer") or "") for a in answered)]
            if step_id and covered:
                # 前提是计划自己的某一步：按 supported 继续，由步骤卡按官方顺序查（客户已说过的由 guide 的事实核对处理）；
                # 没有覆盖任何现象时仍按原路追问，不因此丢掉候选
                dropped.append(f"precondition_in_plan:{pid}:{step_id}")
                h = {**h, "applicability": "supported"}
            elif h.get("applicability") == "needs_confirmation":
                if known.get("answer") == "no" and stated(known.get("customer_quote"), heard):
                    dropped.append(f"precondition_negated:{pid}")  # 客户原话已否定前提：不适用，也不再问（T41）
                    continue
                if known.get("answer") == "yes" and stated(known.get("customer_quote"), heard):
                    dropped.append(f"precondition_known:{pid}")  # 客户原话已说明前提成立：按 supported 继续
                    h = {**h, "applicability": "supported", "rationale": f"前提已知：{known['customer_quote']}"[:80]}
                elif asked_before(h, answered):
                    # 同一候选的同一问题客户已经答过（dbc144：答了 yes，同一句又问一遍）：回答已作为 answered_preconditions
                    # 交给模型，模型看了回答仍确认不了前提，这条候选就不适用，不再问第二次。换一种问法可以（答「不确定」后），
                    # 追问总次数由澄清计数兜底
                    dropped.append(f"precondition_unconfirmed:{pid}")
                    continue
                elif unrelated_question(h, symptoms):
                    dropped.append(f"clarify_unrelated:{pid}")
                    continue
                else:
                    dropped.append(f"not_supported:{pid}")
                    clarify(h, "needs_confirmation", h.get("clarification_question") or "")
                    continue
            else:
                dropped.append(f"not_supported:{pid}")
                continue
        if not covered:
            dropped.append(f"no_supported_symptom:{pid}")
            continue
        ev = [e for e in (h.get("evidence_ids") or []) if e in evidence_ids]
        bad = [e for e in (h.get("evidence_ids") or []) if e not in evidence_ids]
        if bad:
            dropped.append(f"evidence:{pid}:{','.join(bad)}")
        if not ev:
            dropped.append(f"no_evidence:{pid}")
            continue
        # 多故障小节的候选：模型指出的小节必须逐字等于计划首问的某个选项，服务端才替用户选分支（T53）
        section = h.get("matched_section")
        first = plan.first_step()
        if section and not (first.kind == "question" and section in first.branches):
            dropped.append(f"section_unverified:{pid}")
            section = None
        kept.append(
            {
                "plan_id": pid,
                "version": plan.version,
                "confidence": round(float(h.get("confidence", 0)), 3),
                "evidence_ids": ev,
                "rationale": (h.get("rationale") or "")[:80],
                "supported_symptoms": covered,
                "source": "synthesize",
                **({"matched_section": section} if section else {}),
            }
        )
    kept.sort(key=lambda x: -x["confidence"])
    clarifications.sort(key=lambda item: -item["confidence"])
    return kept[:max_n], dropped, clarifications


INSTRUCTION = (
    "根据 <data> 段中的用户描述、图片观察与检索片段，从「允许的排障计划」里选出最可能的假设，最多 {n} 个：\n"
    "- plan_id 只能取允许列表中的值；每个假设至少引用一条支撑它的 evidence_id（只能用给出的 id）；\n"
    "- confidence 为 0–1；rationale 不超过 40 字；不要编造检索片段里没有的现象或原因；\n"
    "- 标为「未解决工单」的片段只说明该次服务未确认解决，不能作为方案依据，只可用作反证；\n"
    "- 先判断 applicability：supported 必须是同一现象且必要前提已成立；前提未知用 needs_confirmation；现象矛盾用 not_applicable。\n"
    "- 入口前提是用户观察到的现象/操作条件，不是尚待检查的故障原因。步骤本来用于检查某个可能原因时，不要求用户先证明该原因。\n"
    "- needs_confirmation 必须填写 clarification_question：只问一个缺失的入口前提，用英文，不给操作指令；answered_preconditions 里客户已经回答的前提按回答判断 supported 或 not_applicable，不再问。\n"
    "- 文档有错误码而用户没有提供错误码，不是拒绝依据；用户现象和文档适用条件一致仍可 supported。\n"
    "- supported_symptoms 只能逐字选择给定的有效症状；不能把共同主题当作覆盖，不能声称一个方案解决所有并列问题。\n"
    "- action_taken 是用户已经做过的操作，只是背景：自述没有卡片反馈精确，候选与这些动作重叠不是拒绝依据，仍按现象判断。\n"
    "- 候选讲的不是客户这件事时填 conflict，不要因为共享关键词就当成同一件事：\n"
    "  object：针对的部件或受电方不同（客户说充电盒自身充不进电，候选讲盒给泵充电）；ask_about 填客户说的那个部件，"
    "customer_quote 从 customer_original 逐字摘录客户那句话。"
    "客户说的问题有先后因果（A 坏了所以 B 也不行，如「充电盒充不进电，所以泵也充不了」）时，只处理后果 B 的候选也是 object："
    "源头 A 没解决，按 B 排查无效；ask_about 填源头 A 的部件，customer_quote 摘客户说 A 的那句；\n"
    "  direction：时机或结果相反（客户说提前启动，候选讲无法启动；始终离线与偶发离线）；\n"
    "  not_reported：候选讲的现象客户根本没说过（客户只说充过电仍开不了机，候选讲充不进电；客户只说左边能用）；"
    "候选只是产品用法、规格或说明（充满要多久、怎么清洁、有没有某功能），客户报的却是故障，也填 not_reported——"
    "只有客户问的正是这条说明时才可用。\n"
    "  只是同一类部件的不同叫法（water tray 与 dirty water tank）、客户说整机而候选讲其部件，不算冲突。\n"
    "- 候选标注了「小节」时，用户现象明确属于其中一个小节就把该小节标题逐字填进 matched_section；不确定留空，不要猜。\n"
    "- needs_confirmation 时同时填 missing_fact：要确认的那个前提在候选原文里的原话（如 perform a new mopping task）。\n"
    "- needs_confirmation 时，前提正是计划第一步本身要检查或要问的事（第一步就是查门扣、第一张问题卡就是问 App 版本），"
    "填 plan_step 为该步 step_id，不要另发追问；前提在后面某一步时不填（前面的步骤已默认它成立，要先问）。\n"
    "- needs_confirmation 时，客户原话已经说过前提成立或不成立（「我们没跑过拖地」否定了「拖地后报错」），填 precondition_known："
    "answer 填 yes / no，customer_quote 从 customer_original 或 answered_preconditions 的回答逐字摘录。\n"
    "- needs_confirmation 时还要填 question_targets（这个追问在区分哪条有效症状，逐字）与 question_relation："
    "前提是该症状的一种具体表现或发生条件（「不走直线」→ 是否反复清扫同一区域）填 narrows；"
    "文档讲的是另一个问题（「清扫不记录」→ 地图是否准确）填 different_problem，这种不要发追问。\n"
    "- 没有任何计划能解释时输出空列表。只输出 JSON。"
)

def active_facts(state: dict[str, Any]) -> list[dict[str, Any]]:
    issue = (state.get("issues") or {}).get(state.get("active_issue_id"), {})
    return [f for f in issue.get("facts", []) if f.get("status") == "active"]


def active_symptoms(state: dict[str, Any], observations: list[str]) -> list[str]:
    """模型可逐字选取的有效症状：现象事实 + 图片观察。一条现象事实都没抽到时（T40 本轮复测主轮：长邮件整段漏抽，
    所有候选都因「没有覆盖任何有效症状」被丢弃，去问一个不相干条目的前提），用检索时的现象原文兜底，
    即客户这封消息本身；它就是 described() 判定「已描述现象」、进入检索的依据。
    抽到过现象事实（哪怕是否定或愿望，T60「I just want my hoover to clean」）就不兜底：那是模型读过后的判断，
    原文兜底会把愿望重新当成现象。原文本身是愿望或评价时也不兜底。
    同样没有现象事实时，客户自己说的肯定观察也可选：模型对「看到的状态」与「故障现象」的划分不稳定（2026-10-13
    deepseek-v4-pro 把 T40「floor detergent level has barely moved」记成 observation，三个对症候选全被丢弃）。"""
    symptoms = [str(s) for s in [*(state.get("symptoms") or []), *observations] if str(s).strip()]
    query = str(state.get("query") or "").strip()
    no_symptom_fact = not state.get("symptoms") and not any(f.get("kind") == "symptom" for f in active_facts(state))
    if no_symptom_fact:
        symptoms += [str(f.get("value")) for f in active_facts(state)
                     if f.get("kind") == "observation" and f.get("polarity", "affirmed") == "affirmed"
                     and f.get("source_kind", "user_report") == "user_report" and str(f.get("value") or "").strip()]
    if no_symptom_fact and query and concrete({"quote": query}):
        symptoms.append(query)
    return list(dict.fromkeys(symptoms))


def synthesis_messages(state, allowed, evidence, observations, max_hypotheses) -> list[tuple[str, str]]:
    """只构造本次可见候选；完整会话来源与预算由 prepare_messages 统一加入。"""
    plans_text = "\n".join(
        f"- {p.plan_id}：{p.fault}（步骤：{'；'.join(f'{s.step_id} {s.title}' for s in p.steps if s.kind in {'action', 'question'})}）"
        + (f"（小节：{' / '.join(p.steps[0].options)}）" if p.steps[0].kind == "question" and p.steps[0].branches else "")
        for p in allowed
    )
    ev_text = "\n".join(render_evidence(e) for e in evidence)
    obs_text = "\n".join(observations) if observations else "（无图片观察）"
    symptoms = active_symptoms(state, observations)
    facts = active_facts(state)
    error_codes = list(state.get("error_codes") or [])
    facts_text = "\n".join(
        f"- kind={f.get('kind')} subject={f.get('subject') or '-'} polarity={f.get('polarity', 'affirmed')} "
        f"timing={f.get('timing') or '-'} value={f.get('value')}"
        for f in facts
    ) or "（无）"
    human = (
        INSTRUCTION.format(n=max_hypotheses)
        + f"\n允许的排障计划：\n{plans_text}\n"
        + "有效症状（supported_symptoms 只能逐字选取）：\n" + wrap_data("\n".join(symptoms), kind="active_symptoms") + "\n"
        + wrap_data(facts_text, kind="structured_facts") + "\n"
        + wrap_data(", ".join(error_codes) or "（无）", kind="error_codes") + "\n"
        + wrap_data(
            " ".join(
                [str(s) for s in state.get("symptoms") or []]
            ),
            kind="user_message",
        )
        + "\n"
        # 引文字段（conflict / precondition_known 的 customer_quote）只能从这里逐字摘录，服务端按同一份原话核对
        + wrap_data("\n---\n".join(user_corpus(state)) or "（无）", kind="customer_original")
        + "\n"
        + wrap_data(obs_text, kind="image_observations")
        + "\n"
        + wrap_data(str(state.get("observations") or []), kind="confirmed_observations")
        + "\n"
        + wrap_data(
            str({"question": (state.get("diagnose_outcome") or {}).get("question"),
                 "answer": state.get("text")}), kind="current_turn",
        )
        + "\n"
        + wrap_data("\n".join(f"- {a.get('plan_id')}: Q: {a.get('question')} A: {a.get('answer')}"
                              for a in state.get("precondition_answers") or []) or "（无）", kind="answered_preconditions")
        + "\n"
        + wrap_data(ev_text, kind="retrieved_snippets")
    )
    return [
        (
            "system",
            compose_system_prompt(
                (state.get("emotion") or {}).get("strategy", "normal"),
                {
                    "stage": "diagnose",
                    "product": (state.get("product_confirmed") or {}).get("name"),
                    "symptoms": state.get("symptoms"),
                },
            ),
        ),
        ("human", human),
    ]


async def synthesize(
    router: ModelRouter | None,
    *,
    state: dict[str, Any],
    allowed: list[Plan],
    evidence: list[dict[str, Any]],
    observations: list[str],
    budget_ms: int,
    max_hypotheses: int,
    session_id: str | None,
    lane: str,
) -> dict[str, Any]:
    """先检查完整消息预算；候选和引用白名单仅覆盖模型本次实际可见的证据。"""
    skipped = {"task": "diagnose.synthesize", "model_used": "skipped", "lane": lane, "attempts": 0}
    if not allowed or not evidence or router is None:
        reason = "no_allowed_plans" if not allowed else "no_evidence" if not evidence else "router_unavailable"
        return {"plans_ranked": [], "dropped": [], "model_trace": skipped, "degraded": reason}
    visible_plans, visible_evidence = list(allowed), list(evidence)
    budget_dropped = []
    while True:
        try:
            messages = prepare_messages(
                "diagnose.synthesize",
                synthesis_messages(state, visible_plans, visible_evidence, observations, max_hypotheses),
                PlansRanked,
            )
            required = measure_input(convert_to_messages(list(messages)))["text_tokens"]
            limit = context_input_budget("diagnose.synthesize", PlansRanked)
            if required > limit:
                raise ContextBudgetExceeded("synthesis_input_exceeds_budget", required, limit)
            break
        except ContextBudgetExceeded:
            # 每轮删一条低优先级证据，最多 len(evidence)-1 次；必要事实和原始证据不改写。
            if len(visible_evidence) <= 1:
                return {"plans_ranked": [], "dropped": budget_dropped,
                        "model_trace": skipped, "degraded": "context_budget_exceeded"}
            removed = visible_evidence.pop()
            budget_dropped.append(f"budget:evidence:{removed['evidence_id']}")
            doc = removed.get("doc_id")
            if doc and not any(item.get("doc_id") == doc for item in visible_evidence):
                remaining = []
                for plan in visible_plans:
                    if any(step.evidence_key.partition("#")[0] == doc for step in plan.steps):
                        budget_dropped.append(f"budget:plan:{plan.plan_id}")
                    else:
                        remaining.append(plan)
                visible_plans = remaining
            if not visible_plans:
                return {"plans_ranked": [], "dropped": budget_dropped,
                        "model_trace": skipped, "degraded": "context_budget_exceeded"}
    # 宽松解析再按枚举过滤：单个越界 plan_id 只丢弃该假设，不让整批作废（枚举写在提示里；
    # _schema_with_enum 供原生 json_schema 模型或票 33 严格模式选用）
    try:
        res = await router.invoke(
            "diagnose.synthesize",
            messages,
            PlansRanked,
            budget_ms=budget_ms,
            session_id=session_id,
            lane=lane,
        )
        raw = [
            h.model_dump() if isinstance(h, BaseModel) else dict(h) for h in res.parsed.hypotheses
        ]
        trace = {
            "task": "diagnose.synthesize",
            "model_used": res.model_used,
            "lane": res.lane,
            "attempts": max(1, sum(1 for a in res.attempts if a.outcome != "skipped")),
        }
    except (ModelInvokeError, CapacityExceeded, ValidationError) as exc:
        attempts = [f"{a.alias}:{a.outcome}:{a.error}" for a in getattr(exc, "attempts", [])]
        log.warning(
            "synthesize degraded session=%s: %s attempts=%s", session_id, str(exc)[:200], attempts
        )
        return {
            "plans_ranked": [],
            "dropped": budget_dropped,
            "attempts": attempts,
            "model_trace": {
                "task": "diagnose.synthesize",
                "model_used": "skipped",
                "lane": lane,
                "attempts": 1,
            },
            "degraded": f"model:{type(exc).__name__}",
        }
    # 前提未知不能成为可执行计划，但有官方证据的候选可以发起事实澄清。
    kept, dropped, clarifications = filter_hypotheses(
        raw,
        allowed={p.plan_id: p for p in visible_plans},
        evidence_ids={e["evidence_id"] for e in visible_evidence},
        symptoms=set(active_symptoms(state, observations)),
        facts=active_facts(state),
        error_codes=list(state.get("error_codes") or []),
        answered=list(state.get("precondition_answers") or []),
        said=user_corpus(state),
        max_n=max_hypotheses,
    )
    dropped = budget_dropped + dropped
    for d in dropped:
        log.info(
            "synthesize dropped hypothesis session=%s %s",
            session_id,
            d,
            extra={"event": "hypothesis_dropped", "detail": d, "session_id": session_id},
        )
    if not kept:
        return {
            "plans_ranked": [],
            "dropped": dropped,
            "model_trace": trace,
            "degraded": "no_applicable_plan",
            "clarifications": clarifications[:1],
        }
    # 待确认的候选随可执行方案一起带上：可执行方案走不下去（全被跳过、原文缺后续说明）时，按它的前提追问，
    # 而不是直接交人工（T40：断链的 rv-0371 判可执行，对症的 rv-0073 待确认被整个丢掉）
    return {"plans_ranked": kept, "dropped": dropped, "model_trace": trace, "degraded": None,
            "clarifications": clarifications[:1]}
