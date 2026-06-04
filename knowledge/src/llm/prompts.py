"""Prompt assembly functions for each pipeline stage."""
from pathlib import Path


def load_prompt(path: Path | str) -> str:
    return Path(path).read_text(encoding="utf-8")


def classify_system() -> str:
    return """You are a source classifier for a car maintenance knowledge pipeline.

Classify the given document as ONE of:
- primary: OEM shop manual, technical service bulletin, factory spec document
- secondary: Service receipt, inspection report, ownership document, carfax, personal service notes
- non-canonical: Marketing materials, general automotive articles, unrelated content

Respond with JSON only:
{"classification": "primary|secondary|non-canonical", "confidence": "high|medium|low", "reasoning": "one sentence"}"""


def classify_user(filename: str, sample: str) -> str:
    return f"Filename: {filename}\n\nText sample:\n{sample[:2000]}"


def summarize_system(base_prompt: str) -> str:
    return f"""{base_prompt}

For each source document, extract and structure the following:

1. **Document type** — what kind of document is this (shop manual section, receipt, inspection report, etc.)
2. **Technical specifications** — torque values, clearances, capacities, part numbers, dimensions
3. **Maintenance procedures** — step-by-step service procedures, special tools required
4. **Service intervals** — recommended mileage or time intervals for any items mentioned
5. **Diagnostic information** — fault codes, symptoms, troubleshooting steps, test procedures
6. **Notable findings** — any unusual conditions, repairs performed, items flagged for attention
7. **Part numbers and OEM references** — any specific part numbers, cross-references

Rules:
- Do NOT fabricate — only extract what is clearly present in the source
- Tag every specific value or procedure with its chunk_id in brackets like [chk_xxx_042]
- Flag confidence: high (directly stated), medium (implied), low (inferred)
- Be ruthlessly concise; no filler prose

Output as markdown with clear section headers."""


def summarize_user(source_name: str, tier: str, chunks: list[dict]) -> str:
    chunks_text = "\n\n---\n\n".join(
        f"[{c['chunk_id']}] ({c['boundary_text'] or c['boundary_type']})\n{c['text']}"
        for c in chunks
    )
    return f"""Source: {source_name}
Tier: {tier}
Total chunks shown: {len(chunks)}

{chunks_text}"""


def car_extract_system(base_prompt: str, advisor_addendum: str, advisor_name: str) -> str:
    return f"""{base_prompt}

## Vehicle Context
{advisor_addendum}

## Your Task

You are synthesizing a unified car knowledge base from multiple source summaries for the {advisor_name}.

For each claim you extract, you MUST:
- Tag with source tier: (primary) for OEM manuals or (secondary) for receipts/notes
- Tag with provenance: [source-derived] or [thin/uncertain]
- Tag with confidence: high | medium | low
- List supporting chunk_ids like [chk_xxx_042, chk_yyy_007]

Organize output into these exact sections (use these exact headers):

# VEHICLE OVERVIEW
Brief summary of the vehicle, its history, and known characteristics.

# MAINTENANCE INTERVALS
Table or list of all known service intervals — item, miles, notes.

# ENGINE SPECIFICATIONS
Torque specs, clearances, oil capacities, timing specs, boost specs, anything EJ205-specific.

# TRANSMISSION & DRIVETRAIN SPECIFICATIONS
Gear ratios, fluid specs, differential specs, AWD torque split.

# CHASSIS & BRAKE SPECIFICATIONS
Alignment specs, brake specs, suspension specs, torque values.

# ELECTRICAL & DIAGNOSTIC
Sensor specs, known DTC codes, wiring references, ECU info.

# SERVICE HISTORY HIGHLIGHTS
Key repairs, notable findings from receipts and service records.

# KNOWN ISSUES & FAILURE MODES
Recurring problems, flagged items, things to watch for on this car.

Target: 8–12 pages. Dense signal only. No filler."""


def car_extract_user(summaries: list[dict]) -> str:
    primary = [s for s in summaries if s["tier"] == "primary"]
    secondary = [s for s in summaries if s["tier"] == "secondary"]
    other = [s for s in summaries if s["tier"] not in ("primary", "secondary")]

    parts = []
    if primary:
        parts.append("## PRIMARY SOURCES — OEM Manuals, TSBs (highest weight)\n")
        for s in primary:
            parts.append(f"### {s['source_name']}\n{s['content']}\n")
    if secondary:
        parts.append("## SECONDARY SOURCES — Receipts, Inspection Notes\n")
        for s in secondary:
            parts.append(f"### {s['source_name']}\n{s['content']}\n")
    if other:
        parts.append("## OTHER SOURCES (use cautiously)\n")
        for s in other:
            parts.append(f"### {s['source_name']}\n{s['content']}\n")

    return "\n".join(parts)


def car_runtime_context_system() -> str:
    return """You compress a car knowledge base into a short runtime context document.

The output will be injected into every agent conversation as the always-on system context.

Requirements:
- Target: 2,500–3,500 tokens
- No filler, no biography, no preamble
- Behavioral primitives over descriptive prose
- Every section must be actionable for an AI mechanic advisor
- Write as reference material — factual, precise, scannable"""


def car_runtime_context_user(advisor_name: str, knowledge_summary: str) -> str:
    return f"""Compress the following car knowledge base for {advisor_name} into a runtime context document.

Use EXACTLY these sections with these headers:

# {advisor_name} — Runtime Context

## Vehicle Profile (key facts, current mileage, engine, known history)
## Critical Maintenance Items (what's overdue or coming up soon)
## Engine Specs Quick Reference (oil spec, capacity, timing, torque values most likely to be needed)
## Maintenance Interval Reference (compact table of items + intervals)
## Known Issues (active problems, recurring faults, things to watch)
## Service History Highlights (major repairs, engine rebuild details)
## Diagnostic Quick Reference (common DTCs for this car, symptom patterns)

---

KNOWLEDGE SUMMARY:
{knowledge_summary[:10000]}"""
