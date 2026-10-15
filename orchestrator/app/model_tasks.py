"""Shared task names for model routes and context configuration; no runtime imports."""

KNOWN_TASKS: tuple[str, ...] = (
    "intake",
    "disambiguate.clarify",
    "diagnose.vision",
    "diagnose.synthesize",
    "guide.step",
    "reply.stream",
    "escalate.summary",
    "warranty.receipt_ocr",
    "remedy.review",
)
OPTIONAL_TASKS: tuple[str, ...] = ("query.rewrite", "retrieve.grade")
