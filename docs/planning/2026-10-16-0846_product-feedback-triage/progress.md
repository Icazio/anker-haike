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
