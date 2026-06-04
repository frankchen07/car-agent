"""LangGraph ReAct agent — provider-agnostic via CHAT_PROVIDER env var."""
import os
from pathlib import Path
from typing import Annotated

from langchain_core.messages import SystemMessage, AIMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from typing_extensions import TypedDict


# ── tools ──────────────────────────────────────────────────────────────────

@tool
def ask_manual(query: str) -> str:
    """Search the WRX shop manual knowledge base for technical specifications,
    maintenance procedures, torque values, diagnostic steps, or any information
    from the OEM manuals. Be specific (e.g. 'head bolt torque DOHC',
    'valve clearance EJ205', 'P0301 misfire diagnosis')."""
    from src.tools.manual import ask_manual as _fn
    return _fn(query=query)


@tool
def get_service_history(limit: int = 20, keyword: str | None = None) -> str:
    """Query the vehicle's service history from the database, ordered by date.
    Optionally filter by keyword (e.g. 'oil', 'timing belt', 'brakes')."""
    from src.tools.service import get_service_history as _fn
    return _fn(limit=limit, keyword=keyword)


@tool
def get_maintenance_plan(current_mileage: int) -> str:
    """Get the current maintenance plan — overdue and upcoming service items
    based on current mileage."""
    from src.tools.service import get_maintenance_plan as _fn
    return _fn(current_mileage=current_mileage)


@tool
def log_service(
    service_date: str,
    mileage: int,
    servicer: str,
    description: str,
    interval_miles: int | None = None,
    next_due_mileage: int | None = None,
) -> str:
    """Log a completed service event. service_date must be YYYY-MM-DD format."""
    from src.tools.service import log_service as _fn
    return _fn(
        service_date=service_date,
        mileage=mileage,
        servicer=servicer,
        description=description,
        interval_miles=interval_miles,
        next_due_mileage=next_due_mileage,
    )


@tool
def get_issues(resolved: bool | None = None) -> str:
    """Get logged issues and symptoms. Pass resolved=True for closed,
    resolved=False for open, omit for all."""
    from src.tools.issues import get_issues as _fn
    return _fn(resolved=resolved)


@tool
def log_issue(
    description: str,
    severity: str = "medium",
    dtc_code: str | None = None,
    conditions: str | None = None,
) -> str:
    """Log a new problem, symptom, or DTC code. severity must be one of:
    low, medium, high, critical."""
    from src.tools.issues import log_issue as _fn
    return _fn(
        description=description,
        severity=severity,
        dtc_code=dtc_code,
        conditions=conditions,
    )


TOOLS = [
    ask_manual,
    get_service_history,
    get_maintenance_plan,
    log_service,
    get_issues,
    log_issue,
]


# ── state ──────────────────────────────────────────────────────────────────

class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    current_mileage: int


# ── LLM factory ────────────────────────────────────────────────────────────

def _build_llm():
    provider = os.environ.get("CHAT_PROVIDER", "anthropic")
    model = os.environ.get("CHAT_MODEL", "claude-sonnet-4-6-20250514")

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model=model, api_key=os.environ["ANTHROPIC_API_KEY"])

    if provider == "openrouter":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=model,
            api_key=os.environ["OPENROUTER_API_KEY"],
            base_url="https://openrouter.ai/api/v1",
        )

    if provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model=model, api_key=os.environ["OPENAI_API_KEY"])

    raise ValueError(f"Unknown CHAT_PROVIDER: {provider}")


# ── system prompt ───────────────────────────────────────────────────────────

def _load_system_prompt() -> str:
    soul_path = Path(__file__).parent.parent / "persona" / "SOUL.md"
    runtime_path = (
        Path(os.environ.get("KNOWLEDGE_OUTPUT_DIR", "knowledge/output/wrx"))
        / "runtime_context.md"
    )
    parts = []
    if soul_path.exists():
        parts.append(soul_path.read_text(encoding="utf-8"))
    if runtime_path.exists():
        parts.append("\n\n---\n\n" + runtime_path.read_text(encoding="utf-8"))
    return "\n".join(parts) if parts else "You are a mechanic advisor for a 2003 Subaru WRX."


# ── graph ───────────────────────────────────────────────────────────────────

def build_graph():
    llm = _build_llm()
    llm_with_tools = llm.bind_tools(TOOLS)
    system_prompt = _load_system_prompt()
    tool_node = ToolNode(TOOLS)

    def call_model(state: AgentState) -> dict:
        # Prepend system message for each LLM call — not stored in state
        full_messages = [SystemMessage(content=system_prompt)] + list(state["messages"])
        response = llm_with_tools.invoke(full_messages)
        return {"messages": [response]}

    def route(state: AgentState) -> str:
        last = state["messages"][-1]
        if isinstance(last, AIMessage) and last.tool_calls:
            return "tools"
        return END

    graph = StateGraph(AgentState)
    graph.add_node("call_model", call_model)
    graph.add_node("tools", tool_node)
    graph.set_entry_point("call_model")
    graph.add_conditional_edges("call_model", route, {"tools": "tools", END: END})
    graph.add_edge("tools", "call_model")

    return graph.compile()
