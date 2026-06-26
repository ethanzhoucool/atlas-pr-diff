"""Thin adapter over the `revyl` CLI for Atlas maps and build metadata.

Everything here shells out to the `revyl` binary so the tool needs no Revyl
SDK and no extra Python deps. Override the binary with REVYL_BIN if it is not
on PATH (the default install lives at ~/.revyl/bin/revyl).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from typing import Any


class RevylError(RuntimeError):
    pass


# substrings that mark a transient failure worth retrying
_TRANSIENT = ("timed out", "timeout", "connection reset", "temporarily",
              "502", "503", "504", "gateway", "too many requests", "rate limit",
              "eof", "broken pipe", "i/o timeout", "tls handshake")


def _bin() -> str:
    env = os.environ.get("REVYL_BIN")
    if env:
        return env
    found = shutil.which("revyl")
    if found:
        return found
    home = os.path.expanduser("~/.revyl/bin/revyl")
    if os.path.exists(home):
        return home
    raise RevylError(
        "revyl CLI not found. Install it or set REVYL_BIN to its path."
    )


def _run(args: list[str], *, timeout: int = 120, retries: int = 2) -> str:
    """Run `revyl <args>`, retrying transient failures with backoff."""
    cmd = [_bin(), *args]
    last = ""
    for attempt in range(retries + 1):
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            last = f"`revyl {' '.join(args)}` timed out after {timeout}s"
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
                continue
            raise RevylError(last)
        if proc.returncode == 0:
            return proc.stdout
        err = (proc.stderr.strip() or proc.stdout.strip())
        last = (f"`revyl {' '.join(args)}` failed (exit {proc.returncode}):\n{err}")
        if attempt < retries and any(t in err.lower() for t in _TRANSIENT):
            time.sleep(1.5 * (attempt + 1))
            continue
        raise RevylError(last)
    raise RevylError(last)


def _run_json(args: list[str], *, timeout: int = 120) -> Any:
    out = _run(args, timeout=timeout)
    # `revyl` occasionally prints a non-JSON preamble line before the payload;
    # find the first '{' or '[' and parse from there.
    out = out.strip()
    if not out:
        raise RevylError(f"`revyl {' '.join(args)}` returned no output")
    if out[0] not in "{[":
        for i, ch in enumerate(out):
            if ch in "{[":
                out = out[i:]
                break
    try:
        return json.loads(out)
    except json.JSONDecodeError as exc:
        raise RevylError(
            f"could not parse JSON from `revyl {' '.join(args)}`: {exc}"
        ) from exc


def atlas_graph(app: str, build: str = "all", *, limit: int = 500,
                surface_scope: str = "app", timeout: int = 180,
                screenshot_dir: str | None = None) -> dict:
    """Return the exact Atlas graph payload for one app at one build.

    `build` accepts a build id, a build version, "latest", or "all".
    If `screenshot_dir` is set, the CLI downloads each screen's screenshot
    there and adds a `local_screenshot_path` to every node.
    """
    args = [
        "atlas", "graph",
        "--app", app,
        "--build", build,
        "--json",
        "--limit", str(limit),
        "--surface-scope", surface_scope,
    ]
    if screenshot_dir:
        os.makedirs(screenshot_dir, exist_ok=True)
        args += ["--screenshot-dir", screenshot_dir]
    return _run_json(args, timeout=timeout)


def ping() -> dict:
    """Check connectivity + credentials. Returns {ok, detail}.

    `revyl ping` prints to stderr and signals failure via exit code, so we
    trust the exit code first and fall back to scanning the combined output.
    """
    try:
        proc = subprocess.run([_bin(), "ping"], capture_output=True, text=True, timeout=30)
    except (subprocess.TimeoutExpired, RevylError) as exc:
        return {"ok": False, "detail": str(exc)}
    combined = (proc.stdout + proc.stderr).strip()
    low = combined.lower()
    ok = proc.returncode == 0 and "invalid" not in low and "fail" not in low
    if "api key valid" in low or "credentials" in low and "valid" in low:
        ok = ok or proc.returncode == 0
    return {"ok": ok, "detail": combined}


def map_node_count(app: str, build: str, *, limit: int = 500) -> int:
    """How many screens Atlas has mapped for a build (0 = not explored yet)."""
    try:
        payload = atlas_graph(app, build, limit=limit)
    except RevylError:
        return 0
    return len(payload.get("nodes") or [])


def wait_for_map(app: str, build: str, *, timeout: int = 0, interval: int = 20,
                 limit: int = 500, log=lambda *_: None) -> int:
    """Poll until the build has a mapped Atlas (>0 screens) or `timeout` secs
    elapse. timeout<=0 means a single check. Returns the final node count."""
    deadline = time.monotonic() + timeout
    while True:
        n = map_node_count(app, build, limit=limit)
        if n > 0 or timeout <= 0:
            return n
        if time.monotonic() >= deadline:
            return n
        log(f"head build not mapped yet (0 screens); retrying in {interval}s...")
        time.sleep(interval)


def list_builds(app: str, *, branch: str | None = None) -> list[dict]:
    """Return uploaded build versions for an app, newest first.

    Each entry carries `.id`, `.version`, `.uploaded_at`, and
    `.metadata.git.{commit, commit_short, branch, message, remote}`.
    """
    args = ["build", "list", "--app", app, "--json"]
    if branch:
        args += ["--branch", branch]
    payload = _run_json(args)
    if isinstance(payload, dict):
        return payload.get("versions") or payload.get("builds") or []
    return payload or []


def list_apps() -> list[dict]:
    payload = _run_json(["atlas", "apps", "--json"])
    if isinstance(payload, dict):
        return payload.get("apps", [])
    return payload or []


def build_for_commit(app: str, commit: str) -> dict | None:
    """Find the most recent build whose git commit matches `commit`.

    Matches full sha or short sha (prefix), case-insensitive.
    """
    commit = (commit or "").strip().lower()
    if not commit:
        return None
    for b in list_builds(app):
        git = (b.get("metadata") or {}).get("git") or {}
        full = (git.get("commit") or "").lower()
        short = (git.get("commit_short") or "").lower()
        if full == commit or short == commit:
            return b
        if commit and (full.startswith(commit) or short.startswith(commit)):
            return b
        if full.startswith(commit[:7]) and len(commit) >= 7:
            return b
    return None


def latest_build_for_branch(app: str, branch: str) -> dict | None:
    builds = list_builds(app, branch=branch)
    if builds:
        return builds[0]
    # fall back to client-side filter if the server ignored --branch
    for b in list_builds(app):
        git = (b.get("metadata") or {}).get("git") or {}
        if (git.get("branch") or "") == branch:
            return b
    return None
