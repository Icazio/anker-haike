import { useEffect, useRef } from 'react';
import type { SessionState } from '../state/types';
import { deriveWorkflow, ROLE_LABELS, type FlowNode, type FlowTurn } from '../state/workflow';
import styles from './WorkflowPanel.module.css';

function Node({ node, live = false }: { node: FlowNode; live?: boolean }) {
  return (
    <li className={styles.node} data-role={node.role} data-live={live || undefined}>
      <span className={styles.role}>{ROLE_LABELS[node.role]}</span>
      <div className={styles.body}>
        <strong>{node.title}</strong>
        {node.lines.map((line) => <p key={line}>{line}</p>)}
      </div>
    </li>
  );
}

/** 一轮折叠后只留角色链，看得出这轮经过了谁；最新一轮展开到每个角色的输入、依据和输出。 */
function Turn({ turn, index, latest }: { turn: FlowTurn; index: number; latest: boolean }) {
  const input = turn.nodes.find((n) => n.role === 'input');
  const chain = turn.nodes.filter((n) => n.role !== 'input' && n.role !== 'reply').map((n) => ROLE_LABELS[n.role]);
  return (
    <details className={styles.turn} open={latest || undefined}>
      <summary>
        <span className={styles.turnNo}>第 {index + 1} 轮</span>
        <span className={styles.turnInput}>{input?.lines[0] ?? input?.title}</span>
        {!latest && chain.length > 0 && <span className={styles.chain}>{chain.join(' → ')}</span>}
      </summary>
      <ol className={styles.nodes}>
        {turn.nodes.filter((n) => n.role !== 'input').map((n) => <Node key={n.role} node={n} />)}
      </ol>
    </details>
  );
}

/** AI 工作流面板（演示视角）：每次客户输入后，Leader 怎么理解、交给哪个 Worker、Worker 依据什么输出了什么、提交前怎么审查。
 *  全部由时间线已有事件派生；意图名与情绪依据等内部判断要等后端公开事件（plan §B1 阶段 2）。 */
export function WorkflowPanel({ state }: { state: SessionState }) {
  const flow = deriveWorkflow(state);
  const listRef = useRef<HTMLDivElement>(null);
  const size = `${flow.turns.length}:${flow.turns.at(-1)?.nodes.reduce((n, x) => n + x.lines.length, 0) ?? 0}:${flow.running?.role ?? ''}`;
  // 只滚面板自己的列表；scrollIntoView 会连带滚动外层页面
  useEffect(() => { const el = listRef.current; if (el) el.scrollTop = el.scrollHeight; }, [size]);

  return (
    <div className={styles.panel} data-testid="workflow-panel">
      <header className={styles.head}>
        <h2>AI 工作流</h2>
        <p>Leader 理解与分派，Worker 依据官方知识与 SOP 办事，提交前独立审查</p>
      </header>
      {flow.turns.length === 0 && !flow.running ? (
        <ol className={styles.legend} aria-label="角色说明">
          {(['leader', 'diagnose', 'consult', 'service', 'review', 'human'] as const).map((role) => (
            <li key={role} data-role={role}><span className={styles.role}>{ROLE_LABELS[role]}</span>{LEGEND[role]}</li>
          ))}
        </ol>
      ) : (
        <div className={styles.turns} ref={listRef}>
          {flow.turns.map((turn, i) => <Turn key={turn.key} turn={turn} index={i} latest={i === flow.turns.length - 1} />)}
          {flow.running && (
            <ol className={styles.nodes} aria-live="polite">
              <Node node={flow.running} live />
            </ol>
          )}
        </div>
      )}
    </div>
  );
}

const LEGEND = {
  leader: '读懂客户这句话：诉求、产品、事实与情绪，决定交给谁',
  diagnose: '按官方 Q&A 一步步引导排障',
  consult: '查订单、物流与质保',
  service: '按售后 SOP 生成换货、退款、补发等方案',
  review: '提交前五项闸门，换货 / 退款再由另一家模型独立复核',
  human: '需要人工时整理交接摘要，进入人工工作台',
} as const;
