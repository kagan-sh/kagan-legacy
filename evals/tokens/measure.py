"""Offline token-cost measurement for Kagan agent prompts.

Three arms (caveman-style):
  __baseline__  — empty prompt (control: model gets no instructions)
  __terse__     — "Answer concisely." (control: generic terseness)
  __current__   — the prompt actually shipped today

Reports char / word / line / approx-token counts for each prompt and writes
a JSON snapshot. Honest delta = `__current__` vs `__terse__`, not vs baseline.

Run:
    uv run python evals/tokens/measure.py                     # print to stdout
    uv run python evals/tokens/measure.py --out FILE.json     # write snapshot
    uv run python evals/tokens/measure.py --diff FILE.json    # compare to snapshot

Token approximation: chars/4 (industry rough heuristic for English prose).
For relative deltas this is stable; absolute numbers are ±15%. Install
tiktoken for tighter numbers — script auto-detects it.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from kagan.core._prompts import (  # noqa: E402
    DEFAULT_ORCHESTRATOR_PROMPT,
    DEFAULT_REVIEW_PROMPT,
)
from kagan.core._session_helpers import build_attached_startup_prompt  # noqa: E402

try:
    import tiktoken  # type: ignore[import-not-found]

    _ENC = tiktoken.get_encoding("cl100k_base")

    def _tokens(text: str) -> int:
        return len(_ENC.encode(text))

    TOKENIZER = "tiktoken/cl100k_base"
except ImportError:

    def _tokens(text: str) -> int:
        return max(1, len(text) // 4)

    TOKENIZER = "approx(chars/4)"


@dataclass
class Measurement:
    name: str
    chars: int
    words: int
    lines: int
    tokens: int


def _measure(name: str, text: str) -> Measurement:
    return Measurement(
        name=name,
        chars=len(text),
        words=len(text.split()),
        lines=text.count("\n") + (1 if text else 0),
        tokens=_tokens(text),
    )


# ── Stub objects for prompts that need a Task -------------------------------


class _StubTask:
    id = "T-stub"
    title = "Stub task title"
    description = "Stub task description used only for measurement."


def _attached_prompt() -> str:
    return build_attached_startup_prompt(
        _StubTask(),  # type: ignore[arg-type]
        criteria_texts=["Stub criterion A", "Stub criterion B"],
    )


def _extract_mcp_prompt(func_name: str) -> str:
    """Extract the UserMessage(...) body from an MCP prompt function by parsing AST.

    Robust against prompt text changes — we anchor on the function definition,
    not the prompt's first words.
    """
    import ast

    src = (REPO_ROOT / "src/kagan/server/mcp/prompts.py").read_text(encoding="utf-8")
    tree = ast.parse(src)

    for node in ast.walk(tree):
        if not isinstance(node, ast.AsyncFunctionDef) or node.name != func_name:
            continue
        for sub in ast.walk(node):
            if (
                isinstance(sub, ast.Call)
                and isinstance(sub.func, ast.Name)
                and sub.func.id == "UserMessage"
                and sub.args
            ):
                # Reconstruct by evaluating any constant fragments + treating
                # f-string expressions as their {placeholder} surface form.
                return _flatten_string_arg(sub.args[0])
    return ""


def _flatten_string_arg(node: ast.AST) -> str:
    """Walk a string-concatenation / f-string AST into a representative prompt.

    Treats interpolated `{var}` slots as literal `{var}` text (since we are
    measuring the prompt template, not a rendered instance).
    """
    import ast

    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        out = []
        for v in node.values:
            if isinstance(v, ast.Constant) and isinstance(v.value, str):
                out.append(v.value)
            elif isinstance(v, ast.FormattedValue) and isinstance(v.value, ast.Name):
                out.append("{" + v.value.id + "}")
            else:
                out.append("{...}")
        return "".join(out)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _flatten_string_arg(node.left) + _flatten_string_arg(node.right)
    return ""


def _mcp_plan_prompt() -> str:
    return _extract_mcp_prompt("plan_tasks_from_description")


def _mcp_diagnose_prompt() -> str:
    return _extract_mcp_prompt("diagnose_failure")


def _mcp_audit_prompt() -> str:
    return _extract_mcp_prompt("security_audit_persona_repo")


# ── Arms --------------------------------------------------------------------

ARMS: dict[str, str] = {
    "__baseline__": "",
    "__terse__": "Answer concisely.",
}


def collect() -> dict[str, Measurement]:
    prompts: dict[str, str] = {
        **ARMS,
        "orchestrator": DEFAULT_ORCHESTRATOR_PROMPT,
        "review": DEFAULT_REVIEW_PROMPT,
        "attached_worker_startup": _attached_prompt(),
        "mcp_plan_tasks": _mcp_plan_prompt(),
        "mcp_diagnose_failure": _mcp_diagnose_prompt(),
        "mcp_security_audit": _mcp_audit_prompt(),
    }
    return {name: _measure(name, text) for name, text in prompts.items()}


def _print_table(measurements: dict[str, Measurement]) -> None:
    print(f"# tokenizer: {TOKENIZER}\n")
    header = f"{'name':<28} {'chars':>7} {'words':>7} {'lines':>6} {'tokens':>7}"
    print(header)
    print("-" * len(header))
    for m in measurements.values():
        print(f"{m.name:<28} {m.chars:>7} {m.words:>7} {m.lines:>6} {m.tokens:>7}")


def _print_diff(current: dict[str, Measurement], baseline_path: Path) -> None:
    base_data = json.loads(baseline_path.read_text(encoding="utf-8"))
    base = {m["name"]: m for m in base_data["measurements"]}
    print(f"# diff vs {baseline_path.name} (tokenizer: {TOKENIZER})\n")
    header = f"{'name':<28} {'tokens(was)':>12} {'tokens(now)':>12} {'Δ':>7} {'Δ%':>7}"
    print(header)
    print("-" * len(header))
    totals = [0, 0]
    for name, m in current.items():
        if name not in base:
            continue
        was = base[name]["tokens"]
        now = m.tokens
        delta = now - was
        pct = (delta / was * 100.0) if was else 0.0
        if name not in {"__baseline__", "__terse__"}:
            totals[0] += was
            totals[1] += now
        print(f"{name:<28} {was:>12} {now:>12} {delta:>+7} {pct:>+6.1f}%")
    if totals[0]:
        d = totals[1] - totals[0]
        p = d / totals[0] * 100.0
        print("-" * len(header))
        print(f"{'TOTAL (excl. controls)':<28} {totals[0]:>12} {totals[1]:>12} {d:>+7} {p:>+6.1f}%")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, help="Write snapshot JSON to this path.")
    parser.add_argument("--diff", type=Path, help="Compare against a snapshot JSON.")
    args = parser.parse_args()

    current = collect()

    if args.diff:
        _print_diff(current, args.diff)
        return 0

    _print_table(current)

    if args.out:
        payload = {
            "tokenizer": TOKENIZER,
            "measurements": [asdict(m) for m in current.values()],
        }
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"\nwrote {args.out}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
