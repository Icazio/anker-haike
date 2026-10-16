"""步骤卡准备（票 34；03 §1.5、09 §1 / §2.5 / §3.2）。

1. 取 plan_cursor 指向的步骤，instruction_src 原文来自官方 Q&A 生成的计划证据索引（app/plans/qa.py）。
2. evidence_ids = 当前允许证据集合中与 instruction_src 同一条 Q&A 的条目 + diagnose 为该计划给出的证据；
   若步骤引用了允许集合外的 id → 丢弃该步骤取下一步（09 §2.5）。
2b. primary_evidence_id = 这一步出自的那条官方 Q&A：本轮已有（错误码精确命中或检索命中）就用它，
   没有才本地发布 Q&A 原文。
3. CP-pre-step：文字含 R4 或含高危动作且无 caution → 丢弃取下一步。
4. 原样发布已审核操作；停止条件独立附在 caution 中，不参与用户风险判定。
card_id = uuid5(session_id, plan_id, step_id)，重跑稳定。
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from app.conversation.operation_conditions import answered_history, step_unavailable
from app.models.router import ModelRouter
from app.plans.library import PlanLibrary
from app.plans.models import Plan, PlanStep
from app.plans.qa import PART_SUFFIX, customer_text, customer_voice, guide_of
from app.rules.service import RulesService

NS = uuid.UUID("2b0f5a9e-64c2-4c7d-9c0a-7f3d1e6a8b21")
PART_ID = re.compile(r"^s(\d+)([b-h]?)$")
GUIDE_BUDGET_MS = 6000


def step_card_id(session_id: str, plan_id: str, step_id: str) -> str:
    return uuid.uuid5(NS, f"{session_id}|{plan_id}|{step_id}").hex


@dataclass
class StepPrep:
    outcome: str  # ready | exhausted | blocked | explained | source_gap
    step: dict[str, Any] | None = None  # 契约 TroubleshootStep 形状
    card_id: str | None = None
    plan_cursor: dict[str, Any] | None = None
    dropped: list[dict[str, Any]] = field(default_factory=list)
    rewritten: bool = False
    model_trace: dict[str, Any] | None = None
    evidence: dict[str, dict[str, Any]] = field(default_factory=dict)
    # 主引用从哪儿来：qa_exact / kb_qa 表示本轮已有这条 Q&A，none 表示退回本地发布
    anchor: dict[str, Any] | None = None
    explanation: str = ""
    displayed_nodes: list[str] = field(default_factory=list)


def _evidence_for(
    step: PlanStep,
    plan: Plan,
    allowed_evidence: dict[str, dict[str, Any]],
    ranked_evidence: list[str],
) -> list[str]:
    """步骤引用的证据：同一条 Q&A 的允许条目 + diagnose 为该计划给出的 evidence_ids。

    前者天然在允许集合内；后者来自模型输出，可能越界，由调用方校验后丢弃该步骤（09 §2.5）。
    """
    doc_id = step.evidence_key.split("#", 1)[0]
    ids = [eid for eid, e in allowed_evidence.items() if e.get("doc_id") == doc_id]
    ids += list(ranked_evidence)
    return sorted(set(ids))


RETRY_NOTE = ("You said you haven't checked this yet. Once you've had a chance to look, pick the option that matches; "
              "the next step depends on what you find.")


# 首卡说明的最后一句按卡片类型给：问题卡没有「未解决」按钮（T36 rv-0341 首张是噪音来源的问题卡），
# 材料卡是「提交 / 暂时没有」（frontend StepCard.tsx）
REPORTED_ANSWER = {
    "action": "if you've already done it this way and the problem is still there, just mark it as not solved.",
    "question": "for this card, just pick the option that matches what you see now, or describe it in a few words.",
    "material_request": "for this card, upload it if you have it, or tell me you don't have it right now.",
}


def reported_note(quotes: list[str], kind: str, symptoms: list[str] = (), *, answer: bool = True) -> str:
    """客户自述做过 / 查过的事（T21「nettoyé et repartit aspirateur a plusieurs reprise」、T27「no blockage seen」）：
    引原话，说明这些检查可能与已做的重叠、仍逐张确认。自述没有卡片反馈精确（没说清洁了哪个部件、是否在平地重启），
    不据此跳过任何步骤。引客户原话（可能不是英文），不替客户改写。
    症状原话一并引（T37「水箱是满的」在症状里，只引「软管、胶圈正常」时客户看不出这张卡针对的是自己的情况）。
    answer=False：同一张卡上的资料覆盖边界说明已经讲了怎么反馈，这里只引原话。"""
    said = "; ".join(f'"{q.strip()}"' for q in quotes)
    described = "; ".join(f'"{s.strip()}"' for s in symptoms if s not in quotes)
    lead = (f"You described: {described}. " if described else "") + f"You mentioned: {said}."
    if not answer:
        return lead
    return (lead + " Some of these checks may overlap with what you've already done or checked. "
            "Please still check each one exactly as described; " + REPORTED_ANSWER.get(kind, REPORTED_ANSWER["action"]))


def _advance_in_plan(plan: Plan, step_id: str, *, option: str | None = None) -> str | None:
    """消费节点后沿已回答分支推进；到 DONE / EXHAUSTED 返回 None。"""
    nxt = plan.next_step_id(step_id, "not_solved", option=option)
    return None if nxt in ("DONE", "EXHAUSTED") else nxt


async def prepare_step(
    *,
    state: dict[str, Any],
    library: PlanLibrary,
    rules: RulesService,
    router: ModelRouter | None,
    lane: str,
    session_id: str,
    budget_ms: int = GUIDE_BUDGET_MS,
) -> StepPrep:
    """校验并发布已审核步骤；router/budget 参数保留以兼容现有编排接口。"""
    cursor = dict(state.get("plan_cursor") or {})
    if not cursor.get("plan_id"):
        return StepPrep("exhausted")
    plan = library.get(cursor["plan_id"])
    product = state.get("product_confirmed") or {}
    if not plan.applies(category=state.get("category") or product.get("category"), sku=product.get("sku")):
        return StepPrep("exhausted", dropped=[{"plan_id": plan.plan_id, "reason": "plan_model_mismatch"}])
    step_id = cursor.get("step_id") or plan.first_step().step_id
    allowed_evidence: dict[str, dict[str, Any]] = dict(state.get("evidence") or {})
    ranked_evidence = next(
        (
            list(p.get("evidence_ids") or [])
            for p in state.get("plans_ranked") or []
            if p.get("plan_id") == plan.plan_id
        ),
        [],
    )
    answered = {s.get("instruction_src"): s for s in answered_history(state)}
    dropped: list[dict[str, Any]] = []
    context: list[str] = []  # 说明段落不单独出卡，附在下一张卡上（I4：标题 / 结论不是操作，不要求反馈）
    explanation_evidence: dict[str, dict] = {}
    displayed_nodes = list(state.get("displayed_knowledge_nodes") or [])

    while step_id is not None:
        step = plan.step(step_id)
        if step.source_gap:
            source_text = library.evidence_snippet(step.instruction_src)
            _, published, _ = _primary_evidence(step, library, source_text, allowed_evidence)
            explanation_evidence.update(published)
            context.append("The supplied official source refers to further instructions, but does not include them or a link. I can't provide those missing steps from this source.")
            return StepPrep("source_gap", dropped=[*dropped, {
                "plan_id": plan.plan_id, "step_id": step_id, "reason": "source_reference_missing",
            }], explanation="\n\n".join(context), evidence=explanation_evidence, displayed_nodes=displayed_nodes)
        if step.kind == "statement":
            source_text = library.evidence_snippet(step.instruction_src)
            node_key = f"{step.instruction_src}@{library.evidence[step.evidence_key].doc_version}"
            if node_key not in displayed_nodes:
                context.append(customer_text(source_text))
                displayed_nodes.append(node_key)
                _, published, _ = _primary_evidence(step, library, source_text, allowed_evidence)
                explanation_evidence.update(published)
            dropped.append({"plan_id": plan.plan_id, "step_id": step_id, "reason": "statement_context"})
            step_id = _advance_in_plan(plan, step_id)
            continue
        if step.kind == "handoff":
            # 「请联系客服继续保修流程」不是给用户的操作：计划到此耗尽，交给 decide_next 走质保 / 人工（I4）
            dropped.append({"plan_id": plan.plan_id, "step_id": step_id, "reason": "handoff_step"})
            break
        unavailable = step_unavailable(state, plan.plan_id, step)
        if unavailable == "condition_not_met":
            # 适用条件已被用户原话否定，或兄弟条件成立（fact_check）：这一步不适用，沿计划往后走
            dropped.append({"plan_id": plan.plan_id, "step_id": step_id, "reason": unavailable})
            step_id = _advance_in_plan(plan, step_id)
            continue
        if unavailable:
            return StepPrep("blocked", dropped=[*dropped, {
                "plan_id": plan.plan_id, "step_id": step_id, "reason": unavailable,
            }])
        # 跨计划去重：与已执行步骤 instruction_src 相同 → 跳过（09 §3.4）
        if step.instruction_src in answered:
            dropped.append(
                {"plan_id": plan.plan_id, "step_id": step_id, "reason": "duplicate_instruction_src"}
            )
            step_id = _advance_in_plan(plan, step_id, option=(answered[step.instruction_src].get("answer") or {}).get("option"))
            continue
        source_text = library.evidence_snippet(step.instruction_src)
        evidence_ids = _evidence_for(step, plan, allowed_evidence, ranked_evidence)
        bad = [e for e in evidence_ids if e not in allowed_evidence]
        if bad:
            dropped.append(
                {
                    "plan_id": plan.plan_id,
                    "step_id": step_id,
                    "reason": f"evidence_out_of_scope:{','.join(bad)}",
                }
            )
            step_id = _advance_in_plan(plan, step_id)
            continue
        pre = rules.check_pre_step(
            instruction=source_text, title=step.title, caution=step.caution, session_id=session_id,
            conditional_notice=source_text in step.stop_conditions,
        )
        if pre.action == "drop":
            dropped.append(
                {
                    "plan_id": plan.plan_id,
                    "step_id": step_id,
                    "reason": (
                        f"safety_term_in_step:{pre.term}"
                        if pre.rule_id == "R4"
                        else f"high_risk_without_caution:{pre.term}"
                    ),
                }
            )
            step_id = _advance_in_plan(plan, step_id)
            continue
        primary_id, published_evidence, anchor_match = _primary_evidence(
            step, library, source_text, allowed_evidence
        )
        if published_evidence:
            evidence_ids = sorted({*evidence_ids, *published_evidence})
        card_id = step_card_id(session_id, plan.plan_id, step_id)
        # 资料覆盖边界：客户原话命中审核写的条件时，说明这张卡能做什么、做不到什么（T34 问能否找回旧地图，资料只有查地图页与重建）。
        # 它已经告诉客户这张卡怎么反馈，下面的自述说明只引原话、不再重复反馈方式
        scoped = bool(step.scope_note and re.search(step.scope_note[0], customer_said(state), re.IGNORECASE))
        if scoped:
            context.append(step.scope_note[1])
            if step.beyond_source and (beyond := f"beyond_source:{plan.plan_id}") not in displayed_nodes:
                displayed_nodes.append(beyond)
        # 客户自述做过的事每个问题只说一次，附在本问题第一张卡上（同 statement 的 displayed_nodes 去重）
        reported_key = f"reported:{state.get('active_issue_id')}"
        if reported_key not in displayed_nodes and (quotes := reported_quotes(state)):
            context.append(reported_note(quotes, step.kind, reported_quotes(state, kinds={"symptom"}), answer=not scoped))
            displayed_nodes.append(reported_key)
        last = next((a for a in reversed(state.get("step_attempts") or []) if a.get("instruction_src") == step.instruction_src), None)
        if last and last.get("retry"):
            # 上次答的是「还没检查 / 不知道」（B21）：重发这张卡，说明为什么还要回答
            context.append(RETRY_NOTE)
        return StepPrep(
            "ready",
            step={
                "step_id": step.step_id,
                "plan_id": plan.plan_id,
                "plan_version": plan.version,
                "step_no": step_no_of(plan, step_id),
                "title": customer_voice(step.title),
                "instruction": customer_text(source_text),
                "expected_result": step.expected_result,
                "caution": "；".join(filter(None, [step.caution, *[c for c in step.stop_conditions if c != source_text]])) or None,
                "evidence_ids": evidence_ids,
                "primary_evidence_id": primary_id,
                "media": step_media(plan.plan_id, step_id),
                "kind": step.kind,
                "options": list(step.options),
                **({"context": "\n".join(context)} if context else {}),
            },
            card_id=card_id,
            displayed_nodes=displayed_nodes,
            plan_cursor={
                "plan_id": plan.plan_id,
                "version": plan.version,
                "step_id": step_id,
                "source": cursor.get("source"),
            },
            dropped=dropped,
            evidence=published_evidence,
            anchor={
                "evidence_key": step.evidence_key,
                "match": anchor_match,
                "primary_evidence_id": primary_id,
                "retrieved": not published_evidence,
            },
        )
    only_explanation = all(s.kind == "statement" for s in plan.steps)
    return StepPrep("explained" if only_explanation else "exhausted", dropped=dropped,
                    explanation="\n\n".join(context), evidence=explanation_evidence, displayed_nodes=displayed_nodes)


def _primary_evidence(
    step: PlanStep,
    library: PlanLibrary,
    source_text: str,
    allowed_evidence: dict[str, dict[str, Any]],
) -> tuple[str, dict[str, dict[str, Any]], str]:
    """这一步的主引用：本轮已有的同一条官方 Q&A（错误码精确命中优先，其次检索命中），没有才本地发布。

    返回 (primary_evidence_id, 需要额外发布的证据, 命中方式 qa_exact / kb_qa / none)。
    一条 Q&A 入库为一个知识、基本一块，doc_id 即 qa_id，按 doc_id 认就是这一步的出处，
    不必像手册那样按小节锚点在同文档的多块里认人。认不出（检索没召回、知识库不可用）时
    本地发布 Q&A 原文：原文即便检索挂了也应当可查，调用方记 anchor_not_retrieved 以便归因。
    """
    doc_id, chunk_id = step.evidence_key.split("#", 1)
    same = [(eid, e) for eid, e in allowed_evidence.items() if e.get("doc_id") == doc_id]
    for source in ("qa_exact", "kb_qa"):
        found = next((eid for eid, e in same if e.get("source") == source), None)
        if found is not None:
            return found, {}, source
    source = library.evidence[step.evidence_key]
    pid = f"plan:{step.evidence_key}:{source.doc_version}"
    return (
        pid,
        {
            pid: {
                "evidence_id": pid,
                "source": "approved_plan",
                "doc_id": doc_id,
                "chunk_id": chunk_id,
                "doc_version": source.doc_version,
                "snippet": source_text,
                "score": 1.0,
                "status": "ok",
            }
        },
        "none",
    )


def customer_said(state: dict[str, Any]) -> str:
    """本问题的客户原话（事实来源消息加本轮输入），给资料覆盖边界说明的条件匹配用。"""
    issue = (state.get("issues") or {}).get(state.get("active_issue_id"), {})
    ids = {sid for f in issue.get("facts", []) if f.get("status") == "active" for sid in f.get("source_entry_ids", [])}
    ids.add(state.get("input_id"))
    return "\n".join(m["text"] for m in state.get("messages") or []
                     if m.get("role") == "user" and m.get("input_id") in ids and (m.get("text") or "").strip())


def reported_quotes(state: dict[str, Any], kinds: set[str] = frozenset({"action_taken", "observation"})) -> list[str]:
    """本问题里客户自己说的原话（active、affirmed、来自客户）：默认是做过的排查与查看到的状态，kinds 可改为症状。"""
    issue = (state.get("issues") or {}).get(state.get("active_issue_id"), {})
    quotes = [(fact.get("quote") or fact.get("value") or "").strip() for fact in issue.get("facts", [])
              if fact.get("status") == "active" and fact.get("kind") in kinds
              and fact.get("polarity", "affirmed") == "affirmed"
              and fact.get("source_kind", "user_report") == "user_report"
              and fact.get("source") in {None, "user_statement", "device_message"}]
    return list(dict.fromkeys(q for q in quotes if q))


def step_media(plan_id: str, step_id: str) -> list[dict[str, str]]:
    """官方 Q&A 步骤附带的图片 / 视频链接；非 Q&A 计划（测试夹具）为空。"""
    guide = guide_of(plan_id)
    if guide is None:
        return []
    # 审核拆分的段落 s{pos}、s{pos}b…同属原文第 pos 段：段落图示只挂在第一张出卡的部分（说明 / 交人工不出卡），
    # 不在每张卡上重复（T32 rv-0061：问候说明 + 胶带操作，图示属于胶带那张）
    match = PART_ID.match(step_id)
    if match is None:
        return []
    index = int(match.group(1)) - 1
    if not 0 <= index < len(guide.steps):
        return []
    paragraph = guide.steps[index]
    if paragraph.parts:
        # 后缀按部分在原段里的位置编（同 plans/qa.py PART_SUFFIX），禁用的部分不重排；
        # 审核用 media 指定了挂图的部分时挂那一部分（T40 rv-0073：文章链接属于「是否已按文章检查」那张）
        carded = next((i for i, part in enumerate(paragraph.parts) if part.owns_media and not part.disabled), None)
        if carded is None:
            carded = next((i for i, part in enumerate(paragraph.parts) if not part.disabled and part.kind not in {"statement", "handoff"}), 0)
        if match.group(2) != PART_SUFFIX[carded]:
            return []
    elif match.group(2):
        return []
    media = paragraph.media if guide.kind == "steps" or paragraph.parts else guide.media
    return [{"url": m.url, "kind": m.kind} for m in media]


def step_no_of(plan: Plan, step_id: str) -> int:
    return next(i for i, s in enumerate(plan.steps, 1) if s.step_id == step_id)
