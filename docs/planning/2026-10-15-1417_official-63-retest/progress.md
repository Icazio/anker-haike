# 执行记录

- 14:05 读上轮 0857 方法与结论、22 难点汇总；确认运行中的容器构建于 10-13，落后 HEAD 十余个提交，不用它测。
- 14:10 写 `run63.py`：`_Harness` 进程内 HTTP + 真实模型 / WeKnora，复用 `live_tickets.run_case`；按单落完整事件流与每次 model_call 的尝试记录。T1、T55、T31 冒烟通过。
- 14:17 全量 63 单，并发 3，约 30 分钟跑完，0 单报错。版本见 `version-before.txt`。
- 边跑边逐单读 `main.txt`（`readable.py` 生成）。
- 14:50 后段 T52–T62 出现成片理解 / 选方案超时；串行补测这 11 单（`retest/`），首轮结果保留。
- 测试前后 HEAD、工作区状态、models.yaml 版本一致（`version-before.txt` / `version-after.txt`）。
- `run/report.md` 不在 .gitignore 范围内，内容只有官方样本工单的首句回复，订单号均为样本 `Anker0xx`，无凭据。
- 结论写入 `结论与问题分类.md`。未改业务代码、未提交、未发布。
- 15:00–15:30 按用户选定方案（并入交接并告知）修第 2 节「多诉求转人工后停摆」，spec 见 docs/claude/spec_2026-10-15-1457_queue-after-handoff.md；真实模型复测 T9/T41/T49/T59/T63 在 queue-fix/（只留本机）。
