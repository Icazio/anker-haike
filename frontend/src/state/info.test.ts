import { describe, expect, it } from 'vitest';
import { deriveInfo } from './info';
import { deriveWorkflow } from './workflow';
import { demoOrdersFor } from '../lib/products';
import { initialState, type SessionState } from './types';
import type { TimelineItem } from '../types/snapshot';

const at = '2026-10-15T07:17:00Z';
// 节选自会话 51fde499（T55 吸奶器，订单 Anker016）走完全链路的时间线
const timeline: TimelineItem[] = [
  { kind: 'user_message', id: 'u1', at, text: 'Source: amazon\nOrder No: Anker016\nProduct Name: eufy S1 Pro Wearbale Breast Pump\nProblem Description: the left pump will no longer suction.', image_ids: ['img1'], images: [] },
  { kind: 'tool', tool_id: 't1', name: 'knowledge.search', status: 'finished', summary: '命中 18 条来源' },
  { kind: 'evidence', items: [{ evidence_id: 'e1', chunk_id: 'c', doc_id: 'bp-0102', doc_version: '1', score: 1, snippet: 's', source: 'kb_qa' }] },
  { kind: 'step_card', card_id: 's1', version: 1, feedback: 'not_solved', step: { step_id: 's1', step_no: 1, title: 'Restore factory settings', instruction: 'x', expected_result: 'y', plan_id: 'qa_bp_0102', plan_version: 1 } },
  { kind: 'action', id: 'a1', at, action_kind: 'step_feedback', label: '反馈排障结果' },
  { kind: 'case_changed', card_id: 'c1', case_id: 'c1', status: 'awaiting_approval', reason: 'r', updated_at: at, version: 2, external_refs: { order_no: 'Anker016', service_order_no: 'SRV-A9C0FA7590AE' } },
  { kind: 'user_message', id: 'u2', at, text: 'SN: T8D04121ABCD0001', image_ids: [], images: [] },
  { kind: 'proposal_card', card_id: 'p1', version: 3, decision_summary: 'under warranty, qualifies for a replacement', options: [{ option_id: 'replace', type: 'replace', title: 'Submit a replacement request' }] },
  { kind: 'action', id: 'a2', at, action_kind: 'confirm_proposal', label: '操作' },
  { kind: 'tool', tool_id: 't2', name: 'service_order.create', status: 'finished', summary: 'After-sales tool responded' },
  { kind: 'execution_card', card_id: 'x1', version: 4, status: 'succeeded', action_kind: 'service_order.create', execution_id: 'e', idempotency_key: 'k',
    receipt: { status: 'submitted', service_order_no: 'SRV-A9C0FA7590AE', data: { sku: 'T8D04', type: 'replace', evidence: { serial_number: 'customer:T8D04121ABCD0001' } } } },
];
const state: SessionState = { ...initialState, id: 's', stage: 'awaiting_human', timeline };

describe('信息收集面板', () => {
  it('从回执与案件里取产品、订单、SN、服务单号，问题只取 Problem Description 一栏', () => {
    const info = deriveInfo(state);
    expect(info.product).toMatchObject({ sku: 'T8D04', name: 'eufy Wearable Breast Pump S1 Pro' });
    expect(info.product?.info?.image).toBe('/products/T8D04.png');
    expect(info.problem).toBe('the left pump will no longer suction.');
    const slot = (key: string) => info.slots.find((s) => s.key === key);
    expect(slot('order_no')).toMatchObject({ value: 'Anker016', verified: true });
    expect(slot('serial_number')?.value).toBe('T8D04121ABCD0001');
    expect(slot('service_order_no')?.value).toBe('SRV-A9C0FA7590AE');
    expect(info.tried).toEqual({ done: 1, total: 1 });
    expect(info.photos).toBe(1);
  });

  it('等凭证且还没有订单号时，待补里列出订单号或购买凭证', () => {
    // 会话 587c65da：客户给的「21312524860245200」不是主办方订单格式，不能算已收集
    const pending = { kind: 'upload_receipt' as const, card_id: 'u', input_token: 'u', version: 1 };
    const noOrder: TimelineItem[] = [{ kind: 'user_message', id: 'u', at, text: '订单号21312524860245200，发票找不到了', image_ids: [], images: [] }];
    expect(deriveInfo({ ...state, timeline: noOrder, pendingInput: pending }).missing).toContain('订单号或购买凭证');
    expect(deriveInfo({ ...state, timeline: timeline.slice(0, 5), pendingInput: pending }).missing).not.toContain('订单号或购买凭证');
  });

  it('客户消息里只出现 PN 时也能认出产品', () => {
    const info = deriveInfo({ ...initialState, timeline: [{ kind: 'user_message', id: 'u', at, text: 'Product PN: T2352\nProblem Code: 3212', image_ids: [], images: [] }] });
    expect(info.product?.sku).toBe('T2352');
  });

  it('演示订单按已确认产品筛选，产品未知时全部给出', () => {
    expect(demoOrdersFor('T8D04')).toEqual({ orders: expect.arrayContaining([expect.objectContaining({ order_no: 'Anker016' })]), note: null });
    expect(demoOrdersFor('T8D04').orders.every((o) => o.sku === 'T8D04')).toBe(true);
    expect(demoOrdersFor(null).orders.length).toBeGreaterThan(5);
    const c20 = demoOrdersFor('T2280');
    expect(c20.orders).toEqual([]);
    expect(c20.note).toContain('Anker016');
  });
});

describe('AI 工作流面板', () => {
  it('每次客户输入算一轮，按 Leader → Worker → 审查 → 人工排列', () => {
    const { turns } = deriveWorkflow(state);
    expect(turns).toHaveLength(4);
    expect(turns[0]!.nodes.map((n) => n.role)).toEqual(['input', 'leader', 'diagnose']);
    expect(turns[1]!.nodes.find((n) => n.role === 'service')!.lines).toEqual(['建立售后案件，核对订单与质保']);
    expect(turns[0]!.nodes.find((n) => n.role === 'diagnose')!.lines).toEqual(expect.arrayContaining(['依据 官方 Q&A bp-0102', '输出 第 1 步：Restore factory settings']));
    const submit = turns[3]!;
    expect(submit.nodes[0]!.lines).toEqual(['确认提交方案']);
    expect(submit.nodes.map((n) => n.role)).toEqual(['input', 'leader', 'service', 'review', 'human']);
    expect(submit.nodes.find((n) => n.role === 'review')!.lines.join()).toContain('换厂商独立审查');
  });

  it('运行中按当前阶段显示正在处理的角色', () => {
    const flow = deriveWorkflow({ ...state, ui: 'tool_running', stage: 'consult' });
    expect(flow.running).toMatchObject({ role: 'consult' });
    expect(deriveWorkflow(state).running).toBeNull();
  });
});
