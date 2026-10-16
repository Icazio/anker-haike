# 客户可见英文固定话术清单

来源：`xiaokekehaha/anker-haike` @ `bb863fe`，叠加分支 `feat/demo-test-fixes`（Icazio fork）。整理日期 2026-10-17。

## 说明

- 共 **184** 条，全部写死在 `orchestrator/app` 的 Python 代码里，不经过大模型，客户原样看到。
- 根因是产品决策 **D2（2026-10-08）"客户可见输出用英文"**。`official/message.py:113` 的 `detect_language` 能识别客户语言，但回复链路没有使用它。
- 抽取方法：脚本扫描字符串字面量，拼接 Python 隐式续行，排除日志、异常、正则、HTTP 头、模型配置报错和测试/评测/管理端目录，再人工逐条复核。可能仍有少量漏网（例如少于 4 个英文词的短句）。
- **★** = 线上测试记录里实际出现过。**（拼接片段）** = 这条不是完整句子，会和变量或其他片段拼成一句。
- 中文列是参考译文，用来看懂含义、评估改动量，不是最终文案。

## 分类统计

| 分类 | 条数 | 测试中出现 |
|---|---|---|
| 1 安全 | 10 | 1 |
| 2 致歉 / 情绪 / 通用 | 17 | 2 |
| 3 追问与澄清 | 12 | 1 |
| 4 产品咨询 | 7 | 0 |
| 5 排障步骤与卡片 | 40 | 2 |
| 6 读图 | 5 | 0 |
| 7 物流 | 17 | 1 |
| 8 订单 / 质保 / 售后办理 | 40 | 4 |
| 9 转人工 / 案件状态 | 28 | 1 |
| 10 系统异常 | 8 | 0 |

## 1 安全（10）

| # | ★ | 位置 | 名称 | 英文原文 | 中文参考 |
|---|---|---|---|---|---|
| 25 |  | `conversation/commands.py:50` | `resolve_command()` | This step is paused because of a safety concern. Let's confirm what the device is doing first. | 由于存在安全隐患，这一步已暂停。我们先确认设备现在的状况。 |
| 51 | ★ | `conversation/reduce.py:114` | `SAFETY_CONFIRM_QUESTION` | Before we continue, I need to check one thing for your safety: is there any smoke, burning smell, visible swelling of the battery, leaking liquid, or is the device too hot to touch? Please reply yes or no. | 继续之前，为了您的安全我需要确认一件事：设备有没有冒烟、焦味、电池鼓包、漏液，或者烫得不能碰？请回答是或否。 |
| 58 |  | `conversation/reply.py:105` | `fallback_reply()` | I'm sorry this isn't resolved. There's still an unconfirmed safety concern with this device, so please stop using and charging it; I can prepare what we know for our support team. | 很抱歉还没解决。这台设备仍有未确认的安全隐患，请停止使用和充电；我可以把已知情况整理给客服团队。 |
| 70 |  | `conversation/reply.py:151` | `fallback_reply()` | This step was meant to check the fault, but there's an open safety concern, so let's pause hands-on steps. We can keep confirming which device it is and what happened. | 这一步本来是用来检查故障的，但存在未解除的安全隐患，所以先暂停动手操作。我们可以继续确认是哪台设备、发生了什么。 |
| 73 |  | `conversation/reply.py:156` | `fallback_reply()` | There's still an unconfirmed safety concern with this device, so please stop using and charging it. You can correct details or ask about earlier messages. | 这台设备仍有未确认的安全隐患，请停止使用和充电。您可以更正信息，或询问之前的对话。 |
| 79 |  | `diagnose/decision.py:180` | `explanation()` | There's an unconfirmed safety concern with this device, so please stop using and charging it. We can review the record or I can prepare it for our support team. | 这台设备有未确认的安全隐患，请停止使用和充电。我们可以回顾记录，或者我整理给客服团队。 |
| 92 |  | `escalation/summary.py:413` | `SAFETY_STOP` | For your safety, please stop using the device and do not charge it. | 为了您的安全，请停止使用设备，也不要充电。 |
| 93 |  | `escalation/summary.py:416` | `INJURY_CARE` | I'm sorry you were hurt. Please stop using the device and do not charge it. If the injury is serious, please seek medical attention promptly. | 很抱歉您受伤了。请停止使用设备，也不要充电。如果伤势严重，请及时就医。（本次修复新增） |
| 95 |  | `escalation/summary.py:438` | `REASSURANCE` | I've put together a record of this issue so a support colleague can look into it. | （REASSURANCE["R4"]，前接"请停止使用…"）已把问题整理成记录，客服同事会进一步查看。 |
| 104 |  | `escalation/summary.py:479` | `reassurance_text()` | I've put together a record of this issue so a support colleague can look into it. | （R4 转人工结尾）已把问题整理成记录，客服同事会进一步查看。 |

## 2 致歉 / 情绪 / 通用（17）

| # | ★ | 位置 | 名称 | 英文原文 | 中文参考 |
|---|---|---|---|---|---|
| 40 |  | `conversation/operation_conditions.py:304` | `EMOTION_PAUSE_TEXT` | I'm sorry this is taking your time. Rather than keep adding steps, I can prepare a summary for our support team now: just say "human agent". If you'd prefer to try the next official step, reply "continue". | 抱歉占用您的时间。与其继续加步骤，我现在就可以给客服团队整理摘要，说"human agent"即可；如果想继续试下一个官方步骤，请回复"continue"。 |
| 52 | ★ | `conversation/reply.py:26` | `ACKNOWLEDGEMENT["dissatisfied"]` | I'm sorry this hasn't been a good experience. | 很抱歉给您带来不好的体验。（情绪"不满"时加在回复开头） |
| 53 |  | `conversation/reply.py:27` | `ACKNOWLEDGEMENT["angry"]` | I'm sorry about the frustration. | 很抱歉让您感到困扰。（情绪"生气"时加在回复开头） |
| 54 |  | `conversation/reply.py:28` | `ACKNOWLEDGEMENT["complaint_risk"]` | I'm sorry we haven't met your expectations. | 很抱歉没有达到您的期望。（情绪"投诉风险"时加在回复开头） |
| 55 |  | `conversation/reply.py:32` | `OFFER_HUMAN` | If you'd like a person to help, just say "human agent" and I'll prepare everything for them. | 如果需要人工帮忙，说"human agent"即可，我会为他们准备好全部信息。 |
| 56 |  | `conversation/reply.py:88` | `fallback_reply()` | I'm sorry this isn't fixed yet; let's keep the remaining effort to a minimum. | 很抱歉还没解决，剩下的我们尽量少折腾您。 |
| 62 |  | `conversation/reply.py:113` | `fallback_reply()` | I'm sorry about the trouble with your device. Tell me what it is doing (or any error shown in the app) and I'll check the official guidance; if you'd rather have a person help, I can prepare a summary for our support team. | 很抱歉您的设备出了问题。请告诉我它现在的表现（或 App 里的报错），我来查官方资料；如果想找人工，我可以给客服团队整理摘要。 |
| 64 |  | `conversation/reply.py:129` | `fallback_reply()` | There are no earlier messages in this conversation yet. | 本对话里还没有更早的消息。 |
| 65 |  | `conversation/reply.py:130` | `fallback_reply()` | Here's what was said earlier: | （拼接片段）之前的对话如下： |
| 74 |  | `conversation/reply.py:159` | `fallback_reply()` | Back to "{issue.get('title', 'the previous issue')}"; everything reported and tried so far is kept. Please tell me how it's going now. | 回到"{问题标题}"；之前反馈和尝试过的内容都保留着。请告诉我现在情况如何。 |
| 75 |  | `conversation/reply.py:161` | `fallback_reply()` | I'm here. You can keep describing the issue, or ask me to review or correct earlier details. | 我在。您可以继续描述问题，或者让我回顾、更正之前的信息。 |
| 78 | ★ | `conversation/tasks.py:136` | `identity()` | I'll handle your requests in this order: | 我会按这个顺序处理您的诉求：{A} → {B}。 |
| 126 |  | `sessions/graph.py:2881` | `closing_text()` | Great, the issue is resolved! | 太好了，问题解决了！ |
| 127 |  | `sessions/graph.py:2889` | `closing_text()` | After following the steps, | （拼接片段）按步骤操作后， |
| 128 |  | `sessions/graph.py:2890` | `closing_text()` | {who} should work normally now. | （拼接片段）{设备}现在应该能正常工作了。 |
| 129 |  | `sessions/graph.py:2891` | `closing_text()` | Regular maintenance as described in the manual helps prevent this. If anything else comes up, just come back here. | 按说明书定期保养可以预防这个问题。还有其他问题，随时回来找我。 |
| 171 |  | `sessions/l3.py:959` | `apply_l3_action()` | Thank you for your feedback. You can check your case progress at any time. | 感谢您的反馈，您可以随时查看案件进度。 |

## 3 追问与澄清（12）

| # | ★ | 位置 | 名称 | 英文原文 | 中文参考 |
|---|---|---|---|---|---|
| 30 |  | `conversation/commands.py:72` | `resolve_command()` | That model isn't one of the options. Could you confirm the model again? | 这个型号不在选项里，请再确认一下型号。 |
| 76 |  | `conversation/reply.py:162` | `fallback_reply()` | Could you tell me which device and what problem you mean? I'll continue from what we have so far. | 您指的是哪台设备、什么问题？我会接着已有的信息继续。 |
| 89 |  | `diagnose/synthesize.py:177` | `CLARIFY_TEMPLATES["polarity_uncertain"]` | You mentioned "{quote}". Which side or part has the problem, and what exactly is it doing? | 您提到"{原话}"。是哪一侧或哪个部件有问题，具体是什么表现？ |
| 90 |  | `diagnose/synthesize.py:178` | `CLARIFY_TEMPLATES["object_conflict"]` | Is the problem with the {subject} itself (for example its own charging light or power input), or with how it works together with other parts? | 问题出在 {部件} 本身（比如它自己的充电灯或电源输入），还是和其他部件配合时出现？ |
| 116 |  | `sessions/clarify.py:33` | `FIXED_QUESTIONS["product"]` | Which product is this? For example: robot vacuum X10 Pro Omni, Omni E25 / E28, S1 Pro or Omni C20; S1 Pro wearable breast pump; or SoloCam S340 camera. The model number (e.g. T2351) also works. | 这是哪款产品？例如：扫地机 X10 Pro Omni、Omni E25 / E28、S1 Pro 或 Omni C20；S1 Pro 穿戴式吸奶器；或 SoloCam S340 摄像头。型号（如 T2351）也可以。 |
| 117 |  | `sessions/clarify.py:36` | `FIXED_QUESTIONS["symptom"]` | Could you describe what the device is doing, or tell me any warning message or error code shown in the app? | 能描述一下设备现在的表现吗？或者告诉我 App 里显示的提示或错误码。 |
| 118 |  | `sessions/clarify.py:38` | `FIXED_QUESTIONS["vague_symptom"]` | I want to make sure I find the right official guidance. Could you describe "{symptom}" in a bit more detail: what exactly happens, when it happens, and is there any message or error code in the app? | 我想确保找到正确的官方资料。能把"{症状}"说得具体些吗：具体发生了什么、什么时候发生、App 里有没有提示或错误码？ |
| 119 | ★ | `sessions/clarify.py:40` | `FIXED_QUESTIONS["conflict"]` | Earlier we confirmed {confirmed}, and now you mentioned {mentioned}. Which one should we look at? | 之前确认的是 {已确认产品}，现在您提到了 {新产品}。我们看哪一台？ |
| 120 |  | `sessions/clarify.py:427` | `fixed_question()` | The device in the photo looks like a {detail['category_name']}. Is that right? | 照片里的设备看起来是{品类}，对吗？ |
| 121 |  | `sessions/clarify.py:429` | `fixed_question()` | I couldn't match that model to our product list. Could you tell me the product type, or send a photo of the model label on the device? | 这个型号没能对上我们的产品列表。能告诉我产品类型，或拍一张设备型号标签的照片吗？ |
| 122 |  | `sessions/clarify.py:471` | `REPEAT_LEAD` | Thanks, noted. I still need one thing first: | 好的，已记下。我还需要先确认一件事： |
| 124 |  | `sessions/graph.py:2471` | `_diagnose_outcome()` | I've kept your description. Please confirm the main fault you want help with, in one sentence. | 您的描述已保存。请用一句话确认您最想解决的故障。 |

## 4 产品咨询（7）

| # | ★ | 位置 | 名称 | 英文原文 | 中文参考 |
|---|---|---|---|---|---|
| 44 |  | `conversation/product_questions.py:184` | `answer_product_question()` | Which product do you mean: {names}? Reply with the product type or model and I'll look up your question. | 您指的是哪款产品：{names}？回复产品类型或型号，我来查您的问题。 |
| 45 |  | `conversation/product_questions.py:186` | `answer_product_question()` | Which product is this? Please tell me the product type and model (the model number on the device label works too), and I'll look up your question. | 这是哪款产品？请告诉我产品类型和型号（设备标签上的型号也行），我来查您的问题。 |
| 46 |  | `conversation/product_questions.py:192` | `answer_product_question()` | This model isn't covered by our product knowledge yet, so I can't confirm the official instructions for this feature. | 这个型号还没有收录到产品知识里，无法确认该功能的官方说明。 |
| 47 |  | `conversation/product_questions.py:233` | `answer_product_question()` | Our knowledge base is unavailable right now, so I can't check the instructions for this feature. | 知识库暂时不可用，无法查询该功能的说明。 |
| 48 |  | `conversation/product_questions.py:233` | `answer_product_question()` | I couldn't find official guidance that answers this feature question. | 没有找到能回答这个功能问题的官方资料。 |
| 49 |  | `conversation/product_questions.py:241` | `answer_product_question()` | I found the official information but can't put together an answer right now. Please try again shortly. | 找到了官方资料，但暂时无法整理出回答，请稍后再试。 |
| 50 |  | `conversation/product_questions.py:262` | `answer_product_question()` | I found the official information but couldn't finish the answer this time. Please try again shortly. | 找到了官方资料，但这次没能完成回答，请稍后再试。 |

## 5 排障步骤与卡片（40）

| # | ★ | 位置 | 名称 | 英文原文 | 中文参考 |
|---|---|---|---|---|---|
| 23 |  | `conversation/commands.py:38` | `resolve_command()` | Please pick an option, or tell me whether the step solved it, didn't help, or couldn't be done. | 请选择一个选项，或告诉我这一步是解决了、没用，还是做不了。 |
| 24 |  | `conversation/commands.py:45` | `resolve_command()` | There's nothing waiting for an answer right now. Which step is this about? | 目前没有待回答的问题。您说的是哪一步？ |
| 26 |  | `conversation/commands.py:53` | `resolve_command()` | I've noted the new details. Does this feedback refer to the step from before the correction? Please confirm. | 已记下新信息。这条反馈是针对更正之前的那一步吗？请确认。 |
| 27 |  | `conversation/commands.py:58` | `resolve_command()` | That answer doesn't match what I asked. Which item would you like to handle? | 这个回答和我问的对不上。您想处理哪一项？ |
| 28 |  | `conversation/commands.py:64` | `resolve_command()` | Please choose an option or tell me the result; I can't submit it for you yet. | 请选择一个选项或告诉我结果，我还不能替您提交。 |
| 29 |  | `conversation/commands.py:68` | `resolve_command()` | That answer doesn't match what I asked. Which item would you like to handle? | 这个回答和我问的对不上。您想处理哪一项？（与上条重复） |
| 31 |  | `conversation/commands.py:74` | `resolve_command()` | Please pick one of the options on the card, or describe it in a few words. | 请选择卡片上的一个选项，或用几个字描述一下。 |
| 32 |  | `conversation/commands.py:88` | `resolve_command()` | Some information is still missing. Please check what the card asks for. | 还缺一些信息，请查看卡片上的要求。 |
| 33 |  | `conversation/operation_conditions.py:172` | `resolve_operation_reply()` | Which one do you have now: the device, the cleaning tool, a spare cable, another device, or a charger? | 您现在手边有哪样：设备、清洁工具、备用线、另一台设备，还是充电器？ |
| 34 |  | `conversation/operation_conditions.py:263` | `support_question()["question"]` | Let's hold this step. Is the device not with you, are you missing a tool, unsure how to do it, or would you like to pause? | 这一步先放一放。是设备不在身边、缺工具、不知道怎么做，还是想暂停？ |
| 35 |  | `conversation/operation_conditions.py:270` | `RESOURCE_RECHECK["device"]` | Do you have the device with you now? If so, reply "I have the device now" and I'll continue from where we left off; otherwise I can prepare a summary. | 设备现在在您身边吗？在的话回复"I have the device now"，我从刚才的地方继续；否则我可以整理一份摘要。 |
| 36 |  | `conversation/operation_conditions.py:271` | `RESOURCE_RECHECK["cleaning_tool"]` | Are the cleaning tools ready? If so, reply "tools ready" and I'll give the next step; otherwise I can prepare a summary. | 清洁工具准备好了吗？好了回复"tools ready"，我给下一步；否则我可以整理一份摘要。 |
| 37 |  | `conversation/operation_conditions.py:272` | `RESOURCE_RECHECK["spare_cable"]` | Do you have a spare cable now? If so, reply "I have a spare cable" and I'll give the next step; otherwise I can prepare a summary. | 有备用线了吗？有的话回复"I have a spare cable"，我给下一步；否则我可以整理一份摘要。 |
| 38 |  | `conversation/operation_conditions.py:273` | `RESOURCE_RECHECK["spare_device"]` | Do you have another device to cross-test with? If so, reply "I have another device"; otherwise I can prepare a summary. | 有另一台设备可以交叉测试吗？有的话回复"I have another device"；否则我可以整理一份摘要。 |
| 39 |  | `conversation/operation_conditions.py:274` | `RESOURCE_RECHECK["charger"]` | Do you have a spare charger now? If so, reply "I have a charger"; otherwise I can prepare a summary. | 有备用充电器吗？有的话回复"I have a charger"；否则我可以整理一份摘要。 |
| 41 |  | `conversation/operation_conditions.py:314` | `pause_text()` | Troubleshooting is paused; everything reported and tried is kept. Say "continue" when you're ready, or I can prepare a summary for our support team. | 排障已暂停，您反馈和尝试过的内容都已保留。准备好后说"continue"，或者我可以给客服团队整理摘要。 |
| 42 |  | `conversation/operation_conditions.py:316` | `pause_text()` | Noted that the device isn't with you, so no hands-on steps for now. When you have it, reply "I have the device now" and I'll continue; or I can prepare a summary. | 已记下设备不在身边，暂不安排需要动手的步骤。拿到设备后回复"I have the device now"，我继续；或者我可以整理摘要。 |
| 43 |  | `conversation/operation_conditions.py:317` | `pause_text()` | I can't confirm the cause yet, so I won't add more steps for now. Everything so far is kept; we can continue when you're ready, or I can prepare a summary for our support team. | 暂时还无法确定原因，所以先不加新步骤。目前的内容都已保留，您准备好后可以继续，或者我给客服团队整理摘要。 |
| 57 |  | `conversation/reply.py:101` | `fallback_reply()` | This step hasn't been done yet. How to do it: {customer_text(instruction)} {caution} When you're ready, reply "retry this step", or we can pause. | 这一步还没做。做法：{步骤}{注意事项} 准备好后回复"retry this step"，或者我们先暂停。 |
| 59 |  | `conversation/reply.py:107` | `fallback_reply()` | I've noted the steps you couldn't do; they won't count as done. | 已记下您做不了的步骤，这些不会算作已完成。 |
| 60 | ★ | `conversation/reply.py:107` | `fallback_reply()` | We won't add more steps for now. | 暂时不再增加步骤。 |
| 63 |  | `conversation/reply.py:115` | `fallback_reply()` | I'm sorry we haven't solved this yet. {detail}You can pause, or tell me whether you'd rather answer questions or try the device; if you'd like a person to help, I can prepare a summary for our support team. | 很抱歉还没解决。{detail}您可以暂停，或者告诉我是想回答问题还是动手试设备；如果想找人工，我可以给客服团队整理摘要。 |
| 71 | ★ | `conversation/reply.py:153` | `fallback_reply()` | The current step is: {step.get('instruction', '')} Once you've tried it, let me know the result on the step card. | 当前步骤是：{步骤} 试过之后，请在步骤卡上告诉我结果。 |
| 72 |  | `conversation/reply.py:154` | `fallback_reply()` | Please confirm the information on the card so I can link the issue to the right product or receipt. Your question doesn't submit the card. | 请确认卡片上的信息，以便把问题关联到正确的产品或凭证。您提问不会提交卡片。 |
| 80 |  | `diagnose/decision.py:185` | `explanation()` | The current step is: {step['instruction']}{caution} Once you've tried it, let me know the result on the step card, or choose "can't do it" if it isn't possible. | 当前步骤是：{步骤}{注意} 试过之后请在步骤卡上告诉我结果；做不到的话选"can't do it"。 |
| 81 |  | `diagnose/decision.py:191` | `explanation()` | The official explanation has been provided; this does not mark the device as repaired. If it doesn't match what you're seeing, describe the difference so we can review it. | 官方说明已经给出，这不代表设备已修好。如果和您看到的情况不符，请描述差异，我们再看。 |
| 84 |  | `diagnose/decision.py:196` | `explanation()` | This issue was marked as resolved. If it comes back, describe what's happening and I'll check the right guidance again. | 这个问题已标记为解决。如果再次出现，请描述情况，我会重新查找对应的资料。 |
| 86 |  | `diagnose/decision.py:201` | `explanation()` | The applicable troubleshooting steps have been tried and it isn't resolved yet. I can prepare the steps you tried for our support team; I won't repeat steps you've already done. | 适用的排障步骤都已试过，问题仍未解决。我可以把您试过的步骤整理给客服团队，不会再重复您做过的步骤。 |
| 87 |  | `diagnose/decision.py:202` | `explanation()` | There's no troubleshooting step to give yet. Tell me more about the problem (or the error code shown in the app) and I'll check the official guidance; if none applies, I'll say so. | 暂时还没有可给的排障步骤。请多告诉我一些问题细节（或 App 里显示的错误码），我来查官方资料；如果没有适用的，我会如实告诉您。 |
| 105 |  | `guide/steps.py:68` | `RETRY_NOTE` | You said you haven't checked this yet. Once you've had a chance to look, pick the option that matches; the next step depends on what you find. | 您说还没检查这一项。看过之后请选择相符的选项，下一步取决于您看到的情况。 |
| 106 |  | `guide/steps.py:92` | `reported_note()` | Some of these checks may overlap with what you've already done or checked. Please still check each one exactly as described; | 其中一些检查可能和您已经做过的重复。请仍然按说明逐项检查； |
| 107 |  | `guide/steps.py:142` | `prepare_step()` | The supplied official source refers to further instructions, but does not include them or a link. I can't provide those missing steps from this source. | 官方资料提到了进一步的说明，但没有附上内容或链接，我无法凭这份资料补出缺失的步骤。 |
| 108 |  | `plans/qa.py:20` | `EXPECTED` | After this step, check whether the problem is resolved. | （步骤卡"预期结果"）做完这一步后，看看问题是否解决。 |
| 109 |  | `plans/qa.py:21` | `ANSWER_EXPECTED` | Pick the option that matches, or describe it in a few words. | （问题卡）选择相符的选项，或用几个字描述。 |
| 110 |  | `plans/qa.py:22` | `MATERIAL_EXPECTED` | Upload it here if you have it, or tell me you don't have it right now. | （材料卡）有的话请在这里上传，没有请告诉我。 |
| 111 |  | `plans/qa.py:25` | `ACTION_WITH_MATERIAL_EXPECTED` | After trying this, tell me whether the problem is resolved. The photo or video it mentions is separate: upload it here whenever you can, it isn't needed to answer this card. | 试过之后告诉我问题是否解决。它提到的照片或视频是另一回事：方便时上传即可，回答这张卡不需要。 |
| 112 |  | `plans/qa.py:28` | `EXPECTED_BY_KIND["statement"]` | No action needed here. | （说明卡）这里不需要操作。 |
| 113 |  | `plans/qa.py:28` | `EXPECTED_BY_KIND["handoff"]` | A support colleague will continue from here. | （转交卡）客服同事会接着处理。 |
| 114 |  | `plans/qa.py:70` | `PROMISE_NOTE` | Whether a replacement or part can be sent depends on a warranty check. | 能否寄送换货或配件，取决于质保核查结果。 |
| 115 |  | `plans/qa.py:125` | `plan_of()` | Which of these problems are you experiencing? Choose the matching section. | 您遇到的是下面哪个问题？请选择对应的部分。 |

## 6 读图（5）

| # | ★ | 位置 | 名称 | 英文原文 | 中文参考 |
|---|---|---|---|---|---|
| 88 |  | `diagnose/localization.py:175` | `echo_findings()` | From the photo I can see: {', '.join(dict.fromkeys(facts))}. If that's not right, just tell me. | 从照片里我能看到：{识别结果}。如果不对，请直接告诉我。 |
| 91 |  | `diagnose/vision.py:45` | `NO_VISION_TEXT` | I can't read images right now. Could you describe what the photo shows (which part, what's wrong)? I'll continue from there. | 我暂时无法读取图片。能描述一下照片里是什么吗（哪个部件、什么问题）？我会接着处理。 |
| 177 |  | `sessions/l3.py:1156` | `prepare_retake()` | The photo still can't be read clearly, so I'll pass the details to a colleague to check. | 照片仍然看不清，我会把信息转给同事核实。 |
| 178 |  | `sessions/l3.py:1172` | `prepare_retake()` | Please take a focused photo of the faulty part of the device. | 请对准设备的故障部位拍一张清晰的照片。 |
| 179 |  | `sessions/l3.py:1182` | `vision_conflict()` | The photo and your description don't quite match. Please confirm: | 照片和您的描述不太一致，请确认： |

## 7 物流（17）

| # | ★ | 位置 | 名称 | 英文原文 | 中文参考 |
|---|---|---|---|---|---|
| 4 |  | `backends/logistics.py:57` | `SOP_TEXT["delivered"]` | Tracking shows the item was delivered, so under our after-sales policy we can't send a replacement shipment. If you really haven't received it, I can open a carrier investigation and a colleague will follow up. | 物流显示已签收，按售后政策不能补发。如果您确实没收到，我可以发起承运商调查，由同事跟进。 |
| 5 |  | `backends/logistics.py:59` | `SOP_TEXT["reship_eligible"]` | Tracking doesn't show the item as delivered, so under our after-sales policy we can arrange a reship for you. | 物流未显示签收，按售后政策可以为您补发。 |
| 6 |  | `backends/logistics.py:60` | `SOP_TEXT["in_transit"]` | The package is still in transit; please allow until the estimated delivery date. If it still hasn't arrived after that, contact us again and we can arrange a reship. | 包裹仍在运输中，请等到预计送达日。届时仍未收到，请再联系我们，可以安排补发。 |
| 7 |  | `backends/logistics.py:62` | `SOP_TEXT["presale"]` | This item is a pre-order and hasn't shipped yet. It will be sent on the expected ship date. | 该商品为预售，尚未发货，将在预计发货日寄出。 |
| 8 |  | `backends/logistics.py:63` | `SOP_TEXT["unknown"]` | The tracking information is incomplete, so I'll pass this to a colleague to check. | 物流信息不完整，我会转给同事核实。 |
| 9 |  | `backends/logistics.py:66` | `PRESALE_ON_HOLD` | This item is a pre-order and hasn't shipped yet; its original expected ship date is shown above. Whether it is held or cancelled is up to the colleague handling your request. | 该商品为预售，尚未发货，原预计发货日见上方。是否暂停或取消，由处理您申请的同事决定。 |
| 10 |  | `backends/logistics.py:74` | `RESHIP_REASON["returned"]` | The package was returned to the sender, so under our after-sales policy we can arrange a reship for you. | 包裹已退回寄件方，按售后政策可以为您补发。 |
| 11 |  | `backends/logistics.py:75` | `RESHIP_REASON["overdue"]` | This package hasn't arrived by its estimated delivery date of {eta}, so under our after-sales policy we can arrange a reship for you. | 包裹超过预计送达日 {eta} 仍未到达，按售后政策可以为您补发。 |
| 12 |  | `backends/logistics.py:77` | `RESHIP_REASON["not_delivered"]` | Tracking doesn't show the item as delivered, so under our after-sales policy we can arrange a reship for you. | 物流未显示签收，按售后政策可以为您补发。 |
| 21 |  | `conversation/answers.py:149` | `record_mismatch_note()` | The order record shows {on_record} | （拼接片段）订单记录显示 {on_record}…… |
| 22 |  | `conversation/answers.py:170` | `record_mismatch_note()` | Our record for {tracking} differs from what you received: it is listed as the main unit, while you mention the accessory kit. I've kept both records as they are; please confirm which item each package contained (the label on the box helps) so a colleague can check with the carrier. | 我们对 {tracking} 的记录与您收到的不一致：记录是主机，而您说收到的是配件包。两条记录都已保留，请确认每个包裹里是什么（看箱子上的标签），以便同事向承运商核实。 |
| 137 | ★ | `sessions/l3.py:91` | `TYPE_DETAILS["carrier_investigation"]` | Tracking shows the package as delivered, so under our after-sales policy we can't send another shipment. If you really haven't received it, I can submit a carrier investigation request and a colleague will check with the carrier. | 物流显示包裹已签收，按售后政策不能再发货。如果您确实没收到，我可以提交承运商调查申请，由同事向承运商核实。 |
| 138 |  | `sessions/l3.py:95` | `RESHIP_TAIL` | Once submitted, a colleague will arrange it. | 提交后同事会安排。 |
| 140 |  | `sessions/l3.py:253` | `service_context()` | Please share your order number or tracking number, and I'll check the delivery status first. | 请提供订单号或运单号，我先查一下物流状态。 |
| 146 |  | `sessions/l3.py:319` | `TRACKING_LATER` | No problem. I can't look up the delivery without an order number or tracking number. The order number is in your order confirmation email, and the tracking number is in the shipping notification. Send either one here when you have it and I'll check the status straight away. | 没问题。没有订单号或运单号就查不了物流。订单号在订单确认邮件里，运单号在发货通知里。有其中一个发到这里，我马上查。 |
| 157 |  | `sessions/l3.py:452` | `_propose_logistics()` | No package record found | （字段值）没有找到包裹记录 |
| 169 |  | `sessions/l3.py:850` | `consult()` | Please share your order number or tracking number and I'll look it up. | 请提供订单号或运单号，我来查。 |

## 8 订单 / 质保 / 售后办理（40）

| # | ★ | 位置 | 名称 | 英文原文 | 中文参考 |
|---|---|---|---|---|---|
| 0 |  | `actions/executor.py:19` | — | We can't confirm the result yet. To avoid a duplicate request, I've passed it to a colleague to check. | 暂时无法确认结果。为避免重复提交，我已转给同事核实。 |
| 3 |  | `actions/registry.py:20` | `SUBMITTED_NEXT_STEP` | Your service request has been submitted and a colleague is handling it. The result will come back to this conversation; please keep your service request number. | 您的服务申请已提交，同事正在处理。结果会回到本对话，请保留服务单号。 |
| 14 |  | `backends/protocol.py:16` | — | I couldn't find that order. Please check the order number. | 没有找到该订单，请核对订单号。 |
| 15 |  | `backends/protocol.py:20` | — | There is already a service request, or the order status conflicts. A colleague will need to check this. | 已存在服务申请，或订单状态冲突，需要同事核实。 |
| 18 |  | `conversation/answers.py:34` | `LABELS["steps_executed"]` | Troubleshooting steps you tried | （字段名）您做过的排障步骤 |
| 19 |  | `conversation/answers.py:98` | `render_answer()` | I couldn't identify which order you mean. Please share the order number you'd like me to check. | 我无法确定您指的是哪个订单，请提供要查询的订单号。 |
| 20 |  | `conversation/answers.py:106` | `render_answer()` | {LABELS[field]}: no confirmed record yet. | （拼接片段）{字段}：暂无确认记录。 |
| 132 |  | `sessions/l3.py:65` | `NOT_EXECUTABLE_TEXT["address_update"]` | Address changes need to be verified by a colleague, so I've passed your request to our team. | 修改地址需要同事核实，我已把您的请求转给团队。 |
| 133 |  | `sessions/l3.py:66` | `NOT_EXECUTABLE_TEXT["order_change"]` | I can't change or hold an order myself, so I've passed your request to a colleague who can. Please note the order may already be in process. | 我无法自己修改或暂停订单，已转给能处理的同事。请注意订单可能已在处理中。 |
| 134 |  | `sessions/l3.py:68` | `NOT_EXECUTABLE_TEXT["parts_purchase"]` | I can't look up spare-part availability or place a parts order here, so I've passed your request (including the part you need) to a colleague who can check it for you. | 我无法在这里查询配件库存或下配件订单，已把您的请求（包括所需配件）转给能核实的同事。 |
| 135 |  | `sessions/l3.py:86` | `TYPE_DETAILS["replace"]` | The fault is still not resolved after troubleshooting and the product is under warranty, so under our after-sales policy it qualifies for a replacement. Once submitted, a colleague will review it and arrange the shipment. | 排障后故障仍未解决，且产品在质保期内，按售后政策可以换货。提交后同事会审核并安排发货。 |
| 136 |  | `sessions/l3.py:88` | `TYPE_DETAILS["refund"]` | The product is under warranty, so you can request a refund. Once submitted, a colleague will review and process it. | 产品在质保期内，您可以申请退款。提交后同事会审核并处理。 |
| 139 |  | `sessions/l3.py:246` | `service_context()` | This involves more than one order. Please tell me which order number you'd like me to handle. | 这涉及多个订单，请告诉我要处理哪个订单号。 |
| 141 |  | `sessions/l3.py:268` | `service_context()` | I've checked: {decision.reason}. Please upload your proof of purchase (the purchase date must be visible) so I can confirm whether it's within the 12-month warranty. | 已核查：{原因}。请上传购买凭证（需能看到购买日期），以便确认是否在 12 个月质保期内。 |
| 142 |  | `sessions/l3.py:280` | `service_context()` | I couldn't find that order number. | 没有找到这个订单号。 |
| 143 |  | `sessions/l3.py:281` | `service_context()` | To check the warranty I'll need your order details. | 查质保需要您的订单信息。 |
| 144 | ★ | `sessions/l3.py:295` | `PROOF_REQUEST` | Please share your order number. If you bought it from another seller, please upload your proof of purchase showing the seller name, country of purchase and purchase date. | 请提供订单号。如果是从其他商家购买，请上传显示商家名称、购买国家和购买日期的购买凭证。 |
| 145 |  | `sessions/l3.py:313` | `PROOF_LATER` | Understood. Without an order number or proof of purchase I can't check the warranty, so nothing will be submitted for now. The order number is in your order confirmation email or your account on the store you bought from; for another seller, a photo of the receipt or invoice works. Send it here whenever you have it and I'll continue from this point. | 明白。没有订单号或购买凭证就查不了质保，所以暂不提交任何申请。订单号在订单确认邮件或购买平台的账户里；其他商家购买的话，拍收据或发票也可以。有了随时发到这里，我从这里继续。 |
| 147 |  | `sessions/l3.py:343` | `HARDWARE_BASIS["guide_exhausted"]` | The official troubleshooting for this issue is complete and the problem isn't resolved, so the next step is an after-sales review; whether it's covered by warranty depends on the check below. | 这个问题的官方排障已全部完成，问题仍未解决，下一步是售后审核；是否在保取决于下面的核查。 |
| 148 | ★ | `sessions/l3.py:346` | `HARDWARE_BASIS["hardware_malfunction"]` | Based on the official guidance for this error code, this is a hardware malfunction, so the next step is an after-sales review rather than further troubleshooting; whether it's covered by warranty depends on the check below. | 根据官方对该错误码的说明，这属于硬件故障，下一步是售后审核而不是继续排障；是否在保取决于下面的核查。 |
| 149 |  | `sessions/l3.py:349` | `HARDWARE_BASIS["physical_damage"]` | From the damage you've described, this isn't something troubleshooting can fix, so the next step is an after-sales review; whether it's covered by warranty depends on the check below. | 从您描述的损坏来看，这不是排障能解决的，下一步是售后审核；是否在保取决于下面的核查。 |
| 153 |  | `sessions/l3.py:421` | `propose()` | I can't confirm the warranty status yet ( | （拼接片段）暂时无法确认质保状态（{原因}），已转给同事核实。 |
| 154 | ★ | `sessions/l3.py:429` | `propose()` | I've checked: {decision.reason}. The warranty has expired (as of {decision.as_of.isoformat()}). I'm sorry, we can't offer a free replacement or refund for products that are out of warranty. To keep using the product, you can follow the care instructions in the user manual, or contact us about buying accessories. | 已核查：{原因}。质保已过期（截至 {日期}）。很抱歉，过保产品无法免费换货或退款。如需继续使用，可以按说明书保养，或联系我们购买配件。 |
| 155 | ★ | `sessions/l3.py:432` | `propose()` | I can still walk you through the official checks for this issue. | 我仍可以带您走一遍这个问题的官方检查。 |
| 156 |  | `sessions/l3.py:439` | `propose()` | I've checked: {decision.reason}. Please contact the seller directly for after-sales support. | 已核查：{原因}。请直接联系卖家获取售后支持。 |
| 158 |  | `sessions/l3.py:478` | `_offer()` | {lead}Before I can submit the {TYPE_NAMES[kind]}, I still need: {labels}. Please upload photos or videos here, and reply with the other details. | {开头}提交{服务类型}前，还需要：{材料}。请在这里上传照片或视频，其他信息直接回复。 |
| 159 |  | `sessions/l3.py:527` | `_pause_for_changed_request()` | I've paused the original plan. Your new request has been passed to a colleague for review, and the result will come back to this conversation. | 已暂停原方案。您的新诉求已转给同事审核，结果会回到本对话。 |
| 160 |  | `sessions/l3.py:538` | `authorize()` | This option needs to be handled by a colleague, so I've submitted it for review. | 这个方案需要同事处理，我已提交审核。 |
| 161 |  | `sessions/l3.py:632` | `execute()` | We can't confirm the result of this submission yet. To avoid a duplicate request, I've passed it to a colleague to check. | 暂时无法确认这次提交的结果。为避免重复申请，已转给同事核实。 |
| 162 |  | `sessions/l3.py:634` | `execute()` | The same request is still being processed. Please check the case status a little later. | 相同的请求仍在处理中，请稍后查看案件状态。 |
| 163 |  | `sessions/l3.py:664` | `execute()` | This submission didn't go through. You can retry the original request or ask for help from a colleague; retrying won't create a duplicate service request. | 这次提交没有成功。您可以重试原申请或请同事帮忙；重试不会产生重复的服务单。 |
| 165 |  | `sessions/l3.py:713` | `track()` | No service request has been submitted for this case yet. | 这个案件还没有提交服务申请。 |
| 167 |  | `sessions/l3.py:775` | `summary_of()` | (including the part you need) | （拼接片段）（包括您需要的配件） |
| 168 |  | `sessions/l3.py:847` | `consult()` | This involves more than one order. Please tell me which order number you'd like me to check. | 这涉及多个订单，请告诉我要查哪个订单号。 |
| 170 |  | `sessions/l3.py:852` | `consult()` | I need the order number to look up this order information. | 查询这个订单信息需要订单号。 |
| 172 |  | `sessions/l3.py:1066` | `reopening_request()` | Please confirm whether the unresolved problem is with your original after-sales case, or with the other order you just asked about. | 请确认未解决的问题是关于您原来的售后案件，还是您刚才问的另一个订单。 |
| 180 |  | `sessions/l3.py:1258` | `advance_tasks()` | I've also added your other request ({labels}) to the same case, so the colleague can handle it together. | 我已把您的另一个诉求（{诉求}）加到同一个案件里，同事可以一并处理。 |
| 181 |  | `warranty/service.py:153` | `decide_by_dealer()` | {seller} is not on our list of authorized dealers in {normalize_country(country)} | （质保判断理由，会拼进回复）{卖家} 不在我们 {国家} 的授权经销商名单里 |
| 182 |  | `warranty/service.py:159` | `decide_by_dealer()` | {found.dealer.seller} ({found.dealer.country}) is an authorized dealer, but the purchase date is missing | （质保判断理由）{卖家}（{国家}）是授权经销商，但缺少购买日期 |
| 183 |  | `warranty/service.py:167` | `decide_by_dealer()` | {found.dealer.seller} is an authorized dealer; the {DEALER_WARRANTY_MONTHS}-month warranty from purchase {'runs' if inside else 'ran'} until {end.isoformat()} | （质保判断理由）{卖家} 是授权经销商；自购买起 {N} 个月的质保有效期至 / 已于 {日期} |

## 9 转人工 / 案件状态（28）

| # | ★ | 位置 | 名称 | 英文原文 | 中文参考 |
|---|---|---|---|---|---|
| 61 | ★ | `conversation/reply.py:111` | `fallback_reply()` | I'm sorry we haven't solved this yet. {detail}Your service case and open items are kept; progress with our team will show in the case record. | 很抱歉还没解决。{detail}您的服务案件和未结事项都已保留，与团队的进展会显示在案件记录里。 |
| 66 |  | `conversation/reply.py:137` | `fallback_reply()` | Your issue and supporting information have been submitted and are awaiting review by a colleague. I can't confirm that someone has picked it up yet. You can add information here while waiting. | 您的问题和材料已提交，等待同事审核。我还无法确认是否已有人接手。等待期间可以在这里补充信息。 |
| 67 |  | `conversation/reply.py:139` | `fallback_reply()` | The handoff is recorded in your service case. The case record contains the review outcome and any next steps. | 转人工已记录在您的服务案件里，审核结果和后续步骤都在案件记录中。 |
| 68 |  | `conversation/reply.py:141` | `fallback_reply()` | No summary has been prepared for our support team yet, and nothing has been handed over. You can keep describing the issue, or ask me to prepare a summary for an agent. | 还没有给客服团队准备摘要，也没有转交任何内容。您可以继续描述问题，或者让我为人工准备摘要。 |
| 69 |  | `conversation/reply.py:142` | `fallback_reply()` | I've prepared a record of the issue, but I don't have confirmation that it has been submitted for review. The prepared summary alone does not mean an agent has picked it up. | 我已整理好问题记录，但无法确认它已提交审核。仅有摘要不代表已有客服接手。 |
| 82 |  | `diagnose/decision.py:193` | `explanation()` | This case is closed, but the problem is not resolved. No new service request has been submitted. Please describe any new information if you need further help. | 该案件已结束，但问题没有解决，也没有提交新的服务申请。如需进一步帮助，请补充新信息。 |
| 83 |  | `diagnose/decision.py:195` | `explanation()` | This case has been closed. If the problem persists, please describe what is happening so we can review the case. | 该案件已关闭。如果问题仍在，请描述现在的情况，我们会重新查看。 |
| 85 |  | `diagnose/decision.py:199` | `explanation()` | Your case is with a support colleague. Anything you add here goes into the case; describe what the device is doing and I'll include it. | 您的案件已在同事手上。您在这里补充的内容都会进入案件；请描述设备的表现，我会一并记录。 |
| 94 |  | `escalation/summary.py:435` | `REASSURANCE["R5"]` | I couldn't confirm official troubleshooting guidance for the symptoms you reported. I've put together a record of this issue so a support colleague can continue from here. | 我没能为您反馈的症状确认官方排障资料。已把问题整理成记录，客服同事可以接着处理。 |
| 96 |  | `escalation/summary.py:439` | `REASSURANCE["R3"]` | I've prepared a summary of your issue for our support team. This summary alone does not confirm submission or that an agent has picked it up. | 已为客服团队准备好问题摘要。仅有摘要不代表已提交或已有客服接手。 |
| 97 |  | `escalation/summary.py:441` | `DEFAULT_REASSURANCE` | I've put together a record of this issue so a support colleague can continue from here. | 已把问题整理成记录，客服同事可以接着处理。 |
| 98 |  | `escalation/summary.py:443` | `CUSTOMER_BOUNDARY["no_supported_followup"]` | The official troubleshooting steps for this issue have all been tried | （拼接片段）这个问题的官方排障步骤都已试过 |
| 99 |  | `escalation/summary.py:444` | `CUSTOMER_BOUNDARY["knowledge_coverage_missing"]` | I couldn't find official guidance that covers this issue | （拼接片段）没有找到覆盖这个问题的官方资料 |
| 100 |  | `escalation/summary.py:445` | `CUSTOMER_BOUNDARY["outcome_beyond_source"]` | The official guidance only covers the steps you tried, not what you asked for | （拼接片段）官方资料只覆盖您试过的步骤，不覆盖您提出的诉求 |
| 101 |  | `escalation/summary.py:461` | `r5_boundary()` | I couldn't confirm official troubleshooting guidance for this issue. | 我没能为这个问题确认官方排障资料。 |
| 102 |  | `escalation/summary.py:463` | `r5_boundary()` | I couldn't confirm official troubleshooting guidance for these issues: {said}. Each of them is kept in the record for our colleague. | 我没能为这些问题确认官方排障资料：{原话}。每一项都已记录，交给同事处理。 |
| 103 |  | `escalation/summary.py:475` | `reassurance_text()` | {boundary}. I've put together the issue and the steps you tried so a support colleague can continue; the summary alone does not confirm submission for review. If anything changes, tell me and we'll continue from the record. | {边界说明}。已把问题和您试过的步骤整理好，客服同事可以接着处理；仅有摘要不代表已提交审核。如有变化请告诉我，我们从记录继续。 |
| 123 |  | `sessions/graph.py:1587` | `out_of_scope_text()` | Our assistant currently supports {' / '.join(lines)} products. "{name}" ({category_name}) isn't covered yet; I'll put together a record you can pass to our support team. | 我们的助手目前支持 {产品线} 产品。"{名称}"（{品类}）暂不在范围内；我会整理一份记录，您可以交给客服团队。 |
| 130 |  | `sessions/graph.py:3120` | `summarize()` | Thanks, I've added this to your case for the support colleague. I still couldn't find official troubleshooting guidance that matches it, so they'll continue from here. | 谢谢，我已把这些补充到您的案件里给客服同事。我仍没找到匹配的官方排障资料，所以由他们接着处理。 |
| 131 |  | `sessions/graph.py:3126` | `summarize()` | I've submitted the issue and supporting information for review by a colleague. You can add information here while waiting. | 已把问题和材料提交给同事审核。等待期间可以在这里补充信息。 |
| 150 |  | `sessions/l3.py:400` | `propose()` | This case is closed, and the problem is not resolved. No new service request has been submitted. | 该案件已结束，问题未解决，没有提交新的服务申请。 |
| 151 |  | `sessions/l3.py:402` | `propose()` | This case has already been closed. No new service request has been submitted. | 该案件已关闭，没有提交新的服务申请。 |
| 152 |  | `sessions/l3.py:410` | `propose()` | Your case is waiting to be processed. Updates will appear in the case status. | 您的案件正在等待处理，进展会显示在案件状态里。 |
| 166 |  | `sessions/l3.py:733` | `await_human()` | I've submitted this for review by a colleague. The decision will come back to this conversation, and you can keep adding information here. | 已提交给同事审核。决定会回到本对话，您可以继续在这里补充信息。 |
| 173 |  | `sessions/l3.py:1096` | `reopen_case()` | I've reopened your original case and kept the previous order and handling records. Next, I'll re-check which option applies. | 已重新打开您原来的案件，之前的订单和处理记录都保留着。接下来我会重新核查适用哪个方案。 |
| 174 |  | `sessions/l3.py:1117` | `apply_case_command()` | A colleague has closed this case. You can still view its history; if the problem persists, please tell me more. | 同事已关闭该案件。您仍可查看历史记录；如果问题仍在，请告诉我更多情况。 |
| 175 |  | `sessions/l3.py:1119` | `apply_case_command()` | A colleague has reopened this case. Please describe what still needs to be handled. Before anything is submitted, I'll re-check the options and ask for your confirmation. | 同事已重新打开该案件。请描述还需要处理什么。提交任何内容前，我会重新核查方案并征求您的确认。 |
| 176 |  | `sessions/l3.py:1134` | `apply_human_decision()` | Reply from our team: | （拼接片段）来自我们团队的回复：{备注} |

## 10 系统异常（8）

| # | ★ | 位置 | 名称 | 英文原文 | 中文参考 |
|---|---|---|---|---|---|
| 1 |  | `actions/executor.py:115` | `run()["summary"]` | Checking our after-sales tool | （工作流面板）正在查询售后工具 |
| 2 |  | `actions/executor.py:200` | `run()["summary"]` | After-sales tool responded | （工作流面板）售后工具已返回 |
| 13 |  | `backends/protocol.py:12` | — | Our after-sales tool can't process this right now. | 售后工具暂时无法处理该请求。 |
| 16 |  | `backends/protocol.py:25` | — | Our after-sales tool is temporarily unavailable. Please try again later or ask for a colleague. | 售后工具暂时不可用，请稍后重试或请同事协助。 |
| 17 |  | `backends/protocol.py:30` | — | Our after-sales tool timed out. Please try again later or ask for a colleague. | 售后工具超时，请稍后重试或请同事协助。 |
| 77 |  | `conversation/reply.py:245` | `STREAM_FAILED_TEXT` | I couldn't finish that answer just now, so please don't act on the partial text above. You can send your question again and I'll try again. | 刚才的回答没能完成，请不要按上面的半段内容操作。您可以重新发送问题，我再试一次。 |
| 125 |  | `sessions/graph.py:2612` | `DIAGNOSE_UNAVAILABLE_TEXT` | I couldn't load the troubleshooting steps just now because of a temporary system problem. This is not a finding about your device. Your description is saved and this issue stays open; send any message (for example "try again") and I'll check the official guidance again, or ask for a colleague if you'd rather not wait. | 由于临时的系统问题，刚才没能加载排障步骤，这不是对您设备的判断。您的描述已保存，问题保持未结；发任意消息（比如"try again"）我会重新查官方资料，不想等也可以找同事。 |
| 164 |  | `sessions/l3.py:669` | `execute()["decision_summary"]` | Our after-sales tool is temporarily unavailable. Please retry the original request or choose help from a colleague. | 售后工具暂时不可用，请重试原申请或选择同事协助。 |

## 不在上表、但同样让客户看到英文的地方

上表只覆盖写死的固定话术。客户看到的英文还有三个来源，改语言时要一起处理。

### A. 大模型提示词里写死"用英文"（9 处）

模型生成的回复也是英文，原因是提示词明确要求英文。只改固定话术、不改这些，回复会中英混杂。

| 位置 | 用途 | 原文要求 |
|---|---|---|
| `conversation/reply.py:186` | 回顾、解释类对话回复 | 用英文回答（官方资料与客户工单都是英文） |
| `conversation/product_questions.py:249` | 产品功能 / 用法问答 | 用英文回答 |
| `prompts/reply.py:12` | 情绪安抚句 | 只输出一到两句英文安抚与承诺 |
| `prompts/reply.py:17` | 基于检索片段的回应 | 用英文回应 |
| `diagnose/synthesize.py:87` | 诊断树追问（字段说明） | 用一句英文询问 |
| `diagnose/synthesize.py:331` | 诊断树追问（提示词） | clarification_question 用英文 |
| `sessions/clarify.py:49` | 澄清追问（输出格式） | 一句具体的英文追问 |
| `sessions/clarify.py:439` | 症状澄清 | 只输出一句具体的英文追问 |
| `sessions/clarify.py:440` | 产品冲突澄清 | 只输出一句具体的英文追问 |

另外，`prompts/guide.py:12` 要求把步骤改写成**中文**，和上面 9 处相反。这个模板目前没有被任何代码调用（只有 `replay/package.py` 读了它的版本号），属于遗留代码，不影响线上，但说明 D2 之前的设计是中文。

### B. 配置文件里的英文

| 位置 | 内容 |
|---|---|
| `config/vision_vocab.yaml` 的 `english:` 段 | 读图识别出的部件 / 现象词，客户看到的是英文映射（如"From the photo I can see: ..."里的词） |
| `config/vision_vocab.yaml:139-145` `retake_guidance` | 6 条补拍指引，例如 "Please wipe the lens, focus on the faulty part, and take the photo again." |

### C. 排障步骤正文

步骤卡上的操作说明直接取自官方 Q&A 原文（`plans/qa.py` 的 `customer_text()` 只改人称，不翻译）。官方 Q&A 本身就是英文，所以即使把上表全部改成中文，步骤内容仍是英文。要做中文，有两条路：用大模型翻译（有改动原意的风险，安全相关步骤尤其要小心），或者预先人工翻译知识库。

## 改造建议

1. **先决定要不要改。** D2 的理由是"官方资料和客户工单都是英文"，这对 63 张官方工单成立。如果评委用英文工单测试，就不需要改；如果演示用中文，至少要改 ★ 标记的话术，以及 A 段的 9 处提示词。
2. **如果改，按客户语言输出，而不是改成全中文。** 荷兰语客户（T6、T13）同样需要匹配，所以在会话里记下 `detect_language` 的结果，按语言选话术。
3. **先集中、再翻译。** 现在 184 条散落在 30 多个文件里。先把它们收进一个按语言分组的话术表（例如 `config/customer_text.yaml`），代码里只引用键名，再填中文。直接在原处改成中文，下一个语言又得全部再改一遍。
4. **不要在输出端加一层大模型翻译。** 固定话术存在的意义，就是保证安全、质保、提交状态这些表述不被模型改写。翻译层会把这个保证一起拿掉。
