# 官方 63 单当前源码回测

目标：用当前 HEAD（b92b3fe，含 66ca080 理解链换厂商、2ce0976 bp-0114 前提）重跑 63 单，看效果，把问题分类。

方法：

- 入口：`run63.py`，进程内 HTTP（`app.replay.cli._Harness`，会话 / 案件 / 业务动作用内存服务），真实模型与 WeKnora；客户策略与指标直接复用 `app/evaluation/live_tickets.run_case`（步骤卡一律"没解决"，问句卡即停，凭证跳过）。
- 容器 `haike-orchestrator-1` 构建于 10-13，落后 HEAD，不用它测。
- 内存模式下 `/admin/api/sessions/{id}/journey` 返回 503，意图改从首个 intake 的 model_call 输出取；`/admin/api/cases` 正常（39 次 200）。
- 并发 3 跑全量；运行异常的单（理解或选方案模型失败）再串行补测一次，首轮结果保留。
- 逐单人工阅读回复、卡片、交接摘要；自动指标只说明"没走错分支"。

不改业务代码、不提交、不发布。JSON / 日志 / 脚本按 .gitignore 只留本机。
