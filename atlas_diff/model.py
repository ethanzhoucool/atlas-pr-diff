"""Normalize a raw `atlas graph` payload into a stable Snapshot.

The raw payload has dozens of fields per node; we keep the ones that define a
screen's *identity* and *behavior* so the diff is meaningful and not noisy.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any


def _norm_text(s: str | None) -> str:
    return " ".join((s or "").split()).strip().lower()


ATLAS_VIEWER = "https://app.revyl.ai/apps/{app}/atlas?focus=screen&entityId={sid}"


@dataclass
class Screen:
    id: str
    name: str                      # semantic_name / display_name (snake_case)
    product_area: str
    screen_kind: str
    description: str
    observation_count: int
    is_entry_point: bool
    is_hub: bool
    is_terminal: bool
    primary_actions: list[str]
    screenshot_key: str | None
    viewer_url: str | None = None          # durable deep-link into the Atlas viewer
    local_screenshot_path: str | None = None
    raw: dict = field(default_factory=dict, repr=False)

    @property
    def label(self) -> str:
        return self.name or self.id[:8]

    def fingerprint(self, out_edges: list["Edge"]) -> str:
        """Hash of the screen's behavior. Changes when the screen meaningfully
        changes: kind, description, primary actions, or where it navigates."""
        nav = sorted(
            f"{_norm_text(e.action_label)}->{e.target}" for e in out_edges
        )
        parts = [
            self.screen_kind,
            _norm_text(self.description),
            "|".join(sorted(_norm_text(a) for a in self.primary_actions)),
            "|".join(nav),
        ]
        return hashlib.sha1("␟".join(parts).encode()).hexdigest()[:12]


@dataclass
class Edge:
    source: str
    target: str
    action_label: str
    action_type: str
    observation_count: int
    test_support: int
    report_support: int
    session_support: int

    @property
    def key(self) -> tuple[str, str]:
        return (self.source, self.target)

    @property
    def tested(self) -> bool:
        return self.test_support > 0


@dataclass
class Flow:
    id: str
    label: str
    area: str
    route_node_ids: list[str]


@dataclass
class Snapshot:
    app_id: str
    build_id: str | None
    build_version: str | None
    git: dict
    screens: dict[str, Screen]            # keyed by screen id
    edges: list[Edge]
    flows: list[Flow]
    stats: dict
    source: str = "live"                  # "live" or "snapshot-file"

    # --- graph helpers -------------------------------------------------
    def out_edges(self, screen_id: str) -> list[Edge]:
        return [e for e in self.edges if e.source == screen_id]

    def in_edges(self, screen_id: str) -> list[Edge]:
        return [e for e in self.edges if e.target == screen_id]

    def reachable_from(self, seeds: set[str]) -> set[str]:
        """Forward BFS over edges: every screen reachable from `seeds`."""
        seen = set(seeds)
        stack = list(seeds)
        adj: dict[str, list[str]] = {}
        for e in self.edges:
            adj.setdefault(e.source, []).append(e.target)
        while stack:
            cur = stack.pop()
            for nxt in adj.get(cur, []):
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        return seen

    def name_of(self, screen_id: str) -> str:
        sc = self.screens.get(screen_id)
        return sc.label if sc else screen_id[:8]

    def viewer_of(self, screen_id: str) -> str | None:
        sc = self.screens.get(screen_id)
        return sc.viewer_url if sc else None

    def entry_points(self) -> list[str]:
        eps = [s.id for s in self.screens.values() if s.is_entry_point]
        if eps:
            return eps
        targeted = {e.target for e in self.edges}
        roots = [sid for sid in self.screens if sid not in targeted]
        return roots or list(self.screens)[:1]

    def shortest_path(self, target: str, sources: list[str] | None = None) -> list[str]:
        """BFS shortest path (list of screen ids) from any entry point to
        `target`. Empty if unreachable."""
        if target not in self.screens:
            return []
        sources = sources or self.entry_points()
        if target in sources:
            return [target]
        adj: dict[str, list[str]] = {}
        for e in self.edges:
            adj.setdefault(e.source, []).append(e.target)
        prev: dict[str, str] = {}
        seen = set(sources)
        queue = list(sources)
        while queue:
            cur = queue.pop(0)
            for nxt in adj.get(cur, []):
                if nxt in seen:
                    continue
                seen.add(nxt)
                prev[nxt] = cur
                if nxt == target:
                    path = [target]
                    while path[-1] in prev:
                        path.append(prev[path[-1]])
                    return list(reversed(path))
                queue.append(nxt)
        return []

    # --- serialization (for cached baselines) --------------------------
    def to_dict(self) -> dict:
        return {
            "_atlas_diff_snapshot": 1,
            "app_id": self.app_id,
            "build_id": self.build_id,
            "build_version": self.build_version,
            "git": self.git,
            "stats": self.stats,
            "screens": [s.raw for s in self.screens.values()],
            "edges": [
                {
                    "source_entity_id": e.source,
                    "target_entity_id": e.target,
                    "action_label": e.action_label,
                    "action_type": e.action_type,
                    "observation_count": e.observation_count,
                    "test_support": e.test_support,
                    "report_support": e.report_support,
                    "session_support": e.session_support,
                }
                for e in self.edges
            ],
            "flows": [
                {"id": f.id, "label": f.label, "area": f.area,
                 "route_node_ids": f.route_node_ids}
                for f in self.flows
            ],
        }

    def save(self, path: str) -> None:
        with open(path, "w") as fh:
            json.dump(self.to_dict(), fh, indent=2)


def _screen_from_node(n: dict, app_id: str = "") -> Screen:
    sid = n.get("id") or n.get("canonical_entity_id") or n.get("semantic_root_entity_id")
    viewer = n.get("viewer_url")
    if not viewer and app_id and sid:
        viewer = ATLAS_VIEWER.format(app=app_id, sid=sid)
    return Screen(
        id=sid,
        name=n.get("semantic_name") or n.get("display_name") or n.get("label") or "",
        product_area=n.get("product_area") or n.get("product_area_key") or "",
        screen_kind=n.get("screen_kind") or n.get("semantic_screen_type") or "",
        description=n.get("semantic_description") or n.get("semantic_summary") or "",
        observation_count=int(n.get("observation_count") or 0),
        is_entry_point=bool(n.get("is_entry_point")),
        is_hub=bool(n.get("is_hub")),
        is_terminal=bool(n.get("is_terminal")),
        primary_actions=list(n.get("primary_actions") or []),
        screenshot_key=n.get("screenshot_s3_key"),
        viewer_url=viewer,
        local_screenshot_path=n.get("local_screenshot_path"),
        raw=n,
    )


def _edge_from_raw(e: dict) -> Edge:
    return Edge(
        source=e.get("source_entity_id") or e.get("source"),
        target=e.get("target_entity_id") or e.get("target"),
        action_label=e.get("action_label") or e.get("label") or "",
        action_type=e.get("action_type") or "tap",
        observation_count=int(e.get("observation_count") or 0),
        test_support=int(e.get("test_support") or 0),
        report_support=int(e.get("report_support") or 0),
        session_support=int(e.get("session_support") or 0),
    )


def from_graph_payload(payload: dict, *, build_version: str | None = None,
                       git: dict | None = None, source: str = "live") -> Snapshot:
    nodes = payload.get("nodes") or []
    raw_edges = payload.get("edges") or payload.get("primary_edges") or payload.get("map_edges") or []
    raw_flows = payload.get("flows") or []
    proj = payload.get("projection") or {}

    app_id = payload.get("app_id") or ""
    screens: dict[str, Screen] = {}
    for n in nodes:
        sc = _screen_from_node(n, app_id)
        if sc.id:
            screens[sc.id] = sc

    edges = [_edge_from_raw(e) for e in raw_edges if (e.get("source_entity_id") or e.get("source"))]

    flows = [
        Flow(
            id=f.get("id") or f.get("node_id") or "",
            label=f.get("label") or f.get("path_label") or "",
            area=f.get("area") or "",
            route_node_ids=list(f.get("route_node_ids") or f.get("node_ids") or []),
        )
        for f in raw_flows
    ]

    return Snapshot(
        app_id=payload.get("app_id") or "",
        build_id=proj.get("requested_build_id") or proj.get("query_build_id")
                 or (payload.get("structure") or {}).get("build_id") or payload.get("build_id"),
        build_version=build_version,
        git=git or {},
        screens=screens,
        edges=edges,
        flows=flows,
        stats=payload.get("stats") or {},
        source=source,
    )


def from_snapshot_file(path: str) -> Snapshot:
    with open(path) as fh:
        data = json.load(fh)
    payload = {
        "app_id": data.get("app_id"),
        "nodes": data.get("screens") or [],
        "edges": data.get("edges") or [],
        "flows": data.get("flows") or [],
        "stats": data.get("stats") or {},
        "projection": {"requested_build_id": data.get("build_id")},
    }
    return from_graph_payload(
        payload, build_version=data.get("build_version"),
        git=data.get("git") or {}, source="snapshot-file",
    )
