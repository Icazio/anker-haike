/** 案件页：坐席打开待处理案件时，交接摘要、核对字段、质保判断、执行与承诺记录都在页面上，不用翻聊天记录。 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, test, vi } from 'vitest';
import type { ServiceCase } from '../l3';
import type { SessionSnapshot } from '../../types/snapshot';

const detail = vi.fn();
const decide = vi.fn();
vi.mock('../l3', () => ({ l3Api: { detail: (...args: unknown[]) => detail(...args), decide: (...args: unknown[]) => decide(...args) } }));

const { CaseDetail } = await import('../pages/CaseDetail');

const CASE: ServiceCase = {
  case_id: 'c0ffee00-0000-4000-8000-000000000001', session_id: 's1', issue_id: 'i1', status: 'awaiting_approval',
  priority: 'normal', complaint_risk: false, revision: 7, opened_at: '2026-09-25T06:00:00Z', updated_at: '2026-09-25T06:05:00Z',
  owner: null, gate_result: null, snapshot: null,
  warranty: { status: 'in_warranty', basis: 'order', warranty_end: '2027-04-01', as_of: '2026-10-08', order_no: 'Anker016', reason: '订单 Anker016 质保至 2027-04-01' },
  external_refs: { order_no: 'Anker016' },
  proposal: { options: [{ option_id: 'replace', type: 'replace', title: '提交换货单', detail: '保内故障经排查仍未解决', source: 'sop' }], chosen_option_id: 'replace' },
  handoff_summary: {
    product: 'eufy Wearable Breast Pump S1 Pro', problem: '左侧无吸力', observations: ['图片：吸奶器机身'],
    steps: [{ step_id: 's1', title: '检查隔膜', feedback: 'not_solved' }, { step_id: 's2', title: '收到时按钮就坏了吗', answer: 'No' }],
    reason: { rule_id: 'R6', text: '提交条件未满足：缺少：产品 SN' },
    emotion: { level: 'calm', strategy: 'normal' },
    receipt: { status: 'order_verified', verified_facts: { order_no: 'Anker016', sku: 'T8D04121', amount: '349.99' } },
    draft_reply: '已整理订单、质保判断与证据，请核实后继续处理。',
  },
  executions: [{
    execution_id: 'e1', action_kind: 'service_order.create', status: 'failed', receipt: { status: 'failed' },
    error: { code: 'OutcomeUnverified', message: '办理结果暂时无法确认，为避免重复办理，已转人工核实。', recoverable: false, needs_review: true },
    gate_result: null, actions_version: 'a1', started_at: '2026-09-25T06:04:00Z',
  }],
  commitments: [{ text: '服务单已提交，人工处理中', source: 'receipt' }],
  events: [
    { seq: 1, type: 'status_changed', at: '2026-09-25T06:01:00Z', actor: 'system', payload: { from: 'proposing', to: 'awaiting_approval', reason: '需要人工审核' } },
    { seq: 2, type: 'request_changed', at: '2026-09-25T06:02:00Z', actor: 'user', payload: { input_id: 'x', quote: '还是改成退款吧', requested: 'refund' } },
  ],
};

function open(row: ServiceCase) {
  detail.mockResolvedValue(row);
  render(
    <MemoryRouter initialEntries={[`/desk/${row.case_id}`]}>
      <Routes><Route path="/desk/:id" element={<CaseDetail />} /></Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  detail.mockReset();
  decide.mockReset().mockResolvedValue({ run_id: 'r' });
  // jsdom 没有实现 <dialog> 的模态方法
  Object.defineProperty(HTMLDialogElement.prototype, 'showModal', { configurable: true, value: function (this: HTMLDialogElement) { this.setAttribute('open', ''); } });
  Object.defineProperty(HTMLDialogElement.prototype, 'close', { configurable: true, value: function (this: HTMLDialogElement) { this.removeAttribute('open'); } });
});

const sendButton = () => screen.getByRole('button', { name: /^按「.+」发送$/ });
const reply = () => screen.getByLabelText('发给客户的回复') as HTMLTextAreaElement;

describe('CaseDetail 人工决定区（spec_2026-10-16-1514 §4）', () => {
  test('横幅先问要决定什么，「发生了什么」只用案件里已有的数据', async () => {
    open(CASE);
    expect(await screen.findByRole('heading', { name: '需要你决定：是否按「换货单」为客户办理？' })).toBeInTheDocument();
    const banner = screen.getByRole('region', { name: '需要你决定' });
    expect(banner).toHaveTextContent('客户反馈 eufy Wearable Breast Pump S1 Pro：左侧无吸力。');
    expect(banner).toHaveTextContent('AI 已排查 2 步，转交原因：提交条件未满足：缺少：产品 SN。');
    expect(banner).toHaveTextContent('质保判断为保内（订单 Anker016 质保至 2027-04-01）。');
  });

  test('默认选中客户已确认的方案；换货发送前二次确认，复述客户会看到的回复', async () => {
    open(CASE);
    const approve = await screen.findByRole('radio', { name: /批准：换货单/ });
    expect(approve).toBeChecked();
    expect(approve.closest('label')).toHaveTextContent('客户已确认');
    // 客户消息里没有中文，模板默认英文
    expect(reply().value).toContain('arranged a replacement for you');
    fireEvent.click(sendButton());
    expect(decide).not.toHaveBeenCalled();
    const dialog = screen.getByRole('dialog', { name: '确认决定' });
    expect(dialog).toHaveTextContent('确认批准「换货单」？');
    expect(dialog).toHaveTextContent('批准后会按此方案提交服务单');
    expect(dialog).toHaveTextContent(`Reply from our team: ${reply().value}`);
    fireEvent.click(screen.getByRole('button', { name: '确认并发送' }));
    expect(decide).toHaveBeenCalledWith(CASE.case_id, expect.objectContaining({
      decision: 'approve', option_id: 'replace', expected_revision: 7, override_reason: null, edited_option: null, note: reply().value,
    }));
    expect(await screen.findByText('决定已保存并投递到会话。')).toBeInTheDocument();
  });

  test('切换方案与语言即换模板；占位没替换前不能发送，拒绝不附带方案、不弹确认', async () => {
    open(CASE);
    fireEvent.click(await screen.findByRole('radio', { name: /拒绝办理/ }));
    expect(reply().value).toContain('[reason]');
    expect(sendButton()).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: '中文' }));
    expect(reply().value).toBe('您好，我们核实后，这次暂时无法为您办理，原因是：【请填写原因】。');
    expect(screen.getByText(/请先替换 【请填写原因】/)).toBeInTheDocument();
    fireEvent.change(reply(), { target: { value: '您好，我们核实后，这次暂时无法为您办理，原因是：订单不在本店购买。' } });
    expect(sendButton()).toHaveTextContent('按「拒绝办理」发送');
    fireEvent.click(sendButton());
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(decide).toHaveBeenCalledWith(CASE.case_id, expect.objectContaining({ decision: 'reject', option_id: null, note: '您好，我们核实后，这次暂时无法为您办理，原因是：订单不在本店购买。' }));
  });

  test('过保仍要批准换货时才出现例外理由，必填', async () => {
    open({ ...CASE, warranty: { ...CASE.warranty!, status: 'out_of_warranty', reason: '订单 Anker011 已于 2026-01-01 过保' } });
    await screen.findByRole('radio', { name: /批准：换货单/ });
    expect(screen.getByRole('textbox', { name: /例外理由/ })).toBeRequired();
    expect(sendButton()).toBeDisabled();
    // 改选补充信息：不是批准，例外理由消失；切回批准时理由重新为空
    fireEvent.click(screen.getByRole('radio', { name: /请客户补充信息/ }));
    expect(screen.queryByRole('textbox', { name: /例外理由/ })).toBeNull();
    fireEvent.click(screen.getByRole('radio', { name: /批准：换货单/ }));
    fireEvent.change(screen.getByRole('textbox', { name: /例外理由/ }), { target: { value: '经销商确认购买日期有误' } });
    fireEvent.click(sendButton());
    expect(screen.getByRole('dialog', { name: '确认决定' })).toHaveTextContent('经销商确认购买日期有误');
    fireEvent.click(screen.getByRole('button', { name: '确认并发送' }));
    expect(decide).toHaveBeenCalledWith(CASE.case_id, expect.objectContaining({ decision: 'approve', override_reason: '经销商确认购买日期有误' }));
  });

  test('客户用中文提问时模板默认中文；页头可回到客户页', async () => {
    const snapshot: SessionSnapshot = {
      session_id: 's1', version: 3, stage: 'awaiting_human', substage: null, pending_input: null, active_run: null, last_error: null, cancelled_run: null,
      timeline: [{ kind: 'user_message', id: 'u1', text: '我的吸奶器左侧没有吸力', at: '2026-09-25T06:00:00Z' }],
    };
    open({ ...CASE, snapshot });
    await screen.findByRole('radio', { name: /批准：换货单/ });
    expect(reply().value).toBe('您好，我们已核实您的订单与问题，为您安排换货。处理结果会显示在本会话中。');
    expect(screen.getByRole('link', { name: '客户页 ↗' })).toHaveAttribute('href', '/?session=s1');
  });

  test('不在待审批时不显示横幅，表单禁用', async () => {
    open({ ...CASE, status: 'approved' });
    await screen.findByText('案件当前不在等待审核，决定表单不可用。');
    expect(screen.queryByRole('region', { name: '需要你决定' })).toBeNull();
    expect(screen.getByRole('radio', { name: /批准：换货单/ })).toBeDisabled();
  });
});

describe('CaseDetail', () => {
  test('交接摘要给出转人工原因、客户诉求、已做排查与核对字段', async () => {
    open(CASE);
    await waitFor(() => expect(screen.getByText('转人工原因：提交条件未满足：缺少：产品 SN')).toBeInTheDocument());
    expect(screen.getByText('左侧无吸力')).toBeInTheDocument();
    // 与对话侧摘要卡同款：操作卡记反馈，问句卡记回答
    expect(screen.getByText('检查隔膜（已操作，仍有问题）；收到时按钮就坏了吗（回答：No）')).toBeInTheDocument();
    expect(screen.getByText('订单金额')).toBeInTheDocument();
    expect(screen.getByText('349.99')).toBeInTheDocument();
    expect(screen.getByText('已整理订单、质保判断与证据，请核实后继续处理。')).toBeInTheDocument();
  });

  test('执行记录标出待人工核实，承诺带依据，事件时间线含客户变更原话', async () => {
    open(CASE);
    await waitFor(() => expect(screen.getByText('失败 · 待人工核实')).toBeInTheDocument());
    expect(screen.getByText('办理结果暂时无法确认，为避免重复办理，已转人工核实。')).toBeInTheDocument();
    expect(screen.getByText('服务单已提交，人工处理中')).toBeInTheDocument();
    expect(screen.getByText(/客户变更诉求：退款「还是改成退款吧」/)).toBeInTheDocument();
    expect(screen.getByText(/等待人工审核：需要人工审核/)).toBeInTheDocument();
  });

  test('质保判断写明依据与判断日期', async () => {
    open(CASE);
    expect((await screen.findAllByText(/订单 Anker016 质保至 2027-04-01/)).length).toBeGreaterThan(0);
    expect(screen.getByText(/依据：订单质保结束日期 · 按 2026-10-08 计/)).toBeInTheDocument();
  });

  test('执行前审查的结论与闸门第 5 项写在案件页上', async () => {
    const detail = '独立审查不一致：审查读到客户诉求是退款，候选是换货：「I just want my money back」';
    open({
      ...CASE,
      gate_result: { passed: false, fallback: 'await_human', checks: [{ name: 'review', passed: false, detail }] },
      events: [{ seq: 3, type: 'review_completed', at: '2026-09-25T06:03:00Z', actor: 'system',
                 payload: { outcome: 'mismatch', detail, snapshot_hash: 'abc123', premises: [] } }],
    });
    await waitFor(() => expect(screen.getByText(`执行前审查：${detail}`, { exact: false })).toBeInTheDocument());
    expect(screen.getByText(/独立审查/, { selector: 'p' })).toBeInTheDocument();
  });

  test('尚未交接的案件说明没有摘要', async () => {
    open({ ...CASE, handoff_summary: null, executions: [], commitments: [], events: [] });
    await waitFor(() => expect(screen.getByText('案件尚未交接人工，没有交接摘要。')).toBeInTheDocument());
    expect(screen.getByText('尚未执行办理动作。')).toBeInTheDocument();
  });
});
