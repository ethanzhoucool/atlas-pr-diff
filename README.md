# atlas-diff

A PR/CI bot built on Revyl **Atlas**.

Atlas auto-explores a mobile app and keeps a graph of its screens and the flows between them. On every PR, `atlas-diff` diffs that map between the base build and the PR build, then posts a review summary as a sticky PR comment plus a GitHub Check: what screens were added/changed/removed, what flows are affected downstream, what is possibly orphaned, what lost test coverage, and the headline signal — new/changed screens that **no test reaches**.

Stdlib-only Python 3 (no `pip install` of dependencies), so it runs anywhere in CI.

In a repo with a committed `.atlas-diff.yml`, the day-to-day command is just:

```bash
atlas-diff diff
```

App comes from config, base defaults to your committed baseline (or the git merge-base with the default branch), head defaults to the current git HEAD commit.

## What the comment looks like

```
🔴 Atlas map diff

New/changed screens are untested  ·  base main-512d672 → head main-20260522-105156

+9 new · ~5 changed · -1 removed · 1 flows affected · 2 untested

### 🔴 Now untested (2)
New or changed screens that no test reaches — the gap this PR introduces:
- uber_one_checkout · Account settings (added)
  - reach it: account_profile_hub → uber_one_membership_detail → uber_one_checkout
  - cover it: revyl test create --app "Ubert" then exercise this screen

### 🆕 New screens (9)
- uber_one_checkout (checkout) · Account settings — Review and confirm a subscription plan...
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

Every screen name in the real comment is a link to its Atlas viewer (a durable deep-link), so you can click straight to the screen. Untested screens also carry the reach-path that gets to them plus a "cover it" hint. Full sample: [`examples/sample-report.md`](examples/sample-report.md), with the structured JSON in [`examples/sample-result.json`](examples/sample-result.json).

## Install

Both paths are stdlib-only, so there is nothing to `pip install` beyond the command itself.

```bash
# install the atlas-diff command (ships a pyproject.toml)
pipx install git+https://github.com/ethanzhoucool/atlas-pr-diff
```

Or clone and run the wrapper script directly:

```bash
git clone https://github.com/ethanzhoucool/atlas-pr-diff
cd atlas-pr-diff
./atlas-diff diff        # same CLI, no install
```

### Prereqs

- Python 3 (stdlib only).
- The `revyl` CLI on `PATH` (or set `REVYL_BIN` to its path; default install is `~/.revyl/bin/revyl`).
- Revyl auth: `REVYL_API_KEY` in the env, or `~/.revyl/credentials.json`.

Everything shells out to `revyl`. The calls it relies on:

- `revyl atlas graph --app <id> --build <ref> --json` — the Atlas map at one build.
- `revyl build list --app <id> --json` — uploaded builds, each carrying `.metadata.git.{commit, commit_short, branch, message}`. That git metadata is how a PR commit/branch joins to a Revyl build.
- `revyl ping` — auth check used by `doctor`.

Run `atlas-diff doctor` first to confirm all of this is wired up (see below).

## Quickstart

### Zero-config (the happy path)

In a repo that has a committed `.atlas-diff.yml`, no flags are needed:

```bash
atlas-diff diff
```

- **app** comes from `app:` in config.
- **base** comes from `baseline:` (or `base:`) in config; if neither is set and you are in a git repo, it falls back to the git merge-base between HEAD and the default branch.
- **head** defaults to the current git HEAD commit (`commit:<sha>`), resolved to its Revyl build.

You only pass flags when you want to override one of these.

### Explicit

```bash
# diff two builds by version
atlas-diff diff --app Ubert --base main-512d672 --head main-20260522-105156

# diff the PR commit against a committed baseline file, write the PR comment
atlas-diff diff --app Ubert \
  --base atlas-baseline.json --head commit:4138aac \
  --md report.md

# download new/changed screen images and embed thumbnails for local review
atlas-diff diff --app Ubert --base atlas-baseline.json --head commit:4138aac \
  --md report.md --screenshot-dir shots/

# save a baseline snapshot of main for later comparison
atlas-diff snapshot --app Ubert --build branch:main -o atlas-baseline.json

# what build does this commit map to?
atlas-diff resolve --app Ubert --commit 4138aac

# list apps that have an Atlas
atlas-diff apps
```

(If you cloned instead of installing, swap `atlas-diff` for `./atlas-diff` or `python -m atlas_diff`.)

### Ref forms

`--base` / `--head` (and `snapshot --build`) accept:

- a build version (`main-20260522-105156`)
- `latest` or `all`
- `commit:<sha>` or a bare 7–40 char git sha
- `branch:<name>`
- a path to a `.json` snapshot file (a committed baseline)

Commit and branch refs are resolved to a build by matching `.metadata.git` from `revyl build list`.

### Screenshots

`--screenshot-dir <dir>` tells Revyl to download new/changed screen images into that directory and embeds them as thumbnails in the report. Thumbnails render when the Markdown is viewed locally or as a CI artifact; the sticky PR comment cannot host local image files, so it relies on the durable Atlas viewer links instead (which are always present, with or without `--screenshot-dir`).

## CI usage

### Onboard a repo: `init`

The recommended way to set up a repo is one command:

```bash
atlas-diff init --app Ubert
```

It scaffolds two files in the project root:

- `.atlas-diff.yml` — the config (app, baseline, fail_on, min_support).
- `.github/workflows/atlas-diff.yml` — a ready-to-run PR workflow.

Add `--snapshot` to also capture the baseline from `main` right now:

```bash
atlas-diff init --app Ubert --snapshot
```

Other `init` flags: `--dir <path>` (project root, default `.`), `--baseline <path>` (default `atlas-baseline.json`), `--force` (overwrite existing files). Without `--snapshot`, it prints the `snapshot` command to run next.

### The GitHub Action

The scaffolded workflow uses the composite Action in [`github/`](github/) (`action.yml` + `post_check.py`); there is also a copy-paste workflow in [`github/workflow-example.yml`](github/workflow-example.yml). On a PR the Action:

- runs `diff` for the PR build,
- posts/updates one **sticky comment** (found by the `<!-- atlas-pr-diff -->` marker, so reruns edit in place instead of stacking),
- sets a **GitHub Check** whose conclusion follows the exit code.

### Check conclusions

- 🟢 no map changes → success
- 🟡 map changed → success or failure, depending on `--fail-on`
- 🔴 new/changed screens are untested → failure under the default gate
- ⚠️ Atlas data missing → **neutral** (not a failure). The head build has no Atlas map yet; the comment tells you to run an exploration.

The neutral case matters: a PR is never failed just because its build has not been Atlas-explored yet.

### Handling exploration lag: `--wait-for-map`

A build only has Atlas data after an exploration runs against it, and in CI that can lag the upload by a bit. Instead of failing on an empty head map, point the diff at the head build and let it poll:

```bash
atlas-diff diff --wait-for-map --wait-timeout 600
```

`--wait-for-map` polls the head build until it has a mapped Atlas (>0 screens) or the timeout elapses (`--wait-timeout`, default 300s; also settable as `wait_timeout` in config). This only applies when head resolves to a live build, not a `.json` baseline file.

### Committed-baseline pattern (recommended)

Each Atlas map comes from an independent exploration, so `main`'s map drifts a little every time it re-explores. To keep PR diffs deterministic, diff against a checked-in file instead of live `main`:

```bash
# once, and whenever you want to move the baseline forward
atlas-diff snapshot --app Ubert --build branch:main -o atlas-baseline.json
git add atlas-baseline.json && git commit -m "atlas baseline"
```

`init` wires `baseline:` to this file by default, so PRs diff against it automatically and the comparison no longer moves under you when main re-explores. `doctor` warns when the committed baseline is more than 30 days old.

## How the diff works

### Signals it reports

- **New screens** — screens in head with no match in base.
- **Changed screens** — a matched screen whose semantics changed (kind, product area, description, primary actions) or that now wires to a brand-new / removed screen. Each comes with the reasons.
- **Renamed** — a screen whose only change is its name.
- **Removed / no longer reached** — screens in base with no match in head.
- **Flows affected downstream** — named Atlas flows whose route passes through an added/changed/removed screen.
- **Possibly orphaned** — screens still in the app that lost their only inbound path because the screen that led to them was removed.
- **Lost test coverage** — edges a test traversed in base but not in head.
- **Now untested** — new/changed screens that no test reaches (no test-backed in/out edge). This is the headline signal and what the default CI gate fires on. Each untested screen shows the reach-path (entry → … → screen) and a "cover it" hint pointing at `revyl test create`.

Screens are matched first by canonical Atlas id, then leftovers by normalized name + product area (so an id churn does not look like a delete-plus-add).

Long sections auto-collapse into `<details>` blocks so a big PR does not produce a wall of text.

### The noise filtering (the reason it is usable)

Each build's map is produced by an independent BFS exploration that takes slightly different paths each run. A naive map diff reports dozens of bogus "changed" screens that differ only by one fluke navigation edge. `atlas-diff` suppresses that two ways:

1. **Low-support edges are ignored.** An edge only counts if a test or report backs it, or it was observed at least `min_support` times (default `2`). One-off exploration edges drop out.
2. **High-signal change is split from nav churn.** A screen is *changed* only if its semantics changed or it wires to a new/removed screen. Screens whose only delta is rerouting noise are bucketed as **nav churn** and kept out of the headline — surfaced as a small "N more screens differ only by low-confidence navigation noise" note.

On the real Ubert example this collapsed 38 spurious "changed" screens down to 5 real ones.

`min_support` is tunable per run with `--min-support` or per repo with `min_support:` in config.

## Config reference

`.atlas-diff.yml` is a **flat** `key: value` file. It is parsed with no YAML dependency, so only top-level scalars are read — no nesting, no lists. `.atlas-diff.json` works too (also `.atlas-diff.yaml`, `atlas-diff.yml`). The file is found by walking up from the working directory.

| Key | Maps to | Notes |
|---|---|---|
| `app` | `--app` | app name or id |
| `baseline` | `--base` | a committed `.json` snapshot path; the most deterministic base |
| `base` | `--base` | fallback if `baseline` is unset |
| `head` | `--head` | rarely set; head usually comes from git HEAD |
| `fail_on` | `--fail-on` | `untested` (default) / `changes` / `none` |
| `title` | `--title` | report title |
| `limit` | `--limit` | max screens fetched per build (default 500) |
| `min_support` | `--min-support` | ignore edges seen fewer than N times (default 2) |
| `wait_timeout` | `--wait-timeout` | seconds to wait under `--wait-for-map` (default 300) |

Dashed key spellings (`fail-on`, `min-support`, `wait-timeout`) are accepted and normalized. A command-line flag always overrides the config value. Example:

```yaml
# atlas-pr-diff config. Flat key: value only (no nesting).
app: Ubert
baseline: atlas-baseline.json
fail_on: untested
min_support: 2
```

## `doctor`

Run a preflight before wiring up CI:

```bash
atlas-diff doctor
```

It checks the `revyl` CLI is present, auth works, a config was found, the app's Atlas is mapped, and the committed baseline is fresh. Example output:

```
  ✓ revyl CLI: /Users/you/.revyl/bin/revyl
  ✓ Revyl auth: ok
  ✓ config: /repo/.atlas-diff.yml
  ✓ Atlas for 'Ubert': 54 mapped screen(s)
  ✓ baseline atlas-baseline.json: 4d old
  ✓ git repo: yes
```

Only the critical checks (revyl missing or auth failed) make `doctor` exit non-zero; a missing config, unmapped app, or stale baseline are flagged with a ✗ but still exit 0 so it is safe to run anywhere.

## Command reference

### `diff`
Diff the Atlas map between two builds.

| Flag | Default | Notes |
|---|---|---|
| `--app` | config | app name or id |
| `--base` | config baseline / git merge-base | baseline ref (see ref forms) |
| `--head` | current git HEAD commit | head ref |
| `--md PATH` | — | write the Markdown PR comment |
| `--json-out PATH` | — | write the structured JSON result |
| `--screenshot-dir DIR` | — | download new/changed screen images here and embed thumbnails |
| `--title` | `Atlas map diff` | report title |
| `--limit` | `500` | max screens fetched per build |
| `--min-support N` | `2` | ignore edges seen fewer than N times |
| `--wait-for-map` | off | poll until the head build is mapped |
| `--wait-timeout N` | `300` | seconds to wait under `--wait-for-map` |
| `--fail-on` | `untested` | `none` / `untested` / `changes` |
| `-q`, `--quiet` | off | suppress the terminal summary |

A global `--config PATH` (before the subcommand) points at a specific config file instead of searching for one.

### `snapshot`
Save a build's Atlas map as a cached baseline `.json`.

| Flag | Default | Notes |
|---|---|---|
| `--app` | config | |
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

### `init`
Scaffold `.atlas-diff.yml` + `.github/workflows/atlas-diff.yml`.

| Flag | Default | Notes |
|---|---|---|
| `--app` | config | app name or id (written into config) |
| `--dir` | `.` | project root |
| `--baseline` | `atlas-baseline.json` | baseline snapshot path |
| `--snapshot` | off | also snapshot `main` now as the baseline |
| `--force` | off | overwrite existing files |

### `doctor`
Preflight checks (auth, config, app mapped, baseline freshness). `--app` overrides the config app.

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

## Limitations / known issues

- **Exploration is a prerequisite.** A build only has Atlas data after an exploration has run against it. The PR build must be uploaded to Revyl **and** Atlas-explored before the bot can diff it. Otherwise the head shows 0 screens, the verdict is "Atlas data missing", and the GitHub check goes **neutral** with a message to run exploration. There is no CLI to trigger exploration — it is an upstream step (the production exploration trigger / app-explorer), not part of this tool. `--wait-for-map` bridges the lag when the explore runs but lands a little after the upload; it cannot start an exploration on its own.
- **Diff quality is bounded by exploration coverage.** Each map is one shallow BFS pass, so a screen or flow the exploration never reached will not appear, on either side. The diff can only compare what was mapped.
- **The noise heuristics are tunable, not perfect.** `min_support` (and the internal nav-churn threshold) trade false "changed" against missed real changes. Bump `min_support` on a noisy app; lower it if real low-traffic changes get hidden.
- **PR-comment thumbnails.** `--screenshot-dir` thumbnails render when the report is viewed locally or as a CI artifact, not inside the sticky PR comment (which has no host for local files). The durable Atlas viewer links cover the in-comment case.

---

Author: Ethan (Revyl).
