# Host (no-Docker) executor with a read-only tmux viewer

> Branch: `feat/host-tmux-executor`

This adds a way to run the **agent-under-test directly on the host** (the
Orcabot sandbox VM), with no inner Docker container, while still being able to
**watch each run live** from a separate, read-only pane.

## Why

slop-code-bench normally runs each problem in its own Docker container. Inside
Orcabot, the sandbox is *already* an isolated VM, so the inner container is
redundant — and getting Docker-in-VM working is a meaningful infra project.
Running on the host instead means:

- no Docker-in-Docker / nested virtualisation,
- the agent runs alongside the orchestrating CLI in the same VM,
- it works on the desktop VM (which can't easily run Docker), and
- each run is a process you can attach to and watch.

The trade-off is weaker isolation and reproducibility than the pinned
container image — see *Caveats*. Use Docker when you need to match the public
leaderboard exactly; use this when you want an Orcabot-native, watchable run.

## What changed

The `local` runtime already existed (`LocalStreamingRuntime`,
`LocalExecRuntime`, `type: local`). It captured the agent's output through
subprocess pipes — correct, but **invisible**. This branch adds an optional
tmux *mirror* so a run can be watched without changing what the harness sees.

| File | Change |
|------|--------|
| `execution/models.py` | `LocalConfig` gains `tmux`, `tmux_session`, `tmux_log_dir` |
| `execution/tmux_support.py` | **new** — `TmuxMirror`, fail-open tmux helpers |
| `execution/local_streaming.py` | tees streamed output to the mirror; spawns/cleans it up |
| `configs/environments/local-tmux-py.yaml` | **new** — base host env with tmux on |
| `configs/environments/local-tmux-py-with-gsd.yaml` | **new** — skills variant (copy-in instead of bind-mount) |
| `configs/prompts/just-solve-with-gsd-local-trigger.jinja` | **new** — references the workspace-relative skill path |
| `tests/execution/tmux_support_test.py` | **new** — unit + real-tmux lifecycle tests |

### How the mirror works (and why it's safe)

The runtime keeps reading the agent's stdout/stderr through its normal pipes,
so the **bytes the evaluator sees are byte-for-byte unchanged**. It just tees
a *copy* of every chunk into a per-run logfile, and a tmux window runs
`tail -F` on that logfile. tmux is never in the harness's data path.

```
agent process ──stdout/stderr──▶ subprocess pipes ──▶ harness (trajectory, eval)
                                        │
                                        └─tee copy─▶ <run>.log ◀─ tmux `tail -F` ◀─ viewer (attach -r)
```

Because the viewer only tails a file (and attaches with `-r`), it is read-only
by construction — it cannot send input to or kill the agent.

### Cross-PTY viewing (security)

The tmux window + `tmux attach -r` is for **same-uid** viewing — a human (or the
orchestrator) in the executor's own shell, using tmux's default per-uid socket.

A **separate viewer process under a different uid** (e.g. an Orcabot viewer pane
when the egress UID pool is active) must **not** be bridged to this tmux socket:
making the socket cross-uid-accessible would expose a tmux *control* socket
(read every pane **and inject commands** into any session), bypassing output
redaction via a local channel. Cross-uid/cross-PTY viewers should instead
**`tail -n +1 -F <logfile>`** — read-only, reaching only that one run. The
`logfile` path is in each `runs.jsonl` record for exactly this purpose. The tmux
mirror stays private to the executor's uid.

**Fail-open:** if `tmux` isn't on PATH, or any tmux command fails, mirroring
silently disables and the run proceeds exactly like plain `local-py`. tmux
problems never fail a benchmark.

## Usage

```bash
# one-time: tmux must be available
which tmux || sudo apt-get install -y tmux

# run with the host + tmux environment
uv run slop-code run \
  --agent claude_code \
  --model anthropic/opus-4.5 \
  --environment configs/environments/local-tmux-py.yaml \
  --prompt configs/prompts/just-solve.jinja \
  --problem file_backup \
  thinking=low version=2.0.51

# in another pane, watch a run read-only
tmux attach -r -t scb:file_backup
# list active runs
tmux list-windows -t scb
```

Each run also appends a discovery record to
`<working_dir>/.scb_tmux/runs.jsonl`:

```json
{"target":"scb:file_backup","session":"scb","window":"file_backup","logfile":"…/file_backup.1718000000.log","created":1718000000.0}
```

An orchestrator (e.g. the Orcabot benchmark template) reads this to learn each
run's tmux target and spawn a matching viewer pane.

## Skills variant (host)

The Docker skills configs bind-mount the skill from a hardcoded host path. The
host variant copies it in instead, from `$SCB_SKILL_<NAME>_DIR`, into a
workspace-relative `.claude/skills/<name>/` (already in the snapshot
ignore-globs, so it never pollutes the solution):

```bash
git clone https://github.com/open-gsd/get-shit-done-redux ~/skills/get-shit-done
export SCB_SKILL_GSD_DIR=~/skills/get-shit-done

uv run slop-code run \
  --agent codex --model codex_auth/gpt-5.5 \
  --environment configs/environments/local-tmux-py-with-gsd.yaml \
  --prompt configs/prompts/just-solve-with-gsd-local-trigger.jinja \
  --problem file_backup \
  thinking=high version=0.136.0
```

To add OMC / SuperPowers / Karpathy: clone the repo, set
`SCB_SKILL_<NAME>_DIR`, copy `local-tmux-py-with-gsd.yaml` →
`…-with-<name>.yaml` (change the copy target + var), and add a
`*-local-trigger.jinja` prompt referencing the relative path.

## Caveats

- **Isolation:** all runs share the VM filesystem and one kernel. Per-run
  working dirs + per-run `uv` venvs keep Python deps separate, but globally
  installed CLIs, `$HOME` dotfiles, and ports are shared. Cap concurrency to
  what the VM's RAM supports (the Docker skills config assumed 12 GB *per*
  container).
- **Reproducibility:** results reflect the VM's toolchain, not the pinned
  image. Good for relative comparisons (model A vs B, skill on vs off); use
  Docker for leaderboard-exact numbers.
- **Eval runs are not mirrored** — only the watchable agent session is, to
  keep tmux windows meaningful.

## Tests

```bash
uv run pytest tests/execution/tmux_support_test.py -v
```

Unit tests (sanitisation, fail-open) run anywhere; the lifecycle test is
skipped unless `tmux` is installed.
