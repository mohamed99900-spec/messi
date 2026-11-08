from utils import Args, normalize

COMMANDS = {}


def command(*names, args=False):
    """تسجيل أمر يعمل بالعربي بدون / ويعمل كـ /command كمان."""
    def deco(fn):
        for name in names:
            COMMANDS[normalize(name)] = (fn, args)
        return fn
    return deco


def resolve(text, bot_username=""):
    text = (text or "").strip()
    if not text:
        return None

    # أوامر السلاش: /mute أو /mute@botname
    if text.startswith("/"):
        parts = text[1:].split()
        if not parts:
            return None
        head = parts[0]
        if "@" in head:
            head, _, target = head.partition("@")
            if bot_username and target.lower() != bot_username.lower():
                return None
        entry = COMMANDS.get(normalize(head))
        if not entry:
            return None
        a = Args(parts[1:])
        a.raw = text.split(None, 1)[1] if len(text.split(None, 1)) > 1 else ""
        return entry[0], a

    words = text.split()
    norm = [normalize(w) for w in words]

    for n in (3, 2, 1):
        if len(words) < n:
            continue
        entry = COMMANDS.get(" ".join(norm[:n]))
        if not entry:
            continue
        fn, takes_args = entry
        if len(words) > n and not takes_args:
            continue
        a = Args(words[n:])
        pieces = text.split(None, n)
        a.raw = pieces[n] if len(pieces) > n else ""
        return fn, a

    return None