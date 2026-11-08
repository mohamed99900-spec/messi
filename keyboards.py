from telegram import InlineKeyboardButton as B
from telegram import InlineKeyboardMarkup as M


def home():
    return M([
        [B("🎮 الألعاب", callback_data="nav:games"), B("💰 محفظتي", callback_data="nav:bal")],
        [B("🏆 المتصدرون", callback_data="nav:top"), B("🧩 فزورة", callback_data="riddle")],
        [B("🤖 الذكاء الاصطناعي", callback_data="nav:ai"), B("📜 المساعدة", callback_data="nav:help")],
    ])


def games():
    return M([
        [B("🧠 سؤال", callback_data="quiz"), B("⚡ تحدي", callback_data="challenge")],
        [B("🧩 فزورة", callback_data="riddle"), B("🎲 نرد", callback_data="dice")],
        [B("✊ حجر ورقة مقص", callback_data="rps_menu"), B("📜 شعر", callback_data="poem")],
        [B("😂 نكتة", callback_data="joke"), B("🏠 الرئيسية", callback_data="nav:home")],
    ])


def back():
    return M([[B("🏠 الرئيسية", callback_data="nav:home")]])


def help_menu():
    return M([
        [B("🎮 الألعاب", callback_data="help:games"), B("💰 الاقتصاد", callback_data="help:econ")],
        [B("🛡️ الإدارة", callback_data="help:admin"), B("🤖 الذكاء", callback_data="help:ai")],
        [B("🏠 الرئيسية", callback_data="nav:home")],
    ])


def rps():
    return M([[
        B("✊ حجر", callback_data="rps:r"),
        B("✋ ورقة", callback_data="rps:p"),
        B("✌️ مقص", callback_data="rps:s"),
    ]])


def after_game(*extra):
    rows = [[B("🔁 سؤال جديد", callback_data="quiz"), B("⚡ تحدي", callback_data="challenge")]]
    rows.append([B("🏠 الرئيسية", callback_data="nav:home")])
    return M(rows)