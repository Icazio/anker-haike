# 证据：12 个会话逐条转写摘要

公网站 https://52.221.175.117/ 经 SSH 转发连到本机后端，会话存在本机 `haike.session_events`。
下表覆盖 10-15 15:09 至 10-16 00:45（北京时间）的全部 12 个会话。这些会话是否都来自这次测试，没有核实。

| 会话 | 北京时间 | 场景 | 走到哪一步 | 暴露的问题 |
| --- | --- | --- | --- | --- |
| 883a1b7a | 10-15 15:09 | 「What does this green light mean」+ 1 张图 | 系统反问是哪款产品，会话到此为止 | — |
| 51fde499 | 10-15 15:17 | T55 吸奶器 RMA 邮件，订单 Anker016 | 走完全链路：3 步排障 → 质保（保内至 2027-04-01）→ 补 SN → 补照片 → 换货方案 → 闸门 + 独立审查通过 → 服务单 SRV-A9C0FA7590AE → 评分 | 补一项材料，系统就把「I've checked: order Anker016 is under warranty…」整段重发一遍 |
| 47b83304 | 10-15 23:13 | 荷兰语物流邮件，订单 Anker006 | 显示已送达 → 方案「承运商调查」→ 客户点「暂不办理」 | 拒绝方案后系统没有回复 |
| e774c74e | 10-15 23:46 | 中文首条是乱码（GBK 还原为「我的扫地机器人回不了充电座」） | 产品卡选 E25 → 步骤 1 → 16 分钟后点「请求人工」 | 首条乱码 |
| 6f4fab6d | 10-15 23:57 | 荷兰语 App 报错 7002 | 步骤 1 解决 → 评分 | 消息发出后直接是步骤卡，没有开场 |
| 4571f88b | 10-15 23:57 | T1 物流，订单 Anker001 | 显示已送达 → 承运商调查 → 暂不办理 → 沉默 76 秒 → 点「请求人工」 | 拒绝方案后系统没有回复 |
| 932565c7 | 10-16 00:05 | C20 走不直，客户不满（「absolutely rubbish since day one」） | 两个纯文本是否题 → 步骤 → 要订单号 → 客户填「123」→ 通用澄清 → 点「请求人工」 | 是否题没有按钮；无效订单号没有引导 |
| 12eb534c | 10-16 00:25 | 德语 App 报错 2111 | 步骤 1 未解决 → 要订单号 → 客户填「111112222222」和「ok」→ 两次回「The applicable troubleshooting steps have been tried…」→ 点「请求人工」 | 答非所问，同一句发了两次 |
| 65379a90 | 10-16 00:27 | 中文：没收到货，没发货就取消订单 | 没要订单号，直接转人工 | 中文问、英文答；人工拿到的案件没有订单号 |
| 5e53274b | 10-16 00:27 | 中文：水箱不出水 | 产品卡选 C20 → 纯文本是否题 → 步骤 → 要订单号 → 跳过 → 转人工 → 新问题 → 点「请求人工」→ 「Your case is waiting…」×2 | 中文问、英文答；是否题没有按钮；同一句发了两次 |
| 9c461c71 | 10-16 00:40 | 中文：X10 水盘不排空 | 步骤 1 解决 → 评分 | 中文问、英文答 |
| 587c65da | 10-16 00:41 | 同上，3 步都选「还没解决」 | 要订单号，同一段逐字发了 3 次 → 跳过 → 转人工 → 「我要退货」「我要退款」→ 同一句 ×2 | 同一段反复发；退货诉求没有回应；中文问、英文答 |

统计：12 个会话共 38 条助手消息，其中 6 条与同会话前面的某条逐字相同。
5 个会话中途点了「请求人工」：e774c74e、4571f88b、932565c7、12eb534c、5e53274b。
只有 51fde499 一个会话走到了方案和审查。

## 会话 587c65da 完整片段

```
00:41:10 客户  我的扫地机器人出问题了：X10 Pro 水盘不能排空。客户已清洁，检查软管没有被挤压……
00:41:23 卡片  步骤 1 Please check whether the cleaning tray is installed correct…   → 还没解决
00:41:41 卡片  步骤 2 Please check whether the buoy in the cleaning tray is insta…   → 还没解决
00:41:45 卡片  步骤 3 If the cleaning tray is in place and water accumulates in t…   → 还没解决
00:41:52 系统  The official troubleshooting for this issue is complete and the problem isn't
               resolved, so the next step is an after-sales review; … Please share your order
               number. If you bought it from another seller, please upload your proof of purchase
               showing the seller name, country of purchase and purchase date.
00:42:11 客户  我现在要求退货
00:42:14 系统  （与 00:41:52 逐字相同）
00:42:45 客户  订单号21312524860245200，发票找不到了
00:42:50 系统  （与 00:41:52 逐字相同）
00:44:56 客户  [暂时没有凭证，跳过]
00:44:59 系统  I can't confirm the warranty status yet (no order or proof of purchase was
               provided), so I've passed the details to a colleague to check.
00:45:06 客户  我要退货
00:45:09 系统  Your case is waiting to be processed. Updates will appear in the case status.
00:45:29 客户  我要退款
00:45:32 系统  Your case is waiting to be processed. Updates will appear in the case status.
```

本会话转人工摘要里情绪为空（`emotion.level = None`），策略为 `normal`。

## 会话 51fde499 的案件事件（证明审查确实跑过）

```
order_identified    {"order_no": "Anker016"}
status_changed      open → proposing → awaiting_confirmation（等待补充 SOP 证据）× 2
status_changed      → awaiting_confirmation（等待客户确认提交）
review_completed    outcome=passed，「独立审查一致：诉求、故障、产品有客户原话或订单依据，无反证」
updated             提交闸门已检查
status_changed      → executing → tracking（服务单已创建）
execution_attached  SRV-A9C0FA7590AE
status_changed      → awaiting_approval（服务单已提交，转人工处理）
```

这些事件只能在管理端 `/admin/desk/:id` 和 `/admin/sessions/:id` 看到，客户页没有展示。

## 截图

| 文件 | 内容 |
| --- | --- |
| img/01-repeat-receipt-ask.jpg | 587c65da：同一段索要订单的话连发 3 次 |
| img/02-after-handoff-repeat.jpg | 587c65da：转人工之后「我要退货」「我要退款」都回同一句 |
| img/03-invalid-order-generic-reply.jpg | 932565c7：订单号填「123」，系统回通用澄清 |
| img/04-product-card-no-image.jpg | 5e53274b：产品卡用表情代替产品图 |
| img/05-home.jpg | 首屏 |
| img/06-admin-flow-graph.jpg | 管理端会话流程图（事后生成的静态图） |

## 官网产品图来源（eufy.com 商品页的 og:image，10-16 取到）

| SKU | 商品页 | 备注 |
| --- | --- | --- |
| T2080 Omni S1 Pro | /products/t2080111 | 已停售，跳转到文章页，只取到文章配图 |
| T2351 X10 Pro Omni | /products/t2351111 | 已停售，页面仍有主图 |
| T2352 Omni E28 | /products/t2352111 | |
| T2353 Omni E25 | /products/t2353111 | |
| T2280 Omni C20 | /products/t2280111 | |
| T2292 Auto-Empty C10 | /products/t2292111 | |
| T8D04 S1 Pro 吸奶器 | /products/t8d04121 | |
| T8170 SoloCam S340 | /products/t81701w1 | |
