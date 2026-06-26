"""Shared risk-tier presentation for the renderers (lever 4, DESIGN section 5).

Pure label/style lookups so the intake header, gate header, and inbox row show
the tier the same way. Unknown tiers fall back to the raw string, dim.
"""

_LABEL: dict[str, str] = {"low": "low risk", "medium": "med risk", "high": "high risk"}
# Semantic theme names (KAGAN_THEME risk tiers); only high is emphasised.
_STYLE: dict[str, str] = {"low": "risk.low", "medium": "risk.med", "high": "risk.high"}


def risk_label(risk: str) -> str:
    return _LABEL.get(risk, f"{risk} risk")


def risk_style(risk: str) -> str:
    return _STYLE.get(risk, "risk.med")


__all__ = ["risk_label", "risk_style"]
