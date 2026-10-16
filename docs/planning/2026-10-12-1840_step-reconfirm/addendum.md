# 补充与勘误

## 2026-10-12 实施中的修正

- 首卡说明的引用范围从 action_taken 扩到 observation。首轮实测 T27 的「no blockage seen」「roller mop area is clear」被抽成 observation，不是 action_taken，首卡没有说明。客户说查过、看到的状态，与做过的操作是同一类自述，都只做标注。文案相应改为「You mentioned: …… may overlap with what you've already done or checked」。
- `carried_answers` 读完后确认它只沿用客户在卡上亲自选过的选项（排除 `source=fact`），属于卡片结果，按标准 4 保留。
- synthesize 提示词里「候选只是重复这些动作则 not_applicable」一句，改为「action_taken 只是背景，与候选重叠不是拒绝依据」。不改的话，模型可能因为客户说做过而拒掉正确的指南，这与标准 1 相冲突。
- `test_knowledge_branches.py` 中 T27 的决策用例原来用的 SKU 是 T2351，与 rv-0147 的适用型号（T2352 / T2353）不符。原断言只看耗尽后的分支，所以没有暴露。改写时换成 T27 的 T2353。

## 实测（make up 后真实模型，reports/eval/2026-10-12-1930_step-reconfirm/、2026-10-12-1945_step-reconfirm-observation/）

| 工单 | 结果 |
|---|---|
| T21 | 第一批 1/3、第二批 3/3 出 rv-0113 三张卡，首卡引用法语原话，之后的卡不重复，最后进入质保判断。第一批有 2 次停在 synthesize 追问（一次事实极性为 uncertain，一次三个候选都是 not_supported，追问 4013），在指南之前，与本改动无关 |
| T51 | 3/3 不再跳过充满：两次走 bp-0111，s5 到 s10 全部发出，包括 s6「fully charged」；一次走 bp-0018（候选选择不同）。intake 把「I've charged my pump」并入症状 quote，没有抽成 action_taken，所以没有首卡说明 |
| T27 | 滚刷卡照发，首卡引用「no blockage seen」「roller mop area is clear」（第二批），反馈未解决后进质保 |
| T29 | 三张卡照发，首卡引用三条自述 |
| T36 | 首卡 rv-0341 问句，引用「Alle filters en borstels zijn vervangen」「alles is schoongemaakt」 |
| T37 | 查水箱卡照发（两次分别为 rv-0111、rv-0021），未解决后进质保；intake 把「tank nog vol」并入症状，没有首卡说明 |
| T46 | 问句 s2 照发，由客户在卡上确认 |
| T22 | 条件判定按原样跳过；本次模型对两步都判 unknown，s1、s2 依次发出，与改前首轮不跳的情况一致，没有错跳 |
| T16 | 滤网安装卡照发并附说明，之后是磁铁卡 |

首轮耗时 5.7 至 11.7 秒，与 17:56 主轮同一量级。

## 遗留

- T21 首轮在 synthesize 处的追问（事实极性为 uncertain、4013 前提追问）属于候选选择问题，不在本 plan 范围内，见 plan「不改」一节。
- 自述被 intake 并入症状 quote 时（T37「tank nog vol」、T51「I've charged」）不会出现说明。卡片照发，行为是正确的，只是少了一句说明，暂不处理。
