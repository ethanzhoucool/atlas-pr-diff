"""atlas-diff — diff an app's Atlas map between two builds for PR review.

Usage examples:
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

from . import render, revyl
from .diff import diff as run_diff
from .model import Snapshot, from_graph_payload, from_snapshot_file

_SHA_RE = re.compile(r"^[0-9a-f]{7,40}$", re.I)


def _eprint(*a):
    print(*a, file=sys.stderr)


def _resolve_ref(app: str, ref: str, *, limit: int) -> tuple[Snapshot, str]:
    """Resolve a base/head ref into a Snapshot + a human label.

    ref forms:
      * a path to a .json snapshot file (cached baseline)
      * "latest" | "all"
      * "commit:<sha>" or a bare 7-40 hex sha
      * "branch:<name>"
      * any other string -> treated as a build version/id
    """
    if ref.endswith(".json") and os.path.exists(ref):
        snap = from_snapshot_file(ref)
        return snap, f"file:{os.path.basename(ref)}"

    git = {}
    build_ref = ref
    label = ref

    if ref.startswith("commit:") or _SHA_RE.match(ref):
        sha = ref.split(":", 1)[1] if ":" in ref else ref
        b = revyl.build_for_commit(app, sha)
        if not b:
            raise SystemExit(f"no Revyl build found for commit {sha} on app {app}")
        build_ref = b["version"]
        git = (b.get("metadata") or {}).get("git") or {}
        label = f"{build_ref} ({git.get('commit_short', sha[:7])})"
    elif ref.startswith("branch:"):
        branch = ref.split(":", 1)[1]
        b = revyl.latest_build_for_branch(app, branch)
        if not b:
            raise SystemExit(f"no Revyl build found for branch {branch} on app {app}")
        build_ref = b["version"]
        git = (b.get("metadata") or {}).get("git") or {}
        label = f"{build_ref} ({branch}@{git.get('commit_short', '?')})"
    elif ref not in ("latest", "all"):
        # bare build version — try to attach its git metadata
        for b in revyl.list_builds(app):
            if b.get("version") == ref or b.get("id") == ref:
                git = (b.get("metadata") or {}).get("git") or {}
                break

    payload = revyl.atlas_graph(app, build_ref, limit=limit)
    snap = from_graph_payload(payload, build_version=build_ref, git=git, source="live")
    return snap, label


def cmd_diff(args) -> int:
    base, base_label = _resolve_ref(args.app, args.base, limit=args.limit)
    head, head_label = _resolve_ref(args.app, args.head, limit=args.limit)

    result = run_diff(base, head)

    meta = {"base_label": base_label, "head_label": head_label,
            "app": args.app, "title": args.title}

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

    # exit code drives the CI check conclusion
    fail_on = args.fail_on
    if fail_on == "none":
        return 0
    if fail_on == "untested":
        return 1 if result.has_untested else 0
    if fail_on == "changes":
        return 1 if result.has_changes else 0
    return 0


def cmd_snapshot(args) -> int:
    snap, label = _resolve_ref(args.app, args.build, limit=args.limit)
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
    out = {"id": b.get("id"), "version": b.get("version"),
           "commit": git.get("commit"), "branch": git.get("branch"),
           "uploaded_at": b.get("uploaded_at")}
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


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="atlas-diff", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("diff", help="diff the Atlas map between two builds")
    d.add_argument("--app", required=True, help="app name or id")
    d.add_argument("--base", required=True,
                   help="baseline ref: build version | latest | all | commit:<sha> | branch:<name> | <file>.json")
    d.add_argument("--head", required=True, help="head ref (same forms as --base)")
    d.add_argument("--md", help="write the Markdown report to this path")
    d.add_argument("--json-out", dest="json_out", help="write the structured JSON result to this path")
    d.add_argument("--title", default="Atlas map diff", help="report title")
    d.add_argument("--limit", type=int, default=500, help="max screens to fetch per build")
    d.add_argument("--fail-on", choices=["none", "untested", "changes"], default="untested",
                   help="exit non-zero when: untested changes (default), any change, or never")
    d.add_argument("-q", "--quiet", action="store_true", help="suppress terminal summary")
    d.set_defaults(func=cmd_diff)

    s = sub.add_parser("snapshot", help="save a build's Atlas map as a cached baseline")
    s.add_argument("--app", required=True)
    s.add_argument("--build", default="latest", help="build version | latest | all | commit:<sha> | branch:<name>")
    s.add_argument("-o", "--output", required=True, help="output .json path")
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
