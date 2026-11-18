# Validation

## Hidden-page replacement correction (2026-10-27)

The expanded real service/kernel/VisiData/Neovim test reproduces
`frontend_delivery_failed` against the original extension when both page and
terminal are hidden. The incremental fix in `jusi-managed-urls-fix.patch` was
validated in an isolated copy, then applied to the sibling `../jusi` checkout
with the user's approval.

- Plugin suite: 14 passed. The lifecycle scenario now checks hidden drilldown,
  bookmark replacement in another tab, direct URL followup with all source
  projections hidden, and a worker-returned URL action sharing the same slot.
  Every earlier buffer is deleted while the other cell's page is preserved.
- Full core Lua frontend and Neovim end-to-end suites passed. Frontend tests
  additionally verify retry after injected buffer-deletion failure and deletion
  of a page mirrored across tabs.
- Full core Python suite: 312 passed, 1 skipped.
- After application, the full core Lua frontend suite passed in the sibling
  checkout. `git diff --check` and full-patch reverse-apply validation passed.
- Two early plugin lifecycle runs exited with native Neovim 0.11.4 signals 6
  and 11. The macOS signal-6 report points to `stl_clear_click_defs` /
  `win_redr_custom` / `ex_redrawstatus`; later targeted and full plugin runs
  passed. The post-application plugin run and a targeted lifecycle rerun both
  exited with signal 11 during the cross-tab case (13 other plugin tests passed).
  The native crash cause is unresolved. This validation does not cover
  Electron rendering or paid Perplexity calls.

## Original extension validation

The generic core patch was first tested in a temporary copy of `../jusi` at
commit `d13769c2854ba2c86f3b39371a1a5b490d52988b` (Jusi 1.0.6), then applied to
the sibling checkout with the user's approval. Final verification below ran
against the actual applied checkout.

- Plugin suite: 12 passed, including a real isolated
  worker, a PTY-hosted VisiData application, bookmark edit/undo/redo, and a full
  real service/kernel/Neovim lifecycle test. The lifecycle regression now waits
  for an idle UI and delayed search response without sending terminal input,
  checks same-window pages with no added split, restores VisiData on followup,
  and replaces a managed page while its terminal is hidden.
- Full Jusi Python suite: 312 passed, 1 opt-in skip.
- Full Jusi headless Lua frontend suite passed.
  Managed-URL tests cover same-window replacement/restoration, hidden and
  repurposed windows, native deletion, separate clients and host failure rollback.
- Full Jusi headless Neovim end-to-end suite passed.
- Wheel built successfully and contains the 11 runtime modules plus metadata.
- `git diff --check` passed in Jusi. The recorded patch matches the applied
  changes (`git apply --reverse --check` passed).

Perplexity requests use a local HTTP fixture, and Neovim's WebBuffer command is
substituted with a test host. Live Perplexity credentials, paid requests, and
Electron rendering were not exercised.

Without the proposed core extension, the plugin's Neovim integration test skips
explicitly, and starting a web client reports the missing managed-URL API.

Commands used for final verification:

```sh
# jusi-web checkout
PYTHONPATH=../jusi/src JUSI_SOURCE_ROOT=../jusi .venv/bin/python -m pytest -q
python -m pip wheel . --no-deps --wheel-dir dist

# jusi checkout
.venv/bin/python -m pytest -q
nvim --headless -u tests/frontend/minimal_init.lua -l tests/frontend/run.lua
nvim --headless -u tests/frontend/minimal_init.lua -l tests/e2e/run.lua
```
