"""Diff two Atlas snapshots into a structured, review-oriented result.

The hard part of diffing Atlas maps is *exploration noise*: each build is
explored by an independent BFS that takes slightly different paths, so a naive
diff reports dozens of "changed" screens that only differ by one fluke
navigation edge. This module separates high-signal change (a screen's
semantics changed, or it now wires to a brand-new/removed screen) from
low-signal navigation churn, and ignores single-observation edges via a
support threshold.

Signals produced:
  * screens added / removed / changed (semantics or flow-wiring) / renamed
  * nav_churn — screens whose only delta is reroute noise (kept separate)
  * flows & screens affected downstream of a change (graph reachability)
  * "now untested" — new/changed screens no test reaches (edge.test_support 0)
  * lost_coverage — edges a test traversed in base but not in head
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .model import Edge, Screen, Snapshot

DEFAULT_MIN_SUPPORT = 2          # ignore edges seen fewer than this many times
NAV_CHURN_THRESHOLD = 3          # net nav deltas below this (with no wiring/semantic change) = noise


def _norm_name(name: str) -> str:
    return " ".join((name or "").replace("-", "_").split()).strip().lower()


def _norm(s: str | None) -> str:
    return " ".join((s or "").split()).strip().lower()


def _significant(e: Edge, min_support: int) -> bool:
    """An edge is trustworthy if a test or report backs it, or it was observed
    enough times to not be a one-off exploration fluke."""
    return e.test_support > 0 or e.report_support > 0 or e.observation_count >= min_support


@dataclass
class ScreenChange:
    screen_id: str
    name: str
    product_area: str
    reasons: list[str]
    base_id: str | None = None
    kind: str = "changed"          # "changed" (high signal) | "nav_churn" (low)


@dataclass
class DiffResult:
    app_id: str
    base: Snapshot
    head: Snapshot

    added: list[Screen] = field(default_factory=list)
    removed: list[Screen] = field(default_factory=list)
    changed: list[ScreenChange] = field(default_factory=list)
    renamed: list[ScreenChange] = field(default_factory=list)
    nav_churn: list[ScreenChange] = field(default_factory=list)

    edges_added: list[Edge] = field(default_factory=list)
    edges_removed: list[Edge] = field(default_factory=list)

    orphaned_screens: list[dict] = field(default_factory=list)
    affected_flows: list[dict] = field(default_factory=list)

    untested_screens: list[dict] = field(default_factory=list)
    lost_coverage_edges: list[Edge] = field(default_factory=list)

    warnings: list[str] = field(default_factory=list)

    @property
    def changed_seed_ids(self) -> set[str]:
        return {c.screen_id for c in self.changed} | {s.id for s in self.added}

    @property
    def has_changes(self) -> bool:
        return bool(self.added or self.removed or self.changed or self.renamed)

    @property
    def has_untested(self) -> bool:
        return bool(self.untested_screens)

    def summary_counts(self) -> dict:
        return {
            "screens_added": len(self.added),
            "screens_removed": len(self.removed),
            "screens_changed": len(self.changed),
            "screens_renamed": len(self.renamed),
            "nav_churn": len(self.nav_churn),
            "edges_added": len(self.edges_added),
            "edges_removed": len(self.edges_removed),
            "orphaned_screens": len(self.orphaned_screens),
            "affected_flows": len(self.affected_flows),
            "untested_screens": len(self.untested_screens),
            "lost_coverage_edges": len(self.lost_coverage_edges),
        }


def _match_screens(base: Snapshot, head: Snapshot
                   ) -> tuple[dict[str, str], list[Screen], list[Screen]]:
    """Match head screens to base screens.

    Pass 1: by canonical id (stable across builds in Atlas).
    Pass 2: leftovers by normalized semantic name + product area (id churn).
    Returns (head_id -> base_id, added, removed).
    """
    matched: dict[str, str] = {}
    used_base: set[str] = set()

    for hid in head.screens:
        if hid in base.screens:
            matched[hid] = hid
            used_base.add(hid)

    base_by_name: dict[tuple[str, str], str] = {}
    for bid, bs in base.screens.items():
        if bid in used_base:
            continue
        base_by_name.setdefault((_norm_name(bs.name), bs.product_area), bid)

    for hid, hs in head.screens.items():
        if hid in matched:
            continue
        bid = base_by_name.get((_norm_name(hs.name), hs.product_area))
        if bid and bid not in used_base:
            matched[hid] = bid
            used_base.add(bid)

    added = [head.screens[h] for h in head.screens if h not in matched]
    removed = [base.screens[b] for b in base.screens if b not in used_base]
    return matched, added, removed


def _structural_reasons(bs: Screen, hs: Screen) -> tuple[list[str], bool]:
    """Semantic deltas that don't depend on which paths the exploration took.
    Returns (reasons, is_pure_rename)."""
    reasons: list[str] = []
    renamed = _norm_name(bs.name) != _norm_name(hs.name)
    if renamed:
        reasons.append(f"renamed `{bs.name}` → `{hs.name}`")
    if bs.screen_kind != hs.screen_kind:
        reasons.append(f"kind `{bs.screen_kind or '?'}` → `{hs.screen_kind or '?'}`")
    if bs.product_area != hs.product_area:
        reasons.append(f"area `{bs.product_area or '?'}` → `{hs.product_area or '?'}`")
    if _norm(bs.description) != _norm(hs.description):
        reasons.append("purpose/description changed")

    b_acts = {_norm(a) for a in bs.primary_actions}
    h_acts = {_norm(a) for a in hs.primary_actions}
    if b_acts != h_acts:
        gained, lost = h_acts - b_acts, b_acts - h_acts
        bits = []
        if gained:
            bits.append(f"+{len(gained)}")
        if lost:
            bits.append(f"-{len(lost)}")
        reasons.append("primary actions " + " ".join(bits))

    is_pure_rename = renamed and len(reasons) == 1
    return reasons, is_pure_rename


def diff(base: Snapshot, head: Snapshot, *, min_support: int = DEFAULT_MIN_SUPPORT) -> DiffResult:
    res = DiffResult(app_id=head.app_id or base.app_id, base=base, head=head)

    if not base.screens:
        res.warnings.append(
            "Base snapshot has 0 screens — the base build is not mapped in Atlas. "
            "Everything in head shows as 'added'; pick a mapped base build or a cached baseline.")
    if not head.screens:
        res.warnings.append(
            "Head snapshot has 0 screens — the head build is not mapped in Atlas yet. "
            "Run an Atlas exploration against the head build before diffing.")

    matched, added, removed = _match_screens(base, head)
    res.added = sorted(added, key=lambda s: (-s.observation_count, s.product_area, s.name))
    res.removed = sorted(removed, key=lambda s: (-s.observation_count, s.product_area, s.name))
    added_ids = {s.id for s in res.added}
    removed_base_ids = {s.id for s in res.removed}
    base_to_head = {b: h for h, b in matched.items()}

    # significant out-edges per screen, in (target_screen_id_in_head_space) terms
    def sig_out_targets(snap: Snapshot, sid: str, remap: dict[str, str] | None) -> dict[str, Edge]:
        out: dict[str, Edge] = {}
        for e in snap.out_edges(sid):
            if not _significant(e, min_support):
                continue
            tgt = (remap or {}).get(e.target, e.target)
            out[tgt] = e
        return out

    # --- per-screen classification -------------------------------------
    for hid, bid in matched.items():
        hs, bs = head.screens[hid], base.screens[bid]
        struct, pure_rename = _structural_reasons(bs, hs)

        # nav wiring, compared in head-id space (remap base targets onto head)
        b_targets = sig_out_targets(base, bid, base_to_head)
        h_targets = sig_out_targets(head, hid, None)
        new_t = set(h_targets) - set(b_targets)
        gone_t = set(b_targets) - set(h_targets)

        to_new = [t for t in new_t if t in added_ids]
        # wiring to removed screens: read straight off base out-edges
        removed_wiring = [base.name_of(e.target)
                          for e in base.out_edges(bid)
                          if _significant(e, min_support) and e.target in removed_base_ids]

        wiring_reasons: list[str] = []
        for t in to_new:
            wiring_reasons.append(f"now navigates to new screen `{head.name_of(t)}`")
        for nm in sorted(set(removed_wiring)):
            wiring_reasons.append(f"no longer navigates to removed screen `{nm}`")

        net_nav = len(new_t) + len(gone_t)

        if pure_rename:
            res.renamed.append(ScreenChange(hid, hs.label, hs.product_area, struct, bid if bid != hid else None))
            continue

        reasons = struct + wiring_reasons
        if reasons:
            res.changed.append(ScreenChange(hid, hs.label, hs.product_area, reasons,
                                            bid if bid != hid else None, kind="changed"))
        elif net_nav >= NAV_CHURN_THRESHOLD:
            res.nav_churn.append(ScreenChange(
                hid, hs.label, hs.product_area,
                [f"{len(new_t)} new / {len(gone_t)} dropped navigation path(s) (likely exploration variance)"],
                None, kind="nav_churn"))
        # else: effectively unchanged

    res.added.sort(key=lambda s: (s.product_area, s.name))
    res.changed.sort(key=lambda c: (c.product_area, c.name))
    res.renamed.sort(key=lambda c: (c.product_area, c.name))
    res.nav_churn.sort(key=lambda c: (c.product_area, c.name))

    # --- edge-level diff (significant edges only, head ids in base space) ---
    base_sig = {(e.source, e.target): e for e in base.edges if _significant(e, min_support)}
    head_sig_in_base = set()
    for e in head.edges:
        if not _significant(e, min_support):
            continue
        bs_id = matched.get(e.source, e.source)
        bt_id = matched.get(e.target, e.target)
        head_sig_in_base.add((bs_id, bt_id))
        if (bs_id, bt_id) not in base_sig:
            res.edges_added.append(e)
    for key, e in base_sig.items():
        if key not in head_sig_in_base:
            res.edges_removed.append(e)

    # --- flows affected: named flows that traverse a changed/added/removed screen ---
    impact_ids = (res.changed_seed_ids & set(head.screens))
    for f in head.flows:
        hit = [n for n in f.route_node_ids if n in impact_ids]
        if hit:
            res.affected_flows.append({"id": f.id, "label": f.label, "area": f.area,
                                       "hit_screens": [head.name_of(n) for n in hit]})
    for f in base.flows:
        hit = [n for n in f.route_node_ids if n in removed_base_ids]
        if hit and not any(af["id"] == f.id for af in res.affected_flows):
            res.affected_flows.append({"id": f.id, "label": f.label, "area": f.area,
                                       "hit_screens": [base.name_of(n) for n in hit], "removed": True})

    # --- orphaned screens: still present in head but lost every inbound path,
    #     where a removed screen used to lead to them (a real downstream break) ---
    seen_orphans: set[str] = set()
    for rs in res.removed:
        for e in base.out_edges(rs.id):
            if not _significant(e, min_support):
                continue
            succ_head = base_to_head.get(e.target, e.target)
            if succ_head not in head.screens or succ_head in seen_orphans:
                continue
            if not any(_significant(ie, min_support) for ie in head.in_edges(succ_head)):
                seen_orphans.add(succ_head)
                res.orphaned_screens.append({
                    "id": succ_head, "name": head.name_of(succ_head),
                    "via_removed": rs.label,
                })

    # --- now-untested: new/changed screens no test reaches -------------
    review_ids = {s.id for s in res.added} | {c.screen_id for c in res.changed}
    for sid in sorted(review_ids):
        sc = head.screens.get(sid)
        if not sc:
            continue
        incoming = head.in_edges(sid)
        out = head.out_edges(sid)
        if not any(e.tested for e in incoming) and not any(e.tested for e in out):
            path_ids = head.shortest_path(sid)
            res.untested_screens.append({
                "id": sid, "name": sc.label, "product_area": sc.product_area,
                "status": "new" if sid in added_ids else "changed",
                "incoming_edges": len(incoming), "outgoing_edges": len(out),
                "reach_path": [head.name_of(p) for p in path_ids],
                "viewer_url": sc.viewer_url,
            })

    # --- lost coverage: tested in base, gone/untested in head ----------
    head_edge_by_key = {(matched.get(e.source, e.source), matched.get(e.target, e.target)): e
                        for e in head.edges}
    for e in base.edges:
        if not e.tested:
            continue
        he = head_edge_by_key.get((e.source, e.target))
        if he is None or not he.tested:
            res.lost_coverage_edges.append(e)

    return res
