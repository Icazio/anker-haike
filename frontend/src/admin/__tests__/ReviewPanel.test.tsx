/** 执行前审查面板：坐席能看到候选方案与审查模型独立读到的结论逐项对照，以及每项依据的原话。 */
import { render, screen, within } from '@testing-library/react';
import { describe, expect, test } from 'vitest';
import { ReviewPanel } from '../components/ReviewPanel';
import type { CaseEvent } from '../l3';

const SNAPSHOT = {
  reviewer_input: {
    customer_texts: ['Order No: Anker016. It works fine now. I still want a replacement just in case.', 'SN: T8D04121ABCD0002'],
    order_lines: [{ sku: 'T8D04121', description: 'eufy S1 Pro breast pump' }],
  },
  worker_claims: {
    kind: 'replace', sku: 'T8D04121', order_no: 'Anker016', basis: null, requested_remedy: 'replace',
    warranty: { status: 'in_warranty', reason: '订单 Anker016 质保至 2027-04-01' }, evidence: {},
  },
};

function review(payload: Record<string, unknown>, seq = 1): CaseEvent {
  return { seq, type: 'review_completed', at: '2026-10-15T08:00:00Z', actor: 'system', payload: { snapshot: SNAPSHOT, snapshot_hash: '3f9c0a1b2c3d4e5f', model_used: 'qwen3.8-max', dropped_quotes: 0, ...payload } };
}

const MISMATCH = review({
  outcome: 'mismatch',
  detail: '独立审查不一致：审查读到故障已经解决：「It works fine now」',
  judgment: { customer_request: 'replace', request_quote: 'I still want a replacement', fault_unresolved: false, fault_quote: 'It works fine now', order_line_sku: null, counter_evidence: [] },
  premises: [
    { premise: 'request', bound: true, source: 'customer:I still want a replacement', judged_by: 'review' },
    { premise: 'fault', bound: false, source: 'customer:It works fine now', judged_by: 'review' },
    { premise: 'product', bound: null, source: 'order:Anker016/T8D04121', judged_by: 'review' },
    { premise: 'warranty', bound: true, source: '订单 Anker016 质保至 2027-04-01', judged_by: 'gate' },
    { premise: 'evidence', bound: null, source: {}, judged_by: 'gate' },
  ],
  counter_evidence: [{ quote: 'It works fine now', against: 'fault', note: '客户说已恢复' }],
});

function row(name: string) {
  return screen.getByRole('row', { name: new RegExp(`^${name}`) });
}

describe('ReviewPanel', () => {
  test('逐项对照候选方案与审查独立读到的结论，不一致的前提带原话', () => {
    render(<ReviewPanel events={[MISMATCH]} gate={null} />);
    expect(screen.getByText('不一致 → 转人工')).toBeInTheDocument();
    expect(screen.getByText(/审查模型只看客户原话（2 条）与订单行（1 行）/)).toBeInTheDocument();
    expect(within(row('诉求')).getByText('「I still want a replacement」')).toBeInTheDocument();
    expect(within(row('诉求')).getByText('✓ 一致')).toBeInTheDocument();
    expect(within(row('故障')).getByText('已解决')).toBeInTheDocument();
    expect(within(row('故障')).getByText('「It works fine now」')).toBeInTheDocument();
    expect(within(row('故障')).getByText('× 不一致')).toBeInTheDocument();
    expect(within(row('产品')).getByText('单行订单不比')).toBeInTheDocument();
    expect(within(row('产品')).getByText('— 不判')).toBeInTheDocument();
    expect(within(row('质保')).getByText('保内')).toBeInTheDocument();
    expect(within(row('反证')).getByText(/客户说已恢复/)).toBeInTheDocument();
    expect(screen.getByText(/审查模型 qwen3.8-max/)).toHaveTextContent('快照 3f9c0a1b · 不采信引用 0 条');
  });

  test('系统给出的换货绑定到排障依据；多次审查显示最近一次', () => {
    const passed = review({
      outcome: 'passed', detail: '独立审查一致',
      judgment: { customer_request: 'none', fault_unresolved: true, fault_quote: 'still no suction', order_line_sku: null, counter_evidence: [] },
      premises: [
        { premise: 'request', bound: true, source: 'basis:guide_exhausted', judged_by: 'review' },
        { premise: 'fault', bound: true, source: 'customer:still no suction', judged_by: 'review' },
      ],
      counter_evidence: [],
    }, 2);
    render(<ReviewPanel events={[MISMATCH, passed]} gate={null} />);
    expect(screen.getByText('一致 → 放行提交')).toBeInTheDocument();
    expect(within(row('诉求')).getByText('未提出具体诉求')).toBeInTheDocument();
    expect(within(row('诉求')).getByText('系统依据：排障走完仍未解决')).toBeInTheDocument();
    expect(within(row('反证')).getByText('无')).toBeInTheDocument();
    expect(screen.getByText(/共 2 次审查，显示最近一次/)).toBeInTheDocument();
  });

  test('审查模型不可用时说明转人工，不画对照表', () => {
    render(<ReviewPanel events={[review({ outcome: 'unavailable', detail: '独立审查模型不可用，需人工复核' })]} gate={null} />);
    expect(screen.getByText('审查模型不可用 → 转人工')).toBeInTheDocument();
    expect(screen.getByText('独立审查模型不可用，需人工复核')).toBeInTheDocument();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });

  test('没有调用审查模型时给出闸门第 5 项的原因', () => {
    const gate = { passed: true, fallback: null, checks: [{ name: 'review', passed: true, detail: '人工已批准，不再审查' }] };
    render(<ReviewPanel events={[]} gate={gate} />);
    expect(screen.getByText('未调用审查模型：人工已批准，不再审查')).toBeInTheDocument();
  });
});
