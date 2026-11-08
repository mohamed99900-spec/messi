import logging

from telegram import BotCommand, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    ChatMemberHandler,
    MessageHandler,
    filters,
)

import ai
import database
import jobs
from config import BOT_TOKEN, GROQ_API_KEY, GROQ_MODEL, SALAWAT_INTERVAL
from handlers import events
from handlers.callbacks import callback_router
from handlers.chat import message_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("MESSI")


async def post_init(app):
    await database.init()
    me = await app.bot.get_me()
    log.info("MESSI BOT CONNECTED: @%s | ID=%s", me.username, me.id)
    await app.bot.set_my_commands([
        BotCommand("start", "ابدأ"),
        BotCommand("help", "المساعدة"),
        BotCommand("bank", "محفظتي"),
        BotCommand("daily", "المكافأة اليومية"),
        BotCommand("top", "المتصدرين"),
        BotCommand("quiz", "سؤال"),
        BotCommand("challenge", "تحدي"),
        BotCommand("riddle", "فزورة"),
        BotCommand("poem", "شعر"),
        BotCommand("joke", "نكتة"),
    ])


async def post_shutdown(app):
    await ai.close()
    await database.close()


async def error_handler(update, context):
    log.error("Unhandled exception", exc_info=context.error)


def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN مش موجود في ملف .env")
    if not GROQ_API_KEY:
        log.warning("GROQ_API_KEY ناقص. البوت هيشتغل بس الذكاء الاصطناعي لأ.")

    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .connect_timeout(30)
        .read_timeout(60)
        .write_timeout(30)
        .pool_timeout(30)
        .get_updates_connect_timeout(30)
        .get_updates_read_timeout(60)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .concurrent_updates(True)
        .build()
    )

    # مكافأة النشاط وتسجيل المستخدمين والجروبات
    app.add_handler(MessageHandler(filters.ALL & filters.UpdateType.MESSAGE, events.activity), group=-1)

    app.add_handler(CallbackQueryHandler(callback_router))
    app.add_handler(ChatMemberHandler(events.my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, events.welcome), group=0)

    # الحماية (بتوقف باقي المعالجة لو حذفت رسالة)
    app.add_handler(
        MessageHandler(
            (filters.TEXT | filters.CAPTION) & filters.ChatType.GROUPS & filters.UpdateType.MESSAGE,
            events.protection,
        ),
        group=1,
    )

    # أوامر القنوات
    app.add_handler(
        MessageHandler(filters.UpdateType.CHANNEL_POST & filters.TEXT, events.channel_post),
        group=2,
    )

    # الأوامر العربية + / + الذكاء الاصطناعي
    app.add_handler(
        MessageHandler(filters.TEXT & filters.UpdateType.MESSAGE, message_router),
        group=3,
    )

    app.add_error_handler(error_handler)

    if app.job_queue:
        app.job_queue.run_repeating(jobs.salawat_job, interval=SALAWAT_INTERVAL, first=60, name="salawat")
        app.job_queue.run_repeating(jobs.cleanup_job, interval=600, first=600, name="cleanup")
    else:
        log.warning("JobQueue مش متسطب. ثبّت: pip install 'python-telegram-bot[job-queue]'")

    log.info("MESSI BOT STARTING | MODEL=%s | SALAWAT every %ss", GROQ_MODEL, SALAWAT_INTERVAL)
    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
        bootstrap_retries=-1,
    )


if __name__ == "__main__":
    main()