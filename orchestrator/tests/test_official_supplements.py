"""官方图表补充经过实际索引、幂等入库、范围检索及HTTP产品咨询；无真实外部调用。"""

import pytest
import yaml
from pydantic import ValidationError

from app.diagnose import get_retrieval_config
from app.knowledge.adapter import Hit, KnowledgeScope, WeKnoraKnowledgeAdapter
from app.knowledge.context import pack_hits
from app.knowledge.ingest import Ingestor, qa_content, write_manifest
from app.knowledge.runtime import set_knowledge_adapter
from app.knowledge.weknora_client import WeKnoraClient
from app.official.models import OfficialData
from app.official.qa_index import QAIndex
from app.official.supplements import load_supplements
from app.settings import REPO_ROOT
from tests.conversation_runtime import conversation as conversation_fixture
from tests.fake_weknora import FakeWeKnora

conversation = conversation_fixture
SOURCE = REPO_ROOT / "data/official/qa_supplements.yaml"
SUPPLEMENT = "supp-bp-s1-pro-green-light"


@pytest.fixture
def data(tmp_path):
    # 保留一个原赛题条目，验证新增补充时不替换不相关知识。
    entry = OfficialData().qa[0].model_dump(mode="json")
    (tmp_path / "qa.yaml").write_text(
        "# sha256=workbook-v1\n" + yaml.safe_dump({"entries": [entry]})
    )
    (tmp_path / "qa_supplements.yaml").write_bytes(SOURCE.read_bytes())
    return OfficialData(tmp_path)


def test_chart_is_a_scoped_explanation_and_does_not_modify_workbook_entries():
    data = OfficialData()
    index = QAIndex.build(data)
    assert len(data.qa) == 875
    guide = index.guides[SUPPLEMENT]
    assert guide.kind == "answer" and all(s.kind == "statement" for s in guide.steps)
    assert guide.pns == ("T8D04",) and guide.category == "breast_pump"
    text = qa_content(guide)
    assert "flashing green" in text and "charging is in progress" in text
    assert "steady (solid) green" in text and "charging is complete" in text
    assert "not the charging case" in text
    assert guide.source and guide.source.review_status == "agent_source_checked"
    assert guide.media[0].url == guide.source.url
    assert guide in index.for_pn("T8D04121")
    assert guide not in index.for_pn("T8D02")


def test_green_definitions_and_scope_survive_a_full_evidence_budget():
    """T48真实复测：12条证据均分5000字符，长范围说明挤掉了常亮定义。"""
    index = QAIndex.build()
    ids = [SUPPLEMENT, "bp-0010", "bp-0004", "bp-0091", "bp-0006", "bp-0105",
           "bp-0012", "bp-0039", "bp-0122", "bp-0065", "bp-0067", "bp-0058"]
    hits = []
    for i, qa_id in enumerate(ids):
        content = qa_content(index.guides[qa_id])
        hits.append(Hit(
            evidence_id=f"{i:036d}", knowledge_id=qa_id, chunk_id=f"{i:036d}",
            doc_id=qa_id, doc_version=index.entry_versions[qa_id], source="kb_qa",
            snippet=content[:400], content=content, score=0.9, knowledge_title=qa_id,
        ))
    cfg = get_retrieval_config().retrieval
    selected = pack_hits(hits, max_items=cfg.final_k, max_chars=cfg.context_chars, item_chars=cfg.item_chars)
    text = next(hit.context_text for hit in selected.hits if hit.doc_id == SUPPLEMENT)
    assert text == qa_content(index.guides[SUPPLEMENT])
    assert "charging is in progress" in text and "charging is complete" in text
    assert "T8D04 pump hub" in text and "not the charging case" in text


@pytest.mark.parametrize("change", ["content", "scope_note", "source"])
def test_supplement_changes_its_version_without_changing_workbook_version(data, change):
    before = QAIndex.build(data)
    path = data.root / "qa_supplements.yaml"
    payload = yaml.safe_load(path.read_text())
    entry = payload["entries"][0]
    if change == "source":
        entry["source"]["image_sha256"] = "a" * 64
    else:
        entry[change] += " Additional reviewed condition."
    path.write_text(yaml.safe_dump(payload))
    after = QAIndex.build(data)
    assert before.version != after.version
    assert before.entry_versions[SUPPLEMENT] != after.entry_versions[SUPPLEMENT]
    base_id = data.qa[0].id
    assert before.entry_versions[base_id] == after.entry_versions[base_id] == "workbook-v1"
    path.write_text("# formatting only\n" + yaml.safe_dump(payload, sort_keys=False))
    assert QAIndex.build(data).version == after.version


@pytest.mark.parametrize("failure", ["duplicate", "missing_source", "bad_hash", "bad_pn"])
def test_invalid_supplement_is_rejected_before_ingestion(data, failure):
    path = data.root / "qa_supplements.yaml"
    payload = yaml.safe_load(path.read_text())
    entry = payload["entries"][0]
    if failure == "duplicate":
        payload["entries"].append(entry)
    elif failure == "missing_source":
        del entry["source"]
    elif failure == "bad_hash":
        entry["source"]["image_sha256"] = "not-a-checksum"
    else:
        entry["pn"] = ["all-products"]
    path.write_text(yaml.safe_dump(payload))
    with pytest.raises((ValidationError, ValueError)):
        load_supplements(path)


async def test_ingest_is_incremental_versioned_and_preserves_source(data, tmp_path):
    server = FakeWeKnora()
    path = data.root / "qa_supplements.yaml"
    source_bytes = path.read_bytes()
    path.unlink()
    before = QAIndex.build(data)
    async with WeKnoraClient("http://fake", server.api_key, transport=server.transport()) as client:
        await Ingestor(client).ingest_qa(embedding_model_id=None, index=before)
        old_id = next(iter(server.knowledge))
        path.write_bytes(source_bytes)
        index = QAIndex.build(data)
        ing = Ingestor(client)
        await ing.ingest_qa(embedding_model_id=None, index=index)
        assert (ing.report.created, ing.report.replaced, ing.report.skipped) == (1, 0, 1)
        assert old_id in server.knowledge
        item = next(k for k in server.knowledge.values() if k["title"] == SUPPLEMENT)
        meta = item["custom_metadata"]
        assert meta["source_type"] == "official_image_summary"
        assert meta["source_url"] == index.guides[SUPPLEMENT].source.url
        assert meta["doc_version"] == index.entry_versions[SUPPLEMENT]
        assert meta["sku_list"] == "T8D04" and meta["scope"] == "sku"
        assert len(meta) <= 20 and all(isinstance(v, str) for v in meta.values())
        first_manifest = write_manifest(tmp_path / "manifest.json", ing.report, source_root=data.root)
        again = Ingestor(client)
        await again.ingest_qa(embedding_model_id=None, index=QAIndex.build(data))
        assert (again.report.created, again.report.replaced, again.report.skipped) == (0, 0, 2)
        payload = yaml.safe_load(path.read_text())
        payload["entries"][0]["scope_note"] += " Reviewed scope clarification."
        path.write_text(yaml.safe_dump(payload))
        changed = Ingestor(client)
        await changed.ingest_qa(embedding_model_id=None, index=QAIndex.build(data))
        assert (changed.report.created, changed.report.replaced, changed.report.skipped) == (1, 1, 1)
        assert old_id in server.knowledge
        last_manifest = write_manifest(tmp_path / "manifest.json", changed.report, source_root=data.root)
        assert first_manifest["kb_ver"] != last_manifest["kb_ver"]


async def test_ingested_chart_is_retrievable_only_for_confirmed_matching_model(data):
    server = FakeWeKnora()
    async with WeKnoraClient("http://fake", server.api_key, transport=server.transport()) as client:
        ing = Ingestor(client)
        await ing.ingest_qa(embedding_model_id=None, index=QAIndex.build(data))
        adapter = WeKnoraKnowledgeAdapter(client, ing.report.kb_ids)
        await adapter.refresh_index()
        result = await adapter.hybrid_search(
            "kb_qa", "green", 5, KnowledgeScope("confirmed_sku", "breast_pump", "T8D04")
        )
        assert [h.doc_id for h in result.hits] == [SUPPLEMENT]
        assert "charging is complete" in result.hits[0].content
        for scope in (
            KnowledgeScope("confirmed_sku", "breast_pump", "T8D02"),
            KnowledgeScope("confirmed_sku", "breast_pump", "T8D03"),
            KnowledgeScope("confirmed_sku", "robot_vacuum", "T2080"),
            KnowledgeScope("category_only", "breast_pump"),
            KnowledgeScope("unknown", "breast_pump"),
        ):
            assert not (await adapter.hybrid_search("kb_qa", "green", 5, scope)).hits


async def test_http_product_answer_receives_ingested_chart_and_scope(conversation, data):
    server = FakeWeKnora()
    async with WeKnoraClient("http://fake", server.api_key, transport=server.transport()) as client:
        ing = Ingestor(client)
        await ing.ingest_qa(embedding_model_id=None, index=QAIndex.build(data))
        set_knowledge_adapter(WeKnoraKnowledgeAdapter(client, ing.report.kb_ids))
        await conversation.send("What does the green indicator light", {"primary_intent": "product_question"})
        events = await conversation.send("S1 Pro Breast Pump, model T8D04", {
            "primary_intent": "supplement", "product_hints": ["T8D04"],
        })
        items = [item for event in events if event["type"] == "evidence" for item in event["items"]]
        assert any(item["doc_id"] == SUPPLEMENT for item in items)
        messages = conversation.models["reply.stream"].calls[-1]["messages"]
        evidence = "\n".join(str(message.content) for message in messages)
        assert "official_evidence" in evidence
        assert "flashing green" in evidence and "steady (solid) green" in evidence
        assert "not the charging case" in evidence
        assert "当前检索到的资料不足" in evidence
        assert not any(event["type"] == "step_card" for event in events)
