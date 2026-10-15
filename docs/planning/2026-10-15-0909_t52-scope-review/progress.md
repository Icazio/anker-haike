# 执行记录

- 读取现有规划、关系约束与测试；开始构造最小复现。未执行生产代码修改或回滚。
- 临时脚本 haike_t52_overblock.py 使用真实方案定义复现误拦截，断言按预期失败。
- 临时脚本 haike_t52_scope_compare.py 在内存中比较三种过滤方式，共九项结果；无网络调用，未修改生产文件。结果保存到已忽略的 scope-review-comparison.json。
- 完成复评结论.md，列出文件级建议、替代实现边界和邻近案例验收条件。
- 本轮不宣称新方案已修复或 63 案已通过；没有部署、提交或执行回滚。
- 两个临时探针已删除；git diff --check 通过，已有生产代码差异统计未变。
- 用户确认保留实体关系抽取，其他新增机制收敛；具体范围写入 addendum.md。继续沿用 planning-with-files 与 diagnosing-bugs 工作流。
- 新增真实 HTTP 调用链的假模型回归，修改前确认失败：bp-0049 被调用前过滤，synthesize 模型 calls 为空（1 failed）。
- 撤掉方案映射 YAML、三处关系过滤及固定交接话术；保留实体关系与原话校验。选案提示词解释关系语义，并修正“源头未修复就不能提供后果帮助”的限制。
- 测试改名为 test_charging_facts.py，删除硬拦截专用预期，保留事实更正、因果原话校验，增加说明发布和模型上下文链路验证。
- 定位时两次命令未找到目标（不存在 test_synthesize.py、shell 无匹配 glob）；改用 rg --files 定位实际测试文件，无代码影响。
- 首轮收敛测试 9 passed / 3 failed：三个失败均因我把 0049、0066 假定为 statement 节点。实际发布计划将其编成 action，已查原文和计划，测试改为核对首卡可发布，不以 explained 作为预期。不把这一既有知识转换问题扩入本轮修复。
- 相关测试七个文件共 95 passed（关系事实、既有适用性、事实更正、容量、步骤类型、两类交接摘要）；make lint 通过，git diff --check 通过。
- 启动 make t52-regression ARM=entity-only，真实模型与知识库，业务会话使用内存；范围 T52/T52-repeat/T52-zh/T52-output/T52-direct/T51/T53/T54/T29/T61。原始 JSON 留 reports/eval/t52-production/entity-only/，不会入库。
- 四个已返回案例均在 intake 理解阶段失败，无关系事实、无选案或步骤卡；日志同时出现 HTTP 503。本批第五个请求被主动中断，其余未执行。没有修改超时、模型或其他任务。
- 保存实施结果.md，包含最终范围、数据流程、失败后通过的回归过程、真实请求逐案中文记录及未验证边界。
- 临时修改/检查/结果提取脚本已删除；最终 diff 检查通过，真实评测 JSON 确认被忽略。未提交、未部署。
