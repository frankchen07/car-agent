"""Stage 6: Assemble runtime_context.md and evidence_index.jsonl."""
import logging
from pathlib import Path

import tiktoken

from src.utils.jsonl import read_jsonl, write_jsonl
from src.llm.prompts import car_runtime_context_system, car_runtime_context_user

logger = logging.getLogger(__name__)


def run(cfg: dict, force: bool = False) -> None:
    output_dir = Path(cfg["paths"]["output"])
    knowledge_path = output_dir / "car_knowledge_summary.md"
    runtime_path = output_dir / "runtime_context.md"
    evidence_path = output_dir / "evidence_index.jsonl"

    if not knowledge_path.exists():
        logger.error("car_knowledge_summary.md not found — run Stage 5 first")
        return

    if not force and runtime_path.exists() and evidence_path.exists():
        logger.info("Stage 6: runtime context already exists, skipping (use --force to re-run)")
        return

    _build_runtime_context(cfg, knowledge_path, runtime_path)
    _build_evidence_index(cfg, output_dir, evidence_path)
    _build_project_upload(cfg, output_dir, runtime_path, knowledge_path)

    logger.info("Stage 6 complete")


def _build_runtime_context(cfg, knowledge_path, runtime_path):
    advisor_name = cfg["advisor"]["name"]
    knowledge_summary = knowledge_path.read_text(encoding="utf-8")

    system = car_runtime_context_system()
    user_msg = car_runtime_context_user(advisor_name, knowledge_summary)

    logger.info("Generating runtime_context.md...")
    from src.llm.client import call_with_cache, get_model
    response = call_with_cache(
        model=get_model(cfg, "sonnet_model"),
        system_blocks=[{"type": "text", "text": system}],
        user_message=user_msg,
        max_tokens=cfg["llm"]["max_tokens_runtime_context"],
    )

    runtime_path.write_text(response, encoding="utf-8")
    enc = tiktoken.get_encoding(cfg["chunking"]["tokenizer"])
    tok = len(enc.encode(response))
    logger.info(f"runtime_context.md written: {tok} tokens")


def _build_evidence_index(cfg, output_dir, evidence_path):
    chunk_index_path = output_dir / "chunk_index.jsonl"
    all_chunks = read_jsonl(chunk_index_path)

    embed_tiers = set(cfg["embeddings"]["tiers_to_embed"])
    embed_model = cfg["embeddings"]["model"]

    records = []
    texts_to_embed = []
    indices_to_embed = []

    for i, chunk in enumerate(all_chunks):
        category = _infer_category(chunk)
        rec = {
            "ev_id": f"ev_{i:05d}",
            "chunk_id": chunk["chunk_id"],
            "source_id": chunk["source_id"],
            "tier": chunk["tier"],
            "provenance": chunk.get("provenance", "source-derived"),
            "confidence": chunk.get("confidence", "high"),
            "category": category,
            "tags": chunk.get("concepts", []),
            "text": chunk["text"],
            "token_count": chunk["token_count"],
            "embedding": None,
        }
        records.append(rec)
        if chunk.get("tier") in embed_tiers:
            texts_to_embed.append(chunk["text"])
            indices_to_embed.append(i)

    if texts_to_embed:
        logger.info(f"Generating embeddings for {len(texts_to_embed)} chunks...")
        from src.utils.embeddings import embed_texts
        embeddings = embed_texts(texts_to_embed, embed_model)
        for idx, emb in zip(indices_to_embed, embeddings):
            records[idx]["embedding"] = emb

    write_jsonl(evidence_path, records)
    logger.info(f"evidence_index.jsonl written: {len(records)} records")


def _build_project_upload(cfg, output_dir, runtime_path, knowledge_path):
    upload_dir = output_dir / "project_upload"
    upload_dir.mkdir(parents=True, exist_ok=True)
    chunks_upload_dir = upload_dir / "chunks"
    chunks_upload_dir.mkdir(parents=True, exist_ok=True)

    for src, dst_name in [
        (runtime_path, "00_runtime_context.md"),
        (knowledge_path, "01_car_knowledge_summary.md"),
    ]:
        if src.exists():
            (upload_dir / dst_name).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

    evidence = read_jsonl(output_dir / "evidence_index.jsonl")
    include_tiers = set(cfg["project_upload"]["include_tiers"])
    min_conf = cfg["project_upload"]["min_confidence"]
    top_n = cfg["project_upload"]["top_chunks_per_category"]

    by_category: dict[str, list[dict]] = {}
    for ev in evidence:
        if ev["tier"] in include_tiers and ev.get("confidence") == min_conf:
            by_category.setdefault(ev["category"], []).append(ev)

    for cat, evs in by_category.items():
        for i, ev in enumerate(evs[:top_n]):
            fname = f"{cat}_{i:02d}_{ev['chunk_id']}.md"
            content = f"# {cat.title()} — {ev['tags']}\n\n**Source:** {ev['source_id']} | **Tier:** {ev['tier']} | **Confidence:** {ev['confidence']}\n\n{ev['text']}"
            (chunks_upload_dir / fname).write_text(content, encoding="utf-8")

    logger.info(f"project_upload/ ready: {upload_dir}")


def _infer_category(chunk: dict) -> str:
    concepts = " ".join(chunk.get("concepts", [])).lower()
    text_lower = chunk.get("text", "").lower()[:300]
    combined = concepts + " " + text_lower

    if any(w in combined for w in ["engine", "oil", "timing", "piston", "valve", "turbo", "boost", "ej205", "head", "camshaft", "crankshaft", "compression", "cylinder"]):
        return "engine"
    if any(w in combined for w in ["transmission", "gearbox", "clutch", "differential", "gear", "awd", "transfer", "synchro"]):
        return "transmission"
    if any(w in combined for w in ["brake", "suspension", "alignment", "steering", "wheel", "tire", "shock", "strut", "caliper", "rotor", "pad"]):
        return "chassis"
    if any(w in combined for w in ["wiring", "sensor", "ecu", "fuse", "relay", "electrical", "battery", "alternator", "abs", "obd", "dtc", "fault", "code"]):
        return "electrical"
    if any(w in combined for w in ["p0", "p1", "b0", "c0", "u0", "cel", "check engine", "misfire", "symptom", "diagnos", "troubleshoot"]):
        return "diagnostics"
    if any(w in combined for w in ["interval", "service", "inspect", "replace", "filter", "fluid", "coolant", "schedule", "maintenance", "oil change"]):
        return "maintenance"
    return "general"
