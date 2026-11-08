import os
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b").strip()
OWNER_ID = int(os.getenv("BOT_OWNER_ID", "0") or 0)

DB_PATH = BASE_DIR / "data" / "messi.sqlite3"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

BOT_NAME = "ميسي بوت"
DEVELOPER = "محمد فرج"
TZ = ZoneInfo("Africa/Cairo")

ACTIVITY_REWARD_SECONDS = 15 * 60
ACTIVITY_REWARD_MIN = 100
ACTIVITY_REWARD_MAX = 200

DAILY_MIN = 500
DAILY_MAX = 1000

SALAWAT_INTERVAL = 15 * 60  # كل ربع ساعة

AI_USER_COOLDOWN = 4
AI_GROUP_COOLDOWN = 2
AI_HISTORY_LIMIT = 12