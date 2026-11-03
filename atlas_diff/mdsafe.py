"""Make untrusted Atlas text safe to drop into GitHub-flavored Markdown.

Screen names, descriptions, product areas, flow labels and action labels all
come from the Atlas exploration (LLM-written, often quoting on-screen text),
so the PR comment must not let them inject markup: an `@handle` would ping a
GitHub user, `</details>` or `<!--` would break or hide the rest of the
comment, a backtick would end a code span early, and `[text](url)` would
plant a link in a bot comment.
"""

from __future__ import annotations

import html
import re
from urllib.parse import quote

_MD_SPECIAL = re.compile(r"([\\`*\[\]~|])")
# `_` only needs escaping where it can open/close emphasis: GFM ignores an
# underscore between two alphanumerics, so snake_case stays readable.
_UNDERSCORE = re.compile(r"(?<![A-Za-z0-9])_|_(?![A-Za-z0-9])")
_MENTION = re.compile(r"@(?=[A-Za-z0-9])")


def _one_line(s) -> str:
    return " ".join(str(s or "").split())


def text(s) -> str:
    """Plain inline text: one line, HTML and Markdown punctuation escaped,
    `@mentions` defused with a zero-width space (as Dependabot does)."""
    s = html.escape(_one_line(s), quote=False)
    s = _MD_SPECIAL.sub(r"\\\1", s)
    s = _UNDERSCORE.sub(r"\\_", s)
    return _MENTION.sub("@&#8203;", s)


def code(s) -> str:
    """An inline code span that holds `s` verbatim, whatever backticks it
    contains. GitHub renders nothing inside code spans (no HTML, links or
    mentions), so this is the safe way to show an identifier."""
    s = _one_line(s)
    if not s:
        return "` `"
    fence = "`" * (max((len(run) for run in re.findall(r"`+", s)), default=0) + 1)
    if s.startswith("`") or s.endswith("`"):
        s = f" {s} "      # CommonMark strips one space on each side
    return f"{fence}{s}{fence}"


def url(u) -> str | None:
    """An http(s) URL that is safe as a Markdown link destination, or None."""
    u = str(u or "").strip()
    if not re.match(r"(?i)^https?://", u):
        return None
    return quote(u, safe=":/?#@!$&'*+,;=%~")


def attr(s) -> str:
    """A value for a double-quoted HTML attribute."""
    return html.escape(str(s or ""), quote=True)
