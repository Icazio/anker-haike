# 卡片说明、事实承接与资料覆写修正（官方 63 单复测 2026-10-12 19:09）

来源：`docs/planning/2026-10-12-1909_reconfirm-verification/`（复测裁定）与
`docs/planning/2026-10-12-1755_official-63-plain-review/addendum.md`（根因表）。
不含语言适配（待决策）、T41 物流插队、T61 时机冲突、T48 读图进问答（待决策或中等改动）、官方口径与知识缺口。

## 代码

| # | 案例 | 问题 → 例子 | 改法 |
| --- | --- | --- | --- |
| C1 | T36 | `reported_note` 只有一种措辞。T36 首卡是问题卡（只有选项和短答），说明却让客户「mark it as not solved」 | `reported_note(quotes, kind)`：action 保留「标记未解决」，question 改「按现在看到的情况选」，material_request 改「有就上传，没有就说暂时没有」；「the steps below」改为不预设后面还有卡 |
| C2 | T37 | 首卡只引 action_taken / observation（「软管正常、胶圈正常」），客户的核心症状「水箱是满的」在 symptom 里，没被承接 | 首卡说明已出现时（有自述做过 / 查过的事），同时引本问题客户原话里的症状：「You described: …」。没有自述时不加，避免所有首卡都多一行 |
| C3 | T41 | ① `uncovered_denials` 用任何事实的 quote 判覆盖，整句症状 quote 含「we have not run」，补抽不触发；② `_stems` 把 dried→dri、drying→dry，对不上；`_covers` 不拆「roller not dried /Mop not dried」；③ `negation_polarity` 把 quote 里含否认句的观察「water injection is still malfunctioning」整条翻成 negated | ① 只认 negated 的 action_taken / observation 为覆盖；② `_stems` 增加 ied→y；`_covers` 按「/」拆备选，任一备选被覆盖即可；③ value 原样出现在 quote 中、且整段位于否认句之前时不翻转（说的是另一件事） |
| C4 | T60 | `concrete()` 用模型截短的 quote 判 WISH：「I just want my hoover to clean…」被截成「my hoover to clean…」，愿望被当成具体症状，直接套清洁效果差方案 | interpret 纠正链里：症状事实所在句命中 WISH、quote 本身没命中时，quote 扩成该整句（仍是逐字原文）。只影响愿望句 |
| C5 | T30 | 读图提示词只要求写品类，扫地机能指整机的词只有「基站」，4 轮都把前景机器人写成基站 | observations 第一条写画面主体：品类 + 本体 / 基站 / 配件，看不出品类只写外形；词表 parts 加「主机」（english: main unit，不进 category_parts）；`VISION_PROMPT_VERSION` 升版 |
| C6 | T31 | 步骤 caution 只来自条目 Tips；覆写文件不能写 caution | `qa_overrides.yaml` 支持 `caution`（与 Tips 合并显示）；支持 `media: true` 指定拆分段里哪一部分挂原段图示 / 链接（默认第一张出卡部分，D2 用） |

## 数据（`data/official/qa_overrides.yaml`）

| # | 案例 | 改法 |
| --- | --- | --- |
| D1 | T31 | rv-0473、rv-0363 第 4 段（长按红键恢复出厂）加 caution，文字取自 rv-0312 第 3 段：长按红键超过 5 秒会删除地图，之后要重新建图。「Wi-Fi 指示灯旁的红键」与 rv-0312「red function button」是否同一键，原文未写明，需官方核实 |
| D2 | T40 | rv-0073 拆三部分：装好清洁液瓶（action）→ 是否已按官方文章检查（question，「还没看」为 retry 选项，链接挂这张）→ 照片 / 视频（material_request）。「还没看」不再被统一「未解决」吞掉、直接判排障完成 |
| D3 | T51 | bp-0111 第 5 段「Check Battery Power」是小标题，改 statement，并入下一张「确保充满」卡 |

## 暂不做

- T37 卡片标题截在 80 字（rv-0111 标题前半是「tank is empty, please add water」）：计划是静态的，生成时不知道命中哪个「/」备选，全文不截断又太长。C2 已在首卡承接「水箱满」，标题另议。
- C5 需真实模型复测读图字段准确率（bake-off）；单测只覆盖提示词与词表。

## 验证

- 新增 / 改写单测：C1 问题卡说明、C2 症状引用、C3 三处、C4 T60 原文、C5 提示词含主体要求、C6/D1 caution 出现在 rv-0473 卡上、D2 rv-0073 三部分与链接位置、D3 bp-0111 首张操作卡为 s6。
- 回归：`test_step_fact_check.py`、`test_negated_facts.py`、`test_knowledge_explanations.py`、`test_p2_wording_and_objects.py`、`test_knowledge_source_gaps.py`、`test_applicability_facts.py`、`test_vision*.py`、`test_official_data.py` 及相关文件；`make lint`。
- 63 单真实复跑由用户决定（花 token）。
