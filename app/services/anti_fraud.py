import re
import random
from typing import Dict, Any, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.sms_template import SmsTemplate


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


def render_template_string(template_str: str, variables: Dict[str, Any], add_noise: bool = False) -> str:
    """
    1. Resolves Spintax {A|B|C}
    2. Substitutes variables like {code}, {service}
    3. Normalizes whitespace so the text is 100% natural, clean and readable
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
