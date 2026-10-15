# 执行前独立审查（合作伙伴「双向验证」最小版）

日期：2026-10-15。用户决定：按最小版做，放 authorize，闸门加第 5 项 review，审查模型换厂商。

## 背景

合作伙伴方案：Worker 提出退款 / 换货方案后、执行前接入独立审查模块，11 个阶段——案件输入 → 证据快照 → 上下文隔离 →
正向独立判断 → 候选结果 → 反向证明 → 证据绑定 → 反证检查 → 一致性门控 → 决策结果 → 后续动作，并沉淀决策档案。

- 正向：审查者看不到 Worker 的结论，只拿证据独立推一遍。
- 反向：从 Worker 的候选方案倒推，每个前提必须指向一条证据，并找反证。

与现有系统的对照：

| 阶段 | 现有 | 本次 |
|---|---|---|
| 1 案件输入 | case（`cases/service.py`） | 不变 |
| 2 证据快照 | `evidence.collect` 每次重算，不冻结 | 冻结快照 + 哈希，写进档案 |
| 3 上下文隔离 / 4 正向独立判断 | 无 | 新增审查模型任务 `remedy.review` |
| 5 候选结果 | `proposal.options` | 不变 |
| 6 反向证明 / 7 证据绑定 | 只有证据四件套带来源前缀 | 新增诉求、故障、产品三个前提的绑定 |
| 8 反证检查 | `vision_conflict`、`changed_request` | 审查模型给反证，代码核原话 |
| 9 一致性门控 | `AuthorizationGate` 四项 | 加第 5 项 `review` |
| 10 决策结果 / 11 后续动作 | `GateResult` → execute / await_human | 不变 |
| 决策档案 | `case_events` + `gate_result` | 新增 `review_completed` 事件 |

## 为什么只审 AI 产出的前提

问题：服务单类型、质保资格、证据清单由代码按 SOP 计算；AI 只产出前提——客户要什么、故障是否未解决、是哪个产品、照片是不是故障照。
真实出过的错都在这一层：

- 2026-10-09：改订单诉求被 `requested_type` 兜底成换货单（`l3.py` `requested_type` 注释）。
- 客户首问里的订单截图被当成故障照片，凑齐换货证据四件套（`evidence.py` 注释）。

方案：审查只覆盖 AI 前提；质保日期、证据是否齐、安全、幂等已经是闸门前四项，不再让模型复判（模型读错日期反而会拦下正常换货）。

## 范围

- 只审 `replace` / `refund`。`reship` / `carrier_investigation` 由包裹状态决定，review 项直接通过，detail 写明。
- 只在 `authorize`（客户确认后、提交服务单前）运行。
- 图片性质（单据 / 故障照）沿用读图结论（`document_image_ids`），本版不复审：审查链是非视觉模型，复审图片需要另一家视觉模型，相关性另议。

## 前提与证据绑定（反向证明）

| 前提 | 绑定到 | 谁判 |
|---|---|---|
| P1 诉求 | 客户原话 `request_quote`；或系统路径 `hardware_basis`（guide_exhausted / hardware_malfunction / physical_damage） | 审查模型给原话，代码核原话是否逐字出现 |
| P2 故障未解决 | 客户原话 `fault_quote` | 同上 |
| P3 产品 | 订单行 `order_line_sku` | 审查模型从订单行里选，代码按 PN 比对候选 SKU |
| P4 保内 | `warranty.basis` / `reason` | 代码（闸门 eligibility），只记入档案 |
| P5 SOP 证据 | `evidence.collect` 的来源串 | 代码（闸门 evidence），只记入档案 |

换货有两条来路，P1 分开处理：

- 客户主动要（`replacement_request` / `refund_request`）：审查模型应读出同一诉求并给原话。
- 排障走不通后系统给出换货（客户没明说要换）：审查模型读出 `none`，P1 绑定到 `hardware_basis`；客户已点确认卡（闸门 evidence 项）。

## 正向独立判断（上下文隔离）

审查模型只拿到：

- 本问题下客户的原话（当前输入 + 历史里 `role=user` 且 `issue_id` 相同的消息），`wrap_data` 包裹。
- 订单行（SKU + 描述），没有订单时为空。
- 一段 SOP 规则说明（换货 / 退款要客户诉求、故障未解决、在保）。

拿不到：意图分类、`requested_remedy`、方案、`hardware_basis`、诊断结论、读图结论、机器人回复。

输出（`ReviewJudgment`）：

- `customer_request`: `replace` | `refund` | `other_remedy` | `none`
- `request_quote`, `fault_unresolved`（true / false / null）, `fault_quote`
- `order_line_sku`（只能取订单行里的 SKU，或 null）
- `counter_evidence`: 最多 5 条 `{quote, against: request|fault|product|other, note}`

模型任务 `remedy.review`（加入 `KNOWN_TASKS`）。链不含 Worker 主位的厂商：

| 通道 | Worker 主位（intake / synthesize） | review 链 |
|---|---|---|
| domestic | deepseek-pro | `[qwen-max, glm]` |
| zhipu | glm / glm-v | `[qwen-max, deepseek]` |
| overseas | haiku / sonnet | `[gemini-flash]` |

`models/config.py` 一致性检查加一条：`remedy.review` 链上任何模型的厂商不得等于同通道 intake 或 diagnose.synthesize 首位的厂商。
预算 15 s：同日另一会话实测 qwen-max 在长提示下 p50 7.7 s、最长 13.1 s（models.yaml 2026-10-15.3）。
glm 只接住主位的快速失败（5xx / 格式错，或 cooldown 中被排到链尾）；主位慢到用完预算时记为不可用、转人工。
调用审查模型前 authorize 先发 `progress: execute`，客户端进度不停在「确认处理方案」。

## 一致性门控（第 5 项 review）

候选为 replace / refund 时，以下全部成立才通过：

1. P1：`customer_request == 候选类型` 且 `request_quote` 逐字出现在客户原话中；
   或候选为 replace、`customer_request == none`、`hardware_basis` 非空。
   `refund` 没有系统路径，必须是客户诉求。
2. P2：`fault_unresolved is True` 且 `fault_quote` 逐字出现。
3. P3：有订单且 `order_line_sku` 非空时，PN 与候选 SKU 一致；为空不判（后端 `_validate` 已核 SKU 属于订单）。
4. 反证：原话逐字出现的反证条目为 0；引用对不上的条目丢弃并计数，不算反证。

不通过时 detail 写具体差异（「审查读到客户要退款，候选是换货」「客户原话：…」），它会原样进转人工原因（`handoff_reason`）。

## 失败语义

| 情形 | review 项 | 理由 |
|---|---|---|
| 人工已批准（case 状态 `approved`） | 通过：人工已批准 | 否则 approve → authorize → review → await_human 循环 |
| 物流类候选 | 通过：不适用 | 由包裹状态决定 |
| `HAIKE_LLM=off`（router 为 None） | 通过：审查未启用 | 模型全局关闭时没有 AI 产出的前提可审；单测默认此状态 |
| router 存在但调用失败（超时、链耗尽、回放未命中） | 不通过 → 转人工 | 被审的就是 AI 结论；同「质保无法确认 → 人工」先例 |
| 前提未绑定 / 不一致 / 有反证 | 不通过 → 转人工 | 本模块目的 |

## 决策档案

`CaseService.record_review(case_id, payload)` 写一条 `review_completed` 事件：
`snapshot_hash`、候选类型与 SKU、`outcome`（passed / mismatch / unavailable / disabled / human_approved / not_applicable）、
正向结论、前提绑定列表、反证、丢弃的引用数、`model_used`、`lane`、`prompt_version`。
不调模型的情形（人工已批准、物流类、未启用）不写事件，只在 `gate_result` 里体现。

快照 = 审查模型输入 + Worker 声明（`requested_remedy`、`hardware_basis`、候选、SKU、订单号、质保结论、证据来源），
规范 JSON 的 sha256 前 16 位。

后台 `CaseRecords` 事件标签「执行前审查」，`GATE_TEXT` 加 `review: '独立审查'`。
案件页「提交检查」下加双向对照面板（`frontend/src/admin/components/ReviewPanel.tsx`）：前提 | 候选方案 | 审查独立读到 | 依据 | 结果，
外加反证、审查模型、快照哈希、不采信引用数。为让不一致的行也有依据，前提即使未绑定也记下核实过的客户原话（`source`）。

## 影响

- `GATE_CHECKS`、`config/actions.yaml` 的 `requires.checks` 同步加 `review`。`GateCheck.name` 是 `str`，不用重新生成 contracts。
- 单测默认 `HAIKE_LLM=off` → 审查未启用 → 现有测试行为不变。
- `inspection/harness.py` 内联模型配置要加 `remedy.review` 路由。
- 演示回放：T55 主线以换货单结尾，回放包没有 `remedy.review` 的录制 → 未命中 → 转人工。
  离线 `make replay-all`（2026-10-15 实测）：7 个包在本改动之前就已全部 `replay_incompatible`
  （models_ver 录制 2026-10-13.2、kb_ver 因补充知识变化），本改动只多出 actions_version 一项。
  7 个包都需要 `make replay-record` 重录（真实模型调用，需用户同意）；重录后 T55 包含 `remedy.review` 的录制。
- 63 单真实评测不在本次运行范围。

## 不做（可选复杂度）

- 11 个独立模块或服务；多轮辩论式审查。
- 对代码算出的前提（质保日期、证据齐全）做模型复判。
- 图片复审。
- 按快照哈希缓存审查结果：`executing_failed` 重试会再调一次模型，量小。
- 出方案时（`_offer`）提前审查：每次出方案都变慢，且客户未必确认。

## 验证

- 单测（`tests/test_remedy_review.py`）：
  - 门控规则：诉求一致 / 不一致、系统路径 replace、refund 无诉求、原话核验失败、故障已解决、多行订单产品不一致、反证引用核验与丢弃。
  - 失败语义：未启用、调用失败、人工已批准、物流类。
  - authorize 集成（假模型）：不一致 → await_human，转人工原因含差异，`review_completed` 事件写入；一致 → 提交服务单。
- 注入错误：客户要退款但候选是换货、客户说已经好了、多行订单里客户说的是配件、反证原话。单据图当故障图本版不覆盖（见范围）。
- `make lint`、相关测试文件、前端 typecheck 与 `CaseRecords` 相关测试、离线 `make replay-all` 看影响面。
