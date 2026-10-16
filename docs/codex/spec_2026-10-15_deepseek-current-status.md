# DeepSeek 当前调用状态复核

时间：2026-10-15 10:30–10:31，北京时间。用户询问是否仍报错、是否为官方问题。本次只做状态诊断，不改代码或模型配置。

## 本机真实请求

通过现有 make model-probe 入口，向每个模型单独发送“只回复两个字：收到”，输出上限 16 token。探针关闭 SDK 重试，不经过备用链，因此失败不会被其他模型成功掩盖。每模型采样一次，不能据此计算长期可用率。

| 命令 | 实际模型 | 结果 |
|---|---|---|
| make model-probe TASK=intake ALIAS=deepseek-pro | deepseek-v4-pro | 9.012 秒，TimeoutError |
| make model-probe TASK=intake ALIAS=deepseek | deepseek-flash | 20.008 秒，TimeoutError |
| make model-probe TASK=intake ALIAS=qwen-flash | qwen3.7-flash | 1.582 秒，返回“收到” |

两个 DeepSeek 模型分别触及当前 9 秒和 20 秒探针上限。本次没有返回 HTTP 503，不能把当前结果写成 503；此前记录中的 503 是另一次调用。

## 官方证据

[官方事故公告](https://status.deepseek.com/incidents/7116348214287)在查询时显示网页/API 部分中断，涉及 DeepSeek V4 Pro API 与 V4.1 Flash API。

- 事故起始：2026-10-15 00:11 UTC，即北京时间 08:11。
- 最新更新：01:08 UTC，即北京时间 09:08；已定位原因，正在实施修复。
- 查询时尚未显示恢复。官方未披露技术根因。

结论：当前仍能复现超时，且官方确认同时间段、同模型服务存在事故，故服务端故障是有直接证据支持的主要原因。Qwen 对照正常说明本机至少可完成其他厂商请求，但不能单凭对照彻底排除到 DeepSeek 的网络路径影响，也不能证明此前每次失败都由同一根因造成。

当前理解链为 deepseek-pro → qwen-flash → deepseek。此文记录的是独立探针，未声称已在本轮验证完整故障切换；主模型超时等待与总预算分配仍是系统自身需要控制的问题。

诊断流程在真实复现与官方事故交叉验证后结束：本次未要求修复业务代码，官方内部根因也不可在本机验证，因此不做推测性代码修改、不添加单测或部署。保留配置，不提交。
