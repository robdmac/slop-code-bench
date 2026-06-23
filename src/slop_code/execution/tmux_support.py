"""tmux mirroring for the local streaming runtime.

REVISION: host-tmux-executor-v1-mirror

Purpose
-------
Make each local (no-Docker) agent run watchable live from a separate pane.
Two viewing paths, by trust boundary:
- **same-uid** (a human/orchestrator in the executor's own shell): attach the
  tmux window read-only, ``tmux attach -r -t scb:<run>``.
- **cross-PTY / cross-uid** (e.g. an Orcabot viewer pane under the egress UID
  pool): ``tail -n +1 -F <logfile>`` instead. Bridging the tmux *control*
  socket across uids would expose read+inject across sessions and bypass output
  redaction, so the socket stays private to the executor's uid. The ``logfile``
  for each run is recorded in ``runs.jsonl``. See docs/HOST_TMUX_EXECUTOR.md.

Design
------
We do **not** run the agent inside tmux and we do **not** use ``tmux
pipe-pane``. Instead the runtime keeps capturing the agent's stdout/stderr
through its normal subprocess pipes (so the harness still gets clean bytes
for trajectory parsing), and *additionally* tees every chunk it reads into a
per-run logfile. A tmux window simply runs ``tail -F`` on that logfile.

Consequences of this choice:
- The harness's captured output is byte-for-byte unchanged — tmux never sits
  in the data path the evaluator sees.
- The viewer is inherently read-only at the data level (it tails a file); we
  additionally attach with ``-r`` so a viewer cannot resize/kill the window.
- It degrades cleanly: a viewer that attaches mid-run still sees the whole
  history because ``tail -F`` replays the file from the configured tail.

Fail-open contract
-------------------
Every tmux interaction is best-effort. If the ``tmux`` binary is missing, or
any tmux command fails, mirroring disables itself and the run proceeds exactly
like a plain ``LocalStreamingRuntime`` run. tmux problems must never fail a
benchmark.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from pathlib import Path

from slop_code.logging import get_logger

logger = get_logger(__name__)

_WINDOW_SANITISE = re.compile(r"[^A-Za-z0-9_.-]+")


def tmux_available() -> bool:
    """Return True if a ``tmux`` binary is on PATH."""
    return shutil.which("tmux") is not None


def _sanitise_window_name(label: str) -> str:
    """Turn an arbitrary label into a tmux-safe window name.

    tmux treats ``:`` and ``.`` specially in target syntax; we keep ``.`` and
    ``-`` but collapse everything else to ``_`` and bound the length.
    """
    name = _WINDOW_SANITISE.sub("_", label).strip("_")
    name = name or "run"
    return name[:40]


class TmuxMirror:
    """Mirrors streamed output into a tmux window via a tailed logfile.

    Construct with :meth:`start`, which returns ``None`` when mirroring cannot
    be set up (tmux missing, command failure). Callers therefore treat the
    mirror as optional: ``if self._tmux: self._tmux.write(chunk)``.
    """

    def __init__(
        self,
        session: str,
        window: str,
        logfile: Path,
        log_dir: Path,
    ) -> None:
        self.session = session
        self.window = window
        self.logfile = logfile
        self.log_dir = log_dir
        self._fh = logfile.open("a", encoding="utf-8", errors="replace")

    # -- construction ----------------------------------------------------

    @classmethod
    def start(
        cls,
        *,
        session: str,
        label: str,
        log_dir: Path,
    ) -> TmuxMirror | None:
        """Create the logfile + tmux window. Returns None on any failure."""
        if not tmux_available():
            logger.debug(
                "tmux not on PATH; skipping mirror", verbose=True
            )
            return None
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            window = _sanitise_window_name(label)
            # Disambiguate if a window of this name already exists in the
            # session (e.g. the same problem run twice in one session).
            logfile = log_dir / f"{window}.{int(time.time())}.log"
            logfile.touch()

            cls._ensure_session(session)
            window = cls._create_window(session, window, logfile)

            mirror = cls(
                session=session,
                window=window,
                logfile=logfile,
                log_dir=log_dir,
            )
            mirror._write_header()
            mirror._append_manifest(log_dir)
            logger.debug(
                "tmux mirror started",
                target=mirror.target,
                logfile=str(logfile),
                verbose=True,
            )
            return mirror
        except Exception as exc:  # noqa: BLE001 - fail open, never break a run
            logger.warning("tmux.mirror_setup_failed", error=str(exc))
            return None

    @staticmethod
    def _tmux(*args: str, check: bool = True) -> subprocess.CompletedProcess:  # noqa: FBT001, FBT002 - keyword-only via *args; bool flag is the natural shape
        # tmux is resolved from PATH (S607) and args are constructed by this
        # module, never from agent/user input (S603); setup is wrapped in a
        # fail-open try/except by the sole caller.
        return subprocess.run(  # noqa: S603
            ["tmux", *args],  # noqa: S607 - tmux resolved from PATH by design
            capture_output=True,
            text=True,
            check=check,
        )

    @classmethod
    def _ensure_session(cls, session: str) -> None:
        """Create the holding session if it does not already exist."""
        exists = cls._tmux("has-session", "-t", session, check=False)
        if exists.returncode == 0:
            return
        # A detached session needs an initial window; park it on a no-op so
        # the session survives even when no runs are active.
        cls._tmux(
            "new-session",
            "-d",
            "-s",
            session,
            "-n",
            "_scb_runs",
            "sh -c 'while :; do sleep 86400; done'",
        )

    @classmethod
    def _create_window(
        cls, session: str, window: str, logfile: Path
    ) -> str:
        """Create a window that tails ``logfile``; return its actual name."""
        # ``-P -F`` prints the new window's name so we use exactly what tmux
        # assigned (tmux may suffix on collision when allow-rename is off).
        result = cls._tmux(
            "new-window",
            "-t",
            session,
            "-n",
            window,
            "-P",
            "-F",
            "#{window_name}",
            f"tail -n +1 -F {logfile}",
        )
        assigned = result.stdout.strip()
        return assigned or window

    # -- runtime ---------------------------------------------------------

    def _write_header(self) -> None:
        self.write(
            f"[slop-code-bench] watching run '{self.window}'  "
            f"(read-only: tmux attach -r -t {self.target})\n"
            f"[slop-code-bench] logfile: {self.logfile}\n\n"
        )

    def _append_manifest(self, log_dir: Path) -> None:
        """Append a discovery record so an orchestrator can find this run.

        Orchestrators (e.g. the Orcabot benchmark template) read this JSONL to
        learn the tmux target of each active run and spawn a viewer pane.
        """
        entry = {
            "target": self.target,
            "session": self.session,
            "window": self.window,
            "logfile": str(self.logfile),
            "created": time.time(),
        }
        try:
            manifest = log_dir / "runs.jsonl"
            with manifest.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry) + "\n")
        except OSError as exc:
            logger.debug("tmux.manifest_write_failed", error=str(exc))

    def write(self, text: str) -> None:
        """Tee a chunk of output to the tailed logfile (best-effort)."""
        if not text:
            return
        try:
            self._fh.write(text)
            self._fh.flush()
        except (ValueError, OSError) as exc:  # closed fh / disk error
            logger.debug("tmux.write_failed", error=str(exc))

    @property
    def target(self) -> str:
        """tmux target string: ``session:window``."""
        return f"{self.session}:{self.window}"

    def close(self) -> None:
        """Flush + close the logfile. The tmux window is intentionally left
        open so the final output stays visible to a viewer after the run."""
        try:
            self.write(
                f"\n[slop-code-bench] run '{self.window}' finished.\n"
            )
            self._fh.close()
        except (ValueError, OSError):
            pass
