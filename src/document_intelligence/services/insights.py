import json
import re
from typing import Any

INSIGHT_PRESETS = {
    "summary": (
        "Summarize the document. Return a JSON object with keys: "
        '"title", "purpose", "key_points" (list of strings), "conclusion".'
    ),
    "key_facts": (
        "Extract the most important facts. Return a JSON object with key "
        '"facts": a list of objects with "fact", "category" and "value".'
    ),
    "risks": (
        "Identify risks, liabilities, gaps and non-compliance concerns. Return a JSON "
        'object with key "risks": a list of objects with "risk", "severity" '
        '(low/medium/high) and "reason".'
    ),
    "obligations": (
        "List obligations, deadlines and responsibilities. Return a JSON object with "
        'key "obligations": a list of objects with "party", "obligation" and "deadline".'
    ),
    "action_items": (
        "List concrete action items. Return a JSON object with key "
        '"action_items": a list of objects with "action", "owner" and "due".'
    ),
}
CODE_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def parse_json_object(text: str) -> dict[str, Any]:
    """Extract the first valid JSON object from model output."""
    candidates = [match.group(1) for match in CODE_FENCE.finditer(text)] + [text]
    decoder = json.JSONDecoder()
    for candidate in candidates:
        for position, char in enumerate(candidate):
            if char != "{":
                continue
            try:
                value, _ = decoder.raw_decode(candidate[position:])
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                return value
    raise ValueError("Structured extraction did not return a JSON object.")
