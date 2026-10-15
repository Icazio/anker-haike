# 理解任务的 Qwen 备用顺序

用户要求将 Qwen 调到第二位。将默认国内通道的 intake（用户意图理解）从 deepseek-pro → deepseek → qwen-flash 改为 deepseek-pro → qwen-flash → deepseek，首选失败后先切换厂商。

qwen-flash 仍对应 qwen3.7-flash；前轮 qwen3.8-flash 对照出现超时，不执行版本升级。读取本轮配置时 deepseek-pro 超时已为 9 秒，本次仅调整理解任务顺序和配置版本，不改其他模型参数或任务路由。

验证：配置加载及路由表相关测试、实际配置的 route-table 展示、make lint。本次不调用真实模型、不提交或发布。

结果：test_models_config.py 的 22 项测试通过；make route-table LANE=domestic 确认 intake 第二位为 qwen-flash；make lint 与 git diff --check 通过。
