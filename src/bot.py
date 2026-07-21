"""Telegram bot interface for the WRX mechanic advisor."""
import asyncio
import base64
import logging
import os

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

_ALLOWED: set[str] = set(filter(None, os.environ.get("TELEGRAM_ALLOWED_USERS", "").split(",")))
_DEFAULT_MILEAGE = 153_000

_histories: dict[int, list] = {}
_mileages: dict[int, int] = {}

_graph = None


def _get_graph():
    global _graph
    if _graph is None:
        from src.agent import build_graph
        _graph = build_graph()
    return _graph


def _is_allowed(update: Update) -> bool:
    if not _ALLOWED:
        return True
    return str(update.effective_chat.id) in _ALLOWED


def _extract_text(msg) -> str:
    content = msg.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [b["text"] for b in content if isinstance(b, dict) and b.get("type") == "text"]
        return "\n".join(p for p in parts if p)
    return ""


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        return
    await update.message.reply_text(
        "WRX mechanic online.\n\n"
        "Ask me anything about your 2003 Subaru WRX — maintenance, service history, issues, or manual specs.\n\n"
        "/mileage <n> — update odometer\n"
        "/reset — clear conversation history"
    )


async def cmd_mileage(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        return
    chat_id = update.effective_chat.id
    try:
        miles = int(ctx.args[0].replace(",", ""))
        _mileages[chat_id] = miles
        await update.message.reply_text(f"Odometer updated to {miles:,} mi.")
    except (IndexError, ValueError):
        current = _mileages.get(chat_id, _DEFAULT_MILEAGE)
        await update.message.reply_text(f"Current odometer: {current:,} mi. Usage: /mileage 154000")


async def cmd_reset(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        return
    _histories.pop(update.effective_chat.id, None)
    await update.message.reply_text("Conversation history cleared.")


async def _typing_loop(bot, chat_id: int, stop: asyncio.Event) -> None:
    while not stop.is_set():
        await bot.send_chat_action(chat_id=chat_id, action="typing")
        try:
            await asyncio.wait_for(stop.wait(), timeout=4)
        except asyncio.TimeoutError:
            pass


async def on_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        return
    chat_id = update.effective_chat.id

    if update.message.photo:
        text = update.message.caption or ""
        photo = update.message.photo[-1]
        file = await photo.get_file()
        photo_bytes = await file.download_as_bytearray()
        b64 = base64.b64encode(photo_bytes).decode()
        content: list = [{"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}]
        if text.strip():
            content.append({"type": "text", "text": text})
        human_msg = HumanMessage(content=content)
    else:
        text = update.message.text or ""
        if not text.strip():
            return
        human_msg = HumanMessage(content=text)

    stop = asyncio.Event()
    typing_task = asyncio.create_task(_typing_loop(ctx.bot, chat_id, stop))

    history = _histories.setdefault(chat_id, [])
    history.append(human_msg)
    mileage = _mileages.get(chat_id, _DEFAULT_MILEAGE)

    try:
        result = await asyncio.to_thread(
            _get_graph().invoke,
            {"messages": history, "current_mileage": mileage},
        )
    except Exception as exc:
        log.exception("Agent error")
        await update.message.reply_text(f"Something went wrong: {exc}")
        return
    finally:
        stop.set()
        await typing_task

    _histories[chat_id] = result["messages"]

    reply_parts = []
    for msg in result["messages"][len(history):]:
        if isinstance(msg, AIMessage):
            txt = _extract_text(msg)
            if txt:
                reply_parts.append(txt)

    reply = "\n\n".join(reply_parts) or "(no response)"
    # Telegram message limit is 4096 chars
    if len(reply) > 4096:
        reply = reply[:4090] + "…"

    await update.message.reply_text(reply)


def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN not set in environment")

    app = (
        ApplicationBuilder()
        .token(token)
        .build()
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("mileage", cmd_mileage))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(MessageHandler((filters.TEXT | filters.PHOTO) & ~filters.COMMAND, on_message))

    log.info("WRX bot polling...")
    app.run_polling()


if __name__ == "__main__":
    main()
