/** 执行前审查的双向对照（案件事件 review_completed，后端 app/actions/review.py）。
 *  正向：审查模型只看客户原话与订单行，独立读出的诉求 / 故障 / 产品；反向：候选方案每个前提绑定到哪条证据。 */
import type { ReactNode } from 'react';
import type { GateResult } from '../../types/events';
import { WARRANTY_TEXT } from '../format';
import type { CaseEvent } from '../l3';

const KIND_TEXT: Record<string, string> = { replace: '换货', refund: '退款' };
const REQUEST_TEXT: Record<string, string> = { replace: '换货', refund: '退款', other_remedy: '其他诉求（改单、补发、配件等）', none: '未提出具体诉求' };
const BASIS_TEXT: Record<string, string> = { guide_exhausted: '排障走完仍未解决', hardware_malfunction: '官方指引判定硬件故障', physical_damage: '客户描述可见损坏' };
const AGAINST_TEXT: Record<string, string> = { request: '诉求', fault: '故障', product: '产品', other: '其他' };
const OUTCOME: Record<string, { label: string; role: string }> = {
  passed: { label: '一致 → 放行提交', role: 'good' },
  mismatch: { label: '不一致 → 转人工', role: 'warning' },
  unavailable: { label: '审查模型不可用 → 转人工', role: 'critical' },
};

type Bag = Record<string, unknown>;
const bag = (v: unknown): Bag => (v && typeof v === 'object' && !Array.isArray(v) ? (v as Bag) : {});
const text = (v: unknown): string | null => (typeof v === 'string' ? v : null);
const list = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);

function evidence(source: unknown): ReactNode {
  const s = text(source);
  if (!s) return <span className="muted">—</span>;
  if (s.startsWith('customer:')) return `「${s.slice('customer:'.length)}」`;
  if (s.startsWith('basis:')) return `系统依据：${BASIS_TEXT[s.slice('basis:'.length)] ?? s.slice('basis:'.length)}`;
  if (s.startsWith('order:')) return <span className="mono">{s}</span>;
  return s;
}

function verdict(bound: unknown): ReactNode {
  if (bound === true) return <span style={{ color: 'var(--ok)' }}>✓ 一致</span>;
  if (bound === false) return <span style={{ color: 'var(--warning)' }}>× 不一致</span>;
  return <span className="muted">— 不判</span>;
}

export function ReviewPanel({ events = [], gate }: { events?: CaseEvent[]; gate: GateResult | null }) {
  const reviews = events.filter((e) => e.type === 'review_completed');
  const latest = reviews.at(-1);
  if (!latest) {
    const check = gate?.checks.find((c) => c.name === 'review');
    return (
      <section aria-label="执行前审查" style={{ marginTop: 14 }}>
        <h3 className="sub" style={{ fontWeight: 600 }}>执行前审查</h3>
        <p className="muted" style={{ fontSize: 12.5 }}>{check ? `未调用审查模型：${check.detail}` : '尚未进行执行前审查。'}</p>
      </section>
    );
  }
  const p = latest.payload;
  const snapshot = bag(p.snapshot);
  const input = bag(snapshot.reviewer_input);
  const claims = bag(snapshot.worker_claims);
  const judgment = bag(p.judgment);
  const premises = new Map(list(p.premises).map((x) => [text(bag(x).premise) ?? '', bag(x)]));
  const lines = list(input.order_lines);
  const outcome = OUTCOME[text(p.outcome) ?? ''] ?? { label: text(p.outcome) ?? '—', role: 'neutral' };
  const fault = judgment.fault_unresolved;
  const rows: { name: string; candidate: ReactNode; found: ReactNode; premise: Bag }[] = [
    {
      name: '诉求', candidate: KIND_TEXT[text(claims.kind) ?? ''] ?? text(claims.kind) ?? '—',
      found: REQUEST_TEXT[text(judgment.customer_request) ?? ''] ?? '—', premise: premises.get('request') ?? {},
    },
    {
      name: '故障', candidate: '未解决',
      found: fault === true ? '未解决' : fault === false ? '已解决' : '看不出', premise: premises.get('fault') ?? {},
    },
    {
      name: '产品', candidate: <span className="mono">{text(claims.sku) ?? '—'}</span>,
      found: text(judgment.order_line_sku) ? <span className="mono">{text(judgment.order_line_sku)}</span> : lines.length > 1 ? '未指明' : '单行订单不比',
      premise: premises.get('product') ?? {},
    },
    {
      name: '质保', candidate: WARRANTY_TEXT[text(bag(claims.warranty).status) ?? ''] ?? '—',
      found: <span className="muted">由闸门判定</span>, premise: premises.get('warranty') ?? {},
    },
  ];
  const counter = list(p.counter_evidence).map(bag);
  const dropped = typeof p.dropped_quotes === 'number' ? p.dropped_quotes : 0;
  const hash = text(p.snapshot_hash) ?? '';

  return (
    <section aria-label="执行前审查" style={{ marginTop: 14 }}>
      <h3 className="sub" style={{ fontWeight: 600, display: 'flex', gap: 10, alignItems: 'center' }}>
        执行前审查
        <span className="badge" style={{ color: 'var(--text)' }}><i className={`role-${outcome.role}`} />{outcome.label}</span>
      </h3>
      <p className="muted" style={{ fontSize: 12, margin: '0 0 8px' }}>
        审查模型只看客户原话（{list(input.customer_texts).length} 条）与订单行（{lines.length} 行），看不到意图判断、方案和诊断结论。
      </p>
      {text(p.outcome) === 'unavailable' ? (
        <p className="notice">{text(p.detail)}</p>
      ) : (
        <div className="scroll-x">
          <table className="data" aria-label="双向对照">
            <thead><tr><th>前提</th><th>候选方案</th><th>审查独立读到</th><th>依据</th><th>结果</th></tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.name}>
                  <td>{r.name}</td><td>{r.candidate}</td><td>{r.found}</td>
                  <td>{evidence(r.premise.source)}</td><td style={{ whiteSpace: 'nowrap' }}>{verdict(r.premise.bound)}</td>
                </tr>
              ))}
              <tr>
                <td>反证</td>
                <td colSpan={4}>
                  {counter.length ? counter.map((c, i) => (
                    <div key={i}>「{text(c.quote)}」<span className="muted">（{AGAINST_TEXT[text(c.against) ?? ''] ?? text(c.against)}{text(c.note) ? ` · ${text(c.note)}` : ''}）</span></div>
                  )) : <span className="muted">无</span>}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      )}
      <p className="muted" style={{ fontSize: 11.5, margin: '6px 0 0' }}>
        审查模型 {text(p.model_used) ?? '—'} · 快照 <span className="mono">{hash.slice(0, 8)}</span> · 不采信引用 {dropped} 条
        {reviews.length > 1 ? ` · 共 ${reviews.length} 次审查，显示最近一次` : ''}
      </p>
    </section>
  );
}
