# 官方 63 单回测：理解 / 选方案运行稳定性修复

来源：[结论与问题分类.md 第 1 节](../planning/2026-10-15-1417_official-63-retest/结论与问题分类.md)。受测基线 `b92b3fe`。

## 问题

1. **理解：主位超时后备用来不及。** `interpret.py` intake 总预算 15 s，deepseek-pro `timeout_s=9`，qwen-flash 只剩约 6 s，而它的 p90 是 8.6 s。并发首轮 T55 / T56 / T57 / T59 / T61 都是「deepseek-pro 9.0 s 超时 → qwen-flash 6.0 s 超时」。
2. **选方案：schema_error 与预算挤占。**
   - schema_error 4 次（补测 T52 两次、T57 一次，以及 T52 同模型重试）全部是 `hypotheses.N.missing_fact: String should have at most 120 characters`。提示要求填候选原文的原话，原话常超过 120 字；带错误提示同模型重试，模型照样超长。
   - T58 形态：intake 主位超时、备用接住用了约 14 s，synthesize 拿到 `min(15 s, 剩余 - 2 s)` 约 4 s，deepseek-pro 吃光后没有备用。厂商过载是成片的（14:45 以后集中），同一轮 intake 主位超时，synthesize 主位大概率也超时。
   - 每轮失败后还有第二次 synthesize（T53 / T54 / T57 的 1–2 s 超时）：是 `retrieve` 的上下文补查，拿剩余 1–2 s 再调同一个已失败的模型。
3. **选方案失败的降级错误。** `_synthesize_step` 只把 `degraded` 写进 trace，`_diagnose_outcome` 看到空 `plans_ranked` + `knowledge_status=ok`，按「候选都不适用」走 R5 `knowledge_gap`：
   - T57 补测：客户收到「I couldn't confirm official troubleshooting guidance」，交接原因写「官方资料没有覆盖」。
   - T53 首轮：过保换货办结后 `advance_tasks` 说「Next up: device troubleshooting」，排障的 synthesize 失败 → R5 → `propose` 看到 `closed_unresolved` 案件，紧接着说「This case is closed」。

## 改动

### 必要

| 改动 | 位置 | 理由 |
|---|---|---|
| `missing_fact` 上限 120 → 300 | `diagnose/synthesize.py`（`Hypothesis` 与 `_schema_with_enum` 两处） | schema_error 的唯一形态；与 `clarification_question` 同上限。只用于去重比对，变长无副作用 |
| deepseek-pro `timeout_s` 9 → 8 | `config/models.yaml` | 63 单成功调用 intake 最长 8.2 s（70 次中 1 次超过 8 s）、synthesize 最长 7.4 s |
| intake 预算 15 → 17 s | `conversation/interpret.py` | 主位 8 s 超时后 qwen-flash 有 9 s，盖住其 p90 8.6 s |
| 选方案模型失败走独立出口 | `sessions/graph.py` | 见下 |

选方案失败出口：

- `_synthesize_step` 返回 `synthesis_failed`（`degraded` 以 `model:` 开头，即超时 / schema 重试耗尽 / 容量满），`retrieve` 取出后传给 `_diagnose_outcome`，不进 state。
- 首批失败不做上下文补查；补查本身失败也算失败（被裁掉的候选没判完）。
- `_diagnose_outcome(synthesis_failed=True)` 且无方案 → `diagnose_outcome = {mode: unavailable, reason: synthesize_failed}`，`escalate_reason=None`。
- `route_after_retrieve` → 新节点 `diagnose_unavailable`：发固定英文说明（暂时系统问题、不是对设备的结论、描述已保存、问题保持打开、再发一条消息会重查、也可找同事），记 `runtime_fault` 日志，→ `commit_issue`。不交人工、不结案、不推进下一项任务。
- 下一条消息：`plans_ranked` 为空，`_after_product` 照常走 `retrieve` 重新检索与选方案。

### 可选复杂度：模型冷却

`retry.cooldown_s`（默认 0 = 关闭，仓库配置 30）：模型用满自身 `timeout_s` 仍超时、或 5xx 后，30 s 内在所有任务的链上排到末位，只调顺序不移除；成功一次即清除。被剩余预算截短的超时不冷却。

- 解决的是相关失败：intake 主位刚超时，同一轮 synthesize 直接从 deepseek-flash 开始，拿到完整预算。只靠单任务预算覆盖不了「intake 主位超时 + 备用 + synthesize 主位超时 + 备用」在 25 s 内的最坏情况。
- 代价：一次偶发超时会让之后 30 s 内的调用用备用模型（intake 用 qwen-flash，synthesize 用 deepseek-flash）。
- 只作用于结构化 `invoke`，`reply.stream` 不变。
- 不要可以删：`router.py` 的 `_ordered` / `_note_outcome` 和 `RetrySpec.cooldown_s`，其余改动不依赖它。

### 评估后不改：synthesize 备用不换厂商

类比 66ca080 对 intake 的改法，评估了 `[deepseek-pro, qwen-max, deepseek]`。用临时配置把 synthesize 链只留 qwen-max 跑 T52–T62（并发 3）：9 次成功 p50 7.7 s、p90 13.1 s，另有超时。主位 8 s 超时后第二位只剩约 7 s，qwen-max 装不下。deepseek-flash 选方案 p50 2.5 s / 本轮 3.8–4.0 s，更适合第二位；DeepSeek 整体过载时两个位都会冷却，qwen-max 自然排到最前并拿到完整预算。

## 不在本次范围

- 25 s 整轮截止不动。
- 理解失败的兜底文案（「Tell me what it is doing…」）不动：本次让理解失败本身变少。
- 知识库不可用（`knowledge_status=unavailable`）仍走 R5，属另一类运行故障，未改。
- 回放包 `models_ver` 仍是 2026-10-13.2，在本次之前已与当前 2026-10-15.2 不一致，演示回放需要重录（与本次无关，版本号再 +1）。

## 测试

- `tests/test_diagnosis_recovery.py`：选方案失败 → 说明运行故障、不交人工、不补查；下一条消息重试出步骤卡。补查失败 → 同一出口。
- `tests/test_conversation_l3.py`：T53 形态（过保办结后排障选方案失败）不出现「case is closed」，排障任务保持 active，下一条消息出步骤卡。
- `tests/test_models_fallback.py`：冷却跨任务生效、到期恢复、冷却中的模型仍在链尾被尝试、被预算截短的超时不冷却。
- `tests/test_vision_graph.py`：全链失败的断言从 R5 改为运行故障。

## 真实链路复测

`run63.py`（进程内 harness，真实模型 + WeKnora），输出只留本机 scratchpad。

**正常配置，T52–T62 并发 3：** 理解 13/13、选方案 8/8 都是 deepseek-pro 首位成功（intake p90 6.8 s、最长 7.6 s；synthesize 最长 7.6 s），无 schema_error、无整轮失败。本轮 DeepSeek 只有两次 77 ms 的连接错误（同模型重试成功），没有出现回测时的成片超时，所以这一轮**没有压到降级路径**；超时场景下的表现靠下面的故障注入和单测证明。

**故障注入（临时配置：deepseek-pro 超时 1 s、synthesize 链只留 deepseek-pro），T53 / T57：**

| 工单 | 调用 | 客户看到 | 状态 |
|---|---|---|---|
| T53 | intake：pro 1 s 超时 → qwen-flash 7.7 s 成功；第二次 intake 因冷却直接从 qwen-flash 开始；synthesize 超时 | 过保说明 → 「Next up: device troubleshooting.」→ 「I couldn't load the troubleshooting steps just now because of a temporary system problem…」，没有「case is closed」 | stage=diagnose，无交接 |
| T57 | intake：pro 连接错误 + 超时 → qwen-flash 5.5 s；synthesize 超时 | 同一段运行故障说明，没有「couldn't confirm official troubleshooting guidance」 | stage=diagnose，无 R5 / knowledge_gap，无交接摘要 |

**qwen-max 探测（synthesize 链只留 qwen-max，T52–T62 并发 3）：** 见上节；同一轮里 T52 选方案超时，客户收到运行故障说明，未交人工。
