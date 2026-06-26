"""Render a DiffResult as Markdown (PR comment), JSON, or a terminal summary."""

from __future__ import annotations

from .diff import DiffResult

MARKER = "<!-- atlas-pr-diff -->"   # lets the Action find & update its sticky comment


def _verdict(res: DiffResult) -> tuple[str, str]:
    if res.warnings and any("0 screens" in w for w in res.warnings):
        return "⚠️", "Atlas data missing"
    if res.has_untested:
        return "🔴", "New/changed screens are untested"
    if res.has_changes:
        return "🟡", "Map changed — review impact"
    return "🟢", "No Atlas map changes"


def render_markdown(res: DiffResult, meta: dict) -> str:
    emoji, verdict = _verdict(res)
    c = res.summary_counts()
    lines: list[str] = [MARKER]
    lines.append(f"## {emoji} {meta.get('title', 'Atlas map diff')}")
    lines.append("")
    lines.append(f"**{verdict}** &nbsp;·&nbsp; base `{meta.get('base_label')}` → head `{meta.get('head_label')}`")
    lines.append("")

    # one-line scoreboard
    score = (
        f"`+{c['screens_added']}` new · `~{c['screens_changed']}` changed · "
        f"`-{c['screens_removed']}` removed · `{c['affected_flows']}` flows affected · "
        f"`{c['untested_screens']}` untested"
    )
    lines.append(score)
    if c["nav_churn"]:
        lines.append(f"<sub>{c['nav_churn']} more screen(s) differ only by low-confidence navigation noise "
                     f"(hidden — likely exploration variance, not a real change).</sub>")
    lines.append("")

    if res.warnings:
        for w in res.warnings:
            lines.append(f"> ⚠️ {w}")
        lines.append("")

    if res.untested_screens:
        lines.append("### 🔴 Now untested")
        lines.append("New or changed screens that no test reaches:")
        lines.append("")
        lines.append("| Screen | Area | Status | In/Out edges |")
        lines.append("|---|---|---|---|")
        for u in res.untested_screens:
            lines.append(f"| `{u['name']}` | {u['product_area'] or '–'} | {u['status']} | "
                         f"{u['incoming_edges']}/{u['outgoing_edges']} |")
        lines.append("")

    if res.added:
        lines.append(f"### 🆕 New screens ({len(res.added)})")
        for s in res.added:
            area = f" · _{s.product_area}_" if s.product_area else ""
            desc = f" — {s.description}" if s.description else ""
            lines.append(f"- `{s.label}` ({s.screen_kind or 'screen'}){area}{desc}")
        lines.append("")

    if res.changed:
        lines.append(f"### ✏️ Changed screens ({len(res.changed)})")
        for ch in res.changed:
            area = f" · _{ch.product_area}_" if ch.product_area else ""
            lines.append(f"- `{ch.name}`{area}")
            for r in ch.reasons:
                lines.append(f"  - {r}")
        lines.append("")

    if res.renamed:
        lines.append(f"### 🔤 Renamed ({len(res.renamed)})")
        for ch in res.renamed:
            lines.append(f"- {ch.reasons[0]}")
        lines.append("")

    if res.removed:
        lines.append(f"### 🗑️ Removed / no longer reached ({len(res.removed)})")
        for s in res.removed:
            area = f" · _{s.product_area}_" if s.product_area else ""
            lines.append(f"- `{s.label}` ({s.screen_kind or 'screen'}){area}")
        lines.append("")

    if res.affected_flows:
        lines.append(f"### 🔀 Flows affected downstream ({len(res.affected_flows)})")
        for f in res.affected_flows:
            tag = " _(broken)_" if f.get("removed") else ""
            hits = ", ".join(f"`{h}`" for h in f["hit_screens"][:5])
            lines.append(f"- **{f['label'] or f['id'][:8]}**{tag} — touches {hits}")
        lines.append("")

    if res.orphaned_screens:
        lines.append(f"### ⚠️ Possibly orphaned ({len(res.orphaned_screens)})")
        lines.append("Still in the app but no longer reached by any mapped path:")
        for o in res.orphaned_screens:
            lines.append(f"- `{o['name']}` — lost its only inbound path via removed `{o['via_removed']}`")
        lines.append("")

    if res.lost_coverage_edges:
        lines.append(f"### 📉 Lost test coverage ({len(res.lost_coverage_edges)})")
        for e in res.lost_coverage_edges[:10]:
            lines.append(f"- `{res.base.name_of(e.source)}` → `{res.base.name_of(e.target)}` "
                         f"({e.action_label or e.action_type})")
        lines.append("")

    if not res.has_changes and not res.warnings:
        lines.append("_The Atlas map is structurally identical between these builds._")
        lines.append("")

    lines.append("---")
    lines.append(f"<sub>🗺️ atlas-pr-diff · {c['screens_added'] + c['screens_changed'] + c['screens_removed']} "
                 f"screen deltas · base {len(res.base.screens)} → head {len(res.head.screens)} screens</sub>")
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
                   "description": s.description} for s in res.added],
        "removed": [{"name": s.label, "area": s.product_area, "kind": s.screen_kind} for s in res.removed],
        "changed": [{"name": c.name, "area": c.product_area, "reasons": c.reasons} for c in res.changed],
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
            out.append(f"     - {u['name']} ({u['status']}, {u['product_area'] or '–'})")
    return "\n".join(out)
