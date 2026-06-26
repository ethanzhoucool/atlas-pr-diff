"""Project config (.atlas-diff.yml / .json) + git auto-detection.

Config keeps a dev from repeating --app/--base/--fail-on on every run. We parse
a FLAT subset (top-level `key: value` only) so there is no YAML dependency —
stdlib only, runs anywhere in CI.
"""

from __future__ import annotations

import json
import os
import subprocess

CONFIG_NAMES = (".atlas-diff.yml", ".atlas-diff.yaml", ".atlas-diff.json", "atlas-diff.yml")

# keys a config file may set (everything is optional)
KNOWN_KEYS = {"app", "base", "head", "fail_on", "fail-on", "title", "limit",
              "min_support", "min-support", "baseline", "wait_timeout", "wait-timeout"}


def _coerce(v: str):
    s = v.strip()
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        return s[1:-1]
    low = s.lower()
    if low in ("true", "false"):
        return low == "true"
    if low in ("null", "none", "~", ""):
        return None
    if s.lstrip("-").isdigit():
        return int(s)
    return s


def _parse_flat_yaml(text: str) -> dict:
    out: dict = {}
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip() if not raw.strip().startswith("#") else ""
        if not line.strip() or ":" not in line:
            continue
        if line[0] in " \t":   # nested — unsupported, skip
            continue
        key, _, val = line.partition(":")
        out[key.strip()] = _coerce(val)
    return out


def find_config(start: str = ".") -> str | None:
    """Walk up from `start` looking for a config file."""
    cur = os.path.abspath(start)
    while True:
        for name in CONFIG_NAMES:
            p = os.path.join(cur, name)
            if os.path.isfile(p):
                return p
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent


def load_config(path: str | None = None) -> dict:
    path = path or find_config()
    if not path or not os.path.isfile(path):
        return {}
    with open(path) as fh:
        text = fh.read()
    data = json.loads(text) if path.endswith(".json") else _parse_flat_yaml(text)
    # normalize dashed keys to underscores
    norm = {}
    for k, v in data.items():
        norm[k.replace("-", "_")] = v
    norm["_path"] = path
    return norm


# --- git helpers ---------------------------------------------------------

def _git(*args: str, cwd: str = ".") -> str | None:
    try:
        out = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    except FileNotFoundError:
        return None
    if out.returncode != 0:
        return None
    return out.stdout.strip()


def git_head_sha(cwd: str = ".") -> str | None:
    return _git("rev-parse", "HEAD", cwd=cwd)


def git_default_branch(cwd: str = ".") -> str:
    ref = _git("symbolic-ref", "--quiet", "refs/remotes/origin/HEAD", cwd=cwd)
    if ref and "/" in ref:
        return ref.rsplit("/", 1)[-1]
    for b in ("main", "master"):
        if _git("rev-parse", "--verify", f"origin/{b}", cwd=cwd) is not None:
            return b
    return "main"


def git_merge_base(branch: str, cwd: str = ".") -> str | None:
    for ref in (f"origin/{branch}", branch):
        mb = _git("merge-base", ref, "HEAD", cwd=cwd)
        if mb:
            return mb
    return None


def in_git_repo(cwd: str = ".") -> bool:
    return _git("rev-parse", "--is-inside-work-tree", cwd=cwd) == "true"
