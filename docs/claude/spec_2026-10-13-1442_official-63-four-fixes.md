# 官方 63 单全量复评：4 处系统修改

来源：`docs/planning/2026-10-13-1058_official-63-full-review/整体情况.md` 列出 9 案"系统需改"。按比赛标准复核后，确认需改的是 5 案、4 处（T50+T53 同根因）。T12、T31、T41、T42 不改，理由见对话复评：T12 的正常保护说明是 T37 有意禁用；T31 与 5a86436 的"自述不跳卡"规则一致；T41 的物流已排队、测试器未回答错误码；T42 读图误差不影响售后路线。10 案英文回复是 D2 决策，不算缺陷。

## 1. T50 / T53：没说过充电问题，不被充电条目带去问充电

问题：bp-0127 标题是"charging case not charging one side"。客户原话里没有可识别的充电关系时，`check_charging_recipient` 返回 unknown，`filter_hypotheses` 固定追问 "Which part is not charging"。

- T53：现象是"一侧停机"，"充了很多次还是开不了机"是做过的操作，却被问充不了电。
- T50 主轮：intake 把 "the left one does work" 抽成 negated 的 "left side does not work"，只把 affirmed 改成 uncertain 的规则没有覆盖到这条。

改法：

- `charging.py` 新增 `mentions_charging`，用多语言词根判断客户现象里有没有充电或电量。
- `synthesize.filter_hypotheses`：结果为 unknown、且客户现象原话（不含 action_taken，不用模型改写的 value）没提充电时，记 `charging_not_reported` 丢弃，不追问。说了充不进电但没说是谁的，仍按原规则追问。
- `interpret.normal_operation_is_uncertain`：被标成 negated 的"某部分正常"句也改成 uncertain，value 还原为原话。

## 2. T57：收 App 版本用问题卡

问题：bp-0164 第 1 段"查看版本"、第 3 段"提供版本"都是操作卡，点两次"未解决"就判指南走完、进质保，版本号从没拿到。

改法（只改 `qa_overrides.yaml`）：禁用第 1 段，第 3 段改成 question 卡，标题里写明查看位置。第 2 段"5.0 以上可能是已知问题"作为说明附在卡上。问题卡上点"未解决"返回 409 `not_allowed_now`。

## 3. T34：资料不覆盖客户要的结果，走完按资料缺口交人工

问题：rv-0312 的 scope_note 对客户说"if you need the old map itself, mark them as not solved and a colleague will check"，实际点"未解决"后进质保收订单，说的和做的对不上。

改法：

- scope_note 新增可选字段 `beyond_source`，rv-0312 设为 true。命中并显示后，在 `displayed_knowledge_nodes` 记 `beyond_source:<plan_id>`。
- `decide_next`：指南走完时带有该标记，返回 `outcome_beyond_source`，映射到 R5 交人工，不收凭证、不进质保。
- 摘要原因与客户说明各加一句：资料只覆盖已试步骤，客户要的结果需人工核查。
- scope_note 未命中（没说要旧图）时仍走原路线：指南走完进质保。

## 4. T48：单张照片不说灯常亮或闪烁

问题：回复写 "solid green light"，随后又问客户是常亮还是闪烁。

改法：`PHOTO_ANSWER_RULES` 第 1 段加约束：只说灯亮着，不写 solid / steady / flashing / blinking。只改提示词，效果需要真实模型复测确认。

## 验证

- 新增 `orchestrator/tests/test_official_63_review_fixes.py`，9 例：T53/T50 不追问充电、说了充不进电仍追问、多语言词根、negated 还原；T57 问题卡、拒绝"未解决"、短答记为事实；T34 走完交 R5、未命中仍进质保；T48 提示词约束。
- `make lint` 通过；相关测试文件 514 + 258 例通过（1 skipped）。
- 未用真实模型复测。T48 依赖模型遵守提示词；T50/T53/T57/T34 是确定性约束。
