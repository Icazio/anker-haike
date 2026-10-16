import type { SessionState } from './types';
import type { EscalationSummary, ExecutionCardItem, ReceiptCardItem, TimelineItem } from '../types/snapshot';
import { findProduct, type ProductInfo } from '../lib/products';
import { CASE_LABELS, caseStatusOf, progressFor } from './progress';

/** 信息收集面板的一项：value 为空表示还没收集到；source 说明这条信息从哪来（客户说的 / 订单核验 / 凭证识别）。 */
export type InfoSlot = { key: string; label: string; value: string | null; source: string | null; verified?: boolean };

export type CollectedInfo = {
  product: { name: string; sku: string | null; info: ProductInfo | null } | null;
  problem: string | null;
  slots: InfoSlot[];
  missing: string[];
  tried: { done: number; total: number };
  caseLabel: string | null;
  route: ReturnType<typeof progressFor>;
  emotion: EscalationSummary['emotion'] | null;
  photos: number;
};

// 与后端 app/actions/params.py 同一套编号格式：订单 Anker016、运单 Anker1234567(-3)。
const ORDER_NO = /(?<![A-Za-z0-9])Anker\d{3}(?![\d-])/i;
// 只认 8 个产品的 PN 原文；「S1 Pro」同时是扫地机和吸奶器，不按名称猜。
const PN = /\b(T2080|T2351|T2352|T2353|T2280|T2292|T8D04|T8170)/i;

// RMA 表单与 App 报错首条消息带一堆表头；面板只取问题描述那一栏（与 app/official/message.py 的字段名一致）
const PROBLEM_FIELD = /(?:Problem Description|Probleembeschrijving|Problembeschreibung|Description du problème|Descripción del problema)\s*:\s*(.+)/i;

// 首屏选产品时预填的「我的 <产品名>（<PN>）：」，产品已单独显示，问题里不再重复
const PICKED_PREFIX = /^我的 .+?（T[0-9A-Z]{4}）：/;

const WARRANTY_LABELS: Record<string, string> = { in_warranty: '保内', out_of_warranty: '已过保', unauthorized_dealer: '非授权经销商', unknown: '待核实' };

function lastOf<K extends TimelineItem['kind']>(timeline: TimelineItem[], kind: K): Extract<TimelineItem, { kind: K }> | null {
  for (let i = timeline.length - 1; i >= 0; i--) if (timeline[i]!.kind === kind) return timeline[i] as Extract<TimelineItem, { kind: K }>;
  return null;
}

/** 回执里的证据带来源前缀（customer:… / order:… / images:…），面板只显示值。 */
function evidenceValue(execution: ExecutionCardItem | null, key: string): string | null {
  const evidence = execution?.receipt.data?.evidence;
  if (!evidence || typeof evidence !== 'object') return null;
  const raw = (evidence as Record<string, unknown>)[key];
  return typeof raw === 'string' ? raw.replace(/^[a-z_]+:/, '') : null;
}

function receiptField(card: ReceiptCardItem | null, key: 'order_no' | 'seller' | 'country' | 'purchase_date'): string | null {
  if (!card || card.skipped_reason) return null;
  return (card.confirmed_fields ?? card.fields)[key] ?? null;
}

/** 面板数据全部从 timeline 派生（与 deriveRecord 同一原则）：快照恢复后结果一致，不另建状态。 */
export function deriveInfo(state: SessionState): CollectedInfo {
  const { timeline } = state;
  const summary = lastOf(timeline, 'escalation_summary')?.summary ?? null;
  const execution = lastOf(timeline, 'execution_card');
  const receipt = lastOf(timeline, 'receipt_card');
  const userTexts = timeline.flatMap((t) => (t.kind === 'user_message' ? [t.text] : []));

  let product: CollectedInfo['product'] = null;
  for (let i = timeline.length - 1; i >= 0 && !product; i--) {
    const item = timeline[i]!;
    if (item.kind === 'product_card' && item.selected_sku) {
      const chosen = item.candidates.find((c) => c.sku === item.selected_sku);
      product = { name: chosen?.name ?? item.selected_sku, sku: item.selected_sku, info: findProduct(item.selected_sku) };
    }
  }
  const receiptSku = typeof execution?.receipt.data?.sku === 'string' ? execution.receipt.data.sku : null;
  if (!product && receiptSku) product = { name: findProduct(receiptSku)?.name ?? receiptSku, sku: receiptSku, info: findProduct(receiptSku) };
  if (!product && summary?.product) {
    const info = findProduct(summary.product);
    product = { name: summary.product, sku: info?.sku ?? null, info };
  }
  if (!product) {
    const pn = userTexts.map((t) => PN.exec(t)?.[1]).find(Boolean);
    const info = findProduct(pn);
    if (info) product = { name: info.name, sku: info.sku, info };
  }

  const caseItem = lastOf(timeline, 'case_changed');
  const refs = caseItem?.external_refs ?? {};
  const stated = userTexts.map((t) => ORDER_NO.exec(t)?.[0]).find(Boolean) ?? null;
  const orderSlot: InfoSlot = refs.order_no
    ? { key: 'order_no', label: '订单号', value: refs.order_no, source: '已关联订单', verified: true }
    : receiptField(receipt, 'order_no')
      ? { key: 'order_no', label: '订单号', value: receiptField(receipt, 'order_no'), source: '凭证识别' }
      : { key: 'order_no', label: '订单号', value: stated, source: stated ? '客户提供' : null };

  const warranty = summary?.warranty ?? null;
  const serial = evidenceValue(execution, 'serial_number');
  const seller = receiptField(receipt, 'seller');
  const slots: InfoSlot[] = [
    orderSlot,
    { key: 'warranty', label: '质保', value: warranty ? `${WARRANTY_LABELS[warranty.status] ?? warranty.status}${warranty.warranty_end ? ` · 至 ${warranty.warranty_end}` : ''}` : null, source: warranty ? '订单核验' : null, verified: !!warranty },
    { key: 'serial_number', label: 'SN', value: serial, source: serial ? '客户提供' : null },
    { key: 'seller', label: '购买渠道', value: seller ? [seller, receiptField(receipt, 'country')].filter(Boolean).join(' · ') : null, source: seller ? '凭证识别' : null },
    { key: 'tracking_no', label: '物流单号', value: refs.tracking_no ?? null, source: refs.tracking_no ? '订单核验' : null, verified: !!refs.tracking_no },
    { key: 'service_order_no', label: '服务单号', value: refs.service_order_no ?? execution?.receipt.service_order_no ?? null, source: refs.service_order_no || execution?.receipt.service_order_no ? '售后系统' : null, verified: true },
  ];

  const missing = [...(summary?.business?.missing ?? [])];
  if (state.pendingInput?.kind === 'upload_receipt' && !orderSlot.value) missing.unshift('订单号或购买凭证');

  const steps = timeline.filter((t) => t.kind === 'step_card');
  const photos = timeline.reduce((n, t) => n + (t.kind === 'user_message' ? t.image_ids?.length ?? 0 : 0), 0);
  const caseStatus = caseStatusOf(timeline, state.activeIssueId);
  return {
    product,
    problem: summary?.problem ?? (userTexts[0] ? PROBLEM_FIELD.exec(userTexts[0])?.[1]?.trim() ?? userTexts[0].replace(PICKED_PREFIX, '') : null),
    slots,
    missing,
    tried: { done: steps.filter((s) => s.kind === 'step_card' && (s.feedback || s.answer)).length, total: steps.length },
    caseLabel: caseStatus ? CASE_LABELS[caseStatus] ?? caseStatus : null,
    route: progressFor(state.stage, caseStatus),
    emotion: summary?.emotion ?? null,
    photos,
  };
}
