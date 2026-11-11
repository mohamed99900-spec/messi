import asyncio
import logging
import re
import time

import httpx
from telegram.constants import ChatAction, ChatType

import ai
import database
from config import AI_GROUP_COOLDOWN, AI_USER_COOLDOWN, DEVELOPER
from handlers import admin, economy, events, games, general  # noqa: F401  (تسجيل الأوامر)
from handlers.games import check_chat_answer
from registry import resolve
from utils import chunks, escape, is_group_chat, md_to_html, normalize, reply

log = logging.getLogger("MESSI.chat")

_user_last = {}
_group_last = {}

_NAME_RE = re.compile(r"(?<!\w)ميسي(?!\w)")
_DEV_RE = re.compile(
    r"(مطور|صانع|مبرمج|مصمم|منشئ)ك"
    r"|(مين|من|منو)\s+(اللي\s+)?(طور|صنع|عمل|برمج|سوا|خلق|انشا|صمم)(ك|ني)"
)


def cleanup():
    now = time.time()
    for key in [k for k, v in _user_last.items() if now - v > 300]:
        _user_last.pop(key, None)
    for key in [k for k, v in _group_last.items() if now - v > 300]:
        _group_last.pop(key, None)


async def _typing(context, chat_id, stop):
    while not stop.is_set():
        try:
            await context.bot.send_chat_action(chat_id, ChatAction.TYPING)
        except Exception:
            pass
        try:
            await asyncio.wait_for(stop.wait(), timeout=4)
        except asyncio.TimeoutError:
            pass


async def message_router(update, context):
    msg = update.effective_message
    user = update.effective_user
    chat = update.effective_chat
    if not msg or not user or user.is_bot or not chat:
        return

    text = (msg.text or "").strip()
    if not text:
        return

    await database.ensure_user(user)

    # 1) الأوامر (عربي أو /)
    found = resolve(text, context.bot.username or "")
    if found:
        handler, args = found
        await handler(update, context, args)
        return
    if text.startswith("/"):
        return

    # 2) إجابات الفزاير والتحديات الشغالة
    if await check_chat_answer(update, context, text):
        return

    # 3) الذكاء الاصطناعي
    in_group = is_group_chat(chat)
    bot_username = (context.bot.username or "").lower()
    norm = normalize(text)

    if in_group:
        settings = await database.get_chat(chat.id, chat.title or "", "group")
        if not settings["ai"]:
            return
        replied_to_bot = bool(
            msg.reply_to_message
            and msg.reply_to_message.from_user
            and msg.reply_to_message.from_user.id == context.bot.id
        )
        addressed = bool(
            _NAME_RE.search(norm)
            or (bot_username and f"@{bot_username}" in text.lower())
            or replied_to_bot
        )
    else:
        addressed = chat.type == ChatType.PRIVATE

    if not addressed:
        return

    # سؤال عن المطور
    if _DEV_RE.search(norm):
        await reply(
            update,
            f"👑 اللي طوّرني وبرمجني هو المبدع <b>{DEVELOPER}</b> ⚽🔥\n"
            "لو عجبك البوت ادعيله بالتوفيق 😎",
        )
        return

    now = time.time()
    if now - _user_last.get((chat.id, user.id), 0) < AI_USER_COOLDOWN:
        return
    if in_group and now - _group_last.get(chat.id, 0) < AI_GROUP_COOLDOWN:
        return
    _user_last[(chat.id, user.id)] = now
    if in_group:
        _group_last[chat.id] = now

    prompt = text
    if in_group:
        if bot_username:
            prompt = re.sub(rf"@{re.escape(bot_username)}", "", prompt, flags=re.IGNORECASE)
        prompt = re.sub(r"(يا\s+)?ميس[يى](\s+بوت)?", "", prompt, count=1).strip()
        if not prompt:
            prompt = "أهلاً يا ميسي"

    # لو رد على رسالة حد تاني: نضيفها كسياق
    quoted = msg.reply_to_message
    if quoted and quoted.from_user and quoted.from_user.id != context.bot.id:
        quoted_text = (quoted.text or quoted.caption or "").strip()
        if quoted_text:
            prompt = f"الرسالة المقتبسة:\n{quoted_text[:2000]}\n\nطلب المستخدم: {prompt}"

    stop = asyncio.Event()
    typing_task = asyncio.create_task(_typing(context, chat.id, stop))
    try:
        answer = await ai.ask(chat.id, user.id, prompt, user_name=user.first_name or "")
        for part in chunks(answer):
            await reply(update, md_to_html(part))
    except ai.AIError as exc:
        log.error("AI error: %s", exc)
        await reply(update, f"🤖 <b>مشكلة في الذكاء الاصطناعي:</b>\n{escape(exc)}")
    except httpx.TimeoutException:
        await reply(update, "⏳ الذكاء الاصطناعي اتأخر في الرد. جرب تاني بعد شوية.")
    except httpx.RequestError:
        log.exception("Groq connection error")
        await reply(update, "🌐 معرفتش أوصل لخدمة الذكاء الاصطناعي. راجع النت وجرب تاني.")
    except Exception:
        log.exception("Unexpected AI error")
        await reply(update, "😅 حصل خطأ غير متوقع وأنا بجهز الرد. جرب تاني.")
    finally:
        stop.set()
        typing_task.cancel()
