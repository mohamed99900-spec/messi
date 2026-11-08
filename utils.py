import html
import logging
import re

from telegram import LinkPreviewOptions
from telegram.constants import ChatType, ParseMode
from telegram.error import BadRequest

log = logging.getLogger("MESSI.utils")

_DIACRITICS = re.compile(r"[\u064B-\u065F\u0670\u0640]")
_LETTERS = str.maketrans({
    "أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي",
    "ة": "ه", "ؤ": "و", "ئ": "ي",
})
_DIGITS = str.maketrans(
    "٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹",
    "01234567890123456789",
)
_NO_PREVIEW = LinkPreviewOptions(is_disabled=True)


class Args(list):
    """قائمة كلمات الأمر + النص الخام بعد الأمر (raw)."""
    raw = ""


def normalize(value):
    value = (value or "").strip().lower()
    value = _DIACRITICS.sub("", value)
    value = value.translate(_LETTERS).translate(_DIGITS)
    return re.sub(r"\s+", " ", value)


def escape(value):
    return html.escape(str(value if value is not None else ""))


def mention(user):
    name = escape(user.full_name or "صديق")
    return f'<a href="tg://user?id={user.id}">{name}</a>'


def mention_id(user_id, name="العضو"):
    return f'<a href="tg://user?id={user_id}">{escape(name)}</a>'


def is_group_chat(chat):
    return bool(chat) and chat.type in (ChatType.GROUP, ChatType.SUPERGROUP)


def fmt(n):
    return f"{int(n):,}"


def md_to_html(text):
    """تحويل Markdown بسيط (من الذكاء الاصطناعي) إلى HTML آمن لتيليجرام."""
    text = html.escape(text or "")
    blocks = []

    def stash(m):
        blocks.append(m.group(1).strip("\n"))
        return f"\x00{len(blocks) - 1}\x00"

    text = re.sub(r"```(?:\w+)?\n?(.*?)```", stash, text, flags=re.S)
    text = re.sub(r"`([^`\n]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text, flags=re.S)
    text = re.sub(r"^#{1,6}\s*(.+)$", r"<b>\1</b>", text, flags=re.M)
    text = re.sub(r"^\s*[-*]\s+", "• ", text, flags=re.M)

    for i, block in enumerate(blocks):
        text = text.replace(f"\x00{i}\x00", f"<pre>{block}</pre>")
    return text


def chunks(text, size=3800):
    text = text or ""
    out = []
    while len(text) > size:
        cut = text.rfind("\n", 0, size)
        if cut < size // 2:
            cut = size
        out.append(text[:cut])
        text = text[cut:].lstrip("\n")
    if text:
        out.append(text)
    return out or [""]


def _plain(text):
    return html.unescape(re.sub(r"<[^>]+>", "", text))


async def reply(update, text, **kwargs):
    msg = update.effective_message
    if not msg:
        return None
    try:
        return await msg.reply_text(
            text,
            parse_mode=ParseMode.HTML,
            link_preview_options=_NO_PREVIEW,
            **kwargs,
        )
    except BadRequest:
        try:
            kwargs.pop("reply_markup", None)
            return await msg.reply_text(_plain(text))
        except Exception:
            log.exception("reply fallback failed")
    except Exception:
        log.exception("reply failed")
    return None


async def send(bot, chat_id, text, **kwargs):
    try:
        return await bot.send_message(
            chat_id,
            text,
            parse_mode=ParseMode.HTML,
            link_preview_options=_NO_PREVIEW,
            **kwargs,
        )
    except BadRequest:
        return await bot.send_message(chat_id, _plain(text))


async def safe_edit(query, text, markup=None):
    try:
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=markup,
            link_preview_options=_NO_PREVIEW,
        )
    except BadRequest as exc:
        if "not modified" not in str(exc).lower():
            log.warning("edit failed: %s", exc)