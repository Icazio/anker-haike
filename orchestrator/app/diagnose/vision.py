"""票 30：读图观察 diagnose.vision（03 §1.4 步骤 1；09 §1 CP-in；07 §6 备用模型不支持图片）。

- 对本 run 新上传、purpose=fault 的图片调用视觉任务（tag=internal），
  输出 {observations, content_kinds, visible_parts}；
  输出只是「观察」，不是假设，进入 image_observations 供检索补充与 synthesize 使用。
- purpose 只是「上传时机」（见 snapshot.ImageRefItem），不回答「这张图是什么」：
  客户在普通首问里传订单截图同样是 purpose=fault。图片内容由 content_kinds 逐图定性，
  判为 document 的图不产生故障 finding，也不算 SOP 的「故障图片/视频」证据（app.sessions.evidence）。
- 观察项再过一次 CP-in（observation_terms：smoke / deformed battery …），R4 命中由调用方直接升级。
- 图片超过链上视觉模型的单请求上限（models.yaml max_images）时只保留最新几张。
- 视觉链全部失败 / 无视觉模型可用：流程不中断，observations 为空并记录 status；
  无视觉能力时给用户一句固定提示「请用文字描述图片内容」（07 §6）。
"""

from __future__ import annotations

import base64
import logging
import time
from dataclasses import dataclass, field
from typing import Annotated, Any, Literal, get_args

from haike_contracts.common import CellField, Finding, ImageContentKind, ImageQuality
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

from app.images.prepare import crop_cell, prepare
from app.images.quality import QualityReport, assess_all
from app.images.store import ImageStore
from app.models.queue import CapacityExceeded
from app.models.router import ModelInvokeError, ModelRouter
from app.prompts import compose_vision_system_prompt

log = logging.getLogger("diagnose.vision")

TASK = "diagnose.vision"
# 单次读图上限。主位 qwen3.8-max 按物体分字段输出单次 10–18 s（2026-10-13 官方照片实测），带图回合截止 45 s
#（runner.IMAGE_DEADLINE_MS）。主位超时后不再有时间试备位：备位只兜底非超时的失败（结构化失败、接口错误）
VISION_BUDGET_MS = 25_000
VISION_RESERVE_MS = 12_000  # 读图之后本轮还要做的事（理解、检索、选方案、发卡）留的时间
ZOOM_RESERVE_MS = 5_000  # 铭牌复看之后留给其余流程的时间：不够就不复看，型号按未验证处理
DEFAULT_MAX_IMAGES = 4
VISION_PROMPT_VERSION = "2026-10-13.1"  # 感知按物体分字段（主体 / 其他物体 / 灯 / 外观异常），observations 由代码拼出
NO_VISION_TEXT = (
    "I can't read images right now. Could you describe what the photo shows (which part, what's wrong)? I'll continue from there."
)

# unusable：像素层画质门控直接判定不可用，**一次模型都没调**（阶段 3）
Status = Literal["ok", "unusable", "skipped", "no_images", "no_vision", "failed"]


class ImageKind(BaseModel):
    """逐图定性。放在 observations 之后、findings 之前：先看见，再说这是什么，最后才下故障结论。"""

    model_config = ConfigDict(extra="forbid")

    image_index: int = Field(ge=1, description="第几张图（就是 Image N 的那个 N）")
    kind: ImageContentKind = Field(description="fault_photo / document / other")


LayerName = Literal["手持", "前景", "中景", "背景"]
# 层次是给细节归属用的提示，不是故障结论：表外的值（2026-10-13 qwen3.8-max 在 T20 写了九宫格「右中」）记为「背景」，
# 不让一个字段越界把整次读图判成失败（同 interpret.ContextField 的做法）
Layer = Annotated[LayerName, BeforeValidator(lambda v: v if v in get_args(LayerName) else "背景")]
SUBJECT_PREFIX = "画面主体："  # 主体观察的固定前缀：下游据此区分「图里是什么东西」与灯 / 异常 / 细节


class SeenObject(BaseModel):
    """画面里的一个物体与只属于它的细节（T42：手持件、背后的机器人底部、远处基站各有各的标签和触点，
    平铺成一串短句时细节会被归到别的物体上）。"""

    model_config = ConfigDict(extra="forbid")

    what: str = Field(description="这是什么：能认出品类时写品类加本体 / 基站 / 配件；认不出只写外形和颜色")
    layer: Layer = Field(description="手持 / 前景 / 中景 / 背景")
    details: list[str] = Field(default_factory=list, description="只属于这个物体的可见细节，看不清写「看不清」")


class SeenLight(BaseModel):
    model_config = ConfigDict(extra="forbid")

    color: str = Field(description="颜色")
    position: str = Field(description="在哪个物体的什么位置、相对哪个按键或标识、几颗")


class SeenAnomaly(BaseModel):
    """外观异常单独成字段：和主体、背景挤在 5 条 × 20 字里时，T48 的裂纹三个模型都会被挤掉（自由回答时 6/6 都看得到）。"""

    model_config = ConfigDict(extra="forbid")

    kind: str = Field(description="裂纹 / 破损 / 缺件 / 变形 / 烧焦 / 漏液 / 鼓包 / 污渍 / 其他")
    where: str = Field(description="在哪个物体的什么位置")


class VisionObservation(BaseModel):
    """模型输出 schema。字段顺序即生成顺序（describe-first）：先按物体写看得见的事实，再据此填受控枚举 ——
    跳过感知阶段直接填终态枚举会显著增加编造（VDGD 等工作报告该两段式在视觉推理上有 2%–33% 的提升）。

    2026-10-13 起感知阶段按物体分字段（subject / others / lights / anomalies），observations 由代码从这些字段拼出，
    不再让模型自己把主体、灯、异常、背景挤进 5 条 × 20 字（docs/planning/2026-10-13-0824_vision-root-cause）。
    模型仍可直接给 observations（旧调用方与备用模型）：结构字段为空时原样使用。

    这里不继承 FaultLocalization，因为有两个字段**不该向模型索取**：
    - conflicts_with_text：图文冲突改由 app.diagnose.conflict 在两个独立结论之间比对（阶段 2）；
    - model_hint_readable：由代码从 model_hint 的字面派生（阶段 1）。
    """

    model_config = ConfigDict(extra="forbid")

    subject: SeenObject | None = Field(default=None, description="第一步：画面主体，手里拿着的东西优先，否则最靠前、最大的那个")
    others: list[SeenObject] = Field(default_factory=list, description="第一步：画面里其他设备或物体，逐个写")
    lights: list[SeenLight] = Field(default_factory=list, description="第一步：亮着的灯")
    anomalies: list[SeenAnomaly] = Field(default_factory=list, description="第一步：外观异常")
    observations: list[str] = Field(
        default_factory=list,
        description="第一步的补充：上面字段装不下的其他可见事实，每条不超过 20 个字，最多 3 条",
    )
    content_kinds: list[ImageKind] = Field(
        default_factory=list, description="第二步：逐图说明这是故障照片还是单据截图"
    )
    findings: list[Finding] = Field(
        default_factory=list, description="第三步：只依据第一步得出的结构化故障定位"
    )
    image_quality: ImageQuality = Field(default_factory=lambda: ImageQuality(usable=True))
    model_hint: str | None = Field(default=None, description="铭牌上逐字符抄录的文字")
    model_hint_cell: CellField = Field(default=None, description="铭牌所在的九宫格")
    model_hint_image: int | None = Field(default=None, ge=1, description="铭牌在第几张图（1 起）")
    visible_parts: list[str] = Field(
        default_factory=list, description="图片中可辨认的部件名称（如 滚刷、尘盒、滤网、充电座）"
    )


def scene_observations(parsed: VisionObservation) -> list[str]:
    """按物体分字段的感知结果 → 给下游的观察句。顺序：主体（第一条，下游的品类线索读它）→ 外观异常 → 灯 →
    主体细节 → 其他物体（带层次与细节）→ 模型补充的观察。异常与灯排在背景前面，不会再被挤掉。"""
    out: list[str] = []
    if parsed.subject is not None:
        lead = "手持" if parsed.subject.layer == "手持" and "手" not in parsed.subject.what else ""
        out.append(f"{SUBJECT_PREFIX}{lead}{parsed.subject.what}")
    out += [f"{a.kind}：{a.where}" for a in parsed.anomalies]
    out += [f"{light.color}灯：{light.position}" for light in parsed.lights]
    if parsed.subject is not None:
        out += [f"主体细节：{d}" for d in parsed.subject.details if d.strip() and d.strip() != "看不清"]
    for item in parsed.others:
        details = [d for d in item.details if d.strip() and d.strip() != "看不清"]
        out.append(f"{item.layer}有{item.what}" + (f"（{'；'.join(details)}）" if details else ""))
    out += [o for o in parsed.observations if o.strip()]
    return [o.strip() for o in out if o.strip()]


@dataclass
class VisionOutcome:
    status: Status
    observations: list[str] = field(default_factory=list)
    visible_parts: list[str] = field(default_factory=list)
    used_image_ids: list[str] = field(default_factory=list)
    dropped_image_ids: list[str] = field(default_factory=list)
    # 经读图确认是单据 / 界面截图（订单、发票、配送详情）的图。这些不算 SOP 的「故障图片/视频」证据。
    # 记「确认不是」而不是「确认是」：读图没跑 / 失败时这里为空，证据判定退回上传时机，
    # 与修复前同行为 —— 视觉链故障不该把正常换货流程整个堵死（app.sessions.evidence）。
    document_image_ids: list[str] = field(default_factory=list)
    model_used: str | None = None
    reason: str | None = None
    model_trace: dict[str, Any] | None = None
    fault_localization: dict | None = None
    user_hint: str | None = None  # 需要提示用户的固定文案（无视觉能力时）
    # 铭牌复看的可观测性：之前只能靠 token 数反推复看有没有跑，排查证据 1 那类问题很费劲
    reread_verdict: str | None = None  # confirmed / overridden / erased / inconclusive / failed / skipped:<原因>
    reread_cell: str | None = None


def _instruction() -> str:
    """指令按 vision_vocab.yaml 生成，词表只有一处真源。

    写法上两条刻意的选择（依据 2026-09-14 调研）：
    - 只说要做什么，不说不要做什么（负面指令在 VLM 上接近随机地被忽略）；
    - 「不可辨」与「其他」分开，并且把「不可辨」写成正常选项而不是例外，
      因为模型默认不会主动弃答，必须显式给出这条通道。
    """
    from app.diagnose.localization import vocabulary

    v = vocabulary()
    return (
        "你正在查看用户上传的图片。只写图片里直接可见的内容，看不清就写「看不清」。\n"
        "第一步，按物体写看到的东西：\n"
        "- subject：画面主体。手里拿着的东西是主体；没有手持物时是最靠前、占画面最大的那一样。"
        "what 能认出品类时写品类加本体、基站或配件（如「扫地机器人本体」「扫地机器人基站」「吸奶器主机」「机器人底部」），"
        "认不出品类时只写外形和颜色，不猜。扫地机器人本体是扁平的圆形或圆角方形机身，正面有传感器窗或标志灯，底部有轮子、边刷；"
        "基站是立在地上的座子，带水箱或尘袋仓，机器人停在它前面或里面。details 只写属于主体本身的细节。\n"
        "- others：画面里其他设备或物体，逐个写 what、layer（手持 / 前景 / 中景 / 背景）和只属于它的 details；"
        "一个细节（标签、触点、胶带、按键）只归到它真正所在的那个物体上，分不清归属就不写。\n"
        "- lights：亮着的灯，写颜色和位置（在哪个物体上、相对哪个按键或标识、几颗）。\n"
        "- anomalies：外观异常（裂纹、破损、缺件、变形、烧焦、漏液、鼓包、污渍），写类型和位置。没有就留空。\n"
        "- observations：上面装不下的其他可见事实，最多 3 条，每条不超过 20 字。"
        "出现冒烟 / 烧焦 / 电池鼓包 / 漏液 / 火花时，在这里中文与英文关键词各写一次"
        "（如「烧焦 burnt」「鼓包 swollen battery」）。\n"
        "第二步 content_kinds：逐图说明每张图是什么，每张图一条，image_index 写它是第几张（Image N 的 N）。"
        "拍到实物设备或其部件的照片填 fault_photo；"
        "订单截图、发票、收据、配送详情页、App 报错页这类以文字为主的单据或界面填 document；"
        "两者都不是时填 other。单据与界面图在第一步只写 subject（是什么单据），其余留空。\n"
        "第三步 findings：只依据第一步写下的事实填写，每条给出 part / phenomenon / evidence / cell。"
        "只为 fault_photo 的图写 findings；document 与 other 的图不写。\n"
        f"part 从 [{' '.join(v['parts'])}] 中选；phenomenon 从 [{' '.join(v['phenomena'])}] 中选。"
        f"看清楚了但不属于表内任何一项时选「其他」；看不出是什么时选「{v['unknown']}」。\n"
        "evidence 抄第一步里支撑这条结论的那句话；"
        f"cell 写它位于九宫格的哪一格，从 [{' '.join(v['cells'])}] 中选；"
        "image_index 写它来自第几张图（就是上面 Image N 的那个 N）。每条 finding 都要有 evidence。\n"
        "image_quality：图看得清就 usable=true；看不清时 usable=false 并从 "
        "blurry / too_dark / too_far / wrong_subject / occluded 中选出 reasons。多图中只要一张能用于判断即为 true。"
        "单据截图上的文字能读清就是 usable=true。\n"
        "model_hint：逐字符抄录铭牌上你看到的字符本身，看不清的单个字符写 ?，没有铭牌或一个字符都认不出时填 null。\n"
        "model_hint_cell：铭牌或疑似铭牌的小标签位于九宫格的哪一格；画面中没有铭牌时填 null。\n"
        "model_hint_image：铭牌在第几张图（Image N 的 N）；没有铭牌时填 null。\n"
        "只输出 JSON。"
    )


NON_FAULT_PHENOMENA = ("正常", "不可辨")

NAMEPLATE_INSTRUCTION = (
    "这是设备铭牌区域的放大图。逐字符抄录你在铭牌上看到的字符，看不清的单个字符写 ?。"
    "一个字符都认不出时留空。只输出 JSON：{\"model_hint\": \"...\"}"
)


class NameplateRead(BaseModel):
    """裁剪复看的输出：只问一件事，因此比多字段任务准得多（2026-09-14 实测）。"""

    model_config = ConfigDict(extra="forbid")
    model_hint: str | None = Field(default=None, description="铭牌上逐字符抄录的文字")


def image_limit(chain: list[Any], registry: Any = None) -> int:
    """链上**第一个可用**视觉模型的 max_images。

    原来取的是链上最小值，于是 deepseek 的 4 张把整条链压到 4 —— 即便实际服务的是能收 10 张的
    qwen-vl，用户多拍的图也会被静默丢掉，而 models.yaml 的注释还写着「qwen-vl / glm-v 收 10 张」。
    降级到后面的模型时按那个模型自己的上限重算即可，没有理由让首位的限制拖累全链。
    """
    for m in chain:
        if not getattr(m.spec, "vision", False):
            continue
        if registry is not None and registry.unavailable_reason(m.alias):
            continue
        return getattr(m.spec, "max_images", None) or DEFAULT_MAX_IMAGES
    return DEFAULT_MAX_IMAGES


def select_images(refs: list[dict[str, Any]], limit: int) -> tuple[list[dict], list[dict]]:
    """超过单请求上限时只保留最新的 limit 张（按上传顺序，后者为新）。返回 (保留, 丢弃)。"""
    if limit <= 0 or len(refs) <= limit:
        return list(refs), []
    return list(refs[-limit:]), list(refs[:-limit])


def build_messages(images: list[tuple[dict[str, Any], bytes, str]]) -> list[Any]:
    """只放图片与指令 —— 用户文字不进这次调用（阶段 2，A5「先验污染测量」）。

    2026-09-15 实测：图里是滚刷缠绕、滤网干净，用户说「应该是滤网堵住了」，
    qwen-vl 与 deepseek 都顺着报出并不存在的「滤网堵塞」。提示词层面的纠偏对此几乎无效，
    唯一可靠的办法是让这次调用根本看不到那句话。签名里没有 text 参数，是为了让这条约束
    由类型保证，而不是靠自觉。

    图先文后并逐图加标签：Anthropic 官方明确图像应在文本之前，多图用 `Image N:` 引入。
    """
    content: list[dict[str, Any]] = []
    for i, (_ref, data, mime) in enumerate(images, 1):
        b64 = base64.b64encode(data).decode("ascii")
        content.append({"type": "text", "text": f"Image {i}（用户上传的第 {i} 张）："})
        content.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}})
    content.append({"type": "text", "text": _instruction()})
    return [
        SystemMessage(content=compose_vision_system_prompt()),
        HumanMessage(content=content),
    ]


def _all_skipped_for_vision(exc: ModelInvokeError) -> bool:
    """链上没有任何模型真正看过图：全部因「无视觉能力」或「不可用（缺 key / 未配置）」被跳过。
    models.yaml 校验已保证 needs_vision 链只含视觉模型，所以实际触发多为视觉模型全部不可用、只剩文本模型可服务。"""
    return bool(exc.attempts) and all(a.outcome == "skipped" for a in exc.attempts)


async def observe_images(
    router: ModelRouter | None,
    store: ImageStore | None,
    *,
    session_id: str,
    refs: list[dict[str, Any]],
    lane: str,
    text: str = "",
    symptoms: list[str] | None = None,
    budget_ms: int = VISION_BUDGET_MS,
) -> VisionOutcome:
    """text / symptoms 只喂给代码层的图文冲突检测，**不进模型调用**（阶段 2）。
    情绪策略与会话状态摘要也不再注入：读图是测量不是对话，见 prompts.compose_vision_system_prompt。"""
    fault_refs = [r for r in refs if r.get("purpose", "fault") == "fault"]
    if not fault_refs:
        return VisionOutcome("no_images")
    if router is None or store is None:
        return VisionOutcome(
            "skipped",
            dropped_image_ids=[r["image_id"] for r in fault_refs],
            reason="router or image store unavailable",
            model_trace={"task": TASK, "model_used": "skipped", "lane": lane, "attempts": 1},
        )
    started = time.monotonic()
    chain = router.registry.chain(TASK, lane)
    keep, dropped = select_images(fault_refs, image_limit(chain, router.registry))
    images: list[tuple[dict[str, Any], bytes, str]] = []
    originals: list[tuple[dict[str, Any], bytes]] = []
    for r in keep:
        got = await store.get(session_id, r["image_id"])
        if got is not None:
            raw = got[1]
            data, mime = prepare(raw, r.get("mime", "image/jpeg"))
            images.append((r, data, mime))
            originals.append((r, raw))
    if not images:
        return VisionOutcome(
            "failed",
            dropped_image_ids=[r["image_id"] for r in fault_refs],
            reason="image bytes not found (expired?)",
        )
    gate = assess_all([data for _, data, _ in images])
    if gate.verdict == "reject":
        log.info(
            "vision gated session=%s reasons=%s metrics=%s（未调用模型）",
            session_id,
            gate.reasons,
            gate.metrics,
        )
        return VisionOutcome(
            "unusable",
            fault_localization=_unusable_localization(gate),
            used_image_ids=[r["image_id"] for r, _, _ in images],
            dropped_image_ids=[r["image_id"] for r in dropped],
            model_trace={"task": TASK, "model_used": "skipped", "lane": lane, "attempts": 0},
        )
    if dropped:
        log.info(
            "vision images truncated session=%s kept=%d dropped=%d",
            session_id,
            len(images),
            len(dropped),
        )
    try:
        res = await router.invoke(
            TASK,
            build_messages(images),
            VisionObservation,
            budget_ms=budget_ms,
            session_id=session_id,
            lane=lane,
        )
    except ModelInvokeError as exc:
        no_vision = _all_skipped_for_vision(exc)
        log.warning(
            "vision degraded session=%s no_vision=%s reason=%s", session_id, no_vision, exc.reason
        )
        return VisionOutcome(
            "no_vision" if no_vision else "failed",
            used_image_ids=[r["image_id"] for r, _, _ in images],
            dropped_image_ids=[r["image_id"] for r in dropped],
            reason=exc.reason[:200],
            model_trace={
                "task": TASK,
                "model_used": "skipped",
                "lane": lane,
                "attempts": max(1, len(exc.attempts)),
            },
            user_hint=NO_VISION_TEXT if no_vision else None,
        )
    except CapacityExceeded as exc:
        return VisionOutcome(
            "failed",
            used_image_ids=[r["image_id"] for r, _, _ in images],
            dropped_image_ids=[r["image_id"] for r in dropped],
            reason=f"CapacityExceeded: {exc}"[:200],
            model_trace={"task": TASK, "model_used": "skipped", "lane": lane, "attempts": 1},
        )
    parsed: VisionObservation = res.parsed
    from app.diagnose.localization import normalize

    localization = normalize(parsed, image_count=len(images))
    reread_cell = localization.get("model_hint_cell")
    localization, reread_verdict = await _reread_nameplate(
        router,
        localization,
        originals,
        session_id=session_id,
        lane=lane,
        budget_ms=budget_ms - int((time.monotonic() - started) * 1000),
    )
    localization = _merge_quality(localization, gate)

    from app.diagnose.conflict import detect_conflicts

    localization["conflicts_with_text"] = detect_conflicts(localization, [text, *(symptoms or [])])
    # 只有真正的故障项才进 observations：它会流进 tool_call 摘要、issue facts 与后续回显，
    # 「吸口正常」「其他不可辨」这类既不是发现也不值得回显给用户。
    derived = [
        f"{f['part']}{f['phenomenon']}"
        for f in localization["findings"]
        if f["phenomenon"] not in NON_FAULT_PHENOMENA
    ]
    kinds = localization["content_kinds"]
    obs = scene_observations(parsed)[:12]
    if kinds and all(kind == "document" for kind in kinds):
        # 全是单据 / 界面截图：只留「是什么单据」那条。单据上抄下来的订单号、商品名、金额不是现象，
        # 进了观察会混进检索词与选方案（T53 发票上的「Wearable Breast Pump」让充电问题去追问对象，2026-10-13 对照）
        obs = obs[:1]
    obs = list(dict.fromkeys([*obs, *derived]))
    parts = [p.strip() for p in parsed.visible_parts if p.strip()][:10]
    parts = list(dict.fromkeys([*parts, *[f["part"] for f in localization["findings"]]]))
    document_image_ids = [
        r["image_id"] for (r, _, _), kind in zip(images, kinds, strict=True) if kind == "document"
    ]
    log.info(
        "vision observed session=%s images=%d kinds=%s observations=%s parts=%s model=%s prompt_ver=%s",
        session_id,
        len(images),
        kinds,
        obs,
        parts,
        res.model_used,
        VISION_PROMPT_VERSION,
    )
    return VisionOutcome(
        "ok",
        fault_localization=localization,
        observations=obs,
        visible_parts=parts,
        used_image_ids=[r["image_id"] for r, _, _ in images],
        dropped_image_ids=[r["image_id"] for r in dropped],
        document_image_ids=document_image_ids,
        model_used=res.model_used,
        reread_verdict=reread_verdict,
        reread_cell=reread_cell,
        model_trace={
            "task": TASK,
            "model_used": res.model_used,
            "lane": res.lane,
            "attempts": max(1, len(res.attempts)),
        },
    )


ZOOM_MIN_BUDGET_MS = 3_000


async def _reread_nameplate(
    router: ModelRouter,
    localization: dict[str, Any],
    originals: list[tuple[dict[str, Any], bytes]],
    *,
    session_id: str,
    lane: str,
    budget_ms: int,
) -> tuple[dict[str, Any], str]:
    """只要读出了型号，就裁出铭牌那一格放大再读一次，并与全图那次交叉核对。返回 (定位结果, 裁定)。

    **触发条件是「model_hint 非空」而不是「读不清」，也不是「模型给了 cell」**：
    2026-09-15 实测里 deepseek 在 14px 铭牌上给出的是 `T2351` —— 一个格式完全合理、不带 ? 占位的假型号，
    按字面判它「读全了」；而它那一次也没给 model_hint_cell。两种写法都会让校验被它要防的那种输出绕开。
    校验的开关不能握在被校验者手里，所以这里对**任何**会被下游消费的型号断言都要求复看。

    裁剪图在该区域上像素严格更多，是更好的一次测量：
    - 两次一致            → verified=True，下游可以自动锁 SKU；
    - 两次不一致          → 取像素更多的那次的值，但 verified=False（有一次是错的，得让用户确认）；
    - 裁剪图读不出（单图）→ 全图那次的自信答案不可信，清空，回到「不知道」去追问；
    - 没法验（无 cell / 多图 / 预算不足 / 裁剪失败）→ 保留原值但 verified=False。
    多图时裁的是最新一张，铭牌可能在别的图里，所以「读不出」只当作无结论，不清空。
    """
    hint = (localization.get("model_hint") or "").strip()
    if not hint:
        return {**localization, "model_hint_verified": False}, "skipped:no_hint"
    cell = localization.get("model_hint_cell")
    target = _target_image(localization.get("model_hint_image"), originals)
    why = (
        "no_cell" if not cell
        else "no_image" if not originals
        else "no_image_index" if target is None
        else "budget" if budget_ms < ZOOM_MIN_BUDGET_MS + ZOOM_RESERVE_MS
        else None
    )
    if why:
        log.info("nameplate unverified session=%s hint=%r reason=%s", session_id, hint, why)
        return {**localization, "model_hint_verified": False}, f"skipped:{why}"
    cropped = crop_cell(target, cell)
    if cropped is None:
        log.info("nameplate unverified session=%s hint=%r reason=crop_failed", session_id, hint)
        return {**localization, "model_hint_verified": False}, "skipped:crop_failed"
    data, mime = cropped
    b64 = base64.b64encode(data).decode("ascii")
    messages = [
        HumanMessage(
            content=[
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                {"type": "text", "text": NAMEPLATE_INSTRUCTION},
            ]
        )
    ]
    try:
        res = await router.invoke(
            TASK, messages, NameplateRead, budget_ms=budget_ms - ZOOM_RESERVE_MS, session_id=session_id, lane=lane
        )
    except (ModelInvokeError, CapacityExceeded) as exc:
        log.info("nameplate reread failed session=%s cell=%s reason=%s", session_id, cell, exc)
        return {**localization, "model_hint_verified": False}, "failed"

    from app.diagnose.localization import model_hint_readable

    zoomed = (res.parsed.model_hint or "").strip()
    readable = model_hint_readable(zoomed)
    if readable == "unreadable":
        # 裁的就是模型自己指认的那张图的那一格，它在更高像素密度下都读不出来，
        # 全图那次的自信答案就不可信，清空回到「不知道」去追问用户。
        verdict, new_hint, readable, verified = "erased", None, "unreadable", False
    elif _same_hint(hint, zoomed):
        verdict, new_hint, verified = "confirmed", zoomed, True
    else:
        verdict, new_hint, verified = "overridden", zoomed, False
    log.info(
        "nameplate reread session=%s cell=%s %s %r → %r (%s, verified=%s)",
        session_id, cell, verdict, hint, new_hint, readable, verified,
    )
    return {
        **localization,
        "model_hint": new_hint,
        "model_hint_readable": readable,
        "model_hint_verified": verified,
    }, verdict


def _same_hint(a: str, b: str) -> bool:
    """比对型号时忽略空白与大小写；? 占位处不参与比较。"""
    def norm(s: str) -> str:
        return "".join(s.split()).casefold()

    x, y = norm(a), norm(b)
    if not x or not y:
        return False
    if len(x) != len(y):
        return x in y or y in x
    return all(p == q or "?" in (p, q) for p, q in zip(x, y, strict=True))


def _quality(reasons: list[str]) -> dict[str, Any]:
    from app.diagnose.localization import vocabulary

    guidance = vocabulary()["retake_guidance"]
    return {
        "usable": not reasons,
        "reasons": reasons,
        "guidance": [guidance[r] for r in reasons if r in guidance],
    }


def _unusable_localization(gate: QualityReport) -> dict[str, Any]:
    """像素层硬阈值命中时的结果对象：没有任何 finding，只带不可用与补拍指引。"""
    return {
        "findings": [],
        "image_quality": _quality(gate.reasons),
        "model_hint": None,
        "model_hint_cell": None,
        "model_hint_readable": "unreadable",
        "conflicts_with_text": [],
    }


def _merge_quality(localization: dict[str, Any], gate: QualityReport) -> dict[str, Any]:
    """usable = 像素层 AND 模型判定 —— 模型不能否决像素层（A3：可信度必须外生）。

    走到这里说明像素层没有硬拦（硬拦的路径根本不会调用模型），所以这一步实际做两件事：
    1. 模型说不可用时，把像素层的软阈值原因并进来，让补拍指引更具体
       （模型只会说「看不清」，像素层能说出「太暗」还是「太远」）；
    2. 模型说可用时保持可用 —— 软阈值不允许单独拦人。
    """
    quality = localization.get("image_quality") or {}
    if quality.get("usable", True):
        return localization
    reasons = list(dict.fromkeys([*quality.get("reasons", []), *gate.reasons]))
    return {**localization, "image_quality": _quality(reasons)}


def _target_image(index: int | None, originals: list[tuple[dict[str, Any], bytes]]) -> bytes | None:
    """按模型给的图序号取原图。单图时序号可省；多图时省了就没法验 —— 不猜。

    之前是固定裁最新一张：多图且铭牌在别的图里时，复看必然「读不出」，等于形同虚设。
    """
    if not originals:
        return None
    if len(originals) == 1:
        return originals[0][1]
    if index is None or not (1 <= index <= len(originals)):
        return None
    return originals[index - 1][1]
