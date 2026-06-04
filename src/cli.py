"""CLI REPL for the WRX mechanic advisor."""
import argparse
import os

from dotenv import load_dotenv

load_dotenv()


def _extract_ai_text(msg) -> str:
    content = msg.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [b["text"] for b in content if isinstance(b, dict) and b.get("type") == "text"]
        return "\n".join(p for p in parts if p)
    return ""


def _fmt_tool_calls(msg) -> str:
    if not getattr(msg, "tool_calls", None):
        return ""
    parts = []
    for tc in msg.tool_calls:
        args = ", ".join(f"{k}={repr(v)}" for k, v in tc["args"].items())[:120]
        parts.append(f"[tool: {tc['name']}({args})]")
    return "\n".join(parts)


def main():
    parser = argparse.ArgumentParser(description="WRX Mechanic Advisor")
    parser.add_argument("--mileage", type=int, default=153000, help="Current odometer reading")
    args = parser.parse_args()

    from langchain_core.messages import HumanMessage, AIMessage
    from src.agent import build_graph
    graph = build_graph()

    print(f"\n[WRX Mechanic] 2003 Subaru WRX | {args.mileage:,} mi")
    print("Type your question or 'quit' to exit.\n")

    history = []
    current_mileage = args.mileage

    while True:
        try:
            user_input = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "q"):
            print("Bye.")
            break

        history.append(HumanMessage(content=user_input))
        prev_len = len(history)

        result = graph.invoke(
            {"messages": history, "current_mileage": current_mileage},
        )
        history = result["messages"]

        for msg in history[prev_len:]:
            if isinstance(msg, AIMessage):
                tool_info = _fmt_tool_calls(msg)
                if tool_info:
                    print(f"\n{tool_info}")
                text = _extract_ai_text(msg)
                if text:
                    print(f"\n{text}\n")


if __name__ == "__main__":
    main()
