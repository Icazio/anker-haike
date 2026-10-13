# 选方案核对：词表规则改为模型判断加引文核对，理解与选方案换 deepseek-v4-pro

## 问题

`diagnose.synthesize` 选出候选后，服务端用三套英文词表和句式规则复核模型的判断：

- **部件**：`_PART_WORDS` / `_is_part` / `_head_part` / `_PART_FAMILY`
- **时机**：`EARLY` / `NOT_STARTED`
- **充电方向**：`charging.py` 的否定词加 charge 句式，用来解析谁给谁充电

另有两处判断靠词干重叠：

- 前提客户是否已说过：`_stems` / `_covers`
- 前提是否就是计划里的检查步骤：`in_plan_check`，看句首是不是 check，再比词干

每修一个错例就补一条词表，换个说法、换种语言就漏。例如：

- "it will not charge" 没有设备主语，认不出受电方
- "won't take a charge" 不符合句式
- 荷兰语"laadt niet op"完全不命中

另一个会话把充电判断改成了"模型摘 `charging_quote`、服务端核对引文"（未提交），方向对，但只覆盖充电这一类。

## 方案

**意思由模型判断，服务端只核对模型给的东西真实存在。**

`Hypothesis` 新增三个字段：

| 字段 | 含义 | 服务端核对 |
|---|---|---|
| `conflict{kind, customer_quote, candidate_quote, ask_about}` | 候选讲的不是客户这件事：`object` 对象不同，`direction` 方向相反，`not_reported` 客户没说过 | 否决只需模型自己认定，直接丢弃。若要追问客户的部件，`customer_quote` 必须出自客户原话，且 `ask_about` 必须出现在引文里 |
| `plan_step` | 前提就是计划第一张卡本身 | 必须是该计划第一张会发出的卡，类型为操作或问题，且不带适用条件 |
| `precondition_known{answer, customer_quote}` | 客户已说过前提成立或不成立 | 引文必须出自客户原话，或出自已答前提的回答 |

否决与追问刻意不对称：

- **否决不核对**：误丢一个候选，代价只是多问一句。
- **追问要核对**：防止模型替客户添加他没说过的对象。

删除和保留：

- **删除**：`charging.py` 整个文件；上面列出的部件、时机词表；`_stems` / `_covers` / `_fact_words` / `precondition_status` / `in_plan_check` / `CHECK_LEAD`；以及 `matched_subject`、`matched_timing`、`charging_quote` 三个字段。合计约 280 行。
- **保留**：所有事实性核对，包括计划 id、证据 id、错误码精确匹配、逐字引文、小节标题逐字匹配。业务规定也照旧保留，例如低于 0.3 的候选不追问、同一问题不问第二遍。

另有两处调整：

- **追问去重**：`answered_precondition` 原来按词干判断两个问题是否相同，改为 `asked_before`，只比较问句或前提原话是否相等。
- **补充可选症状（`active_symptoms`）**：没有抽到现象事实时，客户自己说的肯定观察也可以作为可选症状。原因是 2026-10-13 deepseek-v4-pro 把 T40 的"floor detergent level has barely moved"记成了观察。

## 换模型

`config/models.yaml` 版本号改为 2026-10-13.2：

- domestic 线路的 `intake` 和 `diagnose.synthesize` 主位换成 deepseek-v4-pro（关思考），`timeout_s` 设为 9。
- 主位失败后依次回退：`intake` 落到 deepseek-flash 再到 qwen-flash；`diagnose.synthesize` 落到 deepseek-flash 再到 qwen-max。
- `config/retrieval.yaml` 里 `synthesize.budget_ms` 从 8000 改为 12000，保证主位超时后仍够回退模型调用一次。

依据是 `docs/planning/2026-10-13-1613_stronger-models-63/对比结论.md` 中四组对比：

- 开思考单次调用要 50–90 秒，不可用。
- glm-5.3 准确率 84%，且主模型失败 9 次。

## 复测中修的两处

1. **T52**：模型给 bp-0067 填 `plan_step=s3`（"确认充电盒自身有电"），系统按可执行处理，从第 1 步"对准泵与盒内触点"开始，命中了首卡禁止项。改为只认第一张卡。前提落在后面某一步时，前面的卡已默认它成立，所以要先问。
2. **T40**：现象被记成观察，三个对症候选全被丢弃。改法见上面的 `active_symptoms`。

## 验证

- `make lint` 通过。后端全量测试 1367 通过、2 跳过。
- 改写了依赖旧词表的测试：
  - 删除：`_stems`、部件同义词、充电句式解析的单测。
  - 改为测服务端核对：模型判断冲突后的处理、引文核对、`plan_step` 只认第一张卡、前提已知需要引文。
- 63 单真实链路复测两轮（`after/`、`after2/`），见对比结论末节。

## 后续修正（2026-10-13 19:50）

真实复测（`docs/planning/2026-10-13-1613_stronger-models-63/` 的 `after3/`、`t52-*/`）又发现三处问题，处理如下：

1. **超时后接不上兜底。** 3 会话并发时，deepseek-v4-pro 在 intake 超时 4/17、synthesize 超时 6/17，T31、T35 落到"暂时无法完成理解"。原因：`router.invoke` 在同一模型上再等一次，9 s 加退避再加 9 s，把这一步的任务预算用光了。改法：结构化调用超时后直接换下一个模型；429 和 5xx 仍在同一模型上重试一次。同时把 `synthesize.budget_ms` 从 12000 调到 15000，主模型超时后给 deepseek-flash 留约 6 s。改完后 T31、T35 不再出现理解失败。
2. **T55 补照片被当成新故障。** 5 次里有 2 次，补照片那一轮被理解成 supplement。本轮上传的图要到 `understand` 末尾才并进 `image_refs`，证据检查当时看不到，于是照片又走了一遍读图和选方案，最后转人工。改法：证据检查直接读本轮输入里的故障图。改完复测 5/5 都出换货方案。
3. **T50 观察被当成可执行。** "the left one does work" 被记成 observation 而不是 symptom，于是 `only_uncertain` 没有触发。改法：唯一的客户陈述是"哪部分正常"时，不论它被记成现象还是观察，都先追问。改完复测 5/5。

提示里补了两条：

- 候选只是用法、规格说明，而客户报的是故障时，填 `not_reported`。
- 故障有因果链时（A 坏了导致 B 不行），只处理后果 B 的候选算 `object` 冲突。

**T52 仍未解决，列为已知问题。** 5 次里 2 次模型判出 bp-0066 冲突，但每次都改选了讲"给泵充电"的 bp-0039 / bp-0067。按"泵受电"排查，客户说的"盒子自身充不进电"这个源头被跳过；有 3 次首卡命中禁止项。

规则改造前，这一点靠 `charging.py` 的受电方解析处理，而且是确定性的：盒子自身不进电时，否决所有讲泵受电的条目。现在交给模型判断，没能稳定识别这条因果链。

可选的修法有两种，本轮都没做：

- 在充电盒的知识条目上写审核规则（`qa_overrides` 的 scope_note），把判断落到具体条目上。
- 恢复一条只针对"供电源头"的结构化检查。
