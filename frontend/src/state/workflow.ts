import type { SessionState } from './types';
import type { Stage } from '../types/events';
import type { TimelineItem } from '../types/snapshot';
import { STRATEGY_LABELS } from './record';

/** 工作流面板的角色：对应 docs/planning/2026-10-16-0846_product-feedback-triage/plan.md §B1 的角色映射。
 *  Leader 是 understand / route_entry，Worker 是排障 / 查询 / 办理三条支路，审查是 authorize 的提交闸门。 */
export type Role = 'input' | 'leader' | 'diagnose' | 'consult' | 'service' | 'review' | 'human' | 'reply';

export const ROLE_LABELS: Record<Role, string> = {
  input: '客户输入',
  leader: 'Leader',
  diagnose: 'Worker · 排障',
  consult: 'Worker · 查询',
  service: 'Worker · 办理',
  review: '提交审查',
  human: '人工',
  reply: '回复客户',
};

export type FlowNode = { role: Role; title: string; lines: string[] };
export type FlowTurn = { key: string; at: string | null; nodes: FlowNode[] };
export type Workflow = { turns: FlowTurn[]; running: FlowNode | null };

const TOOL_ROLE: Record<string, Role> = {
  'knowledge.search': 'diagnose',
  'diagnose.vision': 'diagnose',
  'logistics.query': 'consult',
  'warranty.check': 'consult',
  'service_order.create': 'service',
};
const TOOL_LABELS: Record<string, string> = {
  'knowledge.search': '检索官方知识库',
  'diagnose.vision': '识别图片',
  'logistics.query': '查询物流',
  'warranty.check': '查询订单质保',
  'service_order.create': '调用售后工具建单',
};
// 快照里的 action.label 对多数卡片操作只有「操作」，按 action_kind 给出人话
const ACTION_LABELS: Record<string, string> = {
  step_feedback: '反馈排障结果', select_product: '选择产品', confirm_proposal: '确认提交方案', decline_proposal: '暂不办理方案',
  confirm_receipt: '确认凭证信息', skip_receipt: '跳过凭证', rate_satisfaction: '评价服务', request_human: '要求人工',
  new_issue: '开始新问题', resume_issue: '继续之前的问题', skip_retake: '跳过补拍',
};
const ROLE_ORDER: Role[] = ['input', 'leader', 'diagnose', 'consult', 'service', 'review', 'human', 'reply'];
const OPTION_LABELS: Record<string, string> = { replace: '换货', refund: '退款', reship: '补发', carrier_investigation: '承运商调查' };
const EMOTION_LABELS: Record<string, string> = { calm: '平静', anxious: '着急', dissatisfied: '不满', angry: '生气', complaint_risk: '投诉风险' };

/** 运行中的阶段由谁在处理：progress 事件只更新 state.stage，不进 timeline。 */
const STAGE_ROLE: Partial<Record<Stage, { role: Role; title: string }>> = {
  intake: { role: 'leader', title: '理解诉求、抽取事实与情绪' },
  disambiguate: { role: 'leader', title: '确认是哪一款产品' },
  diagnose: { role: 'diagnose', title: '识别图片、检索官方知识库' },
  guide: { role: 'diagnose', title: '整理下一步排障步骤' },
  verify: { role: 'diagnose', title: '核对客户的反馈' },
  consult: { role: 'consult', title: '查询订单与物流' },
  context: { role: 'service', title: '核对订单与质保' },
  propose: { role: 'service', title: '按 SOP 生成方案' },
  execute: { role: 'review', title: '提交闸门与独立审查' },
  awaiting_human: { role: 'human', title: '等待人工处理' },
};

const clip = (text: string, n = 72) => {
  const flat = text.replace(/\s+/g, ' ').trim();
  return flat.length > n ? `${flat.slice(0, n - 1)}…` : flat;
};

function addLine(nodes: FlowNode[], role: Role, title: string, line?: string) {
  let node = nodes.find((n) => n.role === role);
  if (!node) {
    node = { role, title, lines: [] };
    nodes.push(node);
  }
  if (line && !node.lines.includes(line)) node.lines.push(line);
}

/** 一轮 = 一次客户输入（消息或卡片操作）及其后系统产生的全部事件。 */
function buildTurn(items: TimelineItem[], key: string, awaitingReceipt = false): FlowTurn {
  const nodes: FlowNode[] = [];
  const head = items[0]!;
  if (head.kind === 'user_message') addLine(nodes, 'input', '客户消息', `「${clip(head.text || '（图片）', 80)}」${head.image_ids?.length ? ` + ${head.image_ids.length} 张图` : ''}`);
  else if (head.kind === 'action') addLine(nodes, 'input', '客户操作', ACTION_LABELS[head.action_kind] ?? head.label);

  const workers: Role[] = [];
  const route = (role: Role) => { if (!workers.includes(role)) workers.push(role); };
  for (const item of items) {
    if (item.kind === 'tool' && TOOL_ROLE[item.name]) route(TOOL_ROLE[item.name]!);
    if (item.kind === 'step_card') route('diagnose');
    if (item.kind === 'proposal_card' || item.kind === 'execution_card' || item.kind === 'case_changed') route('service');
  }

  const leader: string[] = [];
  if (items.some((t) => t.kind === 'product_card')) leader.push('型号不明确，先请客户确认产品');
  for (const role of workers) leader.push(`分派给 ${ROLE_LABELS[role]}`);
  const summary = items.find((t): t is Extract<TimelineItem, { kind: 'escalation_summary' }> => t.kind === 'escalation_summary');
  if (summary?.summary.emotion.level) {
    leader.push(`情绪 ${EMOTION_LABELS[summary.summary.emotion.level] ?? summary.summary.emotion.level} → 策略「${STRATEGY_LABELS[summary.summary.emotion.strategy] ?? summary.summary.emotion.strategy}」`);
  }
  if (summary) leader.push(`触发转人工：${summary.summary.reason.text}`);
  for (const line of leader) addLine(nodes, 'leader', '理解与分派', line);

  for (const item of items) {
    switch (item.kind) {
      case 'tool':
        if (TOOL_ROLE[item.name] && item.status !== 'started') {
          const role = TOOL_ROLE[item.name]!;
          const summaryText = item.name === 'diagnose.vision' ? null : item.summary;
          addLine(nodes, role, ROLE_LABELS[role], `${TOOL_LABELS[item.name]}${item.status === 'failed' ? '（失败）' : summaryText ? `：${clip(summaryText, 40)}` : ''}`);
        }
        break;
      case 'evidence': {
        const docs = [...new Set(item.items.map((e) => e.doc_id))].slice(0, 3);
        if (docs.length) addLine(nodes, 'diagnose', ROLE_LABELS.diagnose, `依据 官方 Q&A ${docs.join('、')}`);
        break;
      }
      case 'step_card':
        addLine(nodes, 'diagnose', ROLE_LABELS.diagnose, `输出 第 ${item.step.step_no} 步：${clip(item.step.title, 48)}`);
        break;
      // 快照里每个案件只留一条 case_changed（状态是最新的），位置在案件建立的那一轮
      case 'case_changed':
        addLine(nodes, 'service', ROLE_LABELS.service, '建立售后案件，核对订单与质保');
        break;
      case 'proposal_card':
        addLine(nodes, 'service', ROLE_LABELS.service, `依据 SOP：${clip(item.decision_summary, 60)}`);
        addLine(nodes, 'service', ROLE_LABELS.service, `输出 方案：${item.options.map((o) => OPTION_LABELS[o.type] ?? o.title).join(' / ')}（待客户确认）`);
        break;
      case 'execution_card': {
        const type = typeof item.receipt.data?.type === 'string' ? item.receipt.data.type : '';
        addLine(nodes, 'service', ROLE_LABELS.service, `按客户确认的${OPTION_LABELS[type] ?? ''}方案调用售后工具`);
        if (item.status === 'succeeded') {
          addLine(nodes, 'review', '提交前检查', `提交闸门通过：资格、证据、安全、幂等${type === 'replace' || type === 'refund' ? '、换厂商独立审查' : ''}`);
          addLine(nodes, 'review', '提交前检查', `通过后建单 ${item.receipt.service_order_no ?? ''}`.trim());
          addLine(nodes, 'human', '交接给人工', '服务单按 SOP 转人工处理，结果回到本会话');
        } else {
          addLine(nodes, 'review', '提交前检查', '本次提交未完成');
        }
        break;
      }
      case 'escalation_summary': {
        const failed = (item.summary.gate_result?.checks ?? []).filter((c) => !c.passed);
        if (failed.length) addLine(nodes, 'review', '提交前检查', `未通过：${failed.map((c) => c.detail).join('；')}`);
        addLine(nodes, 'human', '交接给人工', `交接摘要第 ${item.revision} 版：${clip(item.summary.reason.text, 40)}`);
        break;
      }
      case 'assistant_message':
        if (item.text.trim() && item.status !== 'replaced') addLine(nodes, 'reply', '回复客户', clip(item.text, 90));
        break;
      default:
        break;
    }
  }
  if (awaitingReceipt) addLine(nodes, 'service', ROLE_LABELS.service, '需要订单号或购买凭证才能判断质保，等待客户提供');
  nodes.sort((a, b) => ROLE_ORDER.indexOf(a.role) - ROLE_ORDER.indexOf(b.role));
  return { key, at: ('at' in head && head.at) || null, nodes };
}

export function deriveWorkflow(state: SessionState): Workflow {
  const groups: TimelineItem[][] = [];
  for (const item of state.timeline) {
    if (item.kind === 'user_message' || item.kind === 'action' || !groups.length) groups.push([item]);
    else groups[groups.length - 1]!.push(item);
  }
  const inputs = groups.filter((g) => g[0]!.kind === 'user_message' || g[0]!.kind === 'action');
  const awaitingReceipt = state.ui === 'awaiting_input' || state.ui === 'idle' ? state.pendingInput?.kind === 'upload_receipt' : false;
  const turns = inputs.map((g, i) => buildTurn(g, `turn-${i}`, awaitingReceipt && i === inputs.length - 1));
  const busy = state.ui === 'streaming' || state.ui === 'tool_running' || state.ui === 'recovering';
  const stage = state.stage ? STAGE_ROLE[state.stage] : undefined;
  return { turns, running: busy && stage ? { role: stage.role, title: stage.title, lines: [] } : null };
}
