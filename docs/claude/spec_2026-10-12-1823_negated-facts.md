# 客户否定事实的补抽与极性校正

## 问题

客户原话里的否定事实（没做过、没发生），没有以 `polarity=negated` 进入事实列表。服务端的前提核对
（`precondition_status`，synthesize.py:217）因此没有可比的事实：本该判「前提不成立」，结果判成「未知」，去问客户。

会话 2d5b2267（2026-10-12 18:15，官方 T41，已含 f459568）：

```
原话: "As the water injection is still malfunctioning we have not run mop cycles and thus havent needed
       any mop drying so im not sure what is triggering this."
intake facts: [symptom affirmed 「received error message related to failed drying」,
               symptom affirmed 「water injection is still malfunctioning」]      ← 漏抽「没跑过拖地」
synthesize:  rv-0146（拖布没烘干）needs_confirmation, missing_fact="roller not dried /Mop not dried"
precondition_status → unknown → 追问: "Does the failed drying error appear during or right after a mop/roller drying cycle?"
客户: during → 新事实「烘干时报错」与原话矛盾 → rv-0146 可执行 → 卡片要求「升级固件后跑一次拖地」→ 客户点解决 → 结案
后续: 转去查补发插头的物流，与「已修好」矛盾
```

本地 logs/events.jsonl 中 T41 首轮共 3 次：

| 会话 | 「没跑过拖地」 | 结果 |
|---|---|---|
| 24f5e167 | 漏抽 | 追问烘干时机 |
| 2d5b2267 | 漏抽 | 追问烘干时机，套用 rv-0146 |
| 016757a0 | 抽到，但 `action_taken polarity=affirmed value="not run mop cycles"` | 仍追问「有没有跑过拖地任务」，之后出 rv-0019 卡 |

3 次都没有以 negated 进入事实。两个独立缺陷：

1. **漏抽**：原话的否定句没进 facts（2/3）。
2. **极性错**：抽到了，但否定词留在 value 里、polarity 记成 affirmed（1/3）。`precondition_status` 看到 affirmed 的
   action_taken 会判「前提已知成立」（synthesize.py:227），与原意正好相反。

已有机制覆盖不到：

- `complete_problem_facts`（interpret.py:343）只在 intake 一条 symptom 都没抽到时补抽，T41 抽到了两条症状，不触发；
  且它只收 `kind=symptom`。
- `normal_operation_is_uncertain`（interpret.py:217）只处理「某部分正常」的肯定句，不管否定句的极性。
- `precondition_status` 本身对否定事实工作正常：已在 test_question_before_fact.py:57 用 T41 原句验证过
  （「perform a new mopping task」对 NOT_RUN_MOP → negated）。缺的只是事实。

## 范围与频率

63 单原文中含否定句的 23 单，多数是现象本身的否定（not working / will not empty / did not arrive），intake 会作为症状
抽取，不受影响。属于「否认做过某事 / 否认某条件」、会影响前提核对的：T41（not run mop cycles）、T29（hose is not
pinched，3/3 已抽到）、T44（kept it dry）、T57（WiFi is fine，0/1 抽到）。样本少，不建立否定词表或同义词表
（docs 约定：按典型场景设计，缺数据用最小机制）。

## 方案

### 1. 极性校正（确定性，服务端）

新增 `negation_polarity(facts)`，在 `normal_operation_is_uncertain` 旁，intake 与补抽结果都经过它：

- `kind in {action_taken, observation, symptom}`、`polarity == "affirmed"`；
- **quote** 中有否定词，且否定词作用于该事实的动词（`have not run`、`havent needed`、`never used`、`did not`），
  而不是作用于故障现象本身（`will not empty`、`not working`、`does not suction` 是在描述异常，保持 affirmed）；
- 判别：value 以否定词开头（`not run mop cycles`），或 kind=action_taken 且 quote 中否定词紧跟助动词
  （have / has / had / did / do / does + not / never，及其缩写），满足即改为 `polarity=negated`，
  value 去掉开头的否定词（`run mop cycles`），subject 不变。
- symptom 不改：症状的否定通常就是异常本身。

依据：action_taken 的语义是「用户做过的操作」，带否定的 action_taken 只能是「没做过」；这是 016757a0 的直接缺陷。

### 2. 否定事实补抽（一次模型调用，条件触发）

扩展 `complete_problem_facts` 的触发条件，不新增模型任务：

- 现有条件：没有任何 symptom → 补抽症状（不变）。
- 新增条件：problem_description 中存在「助动词 + 否定」句（同第 1 节判别），且该句没有被任何已抽事实的 quote 覆盖
  → 只对这些句子补抽，指令限定 `kind in {action_taken, observation}`，polarity 按字面。
- 结果同样要求 quote 逐字在原文中，并经第 1 节极性校正。

两个条件都满足时合并为一次调用。不满足时不调用，不增加延迟。

### 3. 不改的部分

- 不改 synthesize 提示词与 `precondition_status`：现有逻辑在事实正确时已能判 negated 并丢弃 rv-0146。
- 不加否定同义词表、不按 QA 编号特判。
- 不处理「追问只给会让方案成立的选项」（引导性问句）：属于问句生成，另行评估。

## 预期效果（T41）

```
facts: + action_taken negated 「run mop cycles」 quote="we have not run mop cycles"
synthesize: rv-0146 needs_confirmation, missing_fact 覆盖「mop / run」→ precondition_negated → 丢弃，不再问
其余候选（rv-0019 注水异常、rv-0025 烘干器故障）照常核对
```

注意：`_covers` 要求 missing_fact 的每个内容词都出现在事实里。rv-0146 的 missing_fact 若是
「roller not dried /Mop not dried」，对「run mop cycles」不覆盖（roller、dried 不在事实里），仍会判 unknown。
已用当前代码验证：「perform a new mopping task」→ negated，「roller not dried /Mop not dried」→ unknown。
所以第 1、2 节只保证事实正确；synthesize 能否据此丢弃 rv-0146，取决于模型给出的 missing_fact。
structured_facts 会把 negated 事实交给模型（synthesize.py:445），模型看到「没跑过拖地」也可能直接判 not_applicable。
这一点需实测，不能事先保证。

## 测试

新文件 `orchestrator/tests/test_negated_facts.py`：

1. 极性校正判定表：
   - `action_taken affirmed "not run mop cycles" / quote "we have not run mop cycles"` → negated，value `run mop cycles`（016757a0）
   - `action_taken affirmed "never used the mop" / "I've never used the mop"` → negated
   - `symptom affirmed "will not empty" / "Water tray will not empty"` → 不变
   - `symptom affirmed "not suctioning" / "pump not suctioning"` → 不变
   - `action_taken affirmed "insured the hose is not pinched"`（T29）→ 不变：否定作用于 pinched，不作用于 insured
   - `observation affirmed "WiFi is fine"` → 不变
2. 补抽触发：T41 原文、intake 只给两条症状 → 触发补抽，FakeChatModel 返回否定事实后 facts 含 negated 一条；
   T29 原文且 intake 已抽到 hose 句 → 不触发；无否定句的原文 → 不触发。
3. 补抽返回的 quote 不在原文 → 丢弃。
4. HTTP 链路（T41）：intake 漏抽，补抽给出否定事实，synthesize 返回 rv-0146 needs_confirmation、missing_fact
   「perform a new mopping task」→ 不发追问，trace 含 `precondition_negated:qa_rv_0146`。

回归：test_question_before_fact.py、test_conversation_official_tickets.py、test_customer_scope_guards.py、
test_diagnosis_recovery.py、test_text_question_answer.py、test_context_capacity.py（补抽指令长度受 intake 预算约束）。

## 实测

`make up` 后真实模型跑 T41 ×3、T29 ×3、T57 ×1，记录 facts、synthesize 丢弃标记与首轮输出。
判定：T41 不再出现烘干时机或「是否跑过拖地」的追问；T29 不变；首轮延迟增加控制在一次补抽调用以内（约 1–3 秒）。

## 改动范围

- `app/conversation/interpret.py`：negation_polarity；complete_problem_facts 触发条件与指令。
- 新测试文件一个。

## 未决

- 第 2 节的「否定句未被覆盖」用 quote 包含判断。原文一句含多个事实时可能误判已覆盖。先按句判，实测再看。
- 物流衔接（补发插头问订单号）与引导性问句不在本 spec 范围。

## 实施记录（2026-10-12）

- 第 1、2 节已实施（interpret.py：DENIED_ACTION、negation_polarity、uncovered_denials、complete_problem_facts 扩展）。
- 「没做过」限定为客户主语（I / we）+ have / had / did 否定，排除 received / known / been 等。设备主语的否定
  （does not suction、doesn't clean）在 63 单里会误触发补抽，已排除。63 单中只有 T41 触发补抽，其余工单不多一次调用。
- 覆盖判断以否定动作本身为准：同一分句里的「water injection is still malfunctioning」不算覆盖「we have not run」。
- 测试 `tests/test_negated_facts.py` 23 个；相关 811 个通过；ruff 通过。

### 真实模型实测（make up 后，未提交代码；reports/eval/2026-10-12-1850_negated-facts/）

| 工单 | 否定事实 | 首轮 |
|---|---|---|
| T41-r1 | negated「run mop cycles」「mop drying」 | 仍问烘干时机：missing_fact=「roller not dried /Mop not dried」，与「run mop cycles」词不重合 → unknown |
| T41-r2 | 同上 | `precondition_negated:qa_rv_0146`，不问，出 rv-0019（注水异常）s1 卡 |
| T41-r3 | 同上 | 问是否有 6018 注水错误码（rv-0019 待确认），与原话不矛盾 |
| T29 ×3 | hose / connector 仍为 affirmed（未误改） | 3/3 出 rv-0254 s1，与改前一致 |
| T57 ×1 | 无触发 | 文字追问摄像头供电，与改前一致 |

事实层 3/3 修复（改前 0/3 正确）。烘干时机追问从改前 2/2 降到 1/3。剩余 1 次属于本 spec「预期效果」一节写明的边界：
missing_fact 写成症状原话时，词面比对不上否定的动作事实；模型虽在 structured_facts 里看到 negated 事实，仍判 needs_confirmation。
首轮耗时 10.7–12.2 秒，与 T29（12.5–13.5 秒）同量级。

### 定位

本次是事实层修复：否定事实记对（极性校正零成本、无误伤）与漏抽补齐。它不解决「该不该问」：
是否追问仍取决于 missing_fact 与事实的词面比对（_covers），用词不同就判 unknown（T41-r1）。
根本解是文字追问发出前用问题本身核对客户原话（参照 guide/fact_check.py 的判定 + 逐字引文 + 服务端校验），另立 spec。
