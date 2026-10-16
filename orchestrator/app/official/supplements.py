"""经核对的官方图表文字补充；与工作簿生成数据分开，版本由内容与来源共同决定。"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import Field

from app.official.models import Strict


class ReviewedSource(Strict):
    url: str = Field(pattern=r"^https://[^/]+/", min_length=10)
    locator: str = Field(min_length=1)
    image_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reviewed_at: date
    review_status: Literal["agent_source_checked", "human_checked"]


class Supplement(Strict):
    id: str = Field(pattern=r"^supp-[a-z0-9]+(?:-[a-z0-9]+)*$")
    title: str = Field(min_length=1)
    pn: list[Annotated[str, Field(pattern=r"^T(?:8D\d{2}|\d{4})$")]] = Field(min_length=1)
    category: Literal["robot_vacuum", "breast_pump", "security_cam"]
    scope_note: str = Field(min_length=1)
    content: str = Field(min_length=1)
    source: ReviewedSource

    @property
    def version(self) -> str:
        payload = json.dumps(self.model_dump(mode="json"), sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(payload.encode()).hexdigest()[:12]


class SupplementFile(Strict):
    entries: list[Supplement]


def load_supplements(path: Path) -> list[Supplement]:
    if not path.is_file():
        return []
    entries = SupplementFile.model_validate(yaml.safe_load(path.read_text(encoding="utf-8"))).entries
    ids = [entry.id for entry in entries]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate official supplement id")
    return entries
