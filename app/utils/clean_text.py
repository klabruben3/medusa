import re
from langdetect import detect_langs, DetectorFactory, LangDetectException

ABBREVIATIONS = {
    "dr.", "mr.", "mrs.", "ms.", "prof.", "sr.", "jr.",
    "inc.", "ltd.", "co.", "corp.",
    "vs.", "e.g.", "i.e.", "etc.", "al.",
    "u.s.", "u.k.", "u.n.", "u.s.a.",
    "no.", "vol.", "fig.", "pg.", "p.", "pp.",
    "st.", "ave.", "blvd.",
    "jan.", "feb.", "mar.", "apr.", "jun.", "jul.",
    "aug.", "sep.", "sept.", "oct.", "nov.", "dec.",
}

DetectorFactory.seed = 0

_COMMON_EN_WORDS = {
    "subject", "dear", "regards", "content", "conclusion", "email",
    "name", "surname", "student", "number", "reason", "title",
    "initials", "lecturer", "university",
}
_COMMON_AF_WORDS = {
    "onderwerp", "beste", "groete", "afsluiting", "inhoud", "e-pos",
    "naam", "van", "universiteitsnommer", "rede", "dosent", "voorletters",
    "studentenommer",
}

# Matches tight word/word pairs: letters/hyphens on each side, no surrounding
# spaces — e.g. "Onderwerp/Subject", "Beste/Dear". Deliberately excludes
# anything with a space next to the slash so it doesn't clash with the
# phrase-level " / " split.
_WORD_PAIR_RE = re.compile(r"\b([A-Za-z\-]+)/([A-Za-z\-]+)\b")


def _pick_english_token(a: str, b: str) -> str:
    a_lower, b_lower = a.lower(), b.lower()

    a_is_en = a_lower in _COMMON_EN_WORDS
    b_is_en = b_lower in _COMMON_EN_WORDS
    a_is_af = a_lower in _COMMON_AF_WORDS
    b_is_af = b_lower in _COMMON_AF_WORDS

    if a_is_en and not b_is_en:
        return a
    if b_is_en and not a_is_en:
        return b
    if a_is_af and not b_is_af:
        return b
    if b_is_af and not a_is_af:
        return a

    # Neither word is in the dictionary — try langdetect as a tiebreaker,
    # but don't trust it much on single tokens.
    try:
        a_langs = detect_langs(a)
        b_langs = detect_langs(b)
        a_en = a_langs[0].lang == "en"
        b_en = b_langs[0].lang == "en"
        if a_en and not b_en:
            return a
        if b_en and not a_en:
            return b
    except LangDetectException:
        pass

    # Still ambiguous — keep both rather than risk dropping real content.
    return f"{a}/{b}"


def resolve_word_pairs(text: str) -> str:
    """
    Collapses tight 'AfrikaansWord/EnglishWord' pairs down to just the
    English side wherever confidently identifiable, before phrase-level
    '/' splitting runs. Leaves ' / ' (spaced) separators untouched.
    """
    return _WORD_PAIR_RE.sub(
        lambda m: _pick_english_token(m.group(1), m.group(2)),
        text,
    )


def is_mid_sentence(text: str) -> bool:
    if "." not in text:
        return True

    lowered = text.lower()
    stripped = lowered.rstrip(",;:")
    if stripped in ABBREVIATIONS:
        return True

    if re.fullmatch(r"\d+\.\d*", text) or re.fullmatch(r"\d*\.\d+", text):
        return True

    if re.fullmatch(r"([A-Z]\.){1,}", text):
        return True

    return False


# Fragments that are mostly digits/codes/punctuation have no real language
# signal — langdetect will guess wildly on these, so let them through untested
# rather than risk dropping a phone number, room code, or email address.
_LOW_SIGNAL_RE = re.compile(r"^[\d\s\-.,()@/_:+]+$")
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE_RE = re.compile(r"\b\d{3}[-\s]?\d{3,4}[-\s]?\d{0,4}\b")
_TITLE_RE = re.compile(r"\b(Mr|Mrs|Ms|Dr|Prof)\b")


# --- Afrikaans blocklist ---
# Signal words that mean "definitely still Afrikaans" even if langdetect
# scores it ambiguous/short. Checked BEFORE langdetect — if any of these
# appear, reject outright regardless of confidence score.
_AF_SIGNAL_WORDS = {
    "kontakbesonderhede", "kommunikasiekanaal", "kommunikasie",
    "inligting", "studiegids", "dosente", "dosent", "studente",
    "student", "eksamen", "toets", "toetse", "geleentheid",
    "vraestel", "vraestelle", "punte", "punt", "nagesien",
    "aangedui", "onderstaande", "tabel", "gebruik", "moet",
    "kan", "nie", "geen", "gelees", "aangevul", "verantwoordelikheid",
    "afwesighede", "spreekure", "bywoning", "opdragte",
}

_AF_WORD_RE = re.compile(r"[a-zA-Zà-üÀ-Ü'-]+")


def _has_afrikaans_signal(text: str) -> bool:
    words = {w.lower() for w in _AF_WORD_RE.findall(text)}
    return not words.isdisjoint(_AF_SIGNAL_WORDS)


def is_english(text: str, min_confidence: float = 0.6) -> bool:
    text = text.strip()
    if len(text) < 3:
        return True

    if _has_afrikaans_signal(text):
        return False

    if _LOW_SIGNAL_RE.match(text):
        return True

    if _EMAIL_RE.search(text) or _PHONE_RE.search(text) or _TITLE_RE.search(text):
        return True

    try:
        results = detect_langs(text)
    except LangDetectException:
        return False

    top = results[0]
    return top.lang == "en" and top.prob >= min_confidence


def extract_english_portion(text: str, min_confidence: float = 0.6):
    text = text.strip()
    if not text:
        return None

    text = resolve_word_pairs(text)  # collapse word/word pairs first

    parts = [p.strip() for p in text.split("/") if p.strip()]
    if len(parts) <= 1:
        return text if is_english(text, min_confidence) else None

    english_parts = [p for p in parts if is_english(p, min_confidence)]
    if not english_parts:
        return None

    return " / ".join(english_parts) if len(english_parts) > 1 else english_parts[0]

# exports: is_mid_sentence, extract_english_portion
