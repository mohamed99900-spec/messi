import logging
import time

import httpx

from config import AI_HISTORY_LIMIT, DEVELOPER, GROQ_API_KEY, GROQ_MODEL

log = logging.getLogger("MESSI.ai")


class AIError(Exception):
    pass


SYSTEM_PROMPT = f"""
أنت "ميسي بوت" ⚽ — بوت تيليجرام مصري ذكي وقوي وخفيف الظل.

الهوية:
- مطورك ومبتكرك هو "{DEVELOPER}". لو أي حد سألك مين صنعك أو طورك أو برمجك، قول بفخر إنه {DEVELOPER}.
- لو سألوك عن تقنية الذكاء الاصطناعي اللي بتشتغل بيها، قول إنك بتعتمد على نموذج لغوي ذكي، ومتألفش أسماء.

الأسلوب:
- اتكلم بالعامية المصرية البسيطة دايماً، إلا لو المستخدم طلب لغة تانية أو فصحى.
- جاوب على السؤال بوضوح الأول، وبعدين ضيف لمسة كوميدية خفيفة لو مناسبة بدون إهانة.
- متكررش التحية في كل رد، وخلي الردود في الجروبات مختصرة نسبياً.
- في الدراسة والرياضيات والعلوم والبرمجة اشرح خطوة بخطوة بشكل مبسط.
- لو طُلب منك شعر، اكتب شعر حقيقي موزون ومقفى بالعامية المصرية أو الفصحى حسب الطلب.
- احترم الدين والناس، ومتكتبش محتوى مسيء أو ضار أو جنسي.

الصدق:
- لو مش عارف، اعترف. متدّعيش إنك نفذت حاجة معملتهاش.
- أوامر الإدارة (كتم، طرد، حظر...) بتتنفذ بأوامر البوت نفسها بصلاحيات المشرفين، مش بالكلام معاك.
"""

_client = None
_histories = {}  # key -> [timestamp, messages]


def _get_client():
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=20, read=60, write=30, pool=20)
        )
    return _client


async def close():
    if _client:
        await _client.aclose()


def cleanup(max_age=2 * 3600):
    now = time.time()
    for key in [k for k, v in _histories.items() if now - v[0] > max_age]:
        _histories.pop(key, None)


async def ask(chat_id, user_id, prompt, user_name="", remember=True, extra_system=""):
    if not GROQ_API_KEY:
        raise AIError("مفتاح GROQ_API_KEY مش موجود في ملف .env")

    key = f"{chat_id}:{user_id}"
    history = _histories.get(key, [0, []])[1] if remember else []

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if user_name:
        messages.append({"role": "system", "content": f"اسم اللي بيكلمك: {user_name}"})
    if extra_system:
        messages.append({"role": "system", "content": extra_system})
    messages.extend(history[-AI_HISTORY_LIMIT:])
    messages.append({"role": "user", "content": prompt[:5000]})

    payload = {
        "model": GROQ_MODEL,
        "messages": messages,
        "max_tokens": 1500,
        "temperature": 0.8,
    }
    if GROQ_MODEL.startswith("openai/gpt-oss"):
        payload["reasoning_effort"] = "low"

    response = await _get_client().post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
        },
        json=payload,
    )

    code = response.status_code
    if code == 401:
        raise AIError("مفتاح Groq غلط أو اتلغى. راجع GROQ_API_KEY.")
    if code == 403:
        raise AIError("حساب Groq مالوش صلاحية على النموذج ده.")
    if code == 404:
        raise AIError(f"النموذج {GROQ_MODEL} مش متاح. راجع GROQ_MODEL في .env.")
    if code == 429:
        raise AIError("وصلنا لحد الطلبات في Groq مؤقتاً. استنى شوية وجرب.")
    if code >= 500:
        raise AIError("خدمة Groq فيها مشكلة مؤقتة. جرب بعد شوية.")
    if not response.is_success:
        log.error("Groq %s: %s", code, response.text[:400])
        raise AIError(f"Groq رفض الطلب (كود {code}).")

    try:
        answer = response.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError, ValueError):
        raise AIError("جه رد غريب من Groq. جرب تاني.")

    answer = (answer or "").strip()
    if not answer:
        raise AIError("النموذج رجّع رد فاضي. جرب تاني.")

    if remember:
        history = history + [
            {"role": "user", "content": prompt[:5000]},
            {"role": "assistant", "content": answer},
        ]
        _histories[key] = [time.time(), history[-AI_HISTORY_LIMIT:]]

    return answer[:8000]