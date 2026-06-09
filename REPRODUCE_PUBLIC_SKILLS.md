# Reproducing the public-skill runs on gpt-5.5 (codex)

This branch adds the configs and minimal source edits needed to reproduce the
**public agent-skill comparison** on SlopCodeBench against **gpt-5.5 via the codex
CLI** (ChatGPT-subscription backend). Skills compared: **baseline** (no skill),
**GSD**, **OMC**, **SuperPowers**, **Karpathy**.

> The private/in-development skills (Evidence/evidencia, REF, agent-memory) are
> **not** included here — only the publicly-available skills.

## Prerequisites

1. **codex CLI auth** — `codex login` (creates `~/.codex/auth.json`; the codex
   agent copies it into the run container). Runs are billed to your ChatGPT
   subscription.
2. **Python 3.12+ and `uv`** — `uv sync` in the repo root.
3. **Docker** — first run builds the agent image (5–10 min, cached after).

## Get the public skills

Each skill env yaml bind-mounts a skill directory from the host into the agent
container. Clone the four public skills, then point the env yamls at your clones.

| skill | source |
|---|---|
| GSD (Get-Shit-Done) | https://github.com/open-gsd/get-shit-done-redux |
| OMC (oh-my-claudecode) | https://github.com/Yeachan-Heo/oh-my-claudecode |
| SuperPowers | https://github.com/obra/superpowers |
| Karpathy guidelines | https://github.com/multica-ai/andrej-karpathy-skills |

```bash
# example: clone them somewhere, e.g. ./skills/
mkdir -p skills && cd skills
git clone https://github.com/open-gsd/get-shit-done-redux        get-shit-done
git clone https://github.com/Yeachan-Heo/oh-my-claudecode        oh-my-claudecode
git clone https://github.com/obra/superpowers                    superpowers
git clone https://github.com/multica-ai/andrej-karpathy-skills   andrej-karpathy-skills
```

Then edit the `extra_mounts:` host path in each env yaml under
`configs/environments/docker-python3.12-uv-with-<skill>-codex.yaml` to point at
your clone. The container-side mount path (right of the `:`) must stay as-is —
the prompt expects the skill at that location. Current host paths in the yamls
are absolute (`/home/rob/swebench/solution/skill/...`); replace with your own.

| env yaml | mounts skill → container path |
|---|---|
| `...-with-gsd-codex.yaml` | `get-shit-done` → `/tmp/agent_home/.gsd` |
| `...-with-omc-codex.yaml` | `oh-my-claudecode/skills` → `/tmp/agent_home/.claude/skills` |
| `...-with-superpowers-codex.yaml` | `superpowers/skills` → `/tmp/agent_home/.claude/skills` |
| `...-with-karpathy-codex.yaml` | `andrej-karpathy-skills/skills/karpathy-guidelines` → `/tmp/agent_home/.claude/skills/karpathy-guidelines` |

## Run commands

Baseline (no skill):

```bash
uv run slop-code run --agent codex --model codex_auth/gpt-5.5 \
  --environment configs/environments/docker-python3.12-uv.yaml \
  --prompt configs/prompts/just-solve.jinja \
  --problem file_backup \
  thinking=high version=0.136.0
```

A skill (swap env + prompt; example = GSD):

```bash
uv run slop-code run --agent codex --model codex_auth/gpt-5.5 \
  --environment configs/environments/docker-python3.12-uv-with-gsd-codex.yaml \
  --prompt configs/prompts/gsd.jinja \
  --problem file_backup \
  thinking=high version=0.136.0
```

Skill → (env, prompt) pairs:

| skill | `--environment` | `--prompt` |
|---|---|---|
| baseline | `docker-python3.12-uv.yaml` | `just-solve.jinja` |
| GSD | `docker-python3.12-uv-with-gsd-codex.yaml` | `gsd.jinja` |
| OMC | `docker-python3.12-uv-with-omc-codex.yaml` | `omc.jinja` |
| SuperPowers | `docker-python3.12-uv-with-superpowers-codex.yaml` | `superpowers.jinja` |
| Karpathy | `docker-python3.12-uv-with-karpathy-codex.yaml` | `karpathy.jinja` |

Notes:
- `version=0.136.0` pins the codex CLI version used (the image is built with
  `@openai/codex@<version>`; version-drift is disabled — see edits below).
- `thinking=high` matches the runs (maps to codex `model_reasoning_effort=high`).
- Add `--problem <name>` per problem (run `slop-code run --help` for options);
  results land in `outputs/{model}/{agent}-{prompt}_{params}_{timestamp}/`.
- Pass `--num-workers N` / multiple `--problem` to parallelize; the timestamp fix
  below makes concurrent arms safe against output-dir collisions.

## Source edits included in this commit (and why)

All are minimal and isolated — no behavior change for non-skill runs:

1. **Output-timestamp precision** (`entrypoints/config/{loader,run_config}.py`):
   default `save_template` timestamp goes from minute (`%Y%m%dT%H%M`) to
   microsecond (`%Y%m%dT%H%M%S%f`), so concurrent arms don't overwrite each
   other's output directories.
2. **Per-container memory cap** (`execution/docker_runtime/{models,exec}.py` +
   `mem_limit: 12g` in the env yamls): adds an optional `docker.mem_limit` that
   maps to `docker --memory/--memory-swap`, so a runaway solution can't OOM the
   host.
3. **Codex version pinning** (`agent_runner/agents/codex/docker.j2`): sets
   `CODEX_DISABLE_AUTO_UPGRADE`/`NO_UPDATE_NOTIFIER` so the pinned codex version
   doesn't self-update inside the container.
