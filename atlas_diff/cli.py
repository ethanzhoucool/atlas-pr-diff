"""atlas-diff — diff an app's Revyl Atlas map between two builds for PR review.

Quick start (in a repo with a .atlas-diff.yml):
  atlas-diff diff                       # auto: app from config, base=main, head=HEAD
  atlas-diff init --app Ubert           # scaffold config + GitHub workflow
  atlas-diff doctor                     # preflight: auth, app mapped, baseline age

Explicit:
  atlas-diff diff --app Ubert --base latest --head main-20260603-193357
  atlas-diff diff --app Ubert --base baseline.json --head commit:4138aac --md out.md
  atlas-diff snapshot --app Ubert --build latest -o baseline.json
  atlas-diff resolve --app Ubert --commit 4138aac
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time

from . import config as cfg
from . import render, revyl
from .diff import DEFAULT_MIN_SUPPORT, diff as run_diff
from .model import Snapshot, from_graph_payload, from_snapshot_file

_SHA_RE = re.compile(r"^[0-9a-f]{7,40}$", re.I)


def _eprint(*a):
    print(*a, file=sys.stderr)


# --- ref resolution -------------------------------------------------------

def _ref_to_build(app: str, ref: str):
    """Turn a ref into ('file', path, {}, label) or ('build', build_ver, git, label)
    WITHOUT fetching the graph (so callers can wait-for-map first)."""
    if ref.endswith(".json") and os.path.exists(ref):
        return "file", ref, {}, f"file:{os.path.basename(ref)}"

    git: dict = {}
    if ref.startswith("commit:") or _SHA_RE.match(ref):
        sha = ref.split(":", 1)[1] if ":" in ref else ref
        b = revyl.build_for_commit(app, sha)
        if not b:
            raise SystemExit(f"no Revyl build found for commit {sha} on app {app}. "
                             f"Has the build been uploaded? (`revyl build list --app {app}`)")
        git = (b.get("metadata") or {}).get("git") or {}
        return "build", b["version"], git, f"{b['version']} ({git.get('commit_short', sha[:7])})"

    if ref.startswith("branch:"):
        branch = ref.split(":", 1)[1]
        b = revyl.latest_build_for_branch(app, branch)
        if not b:
            raise SystemExit(f"no Revyl build found for branch {branch} on app {app}.")
        git = (b.get("metadata") or {}).get("git") or {}
        return "build", b["version"], git, f"{b['version']} ({branch}@{git.get('commit_short', '?')})"

    if ref not in ("latest", "all"):
        for b in revyl.list_builds(app):
            if b.get("version") == ref or b.get("id") == ref:
                git = (b.get("metadata") or {}).get("git") or {}
                break
    return "build", ref, git, ref


def _fetch_snapshot(app: str, kind: str, val: str, git: dict, *,
                    limit: int, screenshot_dir: str | None = None) -> Snapshot:
    if kind == "file":
        return from_snapshot_file(val)
    payload = revyl.atlas_graph(app, val, limit=limit, screenshot_dir=screenshot_dir)
    return from_graph_payload(payload, build_version=val, git=git, source="live")


# --- auto-detection of app / base / head ---------------------------------

def _resolve_inputs(args, conf: dict):
    app = args.app or conf.get("app")
    if not app:
        raise SystemExit("no --app given and none in config. Run `atlas-diff init --app <name>` "
                         "or pass --app.")

    base = args.base
    if not base:
        base = conf.get("baseline") or conf.get("base")
    if not base:
        if cfg.in_git_repo():
            branch = cfg.git_default_branch()
            mb = cfg.git_merge_base(branch)
            base = f"commit:{mb}" if mb else f"branch:{branch}"
        else:
            base = "branch:main"

    head = args.head
    if not head:
        head = conf.get("head")
    if not head:
        sha = cfg.git_head_sha() if cfg.in_git_repo() else None
        head = f"commit:{sha}" if sha else "latest"

    return app, base, head


# --- commands ------------------------------------------------------------

def cmd_diff(args) -> int:
    conf = cfg.load_config(args.config)
    app, base_ref, head_ref = _resolve_inputs(args, conf)
    limit = args.limit or int(conf.get("limit", 500) or 500)
    min_support = args.min_support if args.min_support is not None else int(
        conf.get("min_support", DEFAULT_MIN_SUPPORT) or DEFAULT_MIN_SUPPORT)
    fail_on = args.fail_on or conf.get("fail_on") or "untested"

    _eprint(f"atlas-diff: app={app}  base={base_ref}  head={head_ref}")

    bk, bv, bgit, base_label = _ref_to_build(app, base_ref)
    hk, hv, hgit, head_label = _ref_to_build(app, head_ref)

    # wait for the head build to be mapped (handles exploration lag in CI)
    if hk == "build" and args.wait_for_map:
        timeout = args.wait_timeout or int(conf.get("wait_timeout", 300) or 300)
        _eprint(f"waiting up to {timeout}s for head build '{hv}' to be mapped...")
        n = revyl.wait_for_map(app, hv, timeout=timeout, limit=limit, log=_eprint)
        _eprint(f"head build mapped screens: {n}")

    base = _fetch_snapshot(app, bk, bv, bgit, limit=limit)
    head = _fetch_snapshot(app, hk, hv, hgit, limit=limit,
                           screenshot_dir=args.screenshot_dir)

    result = run_diff(base, head, min_support=min_support)

    meta = {"base_label": base_label, "head_label": head_label, "app": app,
            "title": args.title or conf.get("title") or "Atlas map diff",
            "embed_shots": bool(args.screenshot_dir)}

    md = render.render_markdown(result, meta)
    if args.md:
        with open(args.md, "w") as fh:
            fh.write(md)
        _eprint(f"wrote markdown -> {args.md}")
    if args.json_out:
        with open(args.json_out, "w") as fh:
            json.dump(render.render_json(result, meta), fh, indent=2)
        _eprint(f"wrote json -> {args.json_out}")

    if not args.quiet:
        print(render.render_terminal(result, meta))

    if fail_on == "none":
        return 0
    if fail_on == "untested":
        return 1 if result.has_untested else 0
    if fail_on == "changes":
        return 1 if result.has_changes else 0
    return 0


def cmd_snapshot(args) -> int:
    conf = cfg.load_config(args.config)
    app = args.app or conf.get("app")
    if not app:
        raise SystemExit("pass --app or set it in .atlas-diff.yml")
    kind, val, git, label = _ref_to_build(app, args.build)
    snap = _fetch_snapshot(app, kind, val, git, limit=args.limit)
    snap.save(args.output)
    _eprint(f"saved baseline snapshot ({len(snap.screens)} screens, "
            f"{len(snap.edges)} edges) from {label} -> {args.output}")
    return 0


def cmd_resolve(args) -> int:
    if args.commit:
        b = revyl.build_for_commit(args.app, args.commit)
    elif args.branch:
        b = revyl.latest_build_for_branch(args.app, args.branch)
    else:
        raise SystemExit("pass --commit or --branch")
    if not b:
        _eprint("no matching build")
        return 2
    git = (b.get("metadata") or {}).get("git") or {}
    out = {"id": b.get("id"), "version": b.get("version"), "commit": git.get("commit"),
           "branch": git.get("branch"), "uploaded_at": b.get("uploaded_at")}
    print(json.dumps(out, indent=2) if args.json else out["version"])
    return 0


def cmd_apps(args) -> int:
    apps = revyl.list_apps()
    if args.json:
        print(json.dumps(apps, indent=2))
    else:
        for a in apps:
            print(f"{a.get('name'):24} {a.get('platform','?'):8} "
                  f"{a.get('id')}  builds={a.get('versions_count','?')}")
    return 0


_WORKFLOW_TEMPLATE = """\
name: Atlas map diff
on:
  pull_request:
permissions:
  pull-requests: write
  checks: write
  contents: read
concurrency:
  group: atlas-diff-${{{{ github.event.pull_request.number }}}}
  cancel-in-progress: true
jobs:
  atlas-diff:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      # Prereq: the PR build must be uploaded to Revyl AND Atlas-explored before
      # this runs. Trigger your build+upload+explore step here, or upstream.
      - uses: ethanzhoucool/atlas-pr-diff/github@main
        with:
          app: {app}
          base: {base}
          revyl-api-key: ${{{{ secrets.REVYL_API_KEY }}}}
"""

_CONFIG_TEMPLATE = """\
# atlas-pr-diff config. Flat key: value only (no nesting).
app: {app}
# baseline: a committed snapshot is the most deterministic base.
#   generate with: atlas-diff snapshot --build branch:main -o atlas-baseline.json
baseline: {baseline}
fail_on: {fail_on}    # untested | changes | none
min_support: {min_support}
"""


def cmd_init(args) -> int:
    app = args.app or cfg.load_config().get("app")
    if not app:
        raise SystemExit("pass --app <name|id> so init can write it into config")

    cfg_path = os.path.join(args.dir, ".atlas-diff.yml")
    baseline_path = args.baseline or "atlas-baseline.json"
    if os.path.exists(cfg_path) and not args.force:
        _eprint(f"{cfg_path} exists (use --force to overwrite)")
    else:
        with open(cfg_path, "w") as fh:
            fh.write(_CONFIG_TEMPLATE.format(app=app, baseline=baseline_path,
                                             fail_on="untested", min_support=DEFAULT_MIN_SUPPORT))
        _eprint(f"wrote {cfg_path}")

    wf_dir = os.path.join(args.dir, ".github", "workflows")
    os.makedirs(wf_dir, exist_ok=True)
    wf_path = os.path.join(wf_dir, "atlas-diff.yml")
    if os.path.exists(wf_path) and not args.force:
        _eprint(f"{wf_path} exists (use --force to overwrite)")
    else:
        with open(wf_path, "w") as fh:
            fh.write(_WORKFLOW_TEMPLATE.format(app=app, base=baseline_path))
        _eprint(f"wrote {wf_path}")

    if args.snapshot:
        kind, val, git, label = _ref_to_build(app, "branch:main")
        snap = _fetch_snapshot(app, kind, val, git, limit=500)
        snap.save(baseline_path)
        _eprint(f"saved baseline ({len(snap.screens)} screens) from {label} -> {baseline_path}")
    else:
        _eprint(f"next: commit a baseline -> atlas-diff snapshot --app {app} "
                f"--build branch:main -o {baseline_path}")
    return 0


def cmd_doctor(args) -> int:
    conf = cfg.load_config(args.config)
    rows: list[tuple[bool, str]] = []
    critical_ok = True   # only revyl-missing / auth-failed should fail the command

    # revyl binary
    try:
        b = revyl._bin()
        rows.append((True, f"revyl CLI: {b}"))
    except revyl.RevylError as exc:
        rows.append((False, str(exc)))
        _print_doctor(rows)
        return 1

    # auth
    p = revyl.ping()
    rows.append((p["ok"], "Revyl auth: " + ("ok" if p["ok"] else "FAILED — set REVYL_API_KEY")))
    critical_ok = critical_ok and p["ok"]

    # config
    if conf.get("_path"):
        rows.append((True, f"config: {conf['_path']}"))
    else:
        rows.append((False, "config: none found (run `atlas-diff init --app <name>`)"))

    app = args.app or conf.get("app")
    if app:
        # app exists / has a mapped Atlas
        try:
            n = revyl.map_node_count(app, "all", limit=conf.get("limit", 500) or 500)
            rows.append((n > 0, f"Atlas for '{app}': {n} mapped screen(s)"
                                + ("" if n > 0 else " — needs an exploration")))
        except revyl.RevylError as exc:
            rows.append((False, f"Atlas for '{app}': error — {exc}"))
    else:
        rows.append((False, "app: not set (config `app:` or --app)"))

    # baseline freshness
    baseline = conf.get("baseline") or conf.get("base")
    if baseline and str(baseline).endswith(".json"):
        if os.path.exists(baseline):
            age_d = (time.time() - os.path.getmtime(baseline)) / 86400
            stale = age_d > 30
            rows.append((not stale, f"baseline {baseline}: {age_d:.0f}d old"
                                    + (" (stale — re-snapshot)" if stale else "")))
        else:
            rows.append((False, f"baseline {baseline}: missing — run `atlas-diff snapshot`"))

    # git (informational)
    rows.append((cfg.in_git_repo(), "git repo: " + ("yes" if cfg.in_git_repo() else "no (auto base/head off)")))

    _print_doctor(rows)
    if not critical_ok:
        _eprint("doctor: critical checks failed (revyl auth). Fix REVYL_API_KEY and retry.")
    return 0 if critical_ok else 1


def _print_doctor(rows):
    for ok, msg in rows:
        print(f"  {'✓' if ok else '✗'} {msg}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="atlas-diff", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--config", help="path to a config file (default: search up for .atlas-diff.yml)")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("diff", help="diff the Atlas map between two builds")
    d.add_argument("--app", help="app name or id (default: config)")
    d.add_argument("--base", help="baseline ref: build version | latest | all | commit:<sha> | "
                                  "branch:<name> | <file>.json  (default: config baseline or git merge-base)")
    d.add_argument("--head", help="head ref, same forms (default: current git HEAD commit)")
    d.add_argument("--md", help="write the Markdown report to this path")
    d.add_argument("--json-out", dest="json_out", help="write the structured JSON result to this path")
    d.add_argument("--screenshot-dir", help="download new/changed screen images here (adds thumbnails)")
    d.add_argument("--title", help="report title")
    d.add_argument("--limit", type=int, help="max screens to fetch per build")
    d.add_argument("--min-support", dest="min_support", type=int,
                   help=f"ignore edges seen < N times (default {DEFAULT_MIN_SUPPORT})")
    d.add_argument("--wait-for-map", action="store_true",
                   help="poll until the head build is mapped (handles exploration lag)")
    d.add_argument("--wait-timeout", type=int, help="seconds to wait for the map (default 300)")
    d.add_argument("--fail-on", choices=["none", "untested", "changes"],
                   help="exit non-zero on: untested changes (default), any change, or never")
    d.add_argument("-q", "--quiet", action="store_true")
    d.set_defaults(func=cmd_diff)

    s = sub.add_parser("snapshot", help="save a build's Atlas map as a cached baseline")
    s.add_argument("--app")
    s.add_argument("--build", default="latest")
    s.add_argument("-o", "--output", required=True)
    s.add_argument("--limit", type=int, default=500)
    s.set_defaults(func=cmd_snapshot)

    r = sub.add_parser("resolve", help="resolve a commit/branch to its Revyl build")
    r.add_argument("--app", required=True)
    r.add_argument("--commit")
    r.add_argument("--branch")
    r.add_argument("--json", action="store_true")
    r.set_defaults(func=cmd_resolve)

    a = sub.add_parser("apps", help="list apps that have an Atlas")
    a.add_argument("--json", action="store_true")
    a.set_defaults(func=cmd_apps)

    i = sub.add_parser("init", help="scaffold .atlas-diff.yml + a GitHub workflow")
    i.add_argument("--app", help="app name or id")
    i.add_argument("--dir", default=".", help="project root (default: .)")
    i.add_argument("--baseline", help="baseline snapshot path (default atlas-baseline.json)")
    i.add_argument("--snapshot", action="store_true", help="also snapshot main now as the baseline")
    i.add_argument("--force", action="store_true", help="overwrite existing files")
    i.set_defaults(func=cmd_init)

    doc = sub.add_parser("doctor", help="preflight: auth, app mapped, baseline freshness")
    doc.add_argument("--app")
    doc.set_defaults(func=cmd_doctor)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except revyl.RevylError as exc:
        _eprint(f"error: {exc}")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
