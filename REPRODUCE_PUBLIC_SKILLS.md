# Reproducing the public-skill runs on gpt-5.5 (codex) — full plugins

This branch adds the configs and minimal source edits to run the **public
agent-skill comparison** on SlopCodeBench against **gpt-5.5 via the codex CLI**
(ChatGPT-subscription backend), using the **actual full skill plugins**. Skills:
**baseline** (no skill), **GSD**, **OMC**, **SuperPowers** (v5.1.0), **Karpathy**,
**Agent Skills** (Addy Osmani).

> **Version pins.** Skills were run at fixed commits (below) for reproducibility.
> "SuperPowers" here is **v5.1.0**; v6 was released mid-study and is benchmarked
> separately.

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

| skill | source | pinned commit |
|---|---|---|
| GSD (Get-Shit-Done) | https://github.com/open-gsd/get-shit-done-redux | `de73ad9` |
| OMC (oh-my-claudecode) | https://github.com/Yeachan-Heo/oh-my-claudecode | `a172043` |
| SuperPowers (v5.1.0) | https://github.com/obra/superpowers | `f2cbfbe` |
| Karpathy guidelines | https://github.com/multica-ai/andrej-karpathy-skills | `2c60614` |
| Agent Skills | https://github.com/addyosmani/agent-skills | `70b7506` |

```bash
mkdir -p skills && cd skills
git clone https://github.com/open-gsd/get-shit-done-redux        get-shit-done         && git -C get-shit-done          checkout de73ad9
git clone https://github.com/Yeachan-Heo/oh-my-claudecode        oh-my-claudecode      && git -C oh-my-claudecode       checkout a172043
git clone https://github.com/obra/superpowers                    superpowers           && git -C superpowers            checkout f2cbfbe
git clone https://github.com/multica-ai/andrej-karpathy-skills   andrej-karpathy-skills && git -C andrej-karpathy-skills checkout 2c60614
git clone https://github.com/addyosmani/agent-skills             addyosmani-agent-skills && git -C addyosmani-agent-skills checkout 70b7506
```

Then edit the `extra_mounts:` **host** path in each `*-real`/full-plugin env yaml
to point at your clone. The container-side mount path (right of the `:`) must stay
as-is — the trigger prompt reads the plugin from there. Current host paths are
absolute (`/home/rob/swebench/solution/skill/...`); replace with your own.

| skill | env yaml | host plugin → container mount | prompt reads |
|---|---|---|---|
| GSD | `docker-python3.12-uv-with-gsd-real.yaml` | `get-shit-done` → `/tmp/agent_home/.claude/skills/get-shit-done` | `.../get-shit-done/README.md` |
| OMC | `docker-python3.12-uv-with-omc-real.yaml` | `oh-my-claudecode` → `/tmp/agent_home/.claude/skills/oh-my-claudecode` | `.../oh-my-claudecode/AGENTS.md` |
| SuperPowers | `docker-python3.12-uv-with-superpowers.yaml` | `superpowers` → `/tmp/agent_home/.claude/skills/superpowers` | `.../superpowers/skills/using-superpowers/SKILL.md` |
| Karpathy | `docker-python3.12-uv-with-karpathy.yaml` | `andrej-karpathy-skills/skills/karpathy-guidelines` → `/tmp/agent_home/.claude/skills/karpathy-guidelines` | `.../karpathy-guidelines/SKILL.md` |
| Agent Skills | `docker-python3.12-uv-with-addyosmani.yaml` | `addyosmani-agent-skills` → `/tmp/agent_home/.claude/skills/addyosmani-agent-skills` | `.../addyosmani-agent-skills/AGENTS.md` |

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
| Agent Skills | `docker-python3.12-uv-with-addyosmani.yaml` | `just-solve-with-addyosmani-trigger.jinja` |

Notes:
- **Seeds & evaluation** — reported numbers are the **mean of 3 seeds** per problem.
  Evaluate **serially** (`SCBENCH_PYTEST_WORKERS=1`): some problems auto-enable pytest
  xdist (`-n auto`), which is order-flaky on parallel-sensitive problems; serial eval is
  deterministic. `test_translator` is heavy — run it one at a time.
- **OMC entry point** — the OMC trigger reads `AGENTS.md` (OMC's agent-facing
  orchestration guide), *not* `skills/skill/SKILL.md` (which is OMC's skill-management
  CLI). Targeting the latter makes the agent burn every checkpoint hunting for the
  workflow and a subagent-spawn tool the codex sandbox doesn't expose → ~0% (validated
  failure mode). The trigger also tells the agent to apply OMC's analyst/architect/
  executor/verifier/reviewer roles as a single-agent sequential pass rather than
  spawning subagents, since OMC's native multi-agent team tooling isn't available in a
  single-agent codex run. Lesson for any plugin: target its real entry doc and adapt
  multi-agent frameworks to single-agent execution.
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
