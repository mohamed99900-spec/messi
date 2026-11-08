import logging
import re
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

from telegram.constants import ChatType
from telegram.error import TelegramError
from telegram.ext import ApplicationHandlerStop

import database
import keyboards
from config import DEVELOPER
from handlers.admin import LOCKED_PERMS, is_admin_user
from utils import escape, is_group_chat, mention, normalize, reply, send

log = logging.getLogger("MESSI.events")

_repeat = {}
_flood = defaultdict(lambda: deque(maxlen=10))
LINK_RE = re.compile(r"(https?://|www\.|t\.me/|telegram\.me/)", re.IGNORECASE)


async def activity(update, context):
    user = update.effective_user
    if not user or user.is_bot:
        return
    await database.ensure_user(user)
    chat = update.effective_chat
    if chat and is_group_chat(chat):
        await database.get_chat(chat.id, chat.title or "", "group")
    await database.activity_reward(user.id)


async def welcome(update, context):
    msg = update.effective_message
    chat = update.effective_chat
    if not msg or not msg.new_chat_members:
        return
    settings = await database.get_chat(chat.id, chat.title or "", "group")
    if not settings["welcome"]:
        return

    for member in msg.new_chat_members:
        if member.is_bot:
            continue
        await database.ensure_user(member)
        template = settings["welcome_text"]
        if template:
            text = (
                escape(template)
                .replace("{name}", mention(member))
                .replace("{group}", escape(chat.title or ""))
            )
        else:
            text = (
                f"🎉 يا أهلاً {mention(member)}!\n\n"
                f"نورت <b>{escape(chat.title or 'الجروب')}</b> مع ميسي بوت ⚽😂\n"
                "اكتب <code>مساعدة</code> علشان تعرف الأوامر."
            )
        if settings["rules"]:
            text += "\n\n📜 اكتب <code>القوانين</code> علشان تقراها."
        await send(context.bot, chat.id, text)


async def my_chat_member(update, context):
    event = update.my_chat_member
    chat = event.chat
    if chat.type == ChatType.PRIVATE:
        return
    kind = "channel" if chat.type == ChatType.CHANNEL else "group"
    new_status = event.new_chat_member.status
    old_status = event.old_chat_member.status

    if new_status in ("member", "administrator"):
        await database.get_chat(chat.id, chat.title or "", kind)
        if old_status in ("left", "kicked"):
            await database.set_chat(chat.id, title=chat.title or "", kind=kind, salawat=0 if kind == "channel" else 1)
            if kind == "group":
                await send(
                    context.bot, chat.id,
                    "👑 <b>ميسي بوت وصل!</b> ⚽😂\n\n"
                    "ارفعني مشرف علشان أقدر أدير الجروب.\n"
                    "اكتب <code>مساعدة</code> لكل الأوامر.\n"
                    f"👨‍💻 المطور: <b>{DEVELOPER}</b>",
                )
    elif new_status in ("left", "kicked"):
        await database.set_chat(chat.id, salawat=0)


async def channel_post(update, context):
    msg = update.channel_post
    chat = update.effective_chat
    if not msg or not msg.text:
        return
    commands = {
        "تفعيل الصلاه": 1, "تفعيل الصلاه على النبي": 1,
        "تعطيل الصلاه": 0, "تعطيل الصلاه على النبي": 0,
    }
    key = normalize(msg.text)
    if key not in commands:
        return
    await database.get_chat(chat.id, chat.title or "", "channel")
    await database.set_chat(chat.id, kind="channel", title=chat.title or "", salawat=commands[key])
    try:
        await msg.delete()
    except TelegramError:
        pass
    state = "اتفعّل 🕌 وهفكركم بالصلاة على النبي ﷺ كل ربع ساعة" if commands[key] else "اتعطّل"
    await send(context.bot, chat.id, f"✅ تذكير الصلاة على النبي {state}.")


async def protection(update, context):
    chat = update.effective_chat
    user = update.effective_user
    msg = update.effective_message
    if not is_group_chat(chat) or not msg or not user or user.is_bot:
        return

    settings = await database.get_chat(chat.id, chat.title or "", "group")
    if not (settings["antilinks"] or settings["antispam"]):
        return
    if await is_admin_user(context, chat.id, user.id):
        return

    text = msg.text or msg.caption or ""

    if settings["antilinks"]:
        entities = list(msg.entities or []) + list(msg.caption_entities or [])
        has_entity = any(e.type in ("url", "text_link") for e in entities)
        if has_entity or LINK_RE.search(text):
            try:
                await msg.delete()
                await send(context.bot, chat.id, f"🔗 {mention(user)} الروابط ممنوعة هنا.")
            except TelegramError:
                log.warning("couldn't delete link message")
            raise ApplicationHandlerStop

    if settings["antispam"]:
        now = time.time()
        key = (chat.id, user.id)

        # فلود: رسائل كتير في وقت قصير
        stamps = _flood[key]
        stamps.append(now)
        if len(stamps) >= 8 and now - stamps[0] < 8:
            stamps.clear()
            try:
                await context.bot.restrict_chat_member(
                    chat.id, user.id, LOCKED_PERMS,
                    until_date=datetime.now(timezone.utc) + timedelta(minutes=5),
                )
                await send(context.bot, chat.id, f"🚨 {mention(user)} اتكتم 5 دقايق بسبب الفلود 😂")
            except TelegramError:
                pass
            raise ApplicationHandlerStop

        # تكرار نفس الرسالة
        if text:
            norm = normalize(text)
            old_text, old_time, count = _repeat.get(key, ("", 0, 0))
            count = count + 1 if norm == old_text and now - old_time < 10 else 0
            _repeat[key] = (norm, now, count)
            if count >= 4:
                try:
                    await msg.delete()
                    await send(context.bot, chat.id, f"⚠️ {mention(user)} بلاش تكرار يا نجم 😂")
                except TelegramError:
                    pass
                raise ApplicationHandlerStop


def cleanup():
    now = time.time()
    for key in [k for k, v in _repeat.items() if now - v[1] > 60]:
        _repeat.pop(key, None)
    for key in [k for k, v in _flood.items() if not v or now - v[-1] > 60]:
        _flood.pop(key, None)