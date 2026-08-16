"""
Build one QET variant (a git ref, optionally with a patch applied) into
an isolated, content-keyed build tree.

Modelled on scripts/asan-compare.sh's two-ref shape (checkout, build,
run, repeat) but generalised and sped up:

  - asan-compare.sh hand-rolls qmake+make against the caller's single
    checkout, switching branches in place. That means only one variant
    can exist on disk at a time and a re-run always starts from a clean
    tree.
  - This module uses a *detached git worktree* per resolved commit sha
    (plus a patch hash, if a patch was given) under
    <repo>/build-ab/<key>/src, and a matching cmake/ninja build tree
    under <repo>/build-ab/<key>/build, built via scripts/qet-fastbuild.sh
    (the fast cmake+ninja+ccache recipe, not qmake+make). Keying by sha
    means a variant already built in a previous run is reused as-is,
    and ccache (shared globally via CCACHE_DIR, keyed on preprocessed
    content + a normalised base_dir -- see qet-fastbuild.sh) makes a
    *new* build tree for a variant that shares most of its source with
    an already-built one fast, even though the build directory itself
    is brand new.
  - Using a worktree (rather than checking out branches in-place in
    <repo>) means this never mutates the caller's checked-out branch in
    /home/user/qet-fix, which TOOLING-PLAN.md's environment facts call
    out as significant (179 local branches; know which one is checked
    out before building).
"""
from __future__ import annotations

import hashlib
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

_FASTBUILD = Path(__file__).resolve().parents[2] / "scripts" / "qet-fastbuild.sh"


class BuildError(RuntimeError):
    """A git or build step failed. Message carries the tail of the failing
    command's stderr so the caller doesn't have to go spelunking in a log
    file to find out why."""


@dataclass
class BuildResult:
    ref: str
    sha: str
    key: str                    # directory name under build_root
    patch: Path | None
    src_dir: Path
    build_dir: Path
    binary: Path
    configure_seconds: float    # 0.0 if configure was skipped (already configured)
    build_seconds: float
    reused: bool                # True if the binary already existed before this call
    log_tail: str                # last few KB of combined build output, for the report


def resolve_sha(repo: Path, ref: str) -> str:
    """Resolve `ref` (branch, tag, sha, HEAD~N, ...) to a full commit sha.

    Deliberately does NOT accept a bare PR number the way asan-compare.sh's
    -p does -- L1's examples only ever pass branches/refs, and silently
    fetching from origin on every invocation would make this tool's first
    run of a session network-dependent and slow for no benefit here.
    Fetch the PR branch yourself first (as asan-compare.sh's resolve_ref
    does) and pass its local branch name instead.
    """
    proc = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--verify", f"{ref}^{{commit}}"],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise BuildError(f"cannot resolve ref {ref!r} in {repo}: {proc.stderr.strip()}")
    return proc.stdout.strip()


def _patch_hash(patch: Path) -> str:
    return hashlib.sha256(patch.read_bytes()).hexdigest()[:12]


def _run(argv: list[str], log_lines: list[str], *, cwd: Path | None = None) -> None:
    proc = subprocess.run(argv, capture_output=True, text=True, cwd=str(cwd) if cwd else None)
    log_lines.append(f"$ {' '.join(argv)}")
    if proc.stdout:
        log_lines.append(proc.stdout)
    if proc.stderr:
        log_lines.append(proc.stderr)
    if proc.returncode != 0:
        raise BuildError(
            f"command failed (exit {proc.returncode}): {' '.join(argv)}\n"
            f"{proc.stderr[-4000:]}"
        )


def _ensure_worktree(repo: Path, sha: str, patch: Path | None, variant_dir: Path) -> Path:
    """Create (or reuse) a detached worktree at variant_dir/src, checked
    out at `sha`, with `patch` applied on top if given. Idempotent: a
    SOURCE_READY marker means the worktree already exists and is correct,
    so a repeat call is a no-op (this is what makes a repeat A/B run of
    the same refs free on the source side)."""
    src_dir = variant_dir / "src"
    marker = variant_dir / "SOURCE_READY"
    log_lines: list[str] = []

    if marker.exists() and src_dir.exists():
        return src_dir

    variant_dir.mkdir(parents=True, exist_ok=True)
    if src_dir.exists():
        shutil.rmtree(src_dir)

    # Stale worktree metadata (e.g. a previous run that died mid-way)
    # would otherwise make `git worktree add` refuse to reuse this path.
    subprocess.run(["git", "-C", str(repo), "worktree", "prune"], capture_output=True)
    _run(["git", "-C", str(repo), "worktree", "add", "--detach", "--force", str(src_dir), sha],
         log_lines)

    if patch is not None:
        _run(["git", "-C", str(src_dir), "apply", "--whitespace=nowarn", str(patch)], log_lines)

    marker.write_text(f"sha={sha}\npatch={patch or ''}\n")
    return src_dir


def build_variant(
    repo: Path,
    ref: str,
    build_root: Path,
    *,
    patch: Path | None = None,
) -> BuildResult:
    sha = resolve_sha(repo, ref)
    key = sha[:12] if patch is None else f"{sha[:12]}-patch-{_patch_hash(patch)}"

    variant_dir = build_root / key
    build_dir = variant_dir / "build"
    log_lines: list[str] = []

    src_dir = _ensure_worktree(repo, sha, patch, variant_dir)

    binary = build_dir / "qelectrotech"
    already_built = binary.exists()

    configure_seconds = 0.0
    if not (build_dir / "build.ninja").exists():
        t0 = time.monotonic()
        _run(["bash", str(_FASTBUILD), "configure", str(src_dir), str(build_dir)], log_lines)
        configure_seconds = time.monotonic() - t0

    t0 = time.monotonic()
    _run(["bash", str(_FASTBUILD), "build", str(build_dir)], log_lines)
    build_seconds = time.monotonic() - t0

    if not binary.exists():
        raise BuildError(f"build for {ref} ({sha}) did not produce {binary}")

    return BuildResult(
        ref=ref, sha=sha, key=key, patch=patch,
        src_dir=src_dir, build_dir=build_dir, binary=binary,
        configure_seconds=configure_seconds, build_seconds=build_seconds,
        reused=already_built, log_tail="\n".join(log_lines)[-6000:],
    )
