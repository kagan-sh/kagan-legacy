from __future__ import annotations


def fuzzy_match(pattern: str, text: str) -> bool:
    lower_text = text.casefold()
    pos = 0
    for ch in pattern.casefold():
        idx = lower_text.find(ch, pos)
        if idx < 0:
            return False
        pos = idx + 1
    return True
