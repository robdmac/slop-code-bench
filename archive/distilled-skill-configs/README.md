# ⚠️ SUPERSEDED — distilled public-skill configs (do not use for new runs)

These are the **distilled** prompt + environment configs for the public agent
skills (GSD, OMC, SuperPowers, Karpathy). They are kept here **only** to trace the
superseded public-skill results, and are out of `configs/` so they can't be picked
up by a run command by accident.

## What went wrong

The gpt-5.5 codex public-skill comparison (run 2026-06-02 → 06-08) was launched
with these **distilled** configs instead of the full plugins. Each `*.jinja` here
embeds a ~28-line inline summary of the methodology ("distilled here for this
single-agent run") and **never directs the agent to read the mounted plugin**. The
`*-codex.yaml` envs bind-mounted the full plugin to `/tmp/agent_home/.gsd` (etc.),
but the distilled prompt ignored it, so the plugin sat inert.

Result: every one of the 121 GSD / 121 OMC / 116 SuperPowers / 114 Karpathy runs
measured a distilled summary, **not** the actual skill plugin. (Evidence/evdalt are
unaffected — those used real trigger prompts pointing at the mounted `evidencia`
skill.)

## Superseded by (the real, full-plugin configs)

| skill | env | prompt |
|---|---|---|
| GSD | `configs/environments/docker-python3.12-uv-with-gsd-real.yaml` | `configs/prompts/just-solve-with-gsd-real-trigger.jinja` |
| OMC | `...-with-omc-real.yaml` | `just-solve-with-omc-real-trigger.jinja` |
| SuperPowers | `...-with-superpowers.yaml` | `just-solve-with-superpowers-real-trigger.jinja` |
| Karpathy | `...-with-karpathy.yaml` | `just-solve-with-karpathy-trigger.jinja` |

Those mount each full plugin into `/tmp/agent_home/.claude/skills/<skill>/` and the
prompt reads the plugin's `README.md`/`SKILL.md` — verified aligned end-to-end.

## Contents of this archive

- `prompts/`  — the distilled `gsd.jinja`, `omc.jinja`, `superpowers.jinja`, `karpathy.jinja`
- `environments/` — the distilled `docker-python3.12-uv-with-{gsd,omc,superpowers,karpathy}-codex.yaml`
