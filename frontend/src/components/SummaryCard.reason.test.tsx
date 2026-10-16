import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { EscalationSummary } from '../types/snapshot';
import { SummaryCard, summaryToText } from './SummaryCard';

const summary: EscalationSummary = {
  product: 'eufy X10 Pro Omni', problem: '不能启动', observations: ['放回基站后有充电提示（指示灯或语音）吗？没有充电提示'], hypotheses: ['无法启动或充电时的基站供电与充电检查'],
  steps: [
    { step_id: 's1', title: '检查基站供电与触点', feedback: 'not_solved' },
    { step_id: 's2', title: '放回基站观察充电', feedback: 'not_solved' },
  ],
  reason: { rule_id: 'R2', text: '已操作但未解决「检查基站供电与触点」、「放回基站观察充电」，现有资料没有进一步可执行的排查操作', cause: 'no_supported_followup' },
  emotion: { level: 'calm', strategy: 'normal' },
  receipt: { status: 'not_collected', verified_facts: {}, conflicts: [] },
  model_trace: [],
};

describe('SummaryCard 的真实结束原因（design §3.5）', () => {
  it('展示真实原因文字；prepared 不显示成已接入', () => {
    const { container } = render(<SummaryCard summary={summary} handoffStatus="prepared" />);
    expect(container.querySelector('[data-kind="end-reason"]')).toHaveTextContent('现有资料没有进一步可执行的排查操作');
    expect(container.querySelector('[data-kind="handoff-status"]')).toHaveTextContent('已整理记录，尚未接入人工');
    expect(summaryToText(summary)).toContain('放回基站观察充电（已操作，仍有问题）');
  });

  it('规则码与 cause 只在观测台（internal）显示，客户页不出现内部编号', () => {
    const { container, rerender } = render(<SummaryCard summary={summary} />);
    const reason = () => container.querySelector('[data-kind="end-reason"]');
    expect(reason()).not.toHaveTextContent('R2');
    expect(reason()).not.toHaveTextContent('no_supported_followup');
    rerender(<SummaryCard summary={summary} internal />);
    expect(reason()).toHaveTextContent('规则码 R2 · no_supported_followup');
  });

  it('「假设」是 AI 内部推断（缺故障名时是方案 ID），客户页不显示，观测台与复制文本保留', () => {
    const planIds: EscalationSummary = { ...summary, hypotheses: ['qa_rv_0270', 'qa_rv_0254'] };
    const { container, rerender } = render(<SummaryCard summary={planIds} />);
    expect(screen.queryByText('假设')).toBeNull();
    expect(container).not.toHaveTextContent('qa_rv_0270');
    rerender(<SummaryCard summary={planIds} internal />);
    expect(screen.getByText('假设')).toBeVisible();
    expect(summaryToText(planIds)).toContain('【假设】qa_rv_0270；qa_rv_0254');
  });

  it('待办诉求显示中文，复制文本仍与后端 summary_to_text 同款', () => {
    const withBusiness: EscalationSummary = {
      ...summary,
      business: { kind: 'device_fault', known: {}, missing: [], pending_requests: [
        { intent: 'refund_request', quote: '我要退款', status: 'waiting_human' },
        { intent: 'logistics_query', quote: '包裹到哪了', status: 'pending' },
        { intent: 'something_new', quote: '', status: 'active' },
      ] },
    };
    const { container } = render(<SummaryCard summary={withBusiness} />);
    expect(container.querySelector('[data-kind="business-pending"]')).toHaveTextContent('退款（等待人工）；查物流（待处理）；其他诉求（处理中）');
    expect(container).not.toHaveTextContent('refund_request');
    expect(summaryToText(withBusiness)).toContain('待办：refund_request(waiting_human)；logistics_query(pending)；something_new(active)');
  });

  it('无法操作的步骤在页面和剪贴板都保留真实反馈，不称为已执行', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal('navigator', { ...navigator, clipboard: { writeText } });
    const skipped: EscalationSummary = {
      ...summary,
      product: '扫地机器人（型号未确认）',
      problem: '扫地机回不了基站',
      observations: ['插上设备后没有输出反应'],
      hypotheses: ['输出接口或连接问题'],
      steps: [
        { step_id: 's1', title: '清洁基站充电触点', feedback: 'cannot_do' },
        { step_id: 's2', title: '更换数据线和被充设备测试', feedback: 'cannot_do' },
      ],
      reason: { rule_id: 'R2', text: '两项操作均无法完成，已整理排查记录', cause: 'no_supported_followup' },
    };
    const { container } = render(<SummaryCard summary={skipped} />);
    expect(screen.getByText('排查记录')).toBeVisible();
    expect(container).toHaveTextContent('清洁基站充电触点（无法操作）');
    expect(container).not.toHaveTextContent('已执行步骤');
    expect(container).not.toHaveTextContent('cannot_do');
    fireEvent.click(screen.getByRole('button', { name: '一键复制' }));
    await screen.findByText('已复制');
    expect(writeText).toHaveBeenCalledWith(summaryToText(skipped));
    expect(summaryToText(skipped)).toContain('【排查记录】清洁基站充电触点（无法操作）');
    expect(summaryToText(skipped)).not.toMatch(/已执行步骤|cannot_do/);
  });

  it('问句卡的回答写进排查记录，和操作反馈区分开（T26 清洁液使用史）', () => {
    const answered: EscalationSummary = {
      ...summary,
      steps: [
        { step_id: 's2', title: '检查注水口传感器镜片', feedback: 'not_solved' },
        { step_id: 's3', title: '是否往基站清水箱加过第三方清洁液', answer: 'Not sure' },
      ],
    };
    const { container } = render(<SummaryCard summary={answered} />);
    expect(container).toHaveTextContent('是否往基站清水箱加过第三方清洁液（回答：Not sure）');
    expect(summaryToText(answered)).toContain('【排查记录】检查注水口传感器镜片（已操作，仍有问题）；是否往基站清水箱加过第三方清洁液（回答：Not sure）');
  });

  it('accepted 才显示人工已接单', () => {
    const { container } = render(<SummaryCard summary={summary} handoffStatus="accepted" />);
    expect(container.querySelector('[data-kind="handoff-status"]')).toHaveTextContent('人工已接单');
  });
});
