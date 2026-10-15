# 证据

- 2026-10-15 13:48 北京时间：官方 https://status.deepseek.com/ 显示所有系统正常，包括 V4 Pro 和 V4.1 Flash API。状态页不证明每个请求正常。
- 当前本地配置：deepseek-pro 超时 9 秒，deepseek 20 秒；理解链顺序 deepseek-pro → qwen-flash → deepseek。qwen-flash 仍为 qwen3.7-flash。
- 工作区开始时干净；本轮不修改生产配置。
- 13:49 五次请求全部成功：Pro 最小 4.315 秒、Flash 最小 0.599 秒；Pro T52/T56 理解 4.164/4.293 秒；Flash T52 理解 1.974 秒。当前链首选均成功，未触发备用。
- 官方错误码页 https://api-docs.deepseek.com/quick_start/error_codes/ 将 503 定义为 Server Overloaded。上午单次 503 可判为服务端过载，其他超时原因仍不能唯一归因。
