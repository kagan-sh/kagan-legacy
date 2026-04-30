"""kagan.tui.widgets._mention_links — linkify kagan and GitHub mention tokens.

Converts bare ``kagan#<id>`` and ``#<n>`` tokens in markdown text into
markdown link syntax.  The transformation is:

- ``kagan#abc12345`` → ``[kagan#abc12345](kagan-task://abc12345)``
- ``#42`` (when *github_repo_slug* is provided) → ``[#42](https://github.com/<slug>/issues/42)``
- ``#42`` (when slug is *None*) → left as-is (plain ``#42``)

The helper is **idempotent**: tokens that are already inside a markdown
link (i.e. preceded by ``[``) or that appear in a URL (e.g.
``https://example.com/path#anchor``) are not transformed again.

Design notes
------------
- Pure-regex, no AST/parsing — intentionally cheap for inline use.
- Called once per ``OutputChunk`` construction in ``streaming.py``.
- The regex for ``#<n>`` requires the hash to be at a word-start boundary
  (not preceded by ``/``, ``?``, alphanumeric, or ``#``) so that URL
  fragments and existing links are left untouched.
"""

from __future__ import annotations

import re

# Matches ``kagan#<6+ hex chars>`` that are NOT already inside a link.
# Negative lookbehind ``(?<!\[)`` skips ``[kagan#...]`` (already linked).
_KAGAN_RE = re.compile(r"(?<!\[)\bkagan#([0-9a-f]{6,})\b")

# Matches ``#<digits>`` at word-start, not preceded by ``/``, ``?``, ``#``,
# alphanumeric (URL fragments, existing links), or ``[`` (already linked).
_GH_RE = re.compile(r"(?<![/\w#\[])#(\d+)\b")


def linkify_mentions(markdown: str, *, github_repo_slug: str | None) -> str:
    """Replace bare mention tokens with markdown links.

    Parameters
    ----------
    markdown:
        Raw markdown string (may contain streamed agent output).
    github_repo_slug:
        ``owner/repo`` format, e.g. ``"octocat/Hello-World"``.  When
        *None* GitHub ``#<n>`` tokens are left as-is.

    Returns
    -------
    str
        Markdown string with mention tokens replaced by links.
    """
    result = _KAGAN_RE.sub(r"[kagan#\1](kagan-task://\1)", markdown)
    if github_repo_slug:
        result = _GH_RE.sub(
            lambda m: f"[#{m.group(1)}](https://github.com/{github_repo_slug}/issues/{m.group(1)})",
            result,
        )
    return result


__all__ = ["linkify_mentions"]
