import re
import random
from typing import Dict, Any, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.sms_template import SmsTemplate

# Zero-width invisible Unicode characters (completely invisible to human eye, unique byte sequence to carrier DPI)
# \u200B - Zero-Width Space
# \u200C - Zero-Width Non-Joiner
# \u2060 - Word Joiner
# \uFEFF - Zero-Width No-Break Space
ZERO_WIDTH_CHARS = ["\u200B", "\u200C", "\u2060", "\uFEFF"]


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


def inject_invisible_antifraud_entropy(text: str) -> str:
    """
    Injects 2-4 invisible zero-width Unicode characters into text words or whitespace.
    CRITICAL: Never touches digits (to preserve 100% copy-paste / OTP autofill compatibility).
    
    Visually for the user: looks 100% clean and natural, without any weird tags or noise.
    For the telecom carrier DPI filter: every single message has a completely unique byte sequence and SHA-256 hash!
    """
    safe_indices = [
        i for i in range(1, len(text))
        if not text[i-1].isdigit() and not text[i].isdigit()
    ]
    if not safe_indices:
        return text + random.choice(ZERO_WIDTH_CHARS)

    count = min(len(safe_indices), random.randint(2, 4))
    chosen_positions = sorted(random.sample(safe_indices, count), reverse=True)

    chars = list(text)
    for pos in chosen_positions:
        chars.insert(pos, random.choice(ZERO_WIDTH_CHARS))
    return "".join(chars)


def render_template_string(template_str: str, variables: Dict[str, Any], add_noise: bool = True) -> str:
    """
    1. Resolves Spintax {A|B|C}
    2. Substitutes variables like {code}, {service}, {time}
    3. Injects invisible zero-width entropy to foil telecom anti-spam hash matching
    """
    resolved_spintax = parse_spintax(template_str)

    # Replace variables case-insensitively or formatted
    rendered = resolved_spintax
    for key, value in variables.items():
        placeholder = "{" + key + "}"
        rendered = rendered.replace(placeholder, str(value))
        rendered = rendered.replace("{" + key.upper() + "}", str(value))

    # Clean up double spaces and normalize
    rendered = re.sub(r"[ \t]+", " ", rendered).strip()

    if add_noise:
        rendered = inject_invisible_antifraud_entropy(rendered)

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
