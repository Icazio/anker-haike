# 63 单真实链路回放（2026-10-15 06:22 UTC）

客户策略与指标口径见 orchestrator/app/evaluation/live_tickets.py。机器人闭环率只统计期望终点可由机器人独立闭环的工单（物流运输中、预售、过保告知、解释）。

**这些数字证明的是「没走错 SOP 分支」，不是「回答内容正确」。**
- `sop_accuracy` 含 ACCEPT 表里的替代终点（排障单走完「还没解决」必然进质保分支，是驱动策略使然）；
  其中完全命中标注终点 `sop_exact` = 63%，经替代终点通过 14 单。
- `hallucination` 只检查标注的禁止承诺与未收录错误码，不校验事实（日期、单号、金额）是否正确。
- 回答质量需人工逐条核对；两者结论曾经不一致，见 docs/planning/2026-10-09-0841_finals-tracking/。

| 指标 | 值 |
| --- | --- |
| cases | 63 |
| errors | 0 |
| intent_accuracy | 86% |
| sop_accuracy | 86% |
| sop_exact | 63% |
| sop_via_alternate | 14 |
| bot_closed_rate | 100% (8/8) |
| service_order_submitted | 8 |
| hallucination_cases | 0 |
| median_seconds | 9.3 |

| id | 语言 | 意图 期望 / 实际 | SOP 期望 → 终点 | 步骤卡 | 服务单 | 转人工原因 | 幻觉 | 秒 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| T1 | en | ✓ logistics_query / logistics_query | ✓ logistics_delivered → logistics_delivered | 0 | 是 |  |  | 6.9 |
| T2 | en | ✓ logistics_query / logistics_query | ✓ logistics_delivered → logistics_delivered | 0 |  |  |  | 9.9 |
| T3 | en | ✓ logistics_query / logistics_query | ✓ logistics_delivered → logistics_delivered | 0 | 是 |  |  | 5.5 |
| T4 | en | ✓ logistics_query / logistics_query | ✓ logistics_delivered → logistics_delivered | 0 | 是 |  |  | 3.8 |
| T5 | en | ✓ logistics_query / logistics_query | ✓ logistics_reship → logistics_reship | 0 | 是 |  |  | 3.2 |
| T6 | nl | ✓ logistics_query / logistics_query | ✓ logistics_delivered → logistics_delivered | 0 | 是 |  |  | 2.8 |
| T7 | en | ✓ logistics_query / logistics_query | ✓ ask_order → ask_order | 0 |  |  |  | 3.0 |
| T8 | en | ✓ logistics_query / logistics_query | ✓ logistics_reship → logistics_reship | 0 | 是 |  |  | 3.6 |
| T9 | en | ✓ logistics_query / logistics_query | ✓ logistics_presale + order_change_human → order_change_human + logistics_presale | 0 |  |  |  | 5.4 |
| T10 | en | ✓ logistics_query / logistics_query | ✓ logistics_delivered → logistics_delivered | 0 | 是 |  |  | 3.1 |
| T11 | en | ✓ report_problem / report_problem | ✓ troubleshoot → troubleshoot | 5 |  | R6 |  | 7.4 |
| T12 | en | ✓ report_problem / report_problem | ✓ explain → troubleshoot | 1 |  |  |  | 9.8 |
| T13 | nl | ✓ report_problem / report_problem | ✓ code_miss → code_miss | 0 |  | R5 |  | 5.4 |
| T14 | en | ✓ report_problem / report_problem | ✓ warranty_by_qa → ask_order | 0 |  | R6 |  | 24.2 |
| T15 | en | ✓ report_problem / report_problem | ✓ troubleshoot → troubleshoot | 4 |  | R6 |  | 7.2 |
| T16 | en | ✓ report_problem / report_problem | ✓ troubleshoot → troubleshoot | 2 |  | R6 |  | 8.2 |
| T17 | en | ✓ report_problem / report_problem | ✓ troubleshoot → troubleshoot | 2 |  | R6 |  | 5.6 |
| T18 | nl | ✓ report_problem / report_problem | ✓ troubleshoot → troubleshoot | 1 |  | R6 |  | 6.9 |
| T19 | en | ✓ report_problem / report_problem | ✓ troubleshoot → troubleshoot | 1 |  |  |  | 14.2 |
| T20 | nl | ✓ report_problem / report_problem | ✗ troubleshoot → explain | 0 |  |  |  | 20.3 |
| T21 | fr | ✓ report_problem / report_problem | ✓ troubleshoot → troubleshoot | 3 |  | R6 |  | 24.4 |
| T22 | nl | ✓ report_problem / report_problem | ✓ troubleshoot → troubleshoot | 2 |  | R6 |  | 8.7 |
| T23 | en | ✓ report_problem / report_problem | ✓ troubleshoot → troubleshoot | 2 |  | R6 |  | 6.9 |
| T24 | en | ✓ report_problem / report_problem | ✓ troubleshoot → troubleshoot | 1 |  | R6 |  | 7.1 |
| T25 | en | ✓ report_problem / report_problem | ✓ troubleshoot → troubleshoot | 2 |  | R6 |  | 6.5 |
| T26 | en | ✓ report_problem / report_problem | ✓ troubleshoot → troubleshoot | 2 |  |  |  | 5.0 |
| T27 | en | ✓ report_problem / report_problem | ✓ troubleshoot → troubleshoot | 1 |  | R6 |  | 9.3 |
| T28 | de | ✓ report_problem / report_problem | ✓ troubleshoot → troubleshoot | 1 |  | R6 |  | 6.6 |
| T29 | en | ✓ report_problem / report_problem | ✓ out_of_warranty → out_of_warranty | 3 |  |  |  | 12.6 |
| T30 | en | ✓ report_problem / report_problem | ✓ troubleshoot → troubleshoot | 2 |  | R6 |  | 21.8 |
| T31 | en | ✓ report_problem / report_problem | ✓ troubleshoot → troubleshoot | 4 |  | R6 |  | 16.3 |
| T32 | en | ✓ report_problem / report_problem | ✓ troubleshoot → troubleshoot | 1 |  | R6 |  | 9.1 |
| T33 | en | ✓ report_problem / report_problem | ✓ troubleshoot → troubleshoot | 1 |  | R6 |  | 5.3 |
| T34 | en | ✓ report_problem / report_problem | ✓ troubleshoot → troubleshoot | 2 |  | R5 |  | 14.2 |
| T35 | en | ✓ report_problem / report_problem | ✓ explain → explain | 0 |  |  |  | 7.8 |
| T36 | nl | ✓ report_problem / report_problem | ✗ troubleshoot → clarify | 0 |  |  |  | 14.7 |
| T37 | nl | ✓ report_problem / report_problem | ✓ troubleshoot → troubleshoot | 1 |  | R6 |  | 14.3 |
| T38 | en | ✓ report_problem / report_problem | ✗ out_of_warranty → troubleshoot | 1 |  |  |  | 21.8 |
| T39 | en | ✓ report_problem / report_problem | ✗ troubleshoot → explain | 0 |  |  |  | 6.6 |
| T40 | en | ✓ report_problem / report_problem | ✓ troubleshoot → troubleshoot | 1 |  |  |  | 10.5 |
| T41 | en | ✓ report_problem / report_problem | ✓ troubleshoot → troubleshoot | 1 |  | R6 |  | 16.7 |
| T42 | en | ✓ report_problem / report_problem | ✓ warranty_by_qa → ask_order | 0 |  | R6 |  | 22.8 |
| T43 | es | ✓ report_problem / report_problem | ✗ troubleshoot → explain | 0 |  |  |  | 9.5 |
| T44 | en | ✓ replacement_request / replacement_request | ✓ warranty_by_qa → ask_order | 0 |  | R6 |  | 6.4 |
| T45 | en | ✓ report_problem / report_problem | ✓ safety_human → safety_human | 0 |  | R4 |  | 7.3 |
| T46 | en | ✓ report_problem / report_problem | ✓ warranty_replace → clarify | 0 |  |  |  | 19.8 |
| T47 | en | ✓ logistics_query / logistics_query | ✓ logistics_delivered → logistics_delivered | 0 | 是 |  |  | 8.9 |
| T48 | en | ✓ report_problem / product_question | ✓ explain → explain | 0 |  |  |  | 16.3 |
| T49 | en | ✗ replacement_request / report_problem | ✓ dealer_check → ask_order | 0 |  | R6 |  | 5.6 |
| T50 | en | ✓ report_problem / report_problem | ✓ clarify → explain | 0 |  |  |  | 8.8 |
| T51 | en | ✗ replacement_request / report_problem | ✓ out_of_warranty → out_of_warranty | 5 |  |  |  | 14.3 |
| T52 | en | ✓ report_problem / report_problem | ✓ clarify → no_guidance | 0 |  | R5 |  | 23.1 |
| T53 | en | ✗ replacement_request / report_problem | ✓ out_of_warranty → out_of_warranty | 0 |  |  |  | 43.1 |
| T54 | en | ✓ report_problem / report_problem | ✗ troubleshoot → explain | 0 |  |  |  | 23.0 |
| T55 | en | ✗ report_problem / None | ✓ warranty_replace → clarify | 0 |  |  |  | 15.0 |
| T56 | en | ✗ report_problem / None | ✓ troubleshoot → ask_order | 0 |  |  |  | 15.0 |
| T57 | en | ✗ report_problem / None | ✗ troubleshoot → clarify | 0 |  |  |  | 15.0 |
| T58 | en | ✓ complaint / complaint | ✓ clarify → explain | 0 |  |  |  | 23.0 |
| T59 | en | ✗ replacement_request / None | ✗ troubleshoot → clarify | 0 |  |  |  | 15.0 |
| T60 | en | ✗ report_problem / complaint | ✓ clarify → explain | 0 |  |  |  | 31.1 |
| T61 | en | ✗ report_problem / None | ✓ clarify → clarify | 0 |  |  |  | 15.0 |
| T62 | en | ✓ report_problem / report_problem | ✗ troubleshoot → explain | 0 |  |  |  | 20.0 |
| T63 | en | ✓ parts_purchase / report_problem | ✓ clarify + order_change_human → order_change_human + explain | 0 |  |  |  | 8.2 |
