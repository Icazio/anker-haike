# T61：错误候选带偏的修复

来源：Codex 2026-10-13 08:05 独立复测 `docs/planning/2026-10-13-0805_independent-12-verification/`，T61 三次中重复一次追问「App 是不是显示了不准确的家庭地图」。
取证：`docs/planning/2026-10-13-1100_t61-candidate/`，复跑 T61 六次、T62 对照六次，并读取各轮会话的 synthesize 原始输出（容器日志）。

## 问题

客户原话：「isn't following my schedule it's going off 2 hours before and the cleans are not being recorded」。

- 知识库里没有「提前启动」「清扫不记录」的条目，正确出口是按知识缺口转人工，并列出两个症状。
- 复跑 T61 六次，六次都正确转人工。失败是概率性的：Codex repeat-1 一次，我之前的 round3 主轮一次。
- 两次失败的内部状态是同一个模式：
  - 两个时机冲突的候选（rv-0551 低电不启动、rv-0522 有任务不启动）被正确丢弃；
  - synthesize 又给了第三个候选，置信度 0.2–0.3，只覆盖第二个症状「cleans are not being recorded」；
  - 它的 missing_fact 与这个症状毫无关系：rv-0565 是「inaccurate mapping」，rv-0542 是「Repeated cleaning / Overlapping cleaning paths」；
  - 这个候选就成了唯一的追问，客户被问「地图准不准」「有没有重复清扫」。
- 六次复跑里这个第三候选每次都出现（rv-0565 / rv-0530 / rv-0542，置信度 0.2）。只是置信度落在 0.3 以下时，上一轮加的门槛把它挡掉了；落到 0.3 时就会漏过去。

## 为什么不能只调门槛

T62（「not cleaning in a straight line」）对同一条 rv-0542 的追问「是不是反复清扫同一区域」，Codex 判为合理，而它的置信度也只有 0.35。只调置信度门槛，分不开「T61 用 rv-0542 问记录缺失」和「T62 用 rv-0542 问路径异常」。

两者的真正区别在于：追问要确认的前提（missing_fact）是不是客户这个症状的某种具体表现。

- T62：missing_fact「Repeated cleaning / Overlapping cleaning paths」是「不走直线」的一种表现，问了能区分；
- T61：「inaccurate mapping」「Overlapping cleaning paths」都不是「清扫不记录」的表现，问了只是把不相干的条目拿来盘问客户。

## 方案

1. **让模型在追问时自报相关性**。Hypothesis 新增 `question_targets`：这个追问在区分客户的哪一条症状（逐字取有效症状），以及 `question_relation`：取值 `narrows`（客户这条症状的一种具体表现或发生条件）或 `different_problem`（文档讲的是另一个问题）。提示词写明：前提描述的是另一个问题时选 different_problem，不发追问。
2. **服务端核对**。`filter_hypotheses` 里 needs_confirmation 只在 `question_relation == "narrows"`、且 `question_targets` 非空并且全部是有效症状时才进入追问；否则记 `clarify_unrelated` 丢弃。字段缺失时（旧模型、旧回放）按原规则处理，即保留低于 0.3 的门槛。
3. **保留现有兜底**：时机 / 对象冲突不追问；置信度低于 0.3 不追问。

## 风险与回归

- T39、T41、T43、T57、T62 的合理追问必须保留：它们的 missing_fact 都是在区分客户已报症状的具体表现或条件，模型应该判 narrows。
- 如果模型把合理追问误判成 different_problem，会多出一些直接转人工的情况。所以要用真实模型复测这些案例。

## 验证

- 单测：用 T61 的失败样本（rv-0565，不相关）、T62 样本（rv-0542，narrows）构造 synthesize 输出，验证追问的保留与丢弃；字段缺失时回退到旧规则。
- 真实复测：重建后，T61 跑 6 次，T62、T39、T41、T43、T57 各跑 2 次；T61 每次都要转人工并列出两个症状，其余案例的追问方向不能变。

## 结果（2026-10-13，`make up` 重建后真实复测，数据在 `docs/planning/2026-10-13-1100_t61-candidate/after/`，按 .gitignore 只留本机）

- 单测 3 项新增；后端全量 1391 项通过；`make lint` 无告警。
- T61 6/6 转人工，交接摘要列出「提前 2 小时启动」「清扫不记录」两个症状。t61-1 的日志里，synthesize 把 rv-0565（inaccurate mapping，置信度 0.15）判为 `different_problem`，记 `clarify_unrelated` 丢弃。
- 对照组各 2 次，追问方向与修复前一致：T62 问 repeatedly clean / overlap，T39 问固件升级，T41 问 6040–6045，T57 问 LED，T20 问是否从基站出发，T60 问具体现象。
- T43：ctl-1 追问 2.4GHz Wi-Fi；ctl-2 直接发 rv-0271 的卡。原因是 missing_fact「your network type is 2.4GHz」就是卡片第 1 步「Verify that the your network type is 2.4GHz」，按原有 `precondition_in_plan` 规则改为发卡（此时 `question_relation='narrows'`，新规则没有参与）。这是原有路径的波动，不是本次改动造成的回退。
