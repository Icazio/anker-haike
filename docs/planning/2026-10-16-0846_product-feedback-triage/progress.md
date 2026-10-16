# 进度

## 2026-10-16 阶段 1：前端布局与 P0-S（分支 feat/product-feedback-ui，未提交）

已做（只动前端，后端未改）：

| plan 编号 | 改动 | 位置 |
| --- | --- | --- |
| B1 / C1 / D1 | 布局改为三栏：对话、信息收集、AI 工作流；配色、字体、卡片样式统一；1280 px 以下工作流收进浮层，900 px 以下两栏都收进浮层 | App.tsx、App.module.css、styles/tokens.css |
| C1 / C2 | 信息收集面板：产品图、型号与 PN；问题（RMA 表单只取 Problem Description）；订单号、质保、SN、购买渠道、物流单号、服务单号逐项填入，并标注来源；待补项 | components/InfoPanel.tsx、state/info.ts |
| B1 / B2 | AI 工作流面板：每次客户输入算一轮，按客户输入 → Leader → Worker（排障 / 查询 / 办理）→ 提交审查 → 人工排列，写出依据和输出；运行中显示当前在处理的角色 | components/WorkflowPanel.tsx、state/workflow.ts |
| D2 | 8 款产品的官网主图放在 public/products/；首屏产品墙和产品确认卡都显示图与 PN | lib/products.ts、ChatPane.tsx、ProductCard.tsx |
| D3 | 去掉常驻的「请求人工」按钮，以及 useSession.requestHuman | App.tsx、RecordPanel.tsx、useSession.ts |
| B3 | 转人工摘要卡加「在人工工作台处理此案件」，新标签页打开 /admin/desk/:case_id；观测台复用摘要卡时不显示 | SummaryCard.tsx、Timeline.tsx |
| B2 | 等凭证时给出同型号的演示订单，点一下填入；主办方数据里没有订单的型号（C20、S340）给出说明 | Composer.tsx、lib/products.ts |
| A4（只做了前端） | 首屏开场语改为客服口吻：「感谢您的咨询……先和您确认情况，再一步步引导您排查」。后端每个问题开头的开场消息还没做 | ChatPane.tsx |
| D4（顺带完成） | 首屏产品墙按 3 个品类排列 8 款产品，可选，点击后预填「我的 <产品>（PN）：」 | ChatPane.tsx |

验证结果：

- `npm run typecheck` 通过；`vitest` 29 个文件、248 个用例全部通过。新增 state/info.test.ts，覆盖信息面板、工作流和演示订单。
- 用浏览器回看了会话 51fde499（T55 全链路）和 932565c7。新跑了一个 C20 会话，到凭证环节时显示了说明文字。新跑了一个 S1 Pro 吸奶器会话，到凭证环节时显示了 Anker016 和 Anker015 两个演示订单。

验证中发现的问题（没有改）：

1. **只发订单号推进不了流程。** 新会话 c5b71a9e：排障 3 步都选「还没解决」之后进入索要凭证，客户发「Anker016」和「My order number is Anker016」，都回 `The applicable troubleshooting steps have been tried…`。
   - 节点轨迹：understand → dialogue → commit_issue，没有进入 service_context。
   - 原因：`route_entry`（graph.py:1548）在凭证阶段只在 `requested_remedy` 有值时才回到 service_context。由「排障未解决」进入凭证阶段时这个字段是空的，所以落到了 dialogue。
   - 影响：演示订单按钮填进去的订单号同样走不通。T55 能走完，是因为订单号写在了第一条消息里。
   - 这个问题属于 A1，需要改后端。
2. **React 重复 key 警告。** 会话 51fde499 的 tool 行与 execution_card 用了同一个 id（e5d0ce30…），Timeline 里出现重复 key。这次改动之前就存在。

## 2026-10-16 修复：排障未解决后只发订单号推进不了（上面问题 1，属 A1）

原因：从「排障未解决」进入订单质保判断时，`service_context` 已经建了 case，也把阶段停在 context（`stage=context`），但 `requested_remedy`（客户提出的退换诉求）是空的。下一轮发「Anker016」，意图被理解成 supplement。`understand` 和 `route_entry` 里「办理中补资料就回到 service_context」的条件都只认 `requested_remedy`，所以落进了 dialogue。会话 c5b71a9e 两轮的意图都是 supplement，可以印证。

改动：

- `graph.py` 新增 `_collecting_order_details`，「售后办理中」改为 `requested_remedy or case_id`，再加上阶段为 context 或待办是凭证卡这一条。`understand`（绑定订单号）和 `route_entry`（回到 service_context）两处共用它。apply_action 处理凭证确认时（`graph.py:818`）本来就是这个口径。
- 回归测试：`test_conversation_official_tickets.py::test_order_number_alone_after_failed_troubleshooting_checks_the_warranty`。T28 一步没解决后只发「Anker003」，断言进入质保判断，回复里出现在保信息。改之前失败（落到 dialogue）。

验证：

- 新测试改前失败、改后通过。相关 10 个测试文件 243 个用例通过；`test_conversation_*`、`test_sessions_*` 共 32 个文件 269 个用例通过；`make lint` 无报错。
- 经用户同意，用 `docker compose up -d --build --no-deps orchestrator` 只重建了 orchestrator，重建期间公网演示后端中断约 1 分钟。
- 浏览器测一单（会话 979a9f46，真实模型）：S1 Pro 吸奶器左侧没有吸力，5 步都选「还没解决」后进入索要凭证。点演示订单 Anker016 发送，回复 `I've checked: order Anker016 is under warranty until 2027-04-01`，并列出换货还缺的故障照片 / 视频和 SN。信息面板订单号显示「已核验」，进度推进到「确认处理方案」。控制台没有报错，后端没有异常日志。

复验中看到、没改的问题：订单核验通过、进入补照片和 SN 之后，输入框仍是凭证模式，演示订单按钮也还在显示。并进 A1 的凭证收集卡一起改。
