# 排障卡片：客户自述只做标注，不消费步骤

## 背景

官方 63 单复测（`docs/planning/2026-10-12-1755_official-63-plain-review/`）里，T21 比上午变差：客户说已经多次清洁和重启，系统仍原样发了清洁卡和重启卡，也没有说明这些卡和客户已做的有什么不同。

checkpoint 追踪：

```
facts: symptom「capteur laser bloquer」
       action_taken「nettoyé et repartit aspirateur a plusieurs reprise」
synthesize: precondition_in_plan:qa_rv_0113:s1（bbcadea）-> 直接进 rv-0113
fact_check: verdicts {}，三步都判 unknown，没有跳过也没有说明
卡片: s1 查雷达罩毛发 / s2 手转雷达 / s3 平地重启，均未提客户已做过的事
```

上午能问到保护膜，是三个候选都没被采用时碰巧发出的追问，不是有意设计的行为。

## 问题

「客户自述做过的事能不能代替某张卡」，现在有四处各自判断：

| 位置 | 判断方式 | 来源 |
|---|---|---|
| `guide/steps.py` `matches_reported` | PART_WORDS / ACTION_WORDS 正则词表 | T27 T36 T37 |
| `guide/fact_check.py` done / partial | 模型判断，提示词里逐案写例子 | T16 T29 T31 T36 T37 |
| `guide/fact_check.py` question answered | 模型判断，从原话推出选项 | T46 |
| `diagnose/decision.py` `done_by_customer` | 根据 done 判定把指南算作走完 | T27 |

每修一个案例就加一条例子或一个词，错误有两个方向：

- 漏判（T21）：清洁、重启只是笼统说法，没有判 done，卡片原样重发，也不说明为什么。
- 错判（T51）：「充过电」被判成步骤「确保充满」done，跳过后整条排障走错，直接进了质保。

两类错误的代价不对称：

- 多发一张卡：客户点一次「还没解决」，多花几秒。
- 错跳一张卡：该查的原因没查，排障提前结束，可能错误进入质保或转人工，事后无法补救。

客户自述的精度低于卡片结果。「清洁过」没说清洁了哪个部件，「重启过」没说是不是在平地上。卡片给出的是具体步骤和明确的反馈。

## 标准

1. 只有卡片反馈能消费步骤：客户点了「解决了 / 还没解决 / 做不到」，或在卡上作答，这一步才算处理过。客户的自由文字不跳过任何操作步骤或问句步骤。
2. 客户自述用来标注，不用来判定。指南第一张卡上原样引用客户说过做过的事，并说明重叠的步骤只需确认：「照卡上的做法做过、仍未解决，直接点还没解决」。每个问题只标注一次。
3. 适用条件不在此列。带 `condition` 的步骤（「卡在楼梯边时设禁区」）问的是这一步是否适用，不是这一步做没做过。客户原话否定了条件，照旧跳过（T22）。
4. 卡片反馈过的同一指令跨指南不再重发（`duplicate_instruction_src`），不变。依据是卡片结果，符合标准 1。

由此得出：

- 不需要判断「部分做过」「做过但更笼统」：标准 2 的说明对所有情况都适用，不用逐步比对。
- 不需要多语言词表：客户原话原样引用，不翻译、不归类。
- 「做过」与「做到了目标状态」不再需要区分（T51）：自述不消费步骤，充满这一步一定会发。

## 改动

删除：

- `guide/steps.py`：`matches_reported`、`user_reported_actions`、PART_WORDS / ACTION_WORDS / *_PATTERNS、`skipped_note`、`announce_skip` / `announce_done_before`、`partial_note`、`ALL_COVERED_NOTE`
- `guide/fact_check.py`：action 的 done / partial、question 的 answered、`judged_elsewhere`、`carried_answers`（跨指南沿用的是 fact 推断的答案；卡上客户自己选的答案由 duplicate_instruction_src 处理，需核实），以及提示词里对应的例子
- `diagnose/decision.py`：`done_by_customer`
- `diagnose/synthesize.py` INSTRUCTION：「候选只是重复这些动作则 not_applicable」。这一句与标准 2 冲突：客户做过的动作，正是要用卡片确认的内容。

保留：

- `fact_check` 只处理 condition 步骤。计划里没有 condition 步骤时不调用模型。872 条计划中带 condition 的 action 步骤共 111 个，多数指南因此少一次模型调用。
- `duplicate_instruction_src` 跨指南去重。

新增：

- `guide/steps.py` `reported_note(state)`：读当前问题中 `kind=action_taken`、`polarity=affirmed`、`source_kind=user_report` 的事实，取其 quote 原文，在本问题的第一张操作卡或问句卡上附一次。去重键写入 `displayed_nodes`（`reported:<issue_id>`）。
  文案（英文，与现有对客语言一致）：
  `You mentioned you've already tried: "<quote>"; "<quote>". Some steps below may overlap. Please still check each one as described; if you already did it exactly this way and the problem remains, just tap "Not solved".`
  按钮文案以前端实际标签为准；对客英文标签需核对后再定。

不改：

- synthesize 的路由与 `in_plan_check`（T29）：进入 rv-0113 本身没有问题，问题在卡片没有说明。T21 选 4012 还是 4011/4013 属于候选选择问题，另行评估。
- intake 事实抽取，以及 a755130 的否定事实。
- 对客语言（T21 法语客户收到英语回复），另列。

## 行为变化（需要接受）

| 案例 | 现在 | 改后 |
|---|---|---|
| T21 | 三张卡原样发，无说明 | 三张卡照发，第一张引用「nettoyé et repartit…」并说明只需确认 |
| T51 | 「充过电」被判 done，跳过充满 | 充满卡照发 |
| T27 | 自述「no blockage seen」-> 指南判为走完 -> 质保 | 滚刷卡照发，客户点还没解决后进质保 |
| T36 / T37 / T16 | 已换滤网、水箱满、已装好滤网 -> 跳过 | 卡照发，带说明 |
| T29 | partial 卡：只看格栅 | 卡照发，带说明（不再逐字给出剩余部分） |
| T46 | 原话里有 intermittent -> 问句不再问 | 问句照发，带说明 |
| T22 | 条件否定 -> 跳过 | 不变 |

代价：自述做得多的客户要多点几次。收益：不会因为文字误判而跳步，四套判断合成一条规则，多数指南少一次模型调用。

可选（本次不做）：卡上提供「我已经做过这一步」作为第四种反馈，与「还没解决」走相同的 next_on，只在摘要里区分。要先看复测时客户点击负担是否真的成问题。

## 测试

- 删除或改写依赖跳过的用例：`test_reported_action_coverage.py`（5 个）、`test_step_fact_check.py` 中的 done / partial / answered / judged_elsewhere / skip note 用例（T16 T29 T36 T37 T46 等约 10 个）、`test_guide_step_kinds.py`（1 个）。改写为：卡照发、首卡带一次说明、第二张卡不重复说明。
- 新增（T21）：action_taken 法语原话 -> 首卡说明原样含 quote；三张卡照发；最后一张反馈后照常进入质保判断。
- 新增（T51）：「I've charged my pump」-> 充满卡照发。
- 保留：T22 条件跳过相关用例全部通过。
- 回归：test_step_fact_check、test_guide_step_kinds、test_knowledge_branches、test_question_before_fact、test_in_plan_precondition、test_conversation_official_tickets、test_outcome_boundaries。

## 实测

`make up` 后用真实模型跑 T21 x3、T51 x3、T27、T29、T36、T37、T46、T22 各一次，核对：

- 首卡说明出现且只出现一次；
- 没有因自述跳过的卡（trace 里没有 user_reported / done）；
- T22 条件仍然跳过；
- 首轮耗时不高于改前。

## 风险

- 删除行为是有意设计（T27 T36 T37 的历次修复）。本 plan 已列出行为变化，用户确认后才执行。
- `carried_answers` 若处理的是客户在卡上作答过的问句（B26），属于卡片结果，应保留。实施前读完整个函数再决定。
