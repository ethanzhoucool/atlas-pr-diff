#!/usr/bin/env python3
"""Post the atlas-diff report to a PR as a sticky comment + a GitHub Check Run.

Stdlib-only (plus an optional shell-out to the preinstalled `gh` CLI). Designed
to never crash CI on a posting hiccup: any GitHub API failure is logged to
stderr and the process still exits 0. The PASS/FAIL of the PR check is driven by
the `atlas-diff diff` exit code in the workflow, not by this script.

Inputs:
  --md   PATH   the rendered Markdown report (first line is the sticky marker)
  --json PATH   the structured JSON result (provides `verdict` for the check run)
  --sha  SHA    head sha for the Check Run (default: env GITHUB_SHA / event sha)
  --pr   N      PR number (default: derived from GITHUB_EVENT_PATH)
  --title STR   one-line title for the check run / fallback
  --no-comment      skip the sticky PR comment
  --no-check-run    skip the GitHub Check Run

Env read: GITHUB_REPOSITORY, GITHUB_TOKEN (or GH_TOKEN), GITHUB_EVENT_PATH,
GITHUB_SHA, GITHUB_API_URL.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request

MARKER = "<!-- atlas-pr-diff -->"
CHECK_NAME = "Atlas map diff"

# verdict (from the JSON result) -> GitHub Check Run conclusion.
# "New/changed screens are untested" is the one actionable gate -> failure.
VERDICT_CONCLUSION = {
    "Atlas data missing": "neutral",
    "New/changed screens are untested": "failure",
    "Map changed — review impact": "neutral",
    "No Atlas map changes": "success",
}
# Per-verdict one-liner shown in the check run output title.
VERDICT_TITLE = {
    "Atlas data missing": "No Atlas map on the PR build — run an exploration first",
    "New/changed screens are untested": "New/changed screens are untested",
    "Map changed — review impact": "Atlas map changed — review impact",
    "No Atlas map changes": "No Atlas map changes",
}

# GitHub caps check-run output.summary at 65535 chars; stay under it.
SUMMARY_LIMIT = 60000


def _eprint(*a) -> None:
    print(*a, file=sys.stderr, flush=True)


def _api_base() -> str:
    return os.environ.get("GITHUB_API_URL", "https://api.github.com").rstrip("/")


def _token() -> str:
    return os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""


def _read_text(path: str | None) -> str:
    if not path:
        return ""
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError as exc:
        _eprint(f"atlas-diff: could not read {path}: {exc}")
        return ""


def _load_json(path: str | None) -> dict:
    raw = _read_text(path)
    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        _eprint(f"atlas-diff: could not parse JSON {path}: {exc}")
        return {}


def _derive_pr_number(explicit: int | None) -> int | None:
    if explicit:
        return explicit
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if event_path and os.path.exists(event_path):
        try:
            with open(event_path, encoding="utf-8") as fh:
                event = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            _eprint(f"atlas-diff: could not read event payload: {exc}")
            event = {}
        for key in ("pull_request", "issue"):
            node = event.get(key) or {}
            num = node.get("number")
            if isinstance(num, int):
                return num
        # Some events expose the number at the top level.
        if isinstance(event.get("number"), int):
            return event["number"]
    return None


def _derive_sha(explicit: str | None) -> str | None:
    if explicit:
        return explicit
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if event_path and os.path.exists(event_path):
        try:
            with open(event_path, encoding="utf-8") as fh:
                event = json.load(fh)
            pr = event.get("pull_request") or {}
            head = pr.get("head") or {}
            if head.get("sha"):
                return head["sha"]
        except (OSError, json.JSONDecodeError):
            pass
    return os.environ.get("GITHUB_SHA") or None


# --------------------------------------------------------------------------- #
# Low-level GitHub REST helpers (urllib first, gh CLI as a fallback).
# --------------------------------------------------------------------------- #

def _gh_available() -> bool:
    return shutil.which("gh") is not None


def _urllib_request(method: str, url: str, token: str, body: dict | None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("User-Agent", "atlas-pr-diff")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode() or "{}"
    return json.loads(raw)


def _gh_api(method: str, path_or_url: str, token: str, body: dict | None):
    """Call the GitHub API. Returns parsed JSON or raises.

    Tries `gh api` (handles auth + base URL itself) and falls back to urllib.
    `path_or_url` may be a full URL or an API path like "/repos/o/r/...".
    """
    base = _api_base()
    if path_or_url.startswith("http"):
        url = path_or_url
        gh_path = path_or_url[len(base):] if path_or_url.startswith(base) else path_or_url
    else:
        gh_path = path_or_url if path_or_url.startswith("/") else "/" + path_or_url
        url = base + gh_path

    if _gh_available():
        cmd = ["gh", "api", "--method", method, gh_path,
               "-H", "Accept: application/vnd.github+json"]
        if body is not None:
            cmd += ["--input", "-"]
        env = dict(os.environ)
        if token:
            env["GH_TOKEN"] = token
        try:
            proc = subprocess.run(
                cmd,
                input=json.dumps(body) if body is not None else None,
                capture_output=True, text=True, env=env, timeout=60,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            _eprint(f"atlas-diff: gh api invocation failed ({exc}); trying urllib")
        else:
            if proc.returncode == 0:
                out = proc.stdout.strip() or "{}"
                try:
                    return json.loads(out)
                except json.JSONDecodeError:
                    return {}
            _eprint(f"atlas-diff: gh api {method} {gh_path} -> rc={proc.returncode}: "
                    f"{proc.stderr.strip()[:400]}; trying urllib")

    # urllib fallback
    return _urllib_request(method, url, token, body)


# --------------------------------------------------------------------------- #
# Sticky comment
# --------------------------------------------------------------------------- #

def upsert_sticky_comment(repo: str, pr: int, token: str, body: str) -> bool:
    """Find the marker comment and PATCH it, else POST a new one."""
    existing_id = None
    page = 1
    while True:
        try:
            comments = _gh_api(
                "GET",
                f"/repos/{repo}/issues/{pr}/comments?per_page=100&page={page}",
                token, None)
        except (urllib.error.URLError, OSError, ValueError) as exc:
            _eprint(f"atlas-diff: could not list comments: {exc}")
            comments = []
        if not isinstance(comments, list) or not comments:
            break
        for c in comments:
            if MARKER in (c.get("body") or ""):
                existing_id = c.get("id")
                break
        if existing_id is not None or len(comments) < 100:
            break
        page += 1

    try:
        if existing_id is not None:
            _gh_api("PATCH", f"/repos/{repo}/issues/comments/{existing_id}",
                    token, {"body": body})
            _eprint(f"atlas-diff: updated sticky comment {existing_id}")
        else:
            _gh_api("POST", f"/repos/{repo}/issues/{pr}/comments",
                    token, {"body": body})
            _eprint("atlas-diff: posted new sticky comment")
        return True
    except (urllib.error.URLError, OSError, ValueError) as exc:
        _eprint(f"atlas-diff: could not upsert comment: {exc}")
        return False


# --------------------------------------------------------------------------- #
# Check run
# --------------------------------------------------------------------------- #

def create_check_run(repo: str, sha: str, token: str, verdict: str,
                     summary_md: str, title: str) -> bool:
    conclusion = VERDICT_CONCLUSION.get(verdict, "neutral")
    one_liner = VERDICT_TITLE.get(verdict, verdict or "Atlas map diff")
    summary = summary_md[:SUMMARY_LIMIT]
    if len(summary_md) > SUMMARY_LIMIT:
        summary += "\n\n_…report truncated; see the PR comment for the full diff._"
    payload = {
        "name": CHECK_NAME,
        "head_sha": sha,
        "status": "completed",
        "conclusion": conclusion,
        "output": {
            "title": one_liner,
            "summary": summary or one_liner,
            "text": title or one_liner,
        },
    }
    try:
        _gh_api("POST", f"/repos/{repo}/check-runs", token, payload)
        _eprint(f"atlas-diff: created check run '{CHECK_NAME}' -> {conclusion}")
        return True
    except (urllib.error.URLError, OSError, ValueError) as exc:
        # Most commonly a 403 when the token lacks `checks:write`. Swallow it —
        # the sticky comment + job status still serve as "the check".
        _eprint(f"atlas-diff: could not create check run (missing checks:write?): {exc}")
        return False


# --------------------------------------------------------------------------- #

def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Post atlas-diff results to a PR.")
    p.add_argument("--md", help="path to the rendered Markdown report")
    p.add_argument("--json", dest="json_path", help="path to the JSON result")
    p.add_argument("--sha", help="head sha for the check run")
    p.add_argument("--pr", type=int, help="PR number (else derived from event)")
    p.add_argument("--title", default="Atlas map diff", help="one-line title")
    p.add_argument("--no-comment", dest="comment", action="store_false")
    p.add_argument("--no-check-run", dest="check_run", action="store_false")
    p.set_defaults(comment=True, check_run=True)
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)

    md = _read_text(args.md)
    result = _load_json(args.json_path)
    verdict = result.get("verdict", "")

    repo = os.environ.get("GITHUB_REPOSITORY", "")
    token = _token()
    pr = _derive_pr_number(args.pr)
    sha = _derive_sha(args.sha)

    body = md or (f"{MARKER}\n\n_atlas-diff produced no Markdown report._")

    # Local / no-context runs: just print and succeed so nothing breaks.
    if not token or not repo:
        _eprint("atlas-diff: no GITHUB_TOKEN/GITHUB_REPOSITORY — printing report only.")
        print(body)
        return 0

    if args.comment:
        if pr:
            upsert_sticky_comment(repo, pr, token, body)
        else:
            _eprint("atlas-diff: no PR number — skipping sticky comment.")
            print(body)

    if args.check_run:
        if sha:
            create_check_run(repo, sha, token, verdict, md, args.title)
        else:
            _eprint("atlas-diff: no head sha — skipping check run.")

    # Always succeed: the workflow controls red/green via the diff exit code.
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # never crash CI on a posting hiccup
        _eprint(f"atlas-diff: post_check unexpected error (ignored): {exc}")
        sys.exit(0)
