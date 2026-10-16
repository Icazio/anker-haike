import { useCallback, useEffect, useRef, useState } from 'react';
import { type OfficialTicket, ticketFiles } from './api/officialTickets';
import { HeaderBar } from './components/HeaderBar';
import { ChatPane } from './components/ChatPane';
import { Composer } from './components/Composer';
import { PendingCard, Timeline } from './components/Timeline';
import { InfoPanel } from './components/InfoPanel';
import { WorkflowPanel } from './components/WorkflowPanel';
import { Toast } from './components/Toast';
import { SessionSwitcher } from './components/SessionSwitcher';
import { useHealth } from './state/useHealth';
import { useSession } from './state/useSession';
import { deriveInfo } from './state/info';
import { demoOrdersFor } from './lib/products';
import cardStyles from './components/Cards.module.css';
import styles from './App.module.css';

type SidePane = 'info' | 'flow';

/** 三栏：左对话（流 + 停靠待办），中信息收集，右 AI 工作流（演示视角）。
 *  窄屏两个侧栏折成一条记录条，点开为浮层，在「信息 / 工作流」间切换。
 *  不提供常驻的「请求人工」按钮：客户可以直接说「转人工」，情绪升级与方案卡上也有人工出口（plan §D3）。 */
export function App() {
  const health = useHealth();
  const session = useSession();
  const { state } = session;
  const [draft, setDraft] = useState('');
  const [hover, setHover] = useState<string[]>([]);
  const [overlay, setOverlay] = useState<SidePane | null>(null);
  const composerRef = useRef<HTMLTextAreaElement>(null);
  const streamRef = useRef<HTMLDivElement>(null);
  const busy = state.ui === 'streaming' || state.ui === 'tool_running' || state.ui === 'recovering';
  const hasHistory = state.timeline.length > 0;
  const pendingKind = state.pendingInput?.kind ?? null;
  const pendingCard = state.ui === 'awaiting_input' ? state.pendingInput?.card_id ?? null : null;
  const receiptUpload = pendingKind === 'upload_receipt';
  const composerContext = state.pendingInput?.card_id ?? 'message';
  useEffect(() => { setDraft(''); }, [composerContext]);

  // 新内容在下方：时间线变化时把流滚到底，待办卡本身在 dock 里不需要滚动去找
  const lastKey = state.timeline.length ? `${state.timeline.length}:${state.timeline[state.timeline.length - 1]?.kind}` : '';
  useEffect(() => {
    const el = streamRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [lastKey, state.ui]);

  const [presetFiles, setPresetFiles] = useState<File[] | null>(null);
  // 连续换工单时，只认最后一次选择；先返回的旧附件丢弃
  const ticketSeq = useRef(0);
  const loadTicket = useCallback(async (ticket: OfficialTicket) => {
    const seq = ++ticketSeq.current;
    pickPrompt(ticket.body);
    // 无附件的工单传空数组，清掉上一单留下的图
    const files = ticket.attachments.length ? await ticketFiles(ticket) : [];
    if (seq === ticketSeq.current) setPresetFiles(files);
  }, []);
  // 换会话时输入框整体重建：草稿、附件、未取用的预置图都不带进新会话
  const [composerEpoch, setComposerEpoch] = useState(0);
  function resetComposer() {
    ticketSeq.current++;
    setPresetFiles(null);
    setDraft('');
    setComposerEpoch((n) => n + 1);
  }

  function pickPrompt(text: string) {
    setDraft(text);
    composerRef.current?.focus();
    requestAnimationFrame(() => {
      const input = composerRef.current;
      if (!input) return;
      input.setSelectionRange(input.value.length, input.value.length);
    });
  }

  /** 新建会话按钮与 logo 共用：空白会话不动作；处理中或有待回答卡片先确认中断。 */
  function goHome() {
    if (!state.id) return;
    const interruptible = busy || state.pendingInput !== null || state.activeRun !== null;
    if (interruptible && !window.confirm('当前排查会中断，确定开始新会话？旧会话仍可从列表切回。')) return;
    setOverlay(null);
    resetComposer();
    void session.startNew();
  }

  const onAction = (kind: Parameters<typeof session.act>[0]['kind'], payload: Record<string, unknown>) => void session.act({ kind, payload });
  const onIssueAction = (kind: 'new_issue' | 'resume_issue', target_issue_id?: string) => void session.act({ kind, target_issue_id });
  const info = deriveInfo(state);
  const stripText = [info.product?.name ?? (info.problem ? info.problem.slice(0, 24) : '新会话'), info.route.label, info.tried.total ? `已排查 ${info.tried.done} 步` : null].filter(Boolean).join('，');

  const infoPanel = (
    <InfoPanel state={state} highlight={hover} busy={state.pendingActionId !== null}
      onNewIssue={state.id ? () => onIssueAction('new_issue') : undefined}
      onResumeIssue={(id) => onIssueAction('resume_issue', id)} />
  );

  return (
    <div className={styles.app} data-ui={state.ui}>
      <a href="#main" className={styles.skip}>跳到主要内容</a>
      <HeaderBar {...health} onHome={goHome}>
        <SessionSwitcher
          currentId={state.id}
          recent={session.recent}
          busy={busy}
          onNew={goHome}
          onSwitch={(id) => { resetComposer(); void session.switchTo(id); }}
        />
      </HeaderBar>
      {hasHistory && (
        <div className={styles.strip}>
          <span className={styles.stripText}>{stripText}</span>
          <button type="button" className={styles.stripButton} onClick={() => setOverlay('info')} aria-expanded={overlay !== null}>信息与工作流</button>
        </div>
      )}
      <main id="main" className={styles.layout}>
        <section className={styles.conv} aria-label="智能售后对话">
          <div className={styles.stream} ref={streamRef}>
            {!hasHistory && <ChatPane onPick={pickPrompt} onLoadTicket={loadTicket} disabled={busy} />}
            <Timeline state={state} onAction={onAction} onHover={setHover} dockPending workbench />
            {state.stalled && busy && <p className={cardStyles.stallNote} role="status">仍在处理，请稍候…</p>}
            {busy && !state.stalled && <p className={cardStyles.sysRow} role="status">{state.ui === 'tool_running' ? '正在检索知识库…' : state.ui === 'recovering' ? '正在恢复连接…' : '正在处理…'}</p>}
            {state.ui === 'failed' && (
              <p className={styles.failed} role="status">这一轮没有完成。{state.id && <button type="button" onClick={() => void session.recover()}>恢复连接</button>}</p>
            )}
          </div>
          <div className={styles.dock}>
            {pendingCard && <PendingCard state={state} onAction={onAction} onHover={setHover} />}
            <Composer
              key={`${composerEpoch}:${composerContext}`}
              pendingKind={pendingKind}
              purpose={receiptUpload ? 'receipt' : 'fault'}
              onSkipReceipt={() => session.act({ kind: 'skip_receipt', payload: { reason: 'none' } })}
              inputRef={composerRef}
              value={draft}
              onChange={setDraft}
              offline={false}
              busy={busy || state.pendingActionId !== null}
              onSend={(text, files, purpose) => session.send(text, { files, purpose })}
              onCancel={state.activeRun ? () => void session.cancel() : undefined}
              presetFiles={presetFiles}
              onPresetConsumed={() => setPresetFiles(null)}
              demo={receiptUpload ? demoOrdersFor(info.product?.sku) : null}
            />
          </div>
        </section>
        <aside className={styles.info} aria-label="信息收集">{infoPanel}</aside>
        <aside className={styles.flow} aria-label="AI 工作流"><WorkflowPanel state={state} /></aside>
      </main>
      {overlay && (
        <div className={styles.overlay} role="dialog" aria-label={overlay === 'info' ? '信息收集' : 'AI 工作流'}>
          <div className={styles.overlayHead}>
            <div className={styles.tabs} role="tablist">
              <button type="button" role="tab" aria-selected={overlay === 'info'} onClick={() => setOverlay('info')}>信息收集</button>
              <button type="button" role="tab" aria-selected={overlay === 'flow'} onClick={() => setOverlay('flow')}>AI 工作流</button>
            </div>
            <button type="button" onClick={() => setOverlay(null)} aria-label="关闭">×</button>
          </div>
          {overlay === 'info' ? infoPanel : <WorkflowPanel state={state} />}
        </div>
      )}
      {state.error && <Toast message={state.error.message || '出现了一个错误'} recoverable={state.error.recoverable} onClose={session.clearError} />}
    </div>
  );
}
