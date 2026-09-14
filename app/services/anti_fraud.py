import re
import random
from typing import Dict, Any, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.sms_template import SmsTemplate

# Visually identical Cyrillic <-> Latin homoglyphs (look 100% identical in all fonts, but have different byte values)
HOMOGLYPHS = {
    'а': 'a', 'е': 'e', 'о': 'o', 'р': 'p', 'с': 'c', 'у': 'y', 'х': 'x',
    'А': 'A', 'В': 'B', 'Е': 'E', 'К': 'K', 'М': 'M', 'Н': 'H', 'О': 'O',
    'Р': 'P', 'С': 'C', 'Т': 'T', 'Х': 'X'
}


def parse_spintax(text: str) -> str:
    """
    Parses nested Spintax format: {option1|option2|{sub1|sub2}}
    Preserves variable placeholders like {code}, {service} that do not contain a pipe '|'.
    """
    pattern = re.compile(r"\{([^{}]+)\}")
    while True:
        match = None
        for m in pattern.finditer(text):
            if "|" in m.group(1):
                match = m
                break
        if not match:
            break
        options = match.group(1).split("|")
        selected = random.choice(options)
        text = text[:match.start()] + selected + text[match.end():]
    return text


def apply_homoglyphs(text: str, rate: float = 0.30) -> str:
    """
    Randomly replaces eligible Cyrillic characters with visual Latin homoglyphs (e.g. 'В'->'B', 'а'->'a', 'о'->'o').
    The result looks 100% identical to the human eye, but changes the byte signature completely,
    preventing telecom carrier DPI anti-spam filters from matching known text templates.
    """
    if rate <= 0:
        return text

    res = []
    for ch in text:
        if ch in HOMOGLYPHS and random.random() < rate:
            res.append(HOMOGLYPHS[ch])
        else:
            res.append(ch)
    return "".join(res)


def render_template_string(
    template_str: str,
    variables: Dict[str, Any],
    add_noise: bool = False,
    use_homoglyphs: bool = True,
    homoglyph_rate: float = 0.30
) -> str:
    """
    1. Resolves Spintax {A|B|C}
    2. Protects variables/digits with placeholders
    3. Optionally substitutes Cyrillic characters with visually identical Latin homoglyphs
    4. Substitutes variables back
    5. Normalizes whitespace
    """
    # 1. Resolve Spintax
    resolved_spintax = parse_spintax(template_str)

    # 2. Protect variables with unique safe placeholders
    placeholders: Dict[str, Any] = {}
    protected_text = resolved_spintax

    for i, (key, value) in enumerate(variables.items()):
        token = f"__VAR_TOKEN_{i}__"
        placeholders[token] = str(value)
        # Replace {key} or {KEY}
        protected_text = re.sub(r"\{" + re.escape(key) + r"\}", token, protected_text, flags=re.IGNORECASE)

    # 3. Apply visual Latin homoglyphs to surrounding Russian words
    if use_homoglyphs and homoglyph_rate > 0:
        protected_text = apply_homoglyphs(protected_text, rate=homoglyph_rate)

    # 4. Restore variables exactly (digits in OTP code are untouched)
    rendered = protected_text
    for token, val in placeholders.items():
        rendered = rendered.replace(token, val)

    # 5. Clean up double spaces and normalize
    rendered = re.sub(r"[ \t]+", " ", rendered).strip()
    return rendered


async def get_random_template_for_category(
    db: AsyncSession,
    category: str = "auth"
) -> Optional[SmsTemplate]:
    """
    Selects an active template from the given category.
    Prioritizes templates with lower usage_count to balance rotation across templates.
    """
    stmt = (
        select(SmsTemplate)
        .where(SmsTemplate.category == category, SmsTemplate.is_active == True)
        .order_by(SmsTemplate.usage_count.asc())
        .limit(10)
    )
    result = await db.execute(stmt)
    candidates = result.scalars().all()
    if not candidates:
        return None

    selected = random.choice(candidates)
    selected.usage_count += 1
    await db.commit()
    return selected
