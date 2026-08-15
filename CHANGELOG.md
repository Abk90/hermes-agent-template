# Changelog

Release notes for this Railway template. The user-facing copy of this lives in
the admin UI under **What's New** (`templates/index.html`) — the two are kept in
sync; see `CLAUDE.md` → *Release workflow*.

**Branch naming:** `release/<hermes-version>/<n>`. `/1` is where that Hermes
version first landed; `/2`, `/3` … are template-only fixes on top of it. The
Hermes version never changes within a series. `main` always holds the newest
release.

---

## release/v2026.8.13/1 — August 15, 2026
**Hermes v2026.8.13 · major (Hermes upgrade, from v2026.8.3)**

### Hermes update
- Hermes Agent **v2026.8.3 → v2026.8.13** — community plugin catalogue, Kanban
  review workflows, and a new **Actual Computer** provider (`ACTUAL_API_KEY`,
  added to `ENV_VARS` and `HERMES_PROVIDER_IDS`). All 22 existing provider-id
  mappings re-verified against the new `PROVIDER_REGISTRY`; none renamed.
- **cgroup-aware agent-cache shedding** (`agent.agent_cache.memory_high_mb:
  auto`, on by default) reads the container's memory limit and evicts LRU
  transcripts before the OOM killer fires — it directly reduces the respawn
  cycle invariant 6 exists to survive.
- **PDF / legacy-Office `read_file`** via `firecrawl-anydoc`, baked into the
  image (see below).

### Changes to support upstream updates
- **`browser.backend` pinned to `off`.** Upstream's new default (`""`) means
  "use Browser Use mode whenever the browser-use CLI is runnable", and
  `_find_cli()` counts a bare `uvx` — which our base image
  (`ghcr.io/astral-sh/uv`) ships. Verified in the built image:
  `is_browser_use_cli_mode()` was `True`, which hides the whole `browser_*`
  surface behind a single `browser_exec` that shells `uvx browser-use` and then
  needs a Chrome this image does not contain. Also verified on **both** the
  v2026.8.3 and v2026.8.13 images that `check_browser_requirements()` is
  already `False` here (no Chromium), so nothing working was lost either way —
  the pin just stops the model being handed a tool that cannot succeed.
  `setdefault`, so an explicit choice in hermes' own settings still wins.
- **`firecrawl-anydoc==0.1.6` baked in.** It is a *lazy* dep
  (`tools/lazy_deps.py` → `tool.doc_extract`), not an extra, so it cannot go in
  the Dockerfile's `.[...]` string; without it the first PDF read pip-installs
  mid-turn into an image that is wiped on every redeploy, retrying only every
  300s while the file reads as binary garbage. Installed from `/` — from
  `/opt/hermes-agent`, uv reads that pyproject's `exclude-newer="14 days"` and
  rejects the package as too new.
- **Pause (ESTOP) surfaced.** v2026.8.13 added `hermes pause` / the in-chat
  `/pause`, which writes `$HERMES_HOME/ESTOP` and makes hermes refuse every new
  turn while the process stays alive — `/health` 200, gateway "running",
  platform online. It is on the volume, so it survives a redeploy, and `/pause`
  is `gateway_only` with no owner gate. `/setup/api/status` now reports
  `paused`, the header shows it, and the Status panel offers **Resume**
  (`POST /setup/api/pause/resume`).
- **`hermes backup` rc 2 handled.** Upstream added a cross-process flock with a
  0.25s acquire timeout and `SystemExit(2)` on contention. Our own
  `backup_lock` cannot prevent it — hermes' snapshot path is reachable
  independently (e.g. `/snapshot` in the proxied Chat tab). Reported as a 409
  "another backup is running, try again" instead of a 500; on the restore path
  this previously surfaced as "the backup command failed", which reads as data
  loss for a quarter-second collision.
- **Install-on-enable logged.** `PUT /api/tools/toolsets/<name>` now spawns
  `hermes tools post-setup` on enable, on a verb the existing warning never
  watched. Deliberately log-only: the one registered predicate today
  (`cua_driver`) installs to `~/.local/bin`, and `HOME=/data`, so it most
  likely lands on the volume — firing the "this will be wiped" notice would
  misinform. The log line was the part that was actually missing.
- **Backup completeness generalised** from `state.db` to every `*.db` on the
  volume (v2026.8.13 adds `cron/notepad.db`; `kanban.db` and
  `cron/executions.db` already existed), mirroring hermes' own `_EXCLUDED_DIRS`
  so it can never demand a file hermes deliberately skips — a false positive
  here aborts a restore.

### Bug fixes
- **A restored `.env` could kill the dashboard permanently.** v2026.8.13's new
  `_start_parent_death_watchdog()` is not gated on `HERMES_DESKTOP`, so a
  `HERMES_PARENT_PID` naming a dead process makes `hermes dashboard`
  `os._exit(0)` seconds after spawn — and unlike `Gateway`, `Dashboard` has no
  respawn supervisor, so every proxied page 503s until the container is
  redeployed. Reproduced locally, then fixed: `build_hermes_env()` drops the
  key (covers a Railway service variable) **and** `_sanitize_env_file()` strips
  it from `$HERMES_HOME/.env` at boot and after a restore — the pop alone is
  not enough, because hermes loads that file into its own `os.environ`.
- **Stale `.partial` backup files swept.** Upstream made `hermes backup -o`
  atomic via a dot-prefixed `.partial` sibling, which no existing cleanup
  matched (`pre-restore-*.zip` never matches a dotted name), so a backup killed
  mid-write leaked a file forever. Swept at boot with a 1-hour age guard so it
  cannot race an in-flight backup.

---

## release/v2026.8.3/1 — August 8, 2026
**Hermes v2026.8.3 · major (Hermes upgrade, from v2026.7.20)**

### Hermes update
- Hermes Agent **v2026.7.20 → v2026.8.3**, covering two upstream releases
  (v2026.7.30 and v2026.8.3) — adds video generation tools, the Vercel AI
  Gateway and Vertex providers, outbound webhooks, and gateway health
  monitoring.
- **Fewer out-of-memory restarts** — Hermes now returns unused memory to the OS
  as it runs (`agent.memory_trim`, on by default).
- **An interrupted message is retried automatically** — a turn killed mid-answer
  by an OOM or a redeploy is re-run on the next boot. Left enabled; a message
  with real-world side effects will therefore be carried out twice.

### Changes to support upstream updates
- **Restart no longer parks the bot** — upstream added
  `agent.restart_after_turn_timeout` (default 21600s) so `/restart` defers until
  the active turn finishes. A wedged turn leaves the bot alive, healthy and
  refusing every message for up to six hours, invisibly to the supervisor.
  `HERMES_RESTART_AFTER_TURN_TIMEOUT=0` restores the immediate drain; it covers
  the in-band `/restart`, SIGUSR1 and the dashboard's own detached restart.
- **WebSocket frame size matched** — upstream set `ws_max_size` to 384 MB while
  both of our hops sat on lower library defaults (1 MB inbound from hermes,
  16 MB from the browser), so oversized frames dropped the Chat/PTY socket with
  nothing in the logs. Mirrored on both legs.
- **Loop watchdog kept on** — upstream's new watchdog exits 75 after ~2 min of a
  stalled event loop. Deliberately left enabled: the supervisor already treats
  exit 75 as a clean restart. Note it can now end a very long turn.
- **Build pinned** — upstream's new `.npmrc` sets `engine-strict=true`, turning
  the Node/npm engine range into a hard build failure (stay on setup_22.x), and
  a new `setup.py` blocks non-editable installs, making the Dockerfile's `-e`
  load-bearing. Both documented in place.

### Improvements
- **Install warning now covers the Tools tab.** `POST /api/tools/toolsets/<name>/post-setup`
  installs into the container exactly like the memory-provider button but
  shipped with no notice. Both now warn, and both are logged. MCP catalog
  installs are deliberately excluded — those land on the volume and do survive.

---

## release/v2026.7.20/2 — July 30, 2026
**Hermes v2026.7.20 · minor**

### Bug fixes
- **Backup restore on cloud browsers** — "Choose file" did nothing on streamed
  browsers, which never surface the file dialog the old hidden-input picker
  relied on. The input is now a real, focusable control. ([#76](https://github.com/praveen-ks-2001/hermes-agent-template/issues/76))

### Improvements
- **Backup restore** — a .zip can be dragged onto the Restore box, and the
  outcome (success / warning / failure reason) now shows in the box rather than
  only as a brief toast.
- **MiniMax (China)** added to the provider dropdown alongside the global one.
  They are separate MiniMax platforms with separate keys, so both can be
  configured at once. Model hints (`MiniMax-M3`, `MiniMax-M2.7`) added for both.

---

## release/v2026.7.20/1 — July 27, 2026
**Hermes v2026.7.20 · major (Hermes upgrade, from v2026.7.1)**

### Hermes update
- Hermes Agent **v2026.7.1 → v2026.7.20** — adds the Hermes Console, session
  export, and three providers (Fireworks AI, DeepInfra, Upstage Solar).

### Changes to support upstream updates
- **Hermes Console** — new WebSocket route added to the proxy's fail-closed
  allowlist, which otherwise 403s it at our edge.
- **Restart throttling** — Hermes added its own respawn brake that blocks before
  the gateway boots. Disabled via `HERMES_GATEWAY_MAX_STARTS=0` so only this
  template's supervisor throttles; repeated saves no longer take the bot offline.
- **Backups** — `hermes backup` can now drop `state.db` and still exit 0. The
  archive is verified directly: a restore aborts unless its safety snapshot is
  complete, and downloads warn instead of handing over a partial file.
- **Paired users** — Hermes now re-copies the inactive pairing dir on every
  start, resurrecting revoked users. The two dirs are consolidated after a
  restore and at boot, and the store is resolved per request rather than cached.
- **Long replies** — Hermes disabled its loopback WebSocket keepalive; the proxy
  now matches it, so Chat no longer drops mid-reply.
- **MCP sign-in** — `HERMES_DASHBOARD_PUBLIC_URL` is derived from
  `RAILWAY_PUBLIC_DOMAIN`, since Hermes builds its OAuth return address from a
  Host header this proxy must rewrite.
- **Memory providers** — a new dashboard button installs into the running
  container with no immutability check; a warning is injected before it runs.
- **Conversation auto-reset** — upstream flipped the default, which would have
  split behaviour between new and existing volumes. Now pinned explicitly.

### Bug fixes
- **Users tab** read the wrong pairing location after a restore — requests could
  be invisible and approvals ignored until the next restart.
- **Gateway shutdown** waits longer, so multiple chat platforms disconnect
  cleanly instead of being cut off.
- **Save & Start on mobile** — the bottom bar sat below the visible viewport
  with no way to scroll to it (`100vh` vs the visible area).

### Improvements
- Sidebar shows the pinned Hermes version, linking to What's New.

---

## v2026.7.1-update — July 13, 2026
**Hermes v2026.7.1 · major**

> Predates the `release/<version>/<n>` convention, so it keeps its original
> branch name.

- **Backup & Restore** added under **Data** — download a full snapshot (config,
  provider keys, channel tokens, approved users, chat history, memories, skills,
  cron jobs) as a zip and restore it, including into a fresh project. A safety
  snapshot is taken automatically before every restore.
