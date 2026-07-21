"""ask_manual: semantic search over the evidence_index.jsonl."""
import json
import os
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

_model: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


def ask_manual(query: str, top_k: int = 5) -> str:
    """Search the WRX manual knowledge base semantically. Returns relevant passages."""
    evidence_path = Path(os.environ.get("KNOWLEDGE_OUTPUT_DIR", "knowledge/output/wrx")) / "evidence_index.jsonl"

    if not evidence_path.exists():
        return "Knowledge base not found. Run the knowledge pipeline first."

    records = [json.loads(line) for line in evidence_path.read_text().splitlines() if line.strip()]
    records_with_embeddings = [r for r in records if r.get("embedding") is not None]

    if not records_with_embeddings:
        return "No embedded chunks found in knowledge base."

    model = _get_model()
    query_embedding = model.encode(query, normalize_embeddings=True)

    embeddings = np.array([r["embedding"] for r in records_with_embeddings], dtype=np.float32)
    scores = embeddings @ query_embedding.astype(np.float32)

    top_indices = np.argsort(scores)[::-1][:top_k]
    results = []
    for i in top_indices:
        rec = records_with_embeddings[i]
        source = rec.get("source_id", "unknown")
        tier = rec.get("tier", "")
        category = rec.get("category", "")
        score = float(scores[i])
        text = rec["text"]
        results.append(f"[{source} | {tier} | {category} | score={score:.3f}]\n{text}")

    return "\n\n---\n\n".join(results)
