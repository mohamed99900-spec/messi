import random
import time
import uuid

import ai
import content
import database
import keyboards
from handlers.economy import level_up_text
from registry import command
from utils import chunks, escape, fmt, md_to_html, mention, normalize, reply

quiz_sessions = {}
riddles = {}
challenges = {}
_dice_last = {}

SLOT_SYMBOLS = ["🍒", "🍋", "🍉", "⭐", "7️⃣", "💎"]


def cleanup():
    now = time.time()
    for sid in [k for k, v in quiz_sessions.items() if now - v["created"] > 180]:
        quiz_sessions.pop(sid, None)
    for cid in [k for k, v in riddles.items() if now - v["time"] > 600]:
        riddles.pop(cid, None)
    for cid in [k for k, v in challenges.items() if now > v["expires"]]:
        challenges.pop(cid, None)
    for uid in [k for k, v in _dice_last.items() if now - v > 600]:
        _dice_last.pop(uid, None)


async def reward(user, coins, xp, won=True):
    await database.change_balance(user.id, coins, "game")
    new_level = await database.add_xp(user.id, xp)
    await database.record_result(user.id, won)
    return level_up_text(new_level)


# ---------------- قايمة الألعاب ----------------

@command("لعبه", "العاب", "games")
async def cmd_game(update, context, args):
    await reply(
        update,
        "🎮 <b>صالة ألعاب ميسي</b>\nاختار اللعبة:",
        reply_markup=keyboards.games(),
    )


# ---------------- الأسئلة ----------------

async def send_question(message, chat_type_private):
    question, options, correct, category, explanation = random.choice(content.QUESTIONS)
    indexed = list(enumerate(options))
    random.shuffle(indexed)
    new_correct = [i for i, (old, _) in enumerate(indexed) if old == correct][0]

    sid = uuid.uuid4().hex[:8]
    quiz_sessions[sid] = {
        "correct": new_correct,
        "explanation": explanation,
        "tried": set(),
        "private": chat_type_private,
        "created": time.time(),
    }

    from telegram import InlineKeyboardButton as B
    from telegram import InlineKeyboardMarkup as M
    rows = [[B(f"{n + 1}️⃣ {text}", callback_data=f"qa:{sid}:{n}")] for n, (_, text) in enumerate(indexed)]
    rows.append([B("❌ إلغاء", callback_data=f"qx:{sid}")])

    await message.reply_text(
        f"🧠 <b>سؤال {escape(category)}</b>\n\n❓ {escape(question)}\n\n"
        "أول واحد يجاوب صح ياخد الجايزة 🏆",
        parse_mode="HTML",
        reply_markup=M(rows),
    )


@command("سؤال", "اختبرني", "اختبار", "quiz")
async def cmd_quiz(update, context, args):
    await database.ensure_user(update.effective_user)
    await send_question(update.effective_message, update.effective_chat.type == "private")


async def quiz_callback(query, data):
    from utils import safe_edit
    parts = data.split(":")
    user = query.from_user
    sid = parts[1] if len(parts) > 1 else ""
    session = quiz_sessions.get(sid)

    if parts[0] == "qx":
        quiz_sessions.pop(sid, None)
        await query.answer("اتلغى")
        await safe_edit(query, "تم إلغاء السؤال.")
        return

    if not session:
        await query.answer("السؤال خلص أو وقته انتهى ⏳", show_alert=True)
        return
    if user.id in session["tried"]:
        await query.answer("إنت جاوبت قبل كده! سيب غيرك يجرب 😂", show_alert=True)
        return

    await database.ensure_user(user)
    selected = int(parts[2])

    if selected == session["correct"]:
        quiz_sessions.pop(sid, None)
        extra = await reward(user, 100, 25, True)
        await query.answer("🎉 صح!")
        await safe_edit(
            query,
            f"🎉 <b>{mention(user)} جاوب صح يا أسطورة!</b>\n\n💰 +100 نقطة\n✨ +25 خبرة{extra}\n\n"
            f"💡 {escape(session['explanation'])}",
            keyboards.after_game(),
        )
        return

    session["tried"].add(user.id)
    await database.record_result(user.id, False)
    if session["private"]:
        quiz_sessions.pop(sid, None)
        await query.answer("❌ غلط", show_alert=False)
        await safe_edit(
            query,
            f"😅 إجابة غلط.\n\n💡 {escape(session['explanation'])}",
            keyboards.after_game(),
        )
    else:
        await query.answer("❌ إجابة غلط! غيرك لسه يقدر يجاوب", show_alert=True)


# ---------------- التحديات ----------------

def make_challenge():
    kind = random.choice(["math", "scramble", "type"])
    if kind == "math":
        a, b = random.randint(11, 99), random.randint(2, 30)
        op = random.choice(["+", "-", "×"])
        result = a + b if op == "+" else a - b if op == "-" else a * b
        return "⚡ تحدي الحساب", f"كم يساوي <b>{a} {op} {b}</b> ؟", str(result)
    if kind == "scramble":
        word = random.choice(content.SCRAMBLE_WORDS)
        letters = list(word)
        for _ in range(10):
            random.shuffle(letters)
            if "".join(letters) != word:
                break
        return "🔤 تحدي ترتيب الحروف", f"رتّب الحروف دي لكلمة: <b>{' - '.join(letters)}</b>", word
    phrase = random.choice(content.TYPING_PHRASES)
    return "⌨️ تحدي الكتابة السريعة", f"اكتب الجملة دي بالظبط:\n<b>{escape(phrase)}</b>", phrase


@command("تحدي", "تحدى", "تحديات", "challenge")
async def cmd_challenge(update, context, args):
    await database.ensure_user(update.effective_user)
    await start_challenge(update.effective_message)


async def start_challenge(message):
    title, text, answer = make_challenge()
    challenges[message.chat_id] = {"answer": answer, "expires": time.time() + 30}
    await message.reply_text(
        f"<b>{title}</b>\n\n{text}\n\n⏱ معاك 30 ثانية! أول واحد يكتب الإجابة صح ياخد 150 نقطة 🏆",
        parse_mode="HTML",
    )


# ---------------- الفزاير ----------------

def build_riddle(chat_id):
    question, answers = random.choice(content.RIDDLES)
    riddles[chat_id] = {"answers": answers, "time": time.time()}
    return (
        f"🧩 <b>فزورة ميسي</b>\n\n❓ {escape(question)}\n\n"
        "اكتب الإجابة في الشات! أو اكتب <code>حل الفزوره</code> لو استسلمت 😂"
    )


@command("فزوره", "لغز", "الغاز", "riddle")
async def cmd_riddle(update, context, args):
    await database.ensure_user(update.effective_user)
    await reply(update, build_riddle(update.effective_chat.id))


@command("حل الفزوره", "الحل")
async def cmd_riddle_answer(update, context, args):
    session = riddles.pop(update.effective_chat.id, None)
    if not session:
        await reply(update, "مفيش فزورة شغالة دلوقتي. اكتب: فزوره")
        return
    await reply(update, f"💡 الحل هو: <b>{escape(session['answers'][0])}</b>\nمتزعلش، كانت عاملة نفسها صعبة 😂")


def _matches(norm_text, answers):
    for answer in answers:
        a = normalize(answer)
        bare = a[2:] if a.startswith("ال") else a
        if norm_text in (a, bare):
            return True
        if len(norm_text.split()) <= 3 and (a in norm_text or bare == norm_text):
            return True
    return False


async def check_chat_answer(update, context, text):
    """يتحقق لو الرسالة العادية إجابة صح لفزورة أو تحدي شغال في الشات."""
    chat_id = update.effective_chat.id
    user = update.effective_user
    norm = normalize(text)
    now = time.time()

    challenge = challenges.get(chat_id)
    if challenge:
        if now > challenge["expires"]:
            challenges.pop(chat_id, None)
        elif norm == normalize(challenge["answer"]):
            challenges.pop(chat_id, None)
            extra = await reward(user, 150, 30, True)
            await reply(update, f"🏆 <b>{mention(user)}</b> كسب التحدي! 💰 +150 نقطة ✨ +30 خبرة{extra}")
            return True

    riddle = riddles.get(chat_id)
    if riddle and now - riddle["time"] < 600 and _matches(norm, riddle["answers"]):
        riddles.pop(chat_id, None)
        extra = await reward(user, 80, 20, True)
        await reply(update, f"🎉 <b>{mention(user)}</b> حلّ الفزورة! 💰 +80 نقطة ✨ +20 خبرة{extra}")
        return True

    return False


# ---------------- ألعاب الحظ ----------------

async def build_dice(user):
    now = time.time()
    if now - _dice_last.get(user.id, 0) < 60:
        wait = int(60 - (now - _dice_last[user.id]))
        return f"🎲 النرد محتاج يستريح! جرب بعد {wait} ثانية 😂"
    _dice_last[user.id] = now
    result = random.randint(1, 6)
    coins = result * 10
    await database.change_balance(user.id, coins, "dice")
    new_level = await database.add_xp(user.id, 5)
    return (
        f"🎲 النرد وقف على: <b>{result}</b>\n🎁 مكافأتك: <b>{coins}</b> نقطة ✨ +5 خبرة"
        f"{level_up_text(new_level)}"
    )


@command("نرد", "ارم النرد", "dice")
async def cmd_dice(update, context, args):
    user = update.effective_user
    await database.ensure_user(user)
    await reply(update, await build_dice(user))


def _bet(args, idx=0):
    if len(args) > idx and args[idx].isdigit():
        return int(args[idx])
    return None


@command("سلوت", "slots", args=True)
async def cmd_slots(update, context, args):
    user = update.effective_user
    await database.ensure_user(user)
    bet = _bet(args)
    if bet is None or not 10 <= bet <= 5000:
        await reply(update, "اكتب المراهنة بين 10 و5000، مثال: <code>سلوت 100</code>")
        return
    row = await database.get_user(user.id)
    if row["balance"] < bet:
        await reply(update, "❌ رصيدك مش كفاية للمراهنة دي.")
        return

    reels = [random.choice(SLOT_SYMBOLS) for _ in range(3)]
    distinct = len(set(reels))
    if distinct == 1:
        payout, verdict = bet * 10, "🎰 <b>جاكبوت!!</b>"
    elif distinct == 2:
        payout, verdict = int(bet * 1.5), "😎 <b>كسبت!</b>"
    else:
        payout, verdict = 0, "😅 خسرت المرة دي"

    await database.change_balance(user.id, payout - bet, "slots")
    await database.record_result(user.id, payout > bet)
    await reply(update, f"🎰 | {' | '.join(reels)} |\n\n{verdict}\nالمبلغ: <b>{fmt(payout - bet)}</b> نقطة")


@command("عمله", "coin", args=True)
async def cmd_coin(update, context, args):
    user = update.effective_user
    await database.ensure_user(user)
    bet = _bet(args)
    side = normalize(args[1]) if len(args) > 1 else ""
    if bet is None or side not in ("صوره", "كتابه") or not 10 <= bet <= 5000:
        await reply(update, "مثال: <code>عملة 100 صورة</code> (المراهنة 10–5000، صورة أو كتابة)")
        return
    result = random.choice(["صوره", "كتابه"])
    won = result == side
    new = await database.change_balance(user.id, bet if won else -bet, "coin")
    if new is None:
        await reply(update, "❌ رصيدك مش كفاية.")
        return
    await database.record_result(user.id, won)
    await reply(
        update,
        f"🪙 العملة وقعت على: <b>{'صورة' if result == 'صوره' else 'كتابة'}</b>\n"
        f"{'🎉 كسبت' if won else '😅 خسرت'} <b>{fmt(bet)}</b> نقطة",
    )


@command("حجر ورقه مقص", "حجر ورقة مقص", "rps")
async def cmd_rps(update, context, args):
    await reply(update, "✊✋✌️ <b>حجر ورقة مقص</b>\nاختار:", reply_markup=keyboards.rps())


async def rps_result(user, choice):
    names = {"r": "✊ حجر", "p": "✋ ورقة", "s": "✌️ مقص"}
    beats = {"r": "s", "p": "r", "s": "p"}
    bot_choice = random.choice(list(names))
    await database.ensure_user(user)
    if choice == bot_choice:
        verdict = "🤝 تعادل!"
    elif beats[choice] == bot_choice:
        await database.change_balance(user.id, 20, "rps")
        await database.record_result(user.id, True)
        verdict = "🎉 كسبت! +20 نقطة"
    else:
        await database.record_result(user.id, False)
        verdict = "😅 خسرت! ميسي كسب"
    return f"إنت: {names[choice]}\nميسي: {names[bot_choice]}\n\n{verdict}"


# ---------------- ترفيه ----------------

def build_joke():
    return random.choice(content.JOKES)


@command("نكته", "اضحكني", "joke")
async def cmd_joke(update, context, args):
    await reply(update, build_joke())


@command("حكمه", "حكمة اليوم", "wisdom")
async def cmd_hikma(update, context, args):
    await reply(update, f"💡 <b>حكمة</b>\n\n{random.choice(content.HIKAM)}")


@command("ذكر", "اذكار", "azkar")
async def cmd_zekr(update, context, args):
    await reply(update, f"🕌 <b>ذكر</b>\n\n{random.choice(content.AZKAR)}")


def build_poem():
    title, text = random.choice(content.POEMS)
    return f"📜 <b>شعر — {escape(title)}</b>\n\n{escape(text)}"


@command("شعر", "قصيده", "poem", args=True)
async def cmd_poem(update, context, args):
    topic = args.raw.strip()
    if topic.startswith("عن "):
        topic = topic[3:].strip()
    if not topic:
        await reply(update, build_poem())
        return

    user = update.effective_user
    await database.ensure_user(user)
    try:
        await context.bot.send_chat_action(update.effective_chat.id, "typing")
        poem = await ai.ask(
            update.effective_chat.id, user.id,
            f"اكتب قصيدة قصيرة (6 أبيات) موزونة ومقفاة بالعامية المصرية عن: {topic[:200]}. "
            "اكتب القصيدة فقط بدون شرح.",
            remember=False,
        )
        for part in chunks(poem):
            await reply(update, "📜 " + md_to_html(part))
    except ai.AIError as exc:
        await reply(update, f"🤖 {escape(exc)}\n\nخد دي من عندي:\n\n{build_poem()}")
    except Exception:
        await reply(update, "😅 معرفتش أألف دلوقتي، جرب بعد شوية.")
