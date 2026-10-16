# 已核对事实

- 现有公网 Caddy 经 SSH 反向隧道访问本机 Vite，仍依赖本机运行；已有正式 IP 证书与独立 viewer/admin 认证。
- 根 Compose 包含 orchestrator、ParadeDB/Postgres、Redis、WeKnora app/docreader、pg-backup，可选 WeKnora UI。
- orchestrator/Dockerfile 已多阶段构建客户与管理前端，FastAPI 托管静态资源；线上不需要 Vite 5173。
- 旧生产覆盖使用 Nginx 80/443，会与现有 Caddy 冲突，且不能直接复用现有双角色认证配置。
- 数据库逻辑备份有 haike/WeKnora 两库；WeKnora 文件卷不在数据库备份内。知识库 manifest、config、官方数据同样影响运行。
- Makefile 的 prod-up 自动 build；db-upgrade/db-check 走本机 uv/.env；这些命令不能未经适配直接视为云端发布流程。
- 当前工作区存在其他会话的前端与 .gitignore 修改，发布须明确冻结版本，不从漂移中的目录打包。
- 2026-10-10 的额度记录是 200 USD、2026-10-31 到期；本轮尚未重查余额，不将历史值表述为当前余额。
- 只读容量快照：本机 Compose 7 个服务运行，容器合计约 1.31 GiB 内存（不是峰值）；Docker 全局镜像 24.44 GB、卷 5.615 GB，包含其他/历史资源，不能直接当迁移数据量。
- 云端只读快照：总内存 911 MiB、无 swap，根文件系统 6.8 GiB、可用 4 GiB，Caddy active，x86_64。完整服务不能按原规格直接搬入。
- Dockerfile 已把官方数据、回放、配置与两个前端入口装入镜像，后端固定单 worker；不能未经并发状态验证就增加 worker 或副本。
- 旧 Nginx 统一账号并透传 remote_user，缺少现有管理员独立授权语义，不能作为迁移后入口直接启用。
- 源库只读容量：haike 2,067,863,219 bytes（约 1.93 GiB），WeKnora 42,194,611 bytes（约 40.2 MiB）；WeKnora 文件卷 /data/files 为 24 KiB。最终停写快照必须再次计量。
- WeKnora 实际扩展：pg_search 0.22.2、vector 0.8.1、pg_trgm 1.6、uuid-ossp 1.1。迁移先保持同版本；不能把普通 PostgreSQL/RDS 当完全等价替换。
- 根 .env 的模型/WeKnora key 已设置，MODEL_LANE=domestic，Langfuse 未启用；未输出任何值。WeKnora AES/JWT 环境项未在根 .env 设置，需核对实际生效值并保留密文解密能力，不能迁库时随意换 AES key。
- 当前 /health 只有数据库 down 时返回 503；WeKnora 或模型配置故障仍可能 HTTP 200。模型健康仅检查配置和 key 存在，不能证明厂商调用可用。验收必须检查 JSON 各组件及真实业务。
- /health/live 仅证明进程存活。知识库适配器缺 API key 或 manifest 可静默降级，因此还必须验证实际召回内容、来源和数量。
- 当前 restore.sh 会吞掉 pg_restore 非零返回码并继续；云端迁移需要严格失败处理与数据比对，不能只看 restore done。
- 根 Compose 会把会话保留期设为 168h，Settings 默认 24h；云端要显式固定与实际源一致，避免迁移后自动清理造成误判。

## 官方资料

- https://aws.amazon.com/ec2/instance-types/t3/：T3 large 2 vCPU / 8 GiB；Standard 与 Unlimited 的性能/费用区别。页面通用价格不可当新加坡报价。
- https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-instance-resize.html：改变现有实例规格需要考虑停机路径。
- https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/working-with-eips.html：固定公网 IP 可重新关联实例。
- https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/burstable-performance-instances-standard-mode.html：Standard CPU 积分耗尽后性能受基线限制，容量验收需观察积分趋势。
- https://www.postgresql.org/docs/16/app-pgdump.html：逻辑备份/恢复与版本兼容；实施按 PG17 文档核对具体参数。
- https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_use_switch-role-ec2.html：EC2 使用 IAM role 获取临时凭据，备份不新增长期 AWS key。

## 干净初始化的实现证据

- 当前 seed_cli 只支持 products/all，写产品目录；订单、经销商、Q&A 从 data/official 读取。旧 database.md 的 seed backends 说明已不匹配当前实现。
- WeKnora 源库有 1,514 条 knowledges、4 条 sessions、20 条 messages，因此不能整库迁移来满足“不迁历史会话”。
- 官方 Q&A 可从 data/official/qa.yaml 幂等重建知识库；推荐云端新 tenant + 新 API key + 新知识库，保留内容/源版本，云端重新生成 manifest ID。会产生一次 embedding 调用费用，实施前计量，不在本轮执行。
- 云端知识重建前对照源库可见条目与 qa_id/版本/正文摘要；若有源文件之外的手工知识，需要内容导出补入，不可默默遗漏。
- knowledge/cli.py 的密钥输出路径硬编码 REPO_ROOT/.env、manifest 硬编码 REPO_ROOT/data/knowledge，容器中 REPO_ROOT 为 /；现有 Compose 又将 manifest 单文件只读挂载。实施必须增加受控 env/manifest 路径和一次性初始化写入路径，运行时再只读挂载。
- wait_parsed 可能返回 failed/pending，verify 命令打印状态但总返回 0；上线验收需显式断言 failed/pending/processing/finalizing=0，而不是只看 CLI 退出码。
- models.yaml 注释记录过智谱账号并发 4 限流；当前主路由 domestic。5 人验收要测厂商限流/降级与延迟，不能用配置 max_in_flight=50 当实际容量证明。

## 价格核对（2026-10-13）

- AWS 官方公开价目 JSON 查询成功（响应体为 gzip）：新加坡 Linux t3.medium 0.0528 USD/h，t3.large 0.1056 USD/h，t3.micro 0.0132 USD/h。
- 数据地址：https://b0.p.awsstatic.com/pricing/2.0/meteredUnitMaps/ec2/USD/current/ec2-ondemand-without-sec-sel/Asia%20Pacific%20(Singapore)/Linux/index.json
- t3.medium rateCode USWP83ASNCY4BSQF.JRTCKXETXF.6YS6EN2CT7；730h 为 38.544 USD。
- 官方 VPC 页面当前公网 IPv4 为 0.005 USD/h，730h 为 3.65 USD。
