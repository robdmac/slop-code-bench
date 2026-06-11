"""Tests for the tmux mirror used by the local streaming runtime."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from slop_code.execution import tmux_support
from slop_code.execution.tmux_support import TmuxMirror
from slop_code.execution.tmux_support import _sanitise_window_name
from slop_code.execution.tmux_support import tmux_available

_HAS_TMUX = tmux_available()
_needs_tmux = pytest.mark.skipif(not _HAS_TMUX, reason="tmux not installed")


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("file_backup", "file_backup"),
        ("file_backup/checkpoint_1", "file_backup_checkpoint_1"),
        ("weird:name with spaces", "weird_name_with_spaces"),
        ("", "run"),
        ("___", "run"),
    ],
)
def test_sanitise_window_name(label: str, expected: str) -> None:
    assert _sanitise_window_name(label) == expected


def test_sanitise_window_name_truncates() -> None:
    assert len(_sanitise_window_name("x" * 200)) == 40


def test_start_fails_open_without_tmux(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """When tmux is absent, start() returns None rather than raising."""
    monkeypatch.setattr(tmux_support.shutil, "which", lambda _name: None)
    mirror = TmuxMirror.start(
        session="scb", label="file_backup", log_dir=tmp_path / "logs"
    )
    assert mirror is None


def test_start_fails_open_on_tmux_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A failing tmux command disables mirroring; it never propagates."""
    monkeypatch.setattr(
        tmux_support.shutil, "which", lambda _name: "/usr/bin/tmux"
    )

    def _boom(*_args: str, **_kwargs: object) -> None:
        raise OSError("tmux exploded")

    monkeypatch.setattr(TmuxMirror, "_tmux", staticmethod(_boom))
    mirror = TmuxMirror.start(
        session="scb", label="file_backup", log_dir=tmp_path / "logs"
    )
    assert mirror is None


@_needs_tmux
def test_mirror_lifecycle_with_real_tmux(tmp_path: Path) -> None:
    """End-to-end: window is created, output is teed, manifest is written."""
    session = "scb_test_lifecycle"
    log_dir = tmp_path / "logs"
    # Clean any stale session from a prior failed run.
    shutil.os.system(f"tmux kill-session -t {session} 2>/dev/null")

    mirror = TmuxMirror.start(
        session=session, label="file_backup", log_dir=log_dir
    )
    assert mirror is not None
    try:
        assert mirror.target == f"{session}:file_backup"
        mirror.write("hello from the agent\n")

        # logfile contains the teed output
        contents = mirror.logfile.read_text()
        assert "hello from the agent" in contents

        # window exists in the session
        windows = shutil.os.popen(
            f"tmux list-windows -t {session} -F '#{{window_name}}'"
        ).read()
        assert "file_backup" in windows

        # manifest records the run for orchestrator discovery
        manifest = log_dir / "runs.jsonl"
        record = json.loads(manifest.read_text().strip().splitlines()[0])
        assert record["target"] == f"{session}:file_backup"
        assert record["session"] == session
    finally:
        mirror.close()
        shutil.os.system(f"tmux kill-session -t {session} 2>/dev/null")
