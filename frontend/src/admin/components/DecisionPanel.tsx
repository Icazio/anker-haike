/** 案件页「人工决定」：先说要决定什么，再给方案单选、随方案切换的回复模板、必要时的例外理由与二次确认。
 *  提交走 POST /admin/api/cases/{id}/decision；note 会以「Reply from our team: 」开头发给客户（sessions/l3.py apply_human_decision）。 */
import { useEffect, useRef, useState } from 'react';
import type { ProposalOption } from '../../types/events';
import type { SessionSnapshot } from '../../types/snapshot';
import { GATE_TEXT, SERVICE_TYPE_TEXT, WARRANTY_TEXT } from '../format';
import type { DecisionRequest, ServiceCase } from '../l3';

type Lang = 'zh' | 'en';
type Plan = { key: string; decision: DecisionRequest['decision']; option: ProposalOption | null; name: string; condition: string; tag: string | null };

/** 后端 apply_human_decision 固定加的前缀，界面上写明客户看到的是什么 */
const REPLY_PREFIX = 'Reply from our team: ';
const NOTE_MAX = 2000;
/** 批准后会办货或动钱的方案：发送前二次确认 */
const HIGH_RISK = new Set(['replace', 'refund', 'reship']);
const TYPE_WORD: Record<string, Record<Lang, string>> = {
  replace: { zh: '换货', en: 'a replacement' },
  refund: { zh: '退款', en: 'a refund' },
  reship: { zh: '补发', en: 'a reshipment' },
  carrier_investigation: { zh: '承运商调查', en: 'a carrier investigation' },
};

const typeName = (o: ProposalOption) => SERVICE_TYPE_TEXT[o.type] ?? o.title;

function plansOf(row: ServiceCase): Plan[] {
  const options = row.proposal?.options ?? [];
  const chosen = row.proposal?.chosen_option_id ?? null;
  const approve: Plan[] = options.length
    ? options.map((o) => ({ key: `approve:${o.option_id}`, decision: 'approve', option: o, name: `批准：${typeName(o)}`, condition: o.detail ?? o.title, tag: o.option_id === chosen ? '客户已确认' : null }))
    : [{ key: 'approve', decision: 'approve', option: null, name: '批准', condition: '不涉及服务单，回复客户后结束本次审核', tag: null }];
  return [
    ...approve,
    { key: 'reject', decision: 'reject', option: null, name: '拒绝办理', condition: '不符合办理条件，告知客户原因', tag: null },
    { key: 'request_info', decision: 'request_info', option: null, name: '请客户补充信息', condition: '缺少办理所需的材料或信息，客户补充后继续', tag: null },
  ];
}

/** 回复模板。blank 是必须由坐席替换的占位，没替换前不能发送。 */
function template(plan: Plan, lang: Lang): { text: string; blank: string | null } {
  const word = plan.option ? TYPE_WORD[plan.option.type]?.[lang] ?? plan.option.title : null;
  if (plan.decision === 'approve') {
    return {
      blank: null,
      text: lang === 'zh'
        ? `您好，我们已核实您的订单与问题，${word ? `为您安排${word}` : '会按核实结果为您处理'}。处理结果会显示在本会话中。`
        : `We've reviewed your case${word ? ` and arranged ${word} for you` : ' and will proceed accordingly'}. Updates will appear in this conversation.`,
    };
  }
  if (plan.decision === 'reject') {
    const blank = lang === 'zh' ? '【请填写原因】' : '[reason]';
    return { blank, text: lang === 'zh' ? `您好，我们核实后，这次暂时无法为您办理，原因是：${blank}。` : `After reviewing your case, we're unable to proceed this time because ${blank}.` };
  }
  const blank = lang === 'zh' ? '【请填写需要补充的内容】' : '[what we need]';
  return { blank, text: lang === 'zh' ? `您好，为了继续为您处理，还需要您补充：${blank}。可以直接在本会话回复或上传图片。` : `To continue with your case, we need ${blank}. You can reply or upload photos in this conversation.` };
}

/** 客户消息里出现中文就默认中文回复，否则英文（后端目前统一英文答复，见 10-16 反馈 A3） */
function customerLang(snapshot: SessionSnapshot | null | undefined): Lang {
  return (snapshot?.timeline ?? []).some((t) => t.kind === 'user_message' && /[一-鿿]/.test(t.text)) ? 'zh' : 'en';
}

/** 与后端 cases/service.py 的校验一致：过保或非授权经销商仍要批准换货 / 退款，必须写例外理由 */
function needsOverride(row: ServiceCase, plan: Plan): boolean {
  return plan.decision === 'approve' && !!plan.option && ['replace', 'refund'].includes(plan.option.type) && !!row.warranty && row.warranty.status !== 'in_warranty';
}

function defaultKey(plans: Plan[]): string {
  return (plans.find((p) => p.tag) ?? plans[0]!).key;
}

/** 决定横幅：标题是要坐席回答的问题；「发生了什么」每句只用案件里已有的数据，没有就不写。 */
export function DecisionBanner({ row }: { row: ServiceCase }) {
  const options = row.proposal?.options ?? [];
  const question = options.length === 1 ? `是否按「${typeName(options[0]!)}」为客户办理？` : options.length > 1 ? '为客户办理哪个方案？' : '怎么答复客户？';
  const s = row.handoff_summary;
  const gate = row.gate_result;
  const failed = gate?.checks.filter((c) => !c.passed).map((c) => GATE_TEXT[c.name] ?? c.name) ?? [];
  const judged = [
    row.warranty ? `质保判断为${WARRANTY_TEXT[row.warranty.status] ?? row.warranty.status}（${row.warranty.reason}）` : null,
    gate ? `提交检查 ${gate.checks.length - failed.length}/${gate.checks.length} 项通过${failed.length ? `，未通过：${failed.join('、')}` : ''}` : null,
  ].filter((x): x is string => x !== null);
  const happened = [
    s ? `客户反馈 ${s.product}：${s.problem}。` : null,
    s ? `${s.steps?.length ? `AI 已排查 ${s.steps.length} 步，` : ''}转交原因：${s.reason.text}。` : null,
    judged.length ? `${judged.join('；')}。` : null,
  ].filter((x): x is string => x !== null);
  return (
    <section className="decision-banner" aria-label="需要你决定">
      <h2>需要你决定：{question}</h2>
      {happened.length > 0 && (
        <div className="decision-happened"><b>发生了什么</b><ol>{happened.map((line) => <li key={line}>{line}</li>)}</ol></div>
      )}
    </section>
  );
}

function ConfirmSheet({ option, reason, note, submitted, onCancel, onConfirm }: { option: ProposalOption; reason: string | null; note: string; submitted: boolean; onCancel: () => void; onConfirm: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => { ref.current?.showModal(); }, []);
  return (
    <dialog className="sheet" ref={ref} onClose={onCancel} aria-label="确认决定">
      <h3>确认批准「{typeName(option)}」？</h3>
      <p style={{ fontSize: 13, margin: '0 0 10px' }}>{submitted ? '服务单已提交，批准后按此结论回复客户。' : '批准后会按此方案提交服务单，并把下面的回复发给客户。'}</p>
      {reason && <><div className="muted" style={{ fontSize: 12 }}>例外理由（会记入案件记录）</div><p className="notice">{reason}</p></>}
      <div className="muted" style={{ fontSize: 12 }}>客户会看到</div>
      <p className="notice" data-kind="confirm-reply">{REPLY_PREFIX}{note}</p>
      <div className="sheet-actions">
        <button type="button" className="btn" onClick={onCancel}>取消</button>
        <button type="button" className="btn" data-variant="primary" onClick={onConfirm}>确认并发送</button>
      </div>
    </dialog>
  );
}

/** 方案单选 → 回复随之切换 → 一个发送按钮。父组件按 revision 给 key，案件刷新后表单重建。 */
export function DecisionPanel({ row, busy, onDecide }: { row: ServiceCase; busy: boolean; onDecide: (body: DecisionRequest) => void }) {
  const plans = plansOf(row);
  const [key, setKey] = useState(() => defaultKey(plans));
  const [lang, setLang] = useState<Lang>(() => customerLang(row.snapshot));
  const plan = plans.find((p) => p.key === key) ?? plans[0]!;
  const [note, setNote] = useState(() => template(plan, lang).text);
  const [override, setOverride] = useState('');
  const [confirming, setConfirming] = useState(false);
  const blank = template(plan, lang).blank;
  const exception = needsOverride(row, plan);
  const ready = !!note.trim() && note.length <= NOTE_MAX && !(blank && note.includes(blank)) && (!exception || !!override.trim());
  const open = row.status === 'awaiting_approval';

  // 切方案或语言即换模板：沿用上一方案的措辞会把「批准」的话发给被拒绝的客户
  function choose(nextKey: string, nextLang: Lang) {
    const next = plans.find((p) => p.key === nextKey) ?? plans[0]!;
    setKey(next.key);
    setLang(nextLang);
    setNote(template(next, nextLang).text);
    setOverride('');
  }
  function send() {
    setConfirming(false);
    onDecide({
      decision_id: crypto.randomUUID(), expected_revision: row.revision, decision: plan.decision,
      option_id: plan.option?.option_id ?? null, note: note.trim(), override_reason: exception ? override.trim() : null, edited_option: null,
    });
  }

  return (
    <form className="decision" onSubmit={(e) => { e.preventDefault(); if (!ready) return; if (plan.decision === 'approve' && plan.option && HIGH_RISK.has(plan.option.type)) setConfirming(true); else send(); }}>
      <fieldset disabled={busy || !open}>
        <legend className="sub">选一个方案，下面的回复会跟着变</legend>
        <div className="plans" role="radiogroup" aria-label="处理方案">
          {plans.map((p) => (
            <label key={p.key} className="plan" data-selected={p.key === plan.key || undefined}>
              <input type="radio" name="plan" value={p.key} checked={p.key === plan.key} onChange={() => choose(p.key, lang)} />
              <span><b>{p.name}</b>{p.tag && <span className="tag">{p.tag}</span>}<small>{p.condition}</small></span>
            </label>
          ))}
        </div>
        {exception && (
          <label>例外理由（必填，会记入案件记录）
            <small className="muted">质保判断为{WARRANTY_TEXT[row.warranty!.status] ?? row.warranty!.status}，按 SOP 不办理{typeName(plan.option!)}；仍要办理需写明理由。</small>
            <textarea required value={override} onChange={(e) => setOverride(e.target.value)} placeholder="例如：客户提供了新的购买凭证，经销商已确认授权。" />
          </label>
        )}
        {/* 不用 label 包：label 会把第一个可标注的后代（语言按钮）当成关联控件，点标题就切了语言 */}
        <div className="field">
          <span className="reply-head">发给客户的回复
            <span className="chips" role="group" aria-label="回复语言">
              {(['zh', 'en'] as const).map((l) => <button key={l} type="button" className="chip" aria-pressed={lang === l} onClick={() => choose(plan.key, l)}>{l === 'zh' ? '中文' : 'English'}</button>)}
            </span>
          </span>
          <textarea required maxLength={NOTE_MAX} value={note} onChange={(e) => setNote(e.target.value)} aria-label="发给客户的回复" />
          <small className="muted">客户会看到「{REPLY_PREFIX.trim()}」开头的这段话。{blank && note.includes(blank) ? `请先替换 ${blank}。` : ''}</small>
        </div>
        <button className="btn" data-variant="primary" disabled={!ready}>按「{plan.name}」发送</button>
      </fieldset>
      {confirming && plan.option && <ConfirmSheet option={plan.option} reason={exception ? override.trim() : null} note={note.trim()} submitted={!!row.external_refs.service_order_no} onCancel={() => setConfirming(false)} onConfirm={send} />}
    </form>
  );
}
