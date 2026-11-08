import database
import keyboards
from handlers import economy, games
from handlers.general import HELP_PAGES
from utils import safe_edit


async def callback_router(update, context):
    query = update.callback_query
    data = query.data or ""
    user = query.from_user
    message = query.message

    if data.startswith(("qa:", "qx:")):
        await games.quiz_callback(query, data)
        return

    await query.answer()
    await database.ensure_user(user)

    if data == "nav:home":
        await safe_edit(query, "👑 <b>القائمة الرئيسية لميسي بوت</b>\nاختار القسم:", keyboards.home())
    elif data == "nav:games":
        await safe_edit(query, "🎮 <b>صالة ألعاب ميسي</b>\nاختار اللعبة:", keyboards.games())
    elif data == "nav:bal":
        await safe_edit(query, await economy.build_balance(user), keyboards.back())
    elif data == "nav:top":
        await safe_edit(query, await economy.build_top(), keyboards.back())
    elif data == "nav:help":
        await safe_edit(query, HELP_PAGES["main"], keyboards.help_menu())
    elif data == "nav:ai":
        await safe_edit(
            query,
            HELP_PAGES["ai"],
            keyboards.back(),
        )
    elif data.startswith("help:"):
        page = data.split(":", 1)[1]
        await safe_edit(query, HELP_PAGES.get(page, HELP_PAGES["main"]), keyboards.help_menu())
    elif data == "quiz":
        await games.send_question(message, message.chat.type == "private")
    elif data == "challenge":
        await games.start_challenge(message)
    elif data == "riddle":
        await safe_edit(query, games.build_riddle(message.chat_id), keyboards.games())
    elif data == "dice":
        await safe_edit(query, await games.build_dice(user), keyboards.games())
    elif data == "joke":
        await safe_edit(query, games.build_joke(), keyboards.games())
    elif data == "poem":
        await safe_edit(query, games.build_poem(), keyboards.games())
    elif data == "rps_menu":
        await safe_edit(query, "✊✋✌️ <b>حجر ورقة مقص</b>\nاختار:", keyboards.rps())
    elif data.startswith("rps:"):
        text = await games.rps_result(user, data.split(":", 1)[1])
        await safe_edit(query, text, keyboards.rps())