"""Stage 5: Cross-source car knowledge extraction."""
import logging
from pathlib import Path

from src.utils.jsonl import read_jsonl
from src.llm.prompts import car_extract_system, car_extract_user, load_prompt

logger = logging.getLogger(__name__)


def run(cfg: dict, force: bool = False) -> None:
    output_dir = Path(cfg["paths"]["output"])
    summaries_dir = output_dir / "summaries"
    knowledge_path = output_dir / "car_knowledge_summary.md"

    if not force and knowledge_path.exists():
        logger.info("Stage 5: car_knowledge_summary.md already exists, skipping (use --force to re-run)")
        return

    records = read_jsonl(output_dir / "source_registry.jsonl")

    summaries = []
    for rec in records:
        tier = rec.get("classification", "non-canonical")
        summary_path = summaries_dir / f"summary_{rec['source_id']}.md"
        if summary_path.exists():
            summaries.append({
                "source_id": rec["source_id"],
                "source_name": rec.get("rel_path", rec["filename"]),
                "tier": tier,
                "content": summary_path.read_text(encoding="utf-8"),
            })

    if not summaries:
        logger.error("No summaries found — run Stage 4 first")
        return

    advisor_name = cfg["advisor"]["name"]
    base_prompt = load_prompt(cfg["paths"]["base_prompt"])
    addendum_path = cfg["paths"]["advisor_addendum"]
    addendum = load_prompt(addendum_path) if Path(addendum_path).exists() else ""

    system = car_extract_system(base_prompt, addendum, advisor_name)
    user_msg = car_extract_user(summaries)

    logger.info(f"Extracting car knowledge from {len(summaries)} source summaries...")

    from src.llm.client import call_with_cache, get_model
    response = call_with_cache(
        model=get_model(cfg, "sonnet_model"),
        system_blocks=[{
            "type": "text",
            "text": system,
            "cache_control": {"type": "ephemeral"},
        }],
        user_message=user_msg,
        max_tokens=cfg["llm"]["max_tokens_extraction"],
    )

    knowledge_path.write_text(response, encoding="utf-8")
    logger.info(f"Stage 5 complete: car_knowledge_summary.md written ({len(response)} chars)")
