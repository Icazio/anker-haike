import { useState } from 'react';
import type { EscalationSummary, ExecutedStep, Feedback, HandoffBusiness } from '../types/snapshot';
import styles from './Cards.module.css';
import { HANDOFF_LABELS, fieldLabel } from '../state/record';

const STATUS: Record<string, string> = {
  not_collected: '未收集', insufficient: '信息不足', order_verified: '订单已核实', order_product_mismatch: '订单与设备不一致',
  needs_manual_check: '需人工核实', dealer_authorized: '授权经销商', dealer_unauthorized: '非授权经销商',
};

const FEEDBACK_LABELS: Record<NonNullable<Feedback>, string> = {
  solved: '已解决', not_solved: '已操作，仍有问题', cannot_do: '无法操作',
};

/** 操作卡记反馈，问句卡记客户的回答（与后端 step_text 同款）。 */
export const stepText = (x: ExecutedStep) => `${x.title}（${x.feedback ? FEEDBACK_LABELS[x.feedback] : `回答：${x.answer ?? ''}`}）`;

export const FACT_LABELS: Record<string, string> = {
  order_no: '订单号', purchase_date: '购买日期', address: '收货地址', dealer: '授权经销商', country: '购买国家',
  sku: '型号', amount: '订单金额',
};

function receiptFacts(facts: Record<string, string>): string {
  return Object.entries(facts).map(([key, value]) => `${FACT_LABELS[key] ?? key}：${value}`).join('；');
}

const BUSINESS_KIND: Record<HandoffBusiness['kind'], string> = {
  device_fault: '设备故障', order_change: '订单变更', parts_purchase: '配件采购', warranty_review: '质保核实', safety: '安全风险', unknown: '待确认',
};
export function businessKnown(b: HandoffBusiness): string {
  return Object.entries(b.known ?? {}).map(([key, value]) => `${fieldLabel(key)}=${value}`).join('；') || '无';
}
export function businessMissing(b: HandoffBusiness): string {
  return (b.missing ?? []).map(fieldLabel).join('、') || '无';
}
export function businessPending(b: HandoffBusiness): string {
  return (b.pending_requests ?? []).map((r) => `${r.intent}(${r.status})`).join('；') || '无';
}

// 键与后端 conversation/tasks.py 的 PRIORITY、任务状态一致；卡片上只显示中文，复制文本仍与后端同款
const INTENT_TEXT: Record<string, string> = {
  replacement_request: '换货', refund_request: '退款', address_update: '修改地址', order_change: '订单变更', parts_purchase: '购买配件',
  report_problem: '故障报修', logistics_query: '查物流', warranty_query: '查质保', order_query: '查订单',
};
const TASK_STATUS_TEXT: Record<string, string> = { pending: '待处理', active: '处理中', waiting_human: '等待人工' };
function pendingText(b: HandoffBusiness): string {
  return (b.pending_requests ?? []).map((r) => `${INTENT_TEXT[r.intent] ?? '其他诉求'}（${TASK_STATUS_TEXT[r.status] ?? '待处理'}）`).join('；') || '无';
}

/** 与后端 summary_to_text 同款的可读文本（票 16 一键复制）。 */
export function summaryToText(s: EscalationSummary): string {
  return [
    `【产品】${s.product}`,
    `【问题】${s.problem}`,
    `【观察】${s.observations?.join('；') || '无'}`,
    `【假设】${s.hypotheses?.join('；') || '无'}`,
    `【排查记录】${s.steps?.map(stepText).join('；') || '无'}`,
    `【升级原因】${s.reason.rule_id}：${s.reason.text}`,
    ...(s.business ? [`【业务】${s.business.kind}；已知：${businessKnown(s.business)}；缺失：${businessMissing(s.business)}；待办：${businessPending(s.business)}`] : []),
    `【情绪】${s.emotion.level ?? '未判断'} / ${s.emotion.strategy}`,
    `【凭证】${s.receipt.status}${s.receipt.next_step ? `，下一步：${s.receipt.next_step}` : ''}`,
    `【凭证核实事实】${receiptFacts(s.receipt.verified_facts ?? {}) || '无'}`,
    `【凭证待核实差异】${s.receipt.conflicts?.join('；') || '无'}`,
  ].join('\n');
}

/** workbench：演示站给出人工工作台的入口（新标签页打开 /admin/desk/:case_id），现场可演示「转人工 → 坐席批准 → 回到会话」。
 *  真实客户页不该出现坐席入口，所以只由客户端 App 传入，观测台复用时不传。
 *  internal：显示规则码与 cause，只给观测台；客户页不出现内部编号与英文枚举。 */
export function SummaryCard({ summary, updatedAt, revision, handoffStatus = 'prepared', outdated = false, workbench = false, internal = false }: { summary: EscalationSummary; updatedAt?: string; revision?: number; handoffStatus?: string; outdated?: boolean; workbench?: boolean; internal?: boolean }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(summaryToText(summary));
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  }
  return (
    <section className={styles.card} data-kind="escalation_summary" aria-label="转人工摘要">
      <header className={styles.cardHead}><strong>问题摘要已整理，可复制给人工客服</strong><button type="button" onClick={copy} className={styles.copyBtn}>{copied ? '已复制' : '一键复制'}</button></header>
      <p className={styles.handoffStatus} data-kind="handoff-status" data-status={handoffStatus}>人工处理：{HANDOFF_LABELS[handoffStatus as keyof typeof HANDOFF_LABELS] ?? handoffStatus}</p>
      {workbench && (
        <a className={styles.workbench} href={summary.case_id ? `/admin/desk/${encodeURIComponent(summary.case_id)}` : '/admin/desk'} target="_blank" rel="noreferrer">
          在人工工作台处理此案件<span aria-hidden="true"> ↗</span>
        </a>
      )}
      {revision && <small>第 {revision} 版{outdated ? ' · 此为当时记录，已有更新' : ''}</small>}
      {updatedAt && <small className={styles.answered}>{new Date(updatedAt).toLocaleString('zh-CN')}</small>}
      <dl className={styles.summary}>
        <div><dt>产品</dt><dd>{summary.product}</dd></div>
        <div><dt>问题</dt><dd>{summary.problem}</dd></div>
        <div><dt>观察</dt><dd>{summary.observations?.length ? summary.observations.join('；') : '无'}</dd></div>
        {/* 假设是 AI 的内部推断，后端缺故障名时直接用方案 ID（qa_rv_0270）充当；只给观测台看，复制文本照旧带上 */}
        {internal && <div><dt>假设</dt><dd>{summary.hypotheses?.length ? summary.hypotheses.join('；') : '无'}</dd></div>}
        <div><dt>排查记录</dt><dd>{summary.steps?.length ? summary.steps.map(stepText).join('；') : '无'}</dd></div>
        {summary.business && (
          <>
            <div><dt>业务类型</dt><dd data-kind="business-kind">{BUSINESS_KIND[summary.business.kind]}</dd></div>
            <div><dt>已知</dt><dd data-kind="business-known">{businessKnown(summary.business)}</dd></div>
            <div><dt>缺失</dt><dd data-kind="business-missing">{businessMissing(summary.business)}</dd></div>
            <div><dt>待办</dt><dd data-kind="business-pending">{pendingText(summary.business)}</dd></div>
          </>
        )}
        <div><dt>结束原因</dt><dd data-kind="end-reason">{summary.reason.text}{internal && <small> · 规则码 <code>{summary.reason.rule_id}</code>{summary.reason.cause ? ` · ${summary.reason.cause}` : ''}</small>}</dd></div>
        <div><dt>凭证状态</dt><dd>{STATUS[summary.receipt.status] ?? summary.receipt.status}{summary.receipt.next_step ? ` · 下一步：${summary.receipt.next_step}` : ''}</dd></div>
        {Object.keys(summary.receipt.verified_facts ?? {}).length > 0 && <div><dt>凭证核实事实</dt><dd>{receiptFacts(summary.receipt.verified_facts ?? {})}</dd></div>}
        {!!summary.receipt.conflicts?.length && <div><dt>凭证待核实差异</dt><dd>{summary.receipt.conflicts.join('；')}</dd></div>}
      </dl>
    </section>
  );
}
