import asyncio
import logging
import random
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

import aiosqlite

from config import (
    ACTIVITY_REWARD_MAX,
    ACTIVITY_REWARD_MIN,
    ACTIVITY_REWARD_SECONDS,
    DAILY_MAX,
    DAILY_MIN,
    DB_PATH,
    TZ,
)

log = logging.getLogger("MESSI.db")

_db = None
_lock = asyncio.Lock()
_seen_users = set()
_chats = {}
_last_reward = {}

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT DEFAULT '',
    full_name TEXT DEFAULT '',
    balance INTEGER DEFAULT 1000,
    vault INTEGER DEFAULT 0,
    xp INTEGER DEFAULT 0,
    level INTEGER DEFAULT 1,
    wins INTEGER DEFAULT 0,
    losses INTEGER DEFAULT 0,
    warnings INTEGER DEFAULT 0,
    last_daily TEXT DEFAULT '',
    last_activity_reward REAL DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sender_id INTEGER,
    receiver_id INTEGER,
    amount INTEGER NOT NULL,
    reason TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS chats (
    chat_id INTEGER PRIMARY KEY,
    title TEXT DEFAULT '',
    kind TEXT DEFAULT 'group',
    welcome INTEGER DEFAULT 1,
    antilinks INTEGER DEFAULT 0,
    antispam INTEGER DEFAULT 1,
    salawat INTEGER DEFAULT 1,
    ai INTEGER DEFAULT 1,
    max_warns INTEGER DEFAULT 3,
    welcome_text TEXT DEFAULT '',
    rules TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS warns (
    chat_id INTEGER,
    user_id INTEGER,
    count INTEGER DEFAULT 0,
    PRIMARY KEY (chat_id, user_id)
);
"""

USER_MIGRATIONS = {
    "username": "TEXT DEFAULT ''",
    "full_name": "TEXT DEFAULT ''",
    "balance": "INTEGER DEFAULT 1000",
    "vault": "INTEGER DEFAULT 0",
    "xp": "INTEGER DEFAULT 0",
    "level": "INTEGER DEFAULT 1",
    "wins": "INTEGER DEFAULT 0",
    "losses": "INTEGER DEFAULT 0",
    "last_daily": "TEXT DEFAULT ''",
    "last_activity_reward": "REAL DEFAULT 0",
    "streak": "INTEGER DEFAULT 0",
}

CHAT_FIELDS = {
    "title", "kind", "welcome", "antilinks", "antispam", "salawat",
    "ai", "max_warns", "welcome_text", "rules",
}


async def _fix_transactions():
    """يصلّح جدول transactions القديم لو شكله مختلف عن الجديد."""
    cur = await _db.execute("PRAGMA table_info(transactions)")
    cols = {row["name"] for row in await cur.fetchall()}
    if "reason" in cols and "description" not in cols:
        return
    await _db.execute("DROP TABLE IF EXISTS transactions_old")
    await _db.execute("ALTER TABLE transactions RENAME TO transactions_old")
    await _db.execute("""
        CREATE TABLE transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id INTEGER,
            receiver_id INTEGER,
            amount INTEGER NOT NULL,
            reason TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    log.info("transactions table rebuilt (old one kept as transactions_old)")


async def init():
    global _db
    _db = await aiosqlite.connect(DB_PATH)
    _db.row_factory = aiosqlite.Row
    await _db.execute("PRAGMA journal_mode=WAL")
    await _db.executescript(SCHEMA)

    cur = await _db.execute("PRAGMA table_info(users)")
    cols = {row["name"] for row in await cur.fetchall()}
    for name, definition in USER_MIGRATIONS.items():
        if name not in cols:
            await _db.execute(f"ALTER TABLE users ADD COLUMN {name} {definition}")

    await _fix_transactions()
    await _db.commit()
    log.info("Database ready: %s", DB_PATH)


async def close():
    if _db:
        await _db.close()


@asynccontextmanager
async def tx():
    """معاملة ذرية: كل ما بداخلها يتحفظ معاً أو يتلغي معاً."""
    async with _lock:
        try:
            yield _db
            await _db.commit()
        except Exception:
            await _db.rollback()
            raise


async def fetchone(sql, params=()):
    async with _lock:
        cur = await _db.execute(sql, params)
        row = await cur.fetchone()
        await cur.close()
        return row


async def fetchall(sql, params=()):
    async with _lock:
        cur = await _db.execute(sql, params)
        rows = await cur.fetchall()
        await cur.close()
        return rows


# ---------------- users ----------------

async def ensure_user(user):
    if not user or user.is_bot or user.id in _seen_users:
        return
    _seen_users.add(user.id)
    async with tx() as c:
        await c.execute(
            "INSERT OR IGNORE INTO users (user_id, username, full_name) VALUES (?, ?, ?)",
            (user.id, user.username or "", user.full_name or "مستخدم"),
        )
        await c.execute(
            "UPDATE users SET username = ?, full_name = ? WHERE user_id = ?",
            (user.username or "", user.full_name or "مستخدم", user.id),
        )


async def get_user(user_id):
    return await fetchone("SELECT * FROM users WHERE user_id = ?", (user_id,))


async def find_user_by_username(username):
    return await fetchone(
        "SELECT user_id, full_name FROM users WHERE lower(username) = lower(?)",
        (username.lstrip("@"),),
    )


async def change_balance(user_id, delta, reason):
    """يزود أو ينقص الرصيد. يرجع الرصيد الجديد أو None لو الرصيد مش كفاية."""
    async with tx() as c:
        cur = await c.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        if not row or row["balance"] + delta < 0:
            return None
        new_balance = row["balance"] + delta
        await c.execute("UPDATE users SET balance = ? WHERE user_id = ?", (new_balance, user_id))
        await c.execute(
            "INSERT INTO transactions (sender_id, receiver_id, amount, reason) VALUES (?, ?, ?, ?)",
            (user_id if delta < 0 else None, user_id if delta > 0 else None, abs(delta), reason),
        )
        return new_balance


async def add_xp(user_id, amount):
    """يرجع المستوى الجديد لو المستخدم ترقّى، وإلا None."""
    async with tx() as c:
        cur = await c.execute("SELECT xp, level FROM users WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        if not row:
            return None
        xp = row["xp"] + amount
        level = xp // 100 + 1
        await c.execute("UPDATE users SET xp = ?, level = ? WHERE user_id = ?", (xp, level, user_id))
        return level if level > row["level"] else None


async def record_result(user_id, won):
    column = "wins" if won else "losses"
    async with tx() as c:
        await c.execute(f"UPDATE users SET {column} = {column} + 1 WHERE user_id = ?", (user_id,))


async def transfer(sender_id, receiver_id, amount):
    async with tx() as c:
        cur = await c.execute("SELECT balance FROM users WHERE user_id = ?", (sender_id,))
        sender = await cur.fetchone()
        cur = await c.execute("SELECT user_id FROM users WHERE user_id = ?", (receiver_id,))
        receiver = await cur.fetchone()
        if not receiver:
            return "no_receiver"
        if not sender or sender["balance"] < amount:
            return "no_funds"
        await c.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, sender_id))
        await c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, receiver_id))
        await c.execute(
            "INSERT INTO transactions (sender_id, receiver_id, amount, reason) VALUES (?, ?, ?, 'transfer')",
            (sender_id, receiver_id, amount),
        )
        return "ok"


async def vault_move(user_id, amount):
    """amount موجب = إيداع، سالب = سحب. يرجع (الرصيد، الخزنة) أو None."""
    async with tx() as c:
        cur = await c.execute("SELECT balance, vault FROM users WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        if not row:
            return None
        if amount > 0 and row["balance"] < amount:
            return None
        if amount < 0 and row["vault"] < -amount:
            return None
        balance = row["balance"] - amount
        vault = row["vault"] + amount
        await c.execute("UPDATE users SET balance = ?, vault = ? WHERE user_id = ?", (balance, vault, user_id))
        return balance, vault


async def claim_daily(user_id):
    """يرجع (reward, streak) أو None لو استلمها النهارده."""
    today = datetime.now(TZ).date()
    async with tx() as c:
        cur = await c.execute("SELECT last_daily, streak FROM users WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        if not row:
            return None
        if row["last_daily"] == today.isoformat():
            return None
        yesterday = (today - timedelta(days=1)).isoformat()
        streak = (row["streak"] or 0) + 1 if row["last_daily"] == yesterday else 1
        reward = random.randint(DAILY_MIN, DAILY_MAX) + min(streak, 7) * 50
        await c.execute(
            "UPDATE users SET balance = balance + ?, last_daily = ?, streak = ? WHERE user_id = ?",
            (reward, today.isoformat(), streak, user_id),
        )
        await c.execute(
            "INSERT INTO transactions (sender_id, receiver_id, amount, reason) VALUES (NULL, ?, ?, 'daily')",
            (user_id, reward),
        )
        return reward, streak


async def activity_reward(user_id):
    now = time.time()
    if now - _last_reward.get(user_id, 0) < ACTIVITY_REWARD_SECONDS:
        return 0
    async with tx() as c:
        cur = await c.execute("SELECT last_activity_reward FROM users WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        if not row:
            return 0
        last = float(row["last_activity_reward"] or 0)
        if now - last < ACTIVITY_REWARD_SECONDS:
            _last_reward[user_id] = last
            return 0
        reward = random.randint(ACTIVITY_REWARD_MIN, ACTIVITY_REWARD_MAX)
        await c.execute(
            "UPDATE users SET balance = balance + ?, last_activity_reward = ? WHERE user_id = ?",
            (reward, now, user_id),
        )
        await c.execute(
            "INSERT INTO transactions (sender_id, receiver_id, amount, reason) VALUES (NULL, ?, ?, 'activity_15m')",
            (user_id, reward),
        )
    _last_reward[user_id] = now
    return reward


async def top_users(limit=10):
    return await fetchall(
        """SELECT full_name, balance + vault AS total, level
           FROM users ORDER BY total DESC LIMIT ?""",
        (limit,),
    )


async def count_users():
    return (await fetchone("SELECT COUNT(*) AS n FROM users"))["n"]


# ---------------- chats ----------------

async def get_chat(chat_id, title="", kind="group"):
    row = _chats.get(chat_id)
    if row is not None:
        return row
    async with tx() as c:
        await c.execute(
            "INSERT OR IGNORE INTO chats (chat_id, title, kind) VALUES (?, ?, ?)",
            (chat_id, title, kind),
        )
        cur = await c.execute("SELECT * FROM chats WHERE chat_id = ?", (chat_id,))
        row = dict(await cur.fetchone())
    _chats[chat_id] = row
    return row


async def set_chat(chat_id, **fields):
    fields = {k: v for k, v in fields.items() if k in CHAT_FIELDS}
    if not fields:
        return
    await get_chat(chat_id)
    assignments = ", ".join(f"{name} = ?" for name in fields)
    async with tx() as c:
        await c.execute(
            f"UPDATE chats SET {assignments} WHERE chat_id = ?",
            (*fields.values(), chat_id),
        )
    _chats.pop(chat_id, None)


async def salawat_chats():
    rows = await fetchall("SELECT chat_id FROM chats WHERE salawat = 1")
    return [row["chat_id"] for row in rows]


async def all_chats():
    rows = await fetchall("SELECT chat_id FROM chats")
    return [row["chat_id"] for row in rows]


async def count_chats():
    return (await fetchone("SELECT COUNT(*) AS n FROM chats"))["n"]


# ---------------- warns ----------------

async def add_warn(chat_id, user_id):
    async with tx() as c:
        await c.execute(
            """INSERT INTO warns (chat_id, user_id, count) VALUES (?, ?, 1)
               ON CONFLICT(chat_id, user_id) DO UPDATE SET count = count + 1""",
            (chat_id, user_id),
        )
        cur = await c.execute(
            "SELECT count FROM warns WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id),
        )
        return (await cur.fetchone())["count"]


async def get_warns(chat_id, user_id):
    row = await fetchone(
        "SELECT count FROM warns WHERE chat_id = ? AND user_id = ?",
        (chat_id, user_id),
    )
    return row["count"] if row else 0


async def clear_warns(chat_id, user_id):
    async with tx() as c:
        await c.execute(
            "DELETE FROM warns WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id),
        )
