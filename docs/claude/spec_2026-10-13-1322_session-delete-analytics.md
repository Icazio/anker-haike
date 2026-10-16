# 按会话删除漏删 analytics 事实

## 问题

`app/retention.py` 的 `SESSION_TABLES` 列了 `model_calls`、`retrieval_calls`、`node_runs`、`run_facts`、`session_facts` 五张表，但没写 schema；`_existing_tables` 只查 `current_schema()`（public）。这五张表实际在 `analytics` schema 下（迁移 0004），库的 search_path 是 `"$user", public`，所以每次都被当成「表不存在」静默跳过。`analytics.cases`（管理台标注）也不在列表里。

追踪（本机库，2026-10-13）：

- public 下没有这五张表；`analytics.session_facts` 有 `first_question`（客户首问，脱敏后不超过 200 字）。
- 管理台会话列表 `AnalyticsQueries.sessions()` 只读 `analytics.session_facts`。
- 结果：`make session-delete SID=…` 或 `DELETE /sessions/{id}` 之后，原始会话没了，管理台列表里这一行和客户首问仍在。

## 两条删除路径的语义

| 路径 | 入口 | analytics |
| --- | --- | --- |
| TTL 过期清理 | `retention_loop`、`make retention-purge`（`delete_session_data(..., expired_before=cutoff)`） | 保留。观测台设计里 analytics 生命周期比原始会话长，`session_facts.raw_available_until` 就是给管理端标「原始会话已过期」的（迁移 0004 说明、`docs/planning/2026-09-13_admin-observability-console/01_design.md` §与现有表的关系）。 |
| 按会话删除 | `DELETE /sessions/{id}`、`make session-delete`（`expired_before=None`） | 删除。这是人工处理用户删除请求，管理台不应再显示这个会话。 |

不改 TTL 的行为：TTL 下删掉 analytics 会让管理台 7 天前的历史全部消失，与观测台设计相反。

## 方案

- `SESSION_TABLES` 去掉这五个没有 schema 的表名（public 下不存在）。
- 新增 `ANALYTICS_TABLES`：`cases`、`model_calls`、`retrieval_calls`、`node_runs`、`run_facts`、`session_facts`，用 `app.analytics.schema.SCHEMA` 拼出全名。
- `delete_session_data` 在 `expired_before is None` 时，同一事务里删除这些表中该会话的行；表存在性按 analytics schema 查。返回计数的键写成 `analytics.<表名>`，避免和 public 的 `cases` 混淆。
- 更新 retention 模块说明、删除接口说明与 Makefile 帮助文字。

## 验证

- `tests/test_retention.py` 新增真实 Postgres 用例（连不上库或 analytics schema 不存在时跳过）：给一个过期会话写满六张 analytics 表；TTL 路径删除后原始会话没了、analytics 行还在；再走按会话删除，六张表都清空，计数各为 1。
- `make lint`；`uv run pytest -q tests/test_retention.py tests/test_l3_postgres.py`。

## 结果（2026-10-13）

- 新用例在真实 Postgres 上运行并通过；把删除分支临时改成不执行时，用例在 analytics 计数断言处失败，说明它能拦住这个回归。
- `make lint` 通过；`test_retention.py`、`test_l3_postgres.py`、`test_admin_api.py`、`test_analytics.py` 共 70 项通过。
- `make up` 重建后，对本机一个当天测试会话执行 `make session-delete`：返回计数里有 `analytics.session_facts: 1`、`analytics.run_facts: 1`、`analytics.node_runs: 4`、`analytics.model_calls: 1`；删除后该会话在 `sessions` 与各 analytics 表中都没有剩余行。
