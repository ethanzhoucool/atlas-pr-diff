# atlas-diff

A PR/CI bot built on Revyl **Atlas**.

Atlas auto-explores a mobile app and keeps a graph of its screens and the flows between them. On every PR, `atlas-diff` diffs that map between the base build and the PR build, then posts a review summary as a sticky PR comment plus a GitHub Check: what screens were added/changed/removed, what flows are affected downstream, and what is now untested.

Stdlib-only Python 3 (no `pip install`), so it runs anywhere in CI.

## What the comment looks like

```
🟡 Atlas map diff

Map changed — review impact  ·  base main-512d672 → head main-20260522-105156

+9 new · ~5 changed · -1 removed · 1 flows affected · 0 untested

### 🆕 New screens (9)
- uber_one_checkout (checkout) · Account settings — Review and confirm a subscription plan...
- package_pickup_details_form (form) · Commerce — Capture the pickup address and driver instructions...
- ride_receipt_rating (checkout) · Home — Trip summary including cost and distance, plus rate and tip...

### ✏️ Changed screens (5)
- account_profile_hub · Account settings
  - now navigates to new screen uber_one_membership_detail
- ride_service_selection · Home
  - no longer navigates to removed screen ride_matching_status

### 🗑️ Removed / no longer reached (1)
- ride_matching_status (loading) · Home

### 🔀 Flows affected downstream (1)
- Select a ride — touches ride_destination_search_results, ride_service_selection

### 📉 Lost test coverage (7)
- ride_service_selection → ride_matching_status (Device action: tap)
- ...

🗺️ atlas-pr-diff · 15 screen deltas · base 46 → head 54 screens
```

Full sample: [`examples/sample-report.md`](examples/sample-report.md), with the structured JSON in [`examples/sample-result.json`](examples/sample-result.json).

## Install / prereqs

- Python 3 (stdlib only, nothing to install).
- The `revyl` CLI on `PATH` (or set `REVYL_BIN` to its path; default install is `~/.revyl/bin/revyl`).
- Revyl auth: `REVYL_API_KEY` in the env, or `~/.revyl/credentials.json`.

Everything shells out to `revyl`. The two calls it relies on:

- `revyl atlas graph --app <id> --build <ref> --json` — the Atlas map at one build.
- `revyl build list --app <id> --json` — uploaded builds, each carrying `.metadata.git.{commit, commit_short, branch, message}`. That git metadata is how a PR commit/branch joins to a Revyl build.

Run it as a module:

```bash
python -m atlas_diff diff --app Ubert --base latest --head main-20260522-105156
```

## Quickstart (local)

```bash
# diff two builds by version
python -m atlas_diff diff --app Ubert \
  --base main-512d672 --head main-20260522-105156

# diff the PR commit against a committed baseline file, write the PR comment
python -m atlas_diff diff --app Ubert \
  --base atlas-baseline.json --head commit:4138aac \
  --md report.md

# save a baseline snapshot of main for later comparison
python -m atlas_diff snapshot --app Ubert --build branch:main -o atlas-baseline.json

# what build does this commit map to?
python -m atlas_diff resolve --app Ubert --commit 4138aac

# list apps that have an Atlas
python -m atlas_diff apps
```

### Ref forms

`--base` / `--head` (and `snapshot --build`) accept:

- a build version (`main-20260522-105156`)
- `latest` or `all`
- `commit:<sha>` or a bare 7–40 char git sha
- `branch:<name>`
- a path to a `.json` snapshot file (a committed baseline)

Commit and branch refs are resolved to a build by matching `.metadata.git` from `revyl build list`.

## CI usage

There is a composite GitHub Action in [`github/`](github/) (`action.yml` + `post_check.py`) and a copy-paste workflow in [`github/workflow-example.yml`](github/workflow-example.yml). On a PR the Action:

- runs `diff` for the PR build,
- posts/updates one **sticky comment** (found by the `<!-- atlas-pr-diff -->` marker, so reruns edit in place instead of stacking),
- sets a **GitHub Check** whose conclusion follows the exit code.

### Check conclusions

The verdict maps to a check conclusion:

- 🟢 no map changes → success
- 🟡 map changed → success or failure, depending on `--fail-on`
- 🔴 new/changed screens are untested → failure under the default gate
- ⚠️ Atlas data missing → **neutral** (not a failure). The head build has no Atlas map yet; the comment tells you to run an exploration.

### Committed-baseline pattern (recommended)

Each Atlas map comes from an independent exploration, so `main`'s map drifts a little every time it re-explores. To keep PR diffs deterministic, diff against a checked-in file instead of live `main`:

```bash
# once, and whenever you want to move the baseline forward
python -m atlas_diff snapshot --app Ubert --build branch:main -o atlas-baseline.json
git add atlas-baseline.json && git commit -m "atlas baseline"
```

Then PRs diff with `--base atlas-baseline.json`. The comparison no longer moves under you when main re-explores.

## How the diff works

### Signals it reports

- **New screens** — screens in head with no match in base.
- **Changed screens** — a matched screen whose semantics changed (kind, product area, description, primary actions) or that now wires to a brand-new / removed screen. Each comes with the reasons.
- **Renamed** — a screen whose only change is its name.
- **Removed / no longer reached** — screens in base with no match in head.
- **Flows affected downstream** — named Atlas flows whose route passes through an added/changed/removed screen.
- **Possibly orphaned** — screens still in the app that lost their only inbound path because the screen that led to them was removed.
- **Lost test coverage** — edges a test traversed in base but not in head.
- **Now untested** — new/changed screens that no test reaches (no test-backed in/out edge). This is what the default CI gate fires on.

Screens are matched first by canonical Atlas id, then leftovers by normalized name + product area (so an id churn does not look like a delete-plus-add).

### The noise filtering (the reason it is usable)

Each build's map is produced by an independent BFS exploration that takes slightly different paths each run. A naive map diff reports dozens of bogus "changed" screens that differ only by one fluke navigation edge. `atlas-diff` suppresses that two ways:

1. **Low-support edges are ignored.** An edge only counts if a test or report backs it, or it was observed at least `min_support` times (`DEFAULT_MIN_SUPPORT = 2`). One-off exploration edges drop out.
2. **High-signal change is split from nav churn.** A screen is *changed* only if its semantics changed or it wires to a new/removed screen. Screens whose only delta is rerouting noise are bucketed as **nav churn** (when net nav deltas reach `NAV_CHURN_THRESHOLD = 3`) and kept out of the headline — surfaced as a small "N more screens differ only by low-confidence navigation noise" note.

On the real Ubert example this collapsed 38 spurious "changed" screens down to 5 real ones.

Both constants live in [`atlas_diff/diff.py`](atlas_diff/diff.py) and are tunable.

## Exit codes / the CI gate

`--fail-on` decides when `diff` exits non-zero:

- `untested` (default) — fail only when the PR adds/changes screens that **no test reaches**.
- `changes` — fail on any map change.
- `none` — never fail.

Codes:

- `0` — passed (or `--fail-on none`).
- `1` — the gate tripped (untested screens, or any change under `--fail-on changes`).
- `2` — `resolve` found no matching build.
- `3` — a `revyl` CLI error (binary missing, auth, bad output).

## Command reference

### `diff`
Diff the Atlas map between two builds.

| Flag | Default | Notes |
|---|---|---|
| `--app` | required | app name or id |
| `--base` | required | baseline ref (see ref forms) |
| `--head` | required | head ref |
| `--md PATH` | — | write the Markdown PR comment |
| `--json-out PATH` | — | write the structured JSON result |
| `--title` | `Atlas map diff` | report title |
| `--limit` | `500` | max screens fetched per build |
| `--fail-on` | `untested` | `none` / `untested` / `changes` |
| `-q`, `--quiet` | off | suppress the terminal summary |

### `snapshot`
Save a build's Atlas map as a cached baseline `.json`.

| Flag | Default | Notes |
|---|---|---|
| `--app` | required | |
| `--build` | `latest` | any ref form |
| `-o`, `--output` | required | output `.json` path |
| `--limit` | `500` | |

### `resolve`
Resolve a commit or branch to its Revyl build. Prints the build version, or full JSON with `--json`.

| Flag | Notes |
|---|---|
| `--app` | required |
| `--commit` | git sha (full or short) |
| `--branch` | branch name |
| `--json` | emit `{id, version, commit, branch, uploaded_at}` |

### `apps`
List apps that have an Atlas. `--json` for raw output.

## Limitations / known issues

- **Exploration is a prerequisite.** A build only has Atlas data after an exploration has run against it. The PR build must be uploaded to Revyl **and** Atlas-explored before the bot can diff it. Otherwise the head shows 0 screens, the verdict is "Atlas data missing", and the GitHub check goes **neutral** with a message to run exploration. There is no CLI to trigger exploration — it is an upstream step (the production exploration trigger / app-explorer), not part of this tool.
- **Diff quality is bounded by exploration coverage.** Each map is one shallow BFS pass, so a screen or flow the exploration never reached will not appear, on either side. The diff can only compare what was mapped.
- **The noise heuristics are tunable, not perfect.** `DEFAULT_MIN_SUPPORT` and `NAV_CHURN_THRESHOLD` trade off false "changed" against missed real changes. Bump them on a noisy app; lower them if real low-traffic changes get hidden.

---

Author: Ethan (Revyl).
