"""Render a DiffResult as Markdown (PR comment), JSON, or a terminal summary."""

from __future__ import annotations

from .diff import DiffResult

MARKER = "<!-- atlas-pr-diff -->"   # lets the Action find & update its sticky comment
_COLLAPSE_OVER = 8                  # wrap longer lists in <details>


def _verdict(res: DiffResult) -> tuple[str, str]:
    if res.warnings and any("0 screens" in w for w in res.warnings):
        return "⚠️", "Atlas data missing"
    if res.has_untested:
        return "🔴", "New/changed screens are untested"
    if res.has_changes:
        return "🟡", "Map changed — review impact"
    return "🟢", "No Atlas map changes"


def _slink(name: str, viewer: str | None) -> str:
    """`name` as a code span, linked to the Atlas viewer when available."""
    return f"[`{name}`]({viewer})" if viewer else f"`{name}`"


def _section(lines: list[str], title: str, body: list[str], *, open_if_small=True):
    """Append a section; collapse it when it's long."""
    if not body:
        return
    if len(body) > _COLLAPSE_OVER:
        lines.append(f"<details><summary>{title}</summary>")
        lines.append("")
        lines.extend(body)
        lines.append("</details>")
    else:
        lines.append(f"### {title}")
        lines.extend(body)
    lines.append("")


def render_markdown(res: DiffResult, meta: dict) -> str:
    emoji, verdict = _verdict(res)
    c = res.summary_counts()
    embed = bool(meta.get("embed_shots"))
    lines: list[str] = [MARKER]
    lines.append(f"## {emoji} {meta.get('title', 'Atlas map diff')}")
    lines.append("")
    lines.append(f"**{verdict}** &nbsp;·&nbsp; base `{meta.get('base_label')}` → head `{meta.get('head_label')}`")
    lines.append("")
    lines.append(
        f"`+{c['screens_added']}` new · `~{c['screens_changed']}` changed · "
        f"`-{c['screens_removed']}` removed · `{c['affected_flows']}` flows affected · "
        f"`{c['untested_screens']}` untested"
    )
    if c["nav_churn"]:
        lines.append(f"<sub>{c['nav_churn']} more screen(s) differ only by low-confidence navigation noise "
                     f"(hidden — likely exploration variance, not a real change).</sub>")
    lines.append("")

    if res.warnings:
        for w in res.warnings:
            lines.append(f"> ⚠️ {w}")
        lines.append("")

    # 🔴 the headline feature: untested, made actionable
    if res.untested_screens:
        body = ["New or changed screens that **no test reaches** — the gap this PR introduces:", ""]
        for u in res.untested_screens:
            link = _slink(u["name"], u.get("viewer_url"))
            body.append(f"- {link} · _{u['product_area'] or '–'}_ ({u['status']})")
            path = u.get("reach_path") or []
            if len(path) > 1:
                body.append(f"  - reach it: {' → '.join('`%s`' % p for p in path)}")
            elif path:
                body.append(f"  - entry screen (reached directly)")
            else:
                body.append(f"  - no mapped path reaches it (deep link / not yet explored)")
            body.append(f"  - cover it: `revyl test create --app \"{meta.get('app','<app>')}\"` "
                        f"then exercise this screen")
        _section(lines, f"🔴 Now untested ({len(res.untested_screens)})", body)

    # 🆕 new screens, with viewer links (+ optional local thumbnails)
    if res.added:
        body = []
        for s in res.added:
            area = f" · _{s.product_area}_" if s.product_area else ""
            desc = f" — {s.description}" if s.description else ""
            body.append(f"- {_slink(s.label, s.viewer_url)} ({s.screen_kind or 'screen'}){area}{desc}")
            if embed and s.local_screenshot_path:
                body.append(f"  <br><img src=\"{s.local_screenshot_path}\" width=\"200\">")
        _section(lines, f"🆕 New screens ({len(res.added)})", body)

    if res.changed:
        body = []
        for ch in res.changed:
            sc = res.head.screens.get(ch.screen_id)
            viewer = sc.viewer_url if sc else None
            area = f" · _{ch.product_area}_" if ch.product_area else ""
            body.append(f"- {_slink(ch.name, viewer)}{area}")
            for r in ch.reasons:
                body.append(f"  - {r}")
        _section(lines, f"✏️ Changed screens ({len(res.changed)})", body)

    if res.renamed:
        body = [f"- {ch.reasons[0]}" for ch in res.renamed]
        _section(lines, f"🔤 Renamed ({len(res.renamed)})", body)

    if res.removed:
        body = []
        for s in res.removed:
            area = f" · _{s.product_area}_" if s.product_area else ""
            body.append(f"- {_slink(s.label, s.viewer_url)} ({s.screen_kind or 'screen'}){area}")
        _section(lines, f"🗑️ Removed / no longer reached ({len(res.removed)})", body)

    if res.affected_flows:
        body = []
        for f in res.affected_flows:
            tag = " _(broken)_" if f.get("removed") else ""
            hits = ", ".join(f"`{h}`" for h in f["hit_screens"][:5])
            body.append(f"- **{f['label'] or f['id'][:8]}**{tag} — touches {hits}")
        _section(lines, f"🔀 Flows affected downstream ({len(res.affected_flows)})", body)

    if res.orphaned_screens:
        body = ["Still in the app but no longer reached by any mapped path:"]
        for o in res.orphaned_screens:
            body.append(f"- {_slink(o['name'], res.head.viewer_of(o['id']))} — "
                        f"lost its only inbound path via removed `{o['via_removed']}`")
        _section(lines, f"⚠️ Possibly orphaned ({len(res.orphaned_screens)})", body)

    if res.lost_coverage_edges:
        body = []
        for e in res.lost_coverage_edges[:12]:
            body.append(f"- `{res.base.name_of(e.source)}` → `{res.base.name_of(e.target)}` "
                        f"({e.action_label or e.action_type})")
        if len(res.lost_coverage_edges) > 12:
            body.append(f"- …(+{len(res.lost_coverage_edges) - 12} more)")
        _section(lines, f"📉 Lost test coverage ({len(res.lost_coverage_edges)})", body)

    if not res.has_changes and not res.warnings:
        lines.append("_The Atlas map is structurally identical between these builds._")
        lines.append("")

    lines.append("---")
    lines.append(f"<sub>🗺️ <a href=\"https://github.com/ethanzhoucool/atlas-pr-diff\">atlas-pr-diff</a> · "
                 f"{c['screens_added'] + c['screens_changed'] + c['screens_removed']} screen deltas · "
                 f"base {len(res.base.screens)} → head {len(res.head.screens)} screens</sub>")
    return "\n".join(lines)


def render_json(res: DiffResult, meta: dict) -> dict:
    return {
        "app": meta.get("app"),
        "base": meta.get("base_label"),
        "head": meta.get("head_label"),
        "verdict": _verdict(res)[1],
        "counts": res.summary_counts(),
        "warnings": res.warnings,
        "added": [{"name": s.label, "area": s.product_area, "kind": s.screen_kind,
                   "description": s.description, "viewer_url": s.viewer_url} for s in res.added],
        "removed": [{"name": s.label, "area": s.product_area, "kind": s.screen_kind,
                     "viewer_url": s.viewer_url} for s in res.removed],
        "changed": [{"name": c.name, "area": c.product_area, "reasons": c.reasons,
                     "viewer_url": res.head.viewer_of(c.screen_id)} for c in res.changed],
        "renamed": [{"reason": c.reasons[0]} for c in res.renamed],
        "nav_churn": [{"name": c.name, "area": c.product_area} for c in res.nav_churn],
        "untested_screens": res.untested_screens,
        "affected_flows": res.affected_flows,
        "orphaned_screens": res.orphaned_screens,
        "lost_coverage_edges": [
            {"from": res.base.name_of(e.source), "to": res.base.name_of(e.target),
             "action": e.action_label} for e in res.lost_coverage_edges
        ],
    }


def render_terminal(res: DiffResult, meta: dict) -> str:
    emoji, verdict = _verdict(res)
    c = res.summary_counts()
    out = [
        f"{emoji}  {verdict}",
        f"   base {meta.get('base_label')}  ->  head {meta.get('head_label')}",
        f"   +{c['screens_added']} new  ~{c['screens_changed']} changed  "
        f"-{c['screens_removed']} removed  |  {c['affected_flows']} flows  "
        f"{c['untested_screens']} untested  {c['lost_coverage_edges']} lost-coverage",
    ]
    for w in res.warnings:
        out.append(f"   ! {w}")
    if res.untested_screens:
        out.append("   untested:")
        for u in res.untested_screens[:10]:
            path = " ← " + " → ".join(u.get("reach_path", [])) if u.get("reach_path") else ""
            out.append(f"     - {u['name']} ({u['status']}, {u['product_area'] or '–'}){path}")
    return "\n".join(out)
