# Reproducing the public-skill runs on gpt-5.5 (codex) — full plugins

This branch adds the configs and minimal source edits to run the **public
agent-skill comparison** on SlopCodeBench against **gpt-5.5 via the codex CLI**
(ChatGPT-subscription backend), using the **actual full skill plugins**. Skills:
**baseline** (no skill), **GSD**, **OMC**, **SuperPowers**, **Karpathy**.

> Each skill prompt is a *real trigger* that bind-mounts the full plugin into the
> container and instructs the agent to read it. An earlier iteration used
> **distilled** variants (inline ~28-line summaries that never read the plugin);
> those are superseded and intentionally not on this branch. They remain available
> in history at commit `c92f1f5` if you need to tie back to the superseded results.
>
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
mkdir -p skills && cd skills
git clone https://github.com/open-gsd/get-shit-done-redux        get-shit-done
git clone https://github.com/Yeachan-Heo/oh-my-claudecode        oh-my-claudecode
git clone https://github.com/obra/superpowers                    superpowers
git clone https://github.com/multica-ai/andrej-karpathy-skills   andrej-karpathy-skills
```

Then edit the `extra_mounts:` **host** path in each `*-real`/full-plugin env yaml
to point at your clone. The container-side mount path (right of the `:`) must stay
as-is — the trigger prompt reads the plugin from there. Current host paths are
absolute (`/home/rob/swebench/solution/skill/...`); replace with your own.

| skill | env yaml | host plugin → container mount | prompt reads |
|---|---|---|---|
| GSD | `docker-python3.12-uv-with-gsd-real.yaml` | `get-shit-done` → `/tmp/agent_home/.claude/skills/get-shit-done` | `.../get-shit-done/README.md` |
| OMC | `docker-python3.12-uv-with-omc-real.yaml` | `oh-my-claudecode` → `/tmp/agent_home/.claude/skills/oh-my-claudecode` | `.../oh-my-claudecode/skills/skill/SKILL.md` |
| SuperPowers | `docker-python3.12-uv-with-superpowers.yaml` | `superpowers` → `/tmp/agent_home/.claude/skills/superpowers` | `.../superpowers/skills/using-superpowers/SKILL.md` |
| Karpathy | `docker-python3.12-uv-with-karpathy.yaml` | `andrej-karpathy-skills/skills/karpathy-guidelines` → `/tmp/agent_home/.claude/skills/karpathy-guidelines` | `.../karpathy-guidelines/SKILL.md` |

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
  --environment configs/environments/docker-python3.12-uv-with-gsd-real.yaml \
  --prompt configs/prompts/just-solve-with-gsd-real-trigger.jinja \
  --problem file_backup \
  thinking=high version=0.136.0
```

Skill → (env, prompt) pairs:

| skill | `--environment` | `--prompt` |
|---|---|---|
| baseline | `docker-python3.12-uv.yaml` | `just-solve.jinja` |
| GSD | `docker-python3.12-uv-with-gsd-real.yaml` | `just-solve-with-gsd-real-trigger.jinja` |
| OMC | `docker-python3.12-uv-with-omc-real.yaml` | `just-solve-with-omc-real-trigger.jinja` |
| SuperPowers | `docker-python3.12-uv-with-superpowers.yaml` | `just-solve-with-superpowers-real-trigger.jinja` |
| Karpathy | `docker-python3.12-uv-with-karpathy.yaml` | `just-solve-with-karpathy-trigger.jinja` |

Notes:
- `version=0.136.0` pins the codex CLI version (image built with `@openai/codex@<version>`;
  version-drift disabled — see edits below).
- `thinking=high` maps to codex `model_reasoning_effort=high`.
- Results land in `outputs/{model}/{agent}-{prompt}_{params}_{timestamp}/`. Pass
  `--num-workers N` / multiple `--problem` to parallelize; the timestamp fix below
  keeps concurrent arms from colliding on output dirs.

## Source edits included in this commit (and why)

All minimal and isolated — no behavior change for non-skill runs:

1. **Output-timestamp precision** (`entrypoints/config/{loader,run_config}.py`):
   default `save_template` timestamp goes from minute to microsecond, so concurrent
   arms don't overwrite each other's output directories.
2. **Per-container memory cap** (`execution/docker_runtime/{models,exec}.py` +
   `mem_limit: 12g` in the env yamls): optional `docker.mem_limit` → `docker
   --memory/--memory-swap`, so a runaway solution can't OOM the host.
3. **Codex version pinning** (`agent_runner/agents/codex/docker.j2`): sets
   `CODEX_DISABLE_AUTO_UPGRADE`/`NO_UPDATE_NOTIFIER` so the pinned codex version
   doesn't self-update inside the container.
