# 多诉求：第一项转人工后，其余诉求不能悬空

来源：[63 单回测](../planning/2026-10-15-1417_official-63-retest/结论与问题分类.md) 第 2 节。

## 问题

系统先告诉客户"按 A → B 的顺序处理"，A 进人工后 B 一直 `pending`：客户没得到答复，交接摘要里也只有一行 `report_problem(pending)`，人工看不出该由谁处理。

| 工单 | A（转人工） | B（悬空） | 转人工路径 |
|---|---|---|---|
| T41 | 排障失败进质保 | 新插头何时到（logistics_query） | `summarize` |
| T49、T59 | 换货（无订单） | 泵 / 摄像头排障（report_problem） | `summarize` |
| T63 | 配件采购 | 清洁差排障（report_problem） | `hand_off_request` |

## 根因（两处）

1. `graph.summarize` 把当前任务记 `waiting_human` 后固定返回 `l3_route="commit_issue"`，不回 `advance_tasks`。只有 `hand_off_request` / `await_human` 经 `l3.waiting_human` 回队列（T9 正常就是走这条）。所以 T41 的物流查询连现有规则允许的推进都没得到。
2. `l3.advance_tasks` 的 round3 规则（46b1777）：等人工时只推进查询类任务，排障 / 办理留 `pending`，避免覆盖 `awaiting_human` 阶段。规则本身保留；但 `apply_human_decision` 之后也不恢复这些任务，于是它们永远没有下文。

## 方案（2026-10-15 用户选定"并入交接并告知"）

- `summarize`：案件进入 `awaiting_approval` 且队列里还有 `pending` 任务时，改走 `advance_tasks`（`task_outcome=waiting_human`），查询类任务照常推进。
- `tasks.carry_over`：等人工时推进不了的 `pending` 任务记 `waiting_human`，并写 `carried_by=<正在等人工的诉求>`。
- `advance_tasks`：没有可推进的任务、但有任务等人工时调用 `carry_over`；对客户说明"另一项诉求也放进同一个案件，由同事一起处理"，并重写交接摘要（【业务】待办里这些任务显示为 waiting_human）。
- `tasks.settle`：人工结论回来时，`carried_by` 该诉求的任务一起收尾（批准 / 驳回记 done，要求补充回 pending）。

- `consult`：等人工期间推进到的查询缺单号时，阶段保持 `awaiting_human`；查到"已送达 / 可补发"时只答事实，不另开补发 / 调查方案（同一案件不能同时等两份审批，包裹状态由 `advance_tasks` 已有分支并进交接摘要）。
- `guide` 撤回人工队列（`resume_diagnosis`）改用 `reopen_waiting`，避免随交接的任务一起变 active。

不做（可选复杂度）：人工结论后自动继续排障；配件采购 / 改单这类与设备无关的转人工期间放开排障（需处理排障进行中人工结论到达时阶段被覆盖）。

## 验证

- 单测：`carry_over` / `settle` 的队列语义。
- HTTP 回归：summarize 路径转人工后查询任务仍被回答（T41 形态）；T63 采购转人工后排障并入交接并告知；请人工后排障不推进但并入交接（更新 round3 测试断言）。
- 真实模型：用 `docs/planning/2026-10-15-1417_official-63-retest/run63.py` 重跑 T41、T49、T59、T63、T9。

## 结果（2026-10-15 15:30）

- 单测 1 条、HTTP 回归 2 条新增；round3 与 T63 两条既有回归按新语义更新断言（排障仍不推进，状态由 pending 改为随交接等人工）。相关 20 个测试文件 348 条通过，`make lint` 清零。
- 真实模型（进程内 harness，并发 3）：

| 工单 | 修复前（回测首轮） | 修复后 |
|---|---|---|
| T9 | 暂缓转人工 + 答物流 | 不变 |
| T41 | 物流诉求 pending，没有答复 | 转人工后"Next up: delivery status"，追问订单号；阶段仍为 awaiting_human |
| T49 | 排障 pending，没有答复 | 告知"also added your other request (device troubleshooting) to the same case"；两项 waiting_human |
| T63 | 排障 pending，没有答复 | 同 T49 |
| T59 | 排障 pending | 本次模型只读出投诉 + 换货，没有排障任务可并入；属意图识别波动，与本修复无关 |

复测时工作区另有并行会话（独立审查）未提交的改动，结果包含这些改动。
