import asyncio
import logging
import random

from telegram.error import BadRequest, Forbidden, RetryAfter, TelegramError

import ai
import content
import database
from handlers import admin, chat, events, games
from utils import send

log = logging.getLogger("MESSI.jobs")


async def salawat_job(context):
    """كل ربع ساعة: تذكير بالصلاة على النبي ﷺ في كل الجروبات والقنوات المفعّلة."""
    for chat_id in await database.salawat_chats():
        text = f"🕌 <b>صلّوا على النبي ﷺ</b>\n\n{random.choice(content.SALAWAT)}"
        try:
            await send(context.bot, chat_id, text)
        except RetryAfter as exc:
            await asyncio.sleep(exc.retry_after + 1)
        except (Forbidden, BadRequest) as exc:
            log.warning("disabling salawat for %s: %s", chat_id, exc)
            await database.set_chat(chat_id, salawat=0)
        except TelegramError as exc:
            log.warning("salawat send failed for %s: %s", chat_id, exc)
        await asyncio.sleep(0.1)


async def cleanup_job(context):
    games.cleanup()
    admin.cleanup()
    events.cleanup()
    chat.cleanup()
    ai.cleanup()