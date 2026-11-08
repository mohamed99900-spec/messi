import database
import keyboards
from config import DEVELOPER, OWNER_ID
from registry import command
from utils import escape, fmt, is_group_chat, mention, reply

HELP_PAGES = {
    "main": (
        "<blockquote>👑 <b>ميسي بوت — مركز التحكم</b></blockquote>\n\n"
        "كل الأوامر بتشتغل بالعربي من غير / وبـ / كمان.\n"
        "اختار القسم اللي عايزه من الأزرار 👇\n\n"
        f"👨‍💻 المطور: <b>{DEVELOPER}</b>"
    ),
    "games": (
        "<b>🎮 الألعاب</b>\n\n"
        "• <code>سؤال</code> — سؤال بأزرار (أول واحد يجاوب صح ياخد المكافأة)\n"
        "• <code>تحدي</code> — حساب / ترتيب حروف / كتابة سريعة\n"
        "• <code>فزوره</code> — اكتب الإجابة في الشات، و<code>حل الفزوره</code> للحل\n"
        "• <code>نرد</code> — نرد بمكافأة\n"
        "• <code>سلوت 100</code> — ماكينة الحظ\n"
        "• <code>عملة 100 صورة</code> — صورة أو كتابة\n"
        "• <code>حجر ورقه مقص</code>\n"
        "• <code>شعر</code> أو <code>شعر عن الحب</code> — شعر جاهز أو من الذكاء الاصطناعي\n"
        "• <code>نكته</code> — <code>حكمه</code> — <code>ذكر</code>"
    ),
    "econ": (
        "<b>💰 الاقتصاد</b>\n\n"
        "• <code>رصيدي</code> — محفظتك\n"
        "• <code>يومي</code> — مكافأة يومية + سلسلة أيام\n"
        "• <code>المتصدرين</code> — أغنى 10\n"
        "• <code>مستواي</code> — خبرتك\n"
        "• <code>تحويل 100</code> بالرد على الشخص، أو <code>تحويل 100 ايدي</code>\n"
        "• <code>ايداع 500</code> / <code>سحب 500</code> — الخزنة\n\n"
        "🎁 مكافأة نشاط تلقائية كل 15 دقيقة للأعضاء النشطين."
    ),
    "admin": (
        "<b>🛡️ الإدارة (للمشرفين)</b>\n\n"
        "بالرد على العضو: <code>كتم</code> أو <code>كتم 10د</code> (د/س/ي) — "
        "<code>فك كتم</code> — <code>طرد</code> — <code>حظر</code> — <code>تحذير</code> — "
        "<code>مسح تحذيرات</code> — <code>تحذيراتي</code>\n"
        "• <code>فك حظر ايدي</code>\n"
        "• <code>مسح</code> بالرد (يمسح لحد الرسالة) أو <code>مسح 20</code>\n"
        "• <code>تثبيت</code> / <code>الغاء تثبيت</code> بالرد\n"
        "• <code>رفع مشرف</code> / <code>تنزيل مشرف</code> (لمالك الجروب)\n"
        "• <code>قفل</code> / <code>فتح</code> الشات\n"
        "• <code>تفعيل</code> / <code>تعطيل</code> + (الترحيب، منع الروابط، منع التكرار، الصلاه، الذكاء)\n"
        "• <code>ضبط الترحيب نص</code> (فيه {name} و{group}) — <code>ضبط القوانين نص</code> — <code>القوانين</code>\n"
        "• <code>حد التحذيرات 3</code> — <code>اعدادات</code>\n\n"
        "<b>📢 القنوات</b>\n"
        "• ضيف البوت مشرف في القناة، واكتب فيها: <code>تفعيل الصلاه</code> لتذكير كل ربع ساعة.\n"
        "• من الجروب: <code>نشر @القناة النص</code> أو بالرد على رسالة <code>نشر @القناة</code>."
    ),
    "ai": (
        "<b>🤖 الذكاء الاصطناعي</b>\n\n"
        "• في الخاص: اكتب رسالتك على طول.\n"
        "• في الجروب: ناديني <code>يا ميسي</code> + سؤالك، أو منشن، أو رد على رسالتي.\n"
        "• اكتب <code>ميسي لخص</code> بالرد على أي رسالة وهلخصها.\n"
        "• أحل مسائل، أشرح دروس، أكتب كود، وأألف شعر. 😎"
    ),
}


@command("ابدأ", "start", "تشغيل")
async def cmd_start(update, context, args):
    user = update.effective_user
    await database.ensure_user(user)
    text = (
        f"👑 يا أهلاً يا {mention(user)}!\n\n"
        "أنا <b>ميسي بوت</b> ⚽😂 — لجنة الترفيه والبنك المركزي ومدير الجروب في نفس الوقت!\n\n"
        "🎮 اكتب <code>لعبه</code> للألعاب\n"
        "💰 اكتب <code>رصيدي</code> للمحفظة\n"
        "🤖 كلمني في الخاص أو ناديني <code>يا ميسي</code> في الجروب\n\n"
        f"👨‍💻 تطويري: <b>{DEVELOPER}</b>"
    )
    await reply(update, text, reply_markup=keyboards.home())


@command("مساعدة", "الاوامر", "اوامر", "help")
async def cmd_help(update, context, args):
    await reply(update, HELP_PAGES["main"], reply_markup=keyboards.help_menu())


@command("المطور", "مطور", "developer")
async def cmd_developer(update, context, args):
    await reply(update, f"👑 اللي طوّرني وبرمجني هو المبدع <b>{DEVELOPER}</b> ⚽🔥")


@command("ايدي", "id")
async def cmd_id(update, context, args):
    msg = update.effective_message
    target = msg.reply_to_message.from_user if msg.reply_to_message else update.effective_user
    text = f"🆔 ايدي {mention(target)}: <code>{target.id}</code>"
    if is_group_chat(update.effective_chat):
        text += f"\n💬 ايدي الجروب: <code>{update.effective_chat.id}</code>"
    await reply(update, text)


@command("معلومات", "info")
async def cmd_info(update, context, args):
    msg = update.effective_message
    target = msg.reply_to_message.from_user if msg.reply_to_message else update.effective_user
    await database.ensure_user(target)
    row = await database.get_user(target.id)
    if not row:
        await reply(update, "مش لاقي بيانات للعضو ده.")
        return
    username = f"@{escape(target.username)}" if target.username else "—"
    await reply(
        update,
        f"👤 <b>{mention(target)}</b>\n"
        f"🆔 <code>{target.id}</code>\n"
        f"🔗 {username}\n"
        f"⭐ المستوى: {row['level']} | ✨ {row['xp']} XP\n"
        f"🪙 الرصيد: {fmt(row['balance'])}\n"
        f"🏆 فوز: {row['wins']} | ❌ خسارة: {row['losses']}",
    )


@command("احصائيات", "status")
async def cmd_stats(update, context, args):
    from config import GROQ_API_KEY, GROQ_MODEL
    if not OWNER_ID or update.effective_user.id != OWNER_ID:
        await reply(update, "الأمر ده لمالك البوت بس 🔒")
        return
    users = await database.count_users()
    chats = await database.count_chats()
    ai = "مفعّل" if GROQ_API_KEY else "مفيش مفتاح"
    await reply(
        update,
        "📊 <b>حالة ميسي بوت</b>\n\n"
        f"👤 المستخدمين: {users}\n"
        f"💬 الجروبات والقنوات: {chats}\n"
        f"🤖 الذكاء: {ai}\n"
        f"🧠 النموذج: <code>{escape(GROQ_MODEL)}</code>",
    )