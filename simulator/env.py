"""
Isolated execution environment for driving a qelectrotech binary.

QET uses SingleApplication: launching a second instance forwards the
request to whatever instance is already running instead of starting a
fresh one. On a machine where XDG_CONFIG_HOME is set (true on this
machine), overriding only HOME does NOT isolate QSettings -- this has
already produced wrong-binary results twice in this project's history
(see qet-translation-workflow memory). Getting this wrong doesn't fail
loudly: it silently runs commands against a different process and reports
that process's state.

Every sandbox this module hands out is therefore self-contained: its own
HOME, XDG_CONFIG_HOME, XDG_DATA_HOME, and a liveness check that refuses to
proceed if a qelectrotech process is already reachable through the
sandboxed environment.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path


class SandboxError(RuntimeError):
    """Raised when an isolated environment cannot be trusted to be isolated."""


@dataclass
class Sandbox:
    """A disposable, isolated QET runtime environment."""

    root: Path
    home: Path
    config_home: Path
    data_home: Path
    work: Path
    env: dict = field(default_factory=dict)

    def child_env(self) -> dict:
        """Full environment dict to pass to subprocess.run()/Popen()."""
        e = dict(os.environ)
        e.update(self.env)
        return e

    def cleanup(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)


def _assert_no_live_instance(sandbox_env: dict) -> None:
    """
    Best-effort check that SingleApplication has nothing to forward to
    inside this sandbox. A fresh HOME/XDG set means SingleApplication's
    lock file (keyed off the config dir) cannot already exist, so this is
    mostly a guard against a caller reusing a root by mistake.
    """
    lock_candidates = []
    for key in ("XDG_RUNTIME_DIR", "HOME"):
        val = sandbox_env.get(key)
        if val:
            lock_candidates.append(Path(val))
    for base in lock_candidates:
        if base.exists() and any(base.rglob("*qelectrotech*lock*")):
            raise SandboxError(
                f"stale SingleApplication lock found under {base} -- "
                "refusing to reuse this sandbox root"
            )


def make_sandbox(base_dir: Path | None = None, *, prefix: str = "qet-sim-") -> Sandbox:
    """
    Create a fresh, fully isolated sandbox. Caller is responsible for
    calling .cleanup() (or use as a context manager via sandbox_context()).
    """
    root = Path(tempfile.mkdtemp(prefix=prefix, dir=str(base_dir) if base_dir else None))
    home = root / "home"
    config_home = root / "config"
    data_home = root / "data"
    work = root / "work"
    for d in (home, config_home, data_home, work):
        d.mkdir(parents=True, exist_ok=True)

    env = {
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(config_home),
        "XDG_DATA_HOME": str(data_home),
        "QT_QPA_PLATFORM": "offscreen",
        # Never let a sandboxed run reach across to a real X/Wayland
        # display or a host-network SingleApplication instance.
        "DISPLAY": "",
        "WAYLAND_DISPLAY": "",
    }

    _assert_no_live_instance(env)

    return Sandbox(
        root=root, home=home, config_home=config_home,
        data_home=data_home, work=work, env=env,
    )


class sandbox_context:
    """Context manager: `with sandbox_context() as sb: ...`"""

    def __init__(self, base_dir: Path | None = None, *, keep_on_error: bool = False):
        self.base_dir = base_dir
        self.keep_on_error = keep_on_error
        self._sandbox: Sandbox | None = None

    def __enter__(self) -> Sandbox:
        self._sandbox = make_sandbox(self.base_dir)
        return self._sandbox

    def __exit__(self, exc_type, exc, tb) -> None:
        assert self._sandbox is not None
        if exc_type is not None and self.keep_on_error:
            # Leave it on disk for post-mortem; caller should log the path.
            return
        self._sandbox.cleanup()


def assert_no_other_qet_running(binary: str) -> None:
    """
    Global (non-sandboxed) safety check: refuse to run the simulator at
    all if a qelectrotech process is already alive on this host, since
    SingleApplication could forward to it regardless of our sandboxed
    HOME/XDG if anything leaks (e.g. a caller passes network_mode: host
    in a container). This is deliberately loud and blocking rather than a
    warning -- see the module docstring for why "quiet" is the wrong
    failure mode here.
    """
    exe_name = os.path.basename(binary) or "qelectrotech"
    try:
        out = subprocess.run(
            ["pgrep", "-x", exe_name], capture_output=True, text=True, timeout=5
        )
    except FileNotFoundError:
        # pgrep unavailable -- fall back to /proc scan.
        found = False
        for pid_dir in Path("/proc").glob("[0-9]*"):
            try:
                if (pid_dir / "comm").read_text().strip() == exe_name:
                    found = True
                    break
            except OSError:
                continue
        if found:
            raise SandboxError(
                f"a process named '{exe_name}' is already running on this host -- "
                "refusing to start the simulator (SingleApplication could forward "
                "to it and every result would silently describe the wrong binary)"
            )
        return

    if out.returncode == 0 and out.stdout.strip():
        raise SandboxError(
            f"a process named '{exe_name}' is already running (pid(s): "
            f"{out.stdout.strip()}) -- refusing to start the simulator"
        )
