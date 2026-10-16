# 进度

- 2026-10-12 18:40 解码 T21 上午（3a3d358f）与本轮（4ed7c8a0）的 checkpoint：检索相同；本轮 synthesize 对 rv-0113 命中 `precondition_in_plan`，直接进指南；fact_check 的 verdicts 为空，三张卡原样发出，没有说明。
- 用户意见：卡片可以重复客户已说过的事，用来再确认。据此定标准：只有卡片反馈能消费步骤，客户自述只做标注；适用条件照旧判断。
- 盘点已做判断共四处（matches_reported / fact_check done·partial·answered / done_by_customer），全部改为标注。
- 19:20 实施完成：steps.py 删除正则跳卡与三种跳过说明，新增 reported_note / reported_quotes；fact_check.py 只判条件步骤（删除 done / partial / answered / judged_elsewhere，保留 carried_answers）；decision.py 删除 done_by_customer；synthesize 提示词不再因 action_taken 判 not_applicable。删除 test_reported_action_coverage.py，改写 test_step_fact_check.py 与 test_knowledge_branches.py 的 T27 用例，新增 T21、T51 回归用例。
- 19:30 第一批实测：T27 没有首卡说明，原因是自述被抽成 observation。将 observation 纳入引用后，19:45 复测 T21 ×3、T27、T37 符合预期。
