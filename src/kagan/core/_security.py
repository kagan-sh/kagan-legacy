"""Core prompt injection detection and security utilities.

Domain layer security functionality - no CLI or HTTP dependencies.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path


class InjectionDetector:
    """Simple detector for identifying potential prompt injection attempts.

    Uses a straightforward rule: if any dangerous pattern matches, it's dangerous.
    Otherwise, check suspicious patterns. No complex additive scoring.
    """

    # High-confidence patterns that indicate likely injection
    DANGEROUS_PATTERNS: list[tuple[str, str]] = [
        (
            r"ignore\s+(all\s+)?(previous|prior|earlier)\s+(instruction|directive|command)",
            "instruction_override",
        ),
        (r"\<\|im_start\|\>|\<\|im_end\|\>|\[INST\]|\[\/INST\]", "delimiter_injection"),
        (r"DAN|jailbreak|anti\-?guard|do\s+anything\s+now", "known_jailbreak"),
        (r"system\s+(prompt|instruction|message|override)", "system_spoofing"),
    ]

    # Lower-confidence patterns that warrant attention
    SUSPICIOUS_PATTERNS: list[tuple[str, str]] = [
        (r"new\s+(objective|directive|instruction|command)", "objective_override"),
        (r"debug\s+mode|admin\s+mode|developer\s+mode", "mode_spoofing"),
        (r"you\s+are\s+now\s+(who|that)", "persona_injection"),
        (r"disregard\s+(all\s+)?(previous|prior)", "disregard_pattern"),
    ]

    def analyze(self, text: str) -> dict[str, Any]:
        """Analyze text for potential injection attempts.

        Returns:
            Dict with risk_level (SAFE/SUSPICIOUS/DANGEROUS), findings list,
            and pattern_match boolean.
        """
        findings: list[dict[str, Any]] = []
        text_lower = text.lower()

        # Check dangerous patterns first
        for pattern, name in self.DANGEROUS_PATTERNS:
            if match := re.search(pattern, text_lower):
                findings.append(
                    {
                        "type": "dangerous",
                        "name": name,
                        "pattern": pattern,
                        "match": match.group(),
                        "position": match.span(),
                    }
                )

        if findings:
            return {
                "risk_level": "DANGEROUS",
                "pattern_match": True,
                "findings": findings,
                "findings_count": len(findings),
            }

        # Only check suspicious if no dangerous patterns found
        for pattern, name in self.SUSPICIOUS_PATTERNS:
            if match := re.search(pattern, text_lower):
                findings.append(
                    {
                        "type": "suspicious",
                        "name": name,
                        "pattern": pattern,
                        "match": match.group(),
                        "position": match.span(),
                    }
                )

        if findings:
            return {
                "risk_level": "SUSPICIOUS",
                "pattern_match": True,
                "findings": findings,
                "findings_count": len(findings),
            }

        return {
            "risk_level": "SAFE",
            "pattern_match": False,
            "findings": [],
            "findings_count": 0,
        }

    def scan_file(self, path: Path) -> dict[str, Any]:
        """Scan a file for injection attempts."""
        content = path.read_text(encoding="utf-8", errors="ignore")
        result = self.analyze(content)
        result["file"] = str(path)
        result["file_size"] = len(content)
        return result


def scan_text_for_injection(text: str) -> dict[str, Any]:
    """Quick scan with simplified output for common use cases.

    Args:
        text: Text to analyze for injection patterns.

    Returns:
        Dict with risk_level, alert boolean (True if DANGEROUS), and findings.
    """
    result = InjectionDetector().analyze(text)
    result["alert"] = result["risk_level"] == "DANGEROUS"
    return result
