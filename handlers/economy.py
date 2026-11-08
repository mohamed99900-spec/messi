import database
import keyboards
from registry import command
from utils import escape, fmt, mention, reply

MEDALS = ["🥇", "🥈", "🥉"]


async def build_balance(user):
    await database.ensure_user(user)
    row = await database.get_user(user.id)
    return (
        f"💰 <b>محفظة {escape(user.first_name)}</b>\n\n"
        f"🪙 الرصيد: <b>{fmt(row['balance'])}</b>\n"
        f"🏦 الخزنة: <b>{fmt(row['vault'])}</b>\n"
        f"⭐ المستوى: <b>{row['level']}</b> | ✨ {row['xp']} XP\n"
        f"🔥 سلسلة اليومي: {row['streak'] or 0} يوم\n"
        f"🏆 فوز: {row['wins']} | ❌ خسارة: {row['losses']}"
    )


async def build_top():
    rows = await database.top_users(10)
    if not rows:
        return "لسه مفيش لاعبين في الترتيب."
    lines = ["🏆 <b>أغنى 10 في إمبراطورية ميسي</b>\n"]
    for i, row in enumerate(rows):
        medal = MEDALS[i] if i < 3 else f"{i + 1}."
        lines.append(f"{medal} {escape(row['full_name'])} — <b>{fmt(row['total'])}</b> | مستوى {row['level']}")
    return "\n".join(lines)


def level_up_text(new_level):
    return f"\n🎉 مبروك! وصلت للمستوى <b>{new_level}</b>!" if new_level else ""


@command("رصيدي", "محفظتي", "فلوسي", "البنك", "balance", "bank")
async def cmd_balance(update, context, args):
    await reply(update, await build_balance(update.effective_user))


@command("يومي", "المكافأه اليوميه", "daily")
async def cmd_daily(update, context, args):
    user = update.effective_user
    await database.ensure_user(user)
    result = await database.claim_daily(user.id)
    if not result:
        await reply(update, "😂 يا عم استلمت مكافأتك النهارده! الخزنة مش ATM شغال 24 ساعة.")
        return
    reward, streak = result
    new_level = await database.add_xp(user.id, 20)
    await reply(
        update,
        f"🎁 <b>المكافأة اليومية وصلت!</b>\n\n"
        f"💰 +{fmt(reward)} نقطة\n✨ +20 خبرة\n🔥 سلسلة: {streak} يوم"
        f"{level_up_text(new_level)}\n\nارجع بكرة علشان السلسلة تكبر 😎",
    )


@command("المتصدرين", "الاغنياء", "توب", "top")
async def cmd_top(update, context, args):
    await reply(update, await build_top())


@command("مستواي", "مستوى", "خبرتي", "level")
async def cmd_level(update, context, args):
    user = update.effective_user
    await database.ensure_user(user)
    row = await database.get_user(user.id)
    remaining = row["level"] * 100 - row["xp"]
    await reply(
        update,
        f"⭐ <b>مستواك: {row['level']}</b>\n✨ خبرتك: {row['xp']} XP\n"
        f"📈 فاضل {max(0, remaining)} خبرة للمستوى الجاي.",
    )


@command("تحويل", "transfer", args=True)
async def cmd_transfer(update, context, args):
    user = update.effective_user
    msg = update.effective_message
    await database.ensure_user(user)

    usage = (
        "طريقة التحويل:\n"
        "بالرد على الشخص: <code>تحويل 100</code>\n"
        "أو: <code>تحويل 100 ايدي_المستلم</code>"
    )
    if not args or not args[0].isdigit():
        await reply(update, usage)
        return

    amount = int(args[0])
    receiver_id = None
    if msg.reply_to_message and msg.reply_to_message.from_user:
        target = msg.reply_to_message.from_user
        if target.is_bot:
            await reply(update, "مينفعش تحول لبوت 😂")
            return
        await database.ensure_user(target)
        receiver_id = target.id
    elif len(args) > 1:
        if args[1].isdigit():
            receiver_id = int(args[1])
        elif args[1].startswith("@"):
            found = await database.find_user_by_username(args[1])
            receiver_id = found["user_id"] if found else None

    if not receiver_id:
        await reply(update, usage)
        return
    if amount <= 0 or amount > 100000:
        await reply(update, "المبلغ لازم يكون بين 1 و100000.")
        return
    if receiver_id == user.id:
        await reply(update, "😂 هتحول لنفسك؟ إنت والمستلم شخص واحد!")
        return

    status = await database.transfer(user.id, receiver_id, amount)
    if status == "no_receiver":
        await reply(update, "المستخدم ده لازم يفتح البوت أو يكتب في الجروب الأول.")
    elif status == "no_funds":
        await reply(update, "❌ رصيدك مش كفاية.")
    else:
        await reply(update, f"✅ تم تحويل <b>{fmt(amount)}</b> نقطة للمستلم <code>{receiver_id}</code>.")


@command("ايداع", "deposit", args=True)
async def cmd_deposit(update, context, args):
    await _vault(update, args, 1)


@command("سحب", "withdraw", args=True)
async def cmd_withdraw(update, context, args):
    await _vault(update, args, -1)


async def _vault(update, args, sign):
    user = update.effective_user
    await database.ensure_user(user)
    if not args or not args[0].isdigit() or int(args[0]) <= 0:
        await reply(update, "اكتب المبلغ، مثال: <code>ايداع 500</code>")
        return
    result = await database.vault_move(user.id, sign * int(args[0]))
    if not result:
        await reply(update, "❌ الرصيد أو الخزنة مش كفاية للعملية دي.")
        return
    balance, vault = result
    await reply(update, f"🏦 تمت العملية.\n🪙 الرصيد: {fmt(balance)}\n🏦 الخزنة: {fmt(vault)}")