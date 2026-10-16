import type { SessionState } from '../state/types';
import { deriveInfo } from '../state/info';
import { deriveRecord } from '../state/record';
import { CATEGORY_LABELS } from '../lib/products';
import { EvidenceDrawer } from './EvidenceDrawer';
import { summaryToText } from './SummaryCard';
import { useState } from 'react';
import styles from './InfoPanel.module.css';

type Props = {
  state: SessionState;
  /** 当前悬停步骤卡引用的 evidence_ids，联动高亮依据 */
  highlight?: string[];
  busy?: boolean;
  onNewIssue?: () => void;
  onResumeIssue?: (issueId: string) => void;
};

/** 信息收集面板：客户提供或系统核验到的信息逐项填入；还没收集到的显示为空位，缺什么一眼可见。 */
export function InfoPanel({ state, highlight = [], busy = false, onNewIssue, onResumeIssue }: Props) {
  const info = deriveInfo(state);
  const record = deriveRecord(state);
  const [copied, setCopied] = useState(false);
  const empty = state.timeline.length === 0;
  const lockIssue = busy || !!state.activeRun;
  const filled = info.slots.filter((s) => s.value);
  const open = info.slots.filter((s) => !s.value && s.key !== 'service_order_no' && s.key !== 'tracking_no');

  async function copy() {
    if (!record.summary) return;
    try {
      await navigator.clipboard.writeText(summaryToText(record.summary));
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch { setCopied(false); }
  }

  return (
    <div className={styles.panel} data-testid="info-panel">
      <section className={styles.product} data-empty={!info.product || undefined} aria-label="产品">
        <div className={styles.photo}>
          {info.product?.info ? <img src={info.product.info.image} alt={info.product.name} /> : <span aria-hidden="true">?</span>}
        </div>
        <div className={styles.productText}>
          <h2>{info.product ? info.product.name : '产品待确认'}</h2>
          {info.product?.sku ? (
            <p><span className={styles.pn}>{info.product.sku}</span>{info.product.info && CATEGORY_LABELS[info.product.info.category]}</p>
          ) : (
            <p>{empty ? '说出型号、PN 或贴 App 报错，系统会自动识别' : '型号不明确时会请客户确认'}</p>
          )}
        </div>
      </section>

      <section aria-label="问题">
        <h3 className={styles.heading}>问题</h3>
        <p className={styles.problem}>{info.problem ?? <span className={styles.muted}>等待客户描述</span>}</p>
        {(info.tried.total > 0 || info.photos > 0) && (
          <p className={styles.meta}>
            {info.tried.total > 0 && <span>已排查 {info.tried.done} / {info.tried.total} 步</span>}
            {info.photos > 0 && <span>客户图片 {info.photos} 张</span>}
          </p>
        )}
      </section>

      {state.issues.length > 1 && onResumeIssue && (
        <section>
          <h3 className={styles.heading}>本次会话的问题</h3>
          <select className={styles.select} aria-label="选择要继续的问题" value={state.activeIssueId ?? ''} disabled={lockIssue} onChange={(e) => onResumeIssue(e.target.value)}>
            {state.issues.map((issue) => <option key={issue.issue_id} value={issue.issue_id}>{issue.title || '待描述的问题'}</option>)}
          </select>
        </section>
      )}

      <section aria-label="已收集信息">
        <h3 className={styles.heading}>已收集 <span>{filled.length} 项</span></h3>
        {filled.length === 0 ? <p className={styles.muted}>订单号、SN、购买渠道等信息出现后会自动填入这里。</p> : (
          <dl className={styles.slots}>
            {filled.map((s) => (
              <div key={s.key} data-verified={s.verified || undefined}>
                <dt>{s.label}</dt>
                <dd><span className={styles.value}>{s.value}</span>{s.source && <small>{s.source}</small>}</dd>
              </div>
            ))}
          </dl>
        )}
        {(info.missing.length > 0 || (!empty && open.length > 0)) && (
          <ul className={styles.missing} aria-label="还未收集">
            {info.missing.map((m) => <li key={m} data-required>{m}</li>)}
            {open.filter((s) => !info.missing.some((m) => m.includes(s.label))).map((s) => <li key={s.key}>{s.label}</li>)}
          </ul>
        )}
      </section>

      <section aria-label="处理进度">
        <h3 className={styles.heading}>处理进度{info.caseLabel && <span>{info.caseLabel}</span>}</h3>
        <ol className={styles.route} aria-label="处理进度">
          {info.route.steps.map((step, i) => {
            const active = i === info.route.active;
            const done = info.route.active > i;
            return (
              <li key={step.key} data-state={active ? 'active' : done ? 'done' : 'idle'} aria-current={active ? 'step' : undefined}>
                <span>{step.label}</span>
                {active && <small>{step.hint}</small>}
              </li>
            );
          })}
        </ol>
      </section>

      {record.evidence.length > 0 && (
        <section>
          <h3 className={styles.heading}>官方依据</h3>
          <EvidenceDrawer items={record.evidence} highlight={highlight} primary={record.primary} />
        </section>
      )}

      {!empty && (record.summary || onNewIssue) && (
        <section className={styles.actions}>
          {record.summary && <button type="button" onClick={() => void copy()}>{copied ? '已复制' : '复制排查记录'}</button>}
          {onNewIssue && <button type="button" disabled={lockIssue} onClick={onNewIssue}>新问题</button>}
        </section>
      )}
    </div>
  );
}
