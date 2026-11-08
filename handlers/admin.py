import logging
import re
import time
from datetime import datetime, timedelta, timezone

from telegram import ChatPermissions
from telegram.error import TelegramError

import database
from config import OWNER_ID
from registry import command
from utils import escape, is_group_chat, mention, mention_id, normalize, reply, send

log = logging.getLogger("MESSI.admin")

OPEN_PERMS = ChatPermissions(
    can_send_messages=True, can_send_audios=True, can_send_documents=True,
    can_send_photos=True, can_send_videos=True, can_send_video_notes=True,
    can_send_voice_notes=True, can_send_polls=True, can_send_other_messages=True,
    can_add_web_page_previews=True, can_invite_users=True,
)
LOCKED_PERMS = ChatPermissions(
    can_send_messages=False, can_send_audios=False, can_send_documents=False,
    can_send_photos=False, can_send_videos=False, can_send_video_notes=False,
    can_send_voice_notes=False, can_send_polls=False, can_send_other_messages=False,
    can_add_web_page_previews=False,
)

_admin_cache = {}

SETTINGS = {
    "الترحيب": "welcome",
    "منع الروابط": "antilinks",
    "منع التكرار": "antispam",
    "الصلاه": "salawat",
    "الصلاه على النبي": "salawat",
    "الذكاء": "ai",
    "الذكاء الاصطناعي": "ai",
}
SETTING_NAMES = {
    "welcome": "الترحيب", "antilinks": "منع الروابط", "antispam": "منع التكرار",
    "salawat": "تذكير الصلاة على النبي", "ai": "الذكاء الاصطناعي",
}

_UNITS = {
    "د": 60, "دقيقه": 60, "m": 60,
    "س": 3600, "ساعه": 3600, "h": 3600,
    "ي": 86400, "يوم": 86400, "d": 86400,
}


def cleanup():
    now = time.time()
    for key in [k for k, v in _admin_cache.items() if now - v[0] > 120]:
        _admin_cache.pop(key, None)


async def is_admin_user(context, chat_id, user_id):
    if OWNER_ID and user_id == OWNER_ID:
        return True
    key = (chat_id, user_id)
    hit = _admin_cache.get(key)
    now = time.time()
    if hit and now - hit[0] < 60:
        return hit[1]
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        ok = member.status in ("administrator", "creator")
    except TelegramError:
        ok = False
    _admin_cache[key] = (now, ok)
    return ok


async def guard(update, context):
    """يتأكد إن الأمر في جروب ومن مشرف."""
    if not is_group_chat(update.effective_chat):
        await reply(update, "الأمر ده للجروبات بس 👥")
        return False
    if not await is_admin_user(context, update.effective_chat.id, update.effective_user.id):
        await reply(update, "❌ الأمر ده للمشرفين بس.")
        return False
    return True


async def resolve_target(update, args):
    msg = update.effective_message
    if msg.reply_to_message and msg.reply_to_message.from_user:
        u = msg.reply_to_message.from_user
        return u.id, mention(u), u
    for token in args:
        if token.startswith("@"):
            found = await database.find_user_by_username(token)
            if found:
                return found["user_id"], mention_id(found["user_id"], found["full_name"]), None
        elif token.lstrip("-").isdigit() and len(token) >= 6:
            return int(token), f"<code>{token}</code>", None
    return None


async def validate_target(update, context, target_id, user_obj):
    if user_obj and user_obj.is_bot:
        await reply(update, "مش هقدر أنفذ الأمر على بوت 🤖")
        return False
    if target_id == update.effective_user.id:
        await reply(update, "مينفعش تنفذ الأمر على نفسك 😂")
        return False
    if target_id == context.bot.id:
        await reply(update, "إنت بتجرب تطردني؟ 😂")
        return False
    if await is_admin_user(context, update.effective_chat.id, target_id):
        await reply(update, "مينفعش تنفذ الأمر ده على مشرف.")
        return False
    return True


def parse_duration(args):
    for token in args:
        m = re.fullmatch(r"(\d+)([^\d\s]+)", normalize(token))
        if m and m.group(2) in _UNITS:
            return int(m.group(1)) * _UNITS[m.group(2)]
    return None


async def _run(update, context, args, action):
    if not await guard(update, context):
        return
    target = await resolve_target(update, args)
    if not target:
        await reply(update, "❗ لازم ترد على رسالة العضو بالأمر (أو تكتب ايديه).")
        return
    target_id, label, user_obj = target
    if action != "unban" and not await validate_target(update, context, target_id, user_obj):
        return

    chat_id = update.effective_chat.id
    try:
        if action == "mute":
            seconds = parse_duration(args)
            kwargs = {}
            note = "لحد ما يتفك الكتم"
            if seconds:
                kwargs["until_date"] = datetime.now(timezone.utc) + timedelta(seconds=seconds)
                note = f"لمدة {seconds // 60} دقيقة"
            await context.bot.restrict_chat_member(chat_id, target_id, LOCKED_PERMS, **kwargs)
            text = f"🔇 تم كتم {label} {note}."
        elif action == "unmute":
            await context.bot.restrict_chat_member(chat_id, target_id, OPEN_PERMS)
            text = f"🔊 تم فك كتم {label}."
        elif action == "ban":
            await context.bot.ban_chat_member(chat_id, target_id)
            text = f"⛔ تم حظر {label}."
        elif action == "unban":
            await context.bot.unban_chat_member(chat_id, target_id, only_if_banned=True)
            text = f"✅ تم فك الحظر عن {label}."
        elif action == "kick":
            await context.bot.ban_chat_member(chat_id, target_id)
            await context.bot.unban_chat_member(chat_id, target_id)
            text = f"👢 تم طرد {label}."
        elif action == "warn":
            chat = await database.get_chat(chat_id)
            count = await database.add_warn(chat_id, target_id)
            limit = chat["max_warns"]
            text = f"⚠️ تم تحذير {label}. التحذيرات: <b>{count}/{limit}</b>"
            if count >= limit:
                await context.bot.restrict_chat_member(
                    chat_id, target_id, LOCKED_PERMS,
                    until_date=datetime.now(timezone.utc) + timedelta(days=1),
                )
                await database.clear_warns(chat_id, target_id)
                text += "\n🔇 وصل للحد الأقصى، اتكتم 24 ساعة."
        elif action == "unwarn":
            await database.clear_warns(chat_id, target_id)
            text = f"✅ اتمسحت تحذيرات {label}."
        else:
            return
        await reply(update, text)
    except TelegramError as exc:
        log.warning("moderation %s failed: %s", action, exc)
        await reply(update, "❌ فشل التنفيذ. اتأكد إن البوت مشرف وعنده الصلاحيات المطلوبة.")


@command("كتم", "mute", args=True)
async def cmd_mute(update, context, args):
    await _run(update, context, args, "mute")


@command("فك كتم", "الغاء الكتم", "unmute", args=True)
async def cmd_unmute(update, context, args):
    await _run(update, context, args, "unmute")


@command("طرد", "kick", args=True)
async def cmd_kick(update, context, args):
    await _run(update, context, args, "kick")


@command("حظر", "ban", args=True)
async def cmd_ban(update, context, args):
    await _run(update, context, args, "ban")


@command("فك حظر", "الغاء الحظر", "unban", args=True)
async def cmd_unban(update, context, args):
    await _run(update, context, args, "unban")


@command("تحذير", "انذار", "warn", args=True)
async def cmd_warn(update, context, args):
    await _run(update, context, args, "warn")


@command("مسح تحذيرات", "unwarn", args=True)
async def cmd_unwarn(update, context, args):
    await _run(update, context, args, "unwarn")


@command("تحذيراتي")
async def cmd_my_warns(update, context, args):
    if not is_group_chat(update.effective_chat):
        return
    chat = await database.get_chat(update.effective_chat.id)
    count = await database.get_warns(update.effective_chat.id, update.effective_user.id)
    await reply(update, f"⚠️ تحذيراتك: <b>{count}/{chat['max_warns']}</b>")


@command("مسح", "clear", args=True)
async def cmd_clear(update, context, args):
    if not await guard(update, context):
        return
    msg = update.effective_message
    chat_id = update.effective_chat.id
    if msg.reply_to_message:
        first = msg.reply_to_message.message_id
    elif args and args[0].isdigit():
        first = msg.message_id - min(int(args[0]), 100)
    else:
        await reply(update, "رد على أول رسالة عايز تمسح منها، أو اكتب: <code>مسح 20</code>")
        return
    ids = list(range(max(first, msg.message_id - 100), msg.message_id + 1))
    try:
        await context.bot.delete_messages(chat_id, ids)
    except TelegramError:
        await reply(update, "❌ معرفتش أمسح. اتأكد إن البوت مشرف وعنده صلاحية حذف الرسائل.")


@command("تثبيت", "pin")
async def cmd_pin(update, context, args):
    if not await guard(update, context):
        return
    target = update.effective_message.reply_to_message
    if not target:
        await reply(update, "رد على الرسالة اللي عايز تثبتها.")
        return
    try:
        await context.bot.pin_chat_message(update.effective_chat.id, target.message_id)
    except TelegramError:
        await reply(update, "❌ معرفتش أثبت. البوت محتاج صلاحية تثبيت الرسائل.")


@command("الغاء تثبيت", "unpin")
async def cmd_unpin(update, context, args):
    if not await guard(update, context):
        return
    target = update.effective_message.reply_to_message
    try:
        await context.bot.unpin_chat_message(
            update.effective_chat.id,
            message_id=target.message_id if target else None,
        )
    except TelegramError:
        await reply(update, "❌ معرفتش ألغي التثبيت.")


async def _is_creator(context, chat_id, user_id):
    if OWNER_ID and user_id == OWNER_ID:
        return True
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        return member.status == "creator"
    except TelegramError:
        return False


@command("رفع مشرف", "promote", args=True)
async def cmd_promote(update, context, args):
    await _set_admin(update, context, args, True)


@command("تنزيل مشرف", "demote", args=True)
async def cmd_demote(update, context, args):
    await _set_admin(update, context, args, False)


async def _set_admin(update, context, args, promote):
    if not is_group_chat(update.effective_chat):
        await reply(update, "الأمر ده للجروبات بس 👥")
        return
    chat_id = update.effective_chat.id
    if not await _is_creator(context, chat_id, update.effective_user.id):
        await reply(update, "❌ الأمر ده لمالك الجروب بس.")
        return
    target = await resolve_target(update, args)
    if not target:
        await reply(update, "❗ رد على رسالة العضو.")
        return
    target_id, label, _ = target
    try:
        await context.bot.promote_chat_member(
            chat_id, target_id,
            can_manage_chat=promote,
            can_delete_messages=promote,
            can_restrict_members=promote,
            can_pin_messages=promote,
            can_invite_users=promote,
        )
        _admin_cache.pop((chat_id, target_id), None)
        await reply(update, f"{'⭐ تم رفع' if promote else '⬇️ تم تنزيل'} {label} {'لمشرف' if promote else 'من الإشراف'}.")
    except TelegramError:
        await reply(update, "❌ فشل التنفيذ. البوت لازم يكون مشرف بصلاحية إضافة مشرفين.")


@command("قفل", "lock")
async def cmd_lock(update, context, args):
    if not await guard(update, context):
        return
    try:
        await context.bot.set_chat_permissions(update.effective_chat.id, LOCKED_PERMS)
        await reply(update, "🔒 تم قفل الشات.")
    except TelegramError:
        await reply(update, "❌ معرفتش أغير صلاحيات الجروب.")


@command("فتح", "unlock")
async def cmd_unlock(update, context, args):
    if not await guard(update, context):
        return
    try:
        await context.bot.set_chat_permissions(update.effective_chat.id, OPEN_PERMS)
        await reply(update, "🔓 تم فتح الشات.")
    except TelegramError:
        await reply(update, "❌ معرفتش أغير صلاحيات الجروب.")


@command("تفعيل", "enable", args=True)
async def cmd_enable(update, context, args):
    await _toggle(update, context, args, 1)


@command("تعطيل", "disable", args=True)
async def cmd_disable(update, context, args):
    await _toggle(update, context, args, 0)


async def _toggle(update, context, args, value):
    if not await guard(update, context):
        return
    key = SETTINGS.get(normalize(" ".join(args)))
    if not key:
        await reply(update, "الإعدادات المتاحة: الترحيب، منع الروابط، منع التكرار، الصلاه، الذكاء")
        return
    await database.set_chat(update.effective_chat.id, **{key: value})
    await reply(update, f"⚙️ تم {'تفعيل' if value else 'تعطيل'} {SETTING_NAMES[key]}.")


@command("اعدادات", "settings")
async def cmd_settings(update, context, args):
    if not await guard(update, context):
        return
    chat = await database.get_chat(update.effective_chat.id)
    lines = ["⚙️ <b>إعدادات الجروب</b>\n"]
    for key, name in SETTING_NAMES.items():
        lines.append(f"{'✅' if chat[key] else '❌'} {name}")
    lines.append(f"⚠️ حد التحذيرات: {chat['max_warns']}")
    await reply(update, "\n".join(lines))


@command("ضبط الترحيب", args=True)
async def cmd_set_welcome(update, context, args):
    if not await guard(update, context):
        return
    if not args.raw.strip():
        await reply(update, "اكتب نص الترحيب، تقدر تستخدم {name} و{group}.\nمثال: <code>ضبط الترحيب نورت يا {name} في {group}</code>")
        return
    await database.set_chat(update.effective_chat.id, welcome_text=args.raw.strip()[:500])
    await reply(update, "✅ تم ضبط رسالة الترحيب.")


@command("ضبط القوانين", args=True)
async def cmd_set_rules(update, context, args):
    if not await guard(update, context):
        return
    if not args.raw.strip():
        await reply(update, "اكتب القوانين بعد الأمر.")
        return
    await database.set_chat(update.effective_chat.id, rules=args.raw.strip()[:1500])
    await reply(update, "✅ تم حفظ القوانين.")


@command("القوانين", "rules")
async def cmd_rules(update, context, args):
    if not is_group_chat(update.effective_chat):
        return
    chat = await database.get_chat(update.effective_chat.id)
    if not chat["rules"]:
        await reply(update, "لسه مفيش قوانين متحددة للجروب.")
        return
    await reply(update, f"📜 <b>قوانين الجروب</b>\n\n{escape(chat['rules'])}")


@command("حد التحذيرات", args=True)
async def cmd_warn_limit(update, context, args):
    if not await guard(update, context):
        return
    if not args or not args[0].isdigit() or not 1 <= int(args[0]) <= 10:
        await reply(update, "اكتب رقم من 1 لـ 10، مثال: <code>حد التحذيرات 3</code>")
        return
    await database.set_chat(update.effective_chat.id, max_warns=int(args[0]))
    await reply(update, f"✅ حد التحذيرات بقى {args[0]}.")


@command("نشر", "publish", args=True)
async def cmd_publish(update, context, args):
    """نشر رسالة في قناة: نشر @القناة النص  أو بالرد على رسالة."""
    user = update.effective_user
    if not args:
        await reply(update, "مثال: <code>نشر @mychannel النص هنا</code> أو بالرد على رسالة: <code>نشر @mychannel</code>")
        return
    channel = args[0]
    if not (channel.startswith("@") or channel.lstrip("-").isdigit()):
        await reply(update, "اكتب يوزر القناة أو ايديها الأول، مثال: <code>نشر @mychannel النص</code>")
        return
    channel_id = channel if channel.startswith("@") else int(channel)

    try:
        member = await context.bot.get_chat_member(channel_id, user.id)
        allowed = member.status in ("administrator", "creator") or user.id == OWNER_ID
    except TelegramError:
        allowed = user.id == OWNER_ID
    if not allowed:
        await reply(update, "❌ لازم تكون مشرف في القناة دي علشان تنشر فيها.")
        return

    pieces = args.raw.split(None, 1)
    text = pieces[1].strip() if len(pieces) > 1 else ""
    msg = update.effective_message
    try:
        if text:
            await send(context.bot, channel_id, escape(text))
        elif msg.reply_to_message:
            await context.bot.copy_message(channel_id, update.effective_chat.id, msg.reply_to_message.message_id)
        else:
            await reply(update, "اكتب النص بعد اسم القناة أو رد على رسالة.")
            return
        await reply(update, "✅ تم النشر في القناة.")
    except TelegramError:
        await reply(update, "❌ معرفتش أنشر. اتأكد إن البوت مشرف في القناة وعنده صلاحية النشر.")


@command("اذاعه", "broadcast", args=True)
async def cmd_broadcast(update, context, args):
    import asyncio
    if not OWNER_ID or update.effective_user.id != OWNER_ID:
        await reply(update, "الأمر ده لمالك البوت بس 🔒")
        return
    text = args.raw.strip()
    if not text:
        await reply(update, "اكتب نص الإذاعة بعد الأمر.")
        return
    sent = failed = 0
    for chat_id in await database.all_chats():
        try:
            await send(context.bot, chat_id, f"📢 <b>إعلان</b>\n\n{escape(text)}")
            sent += 1
        except TelegramError:
            failed += 1
        await asyncio.sleep(0.1)
    await reply(update, f"📢 اتبعتت لـ {sent} شات، وفشلت في {failed}.")