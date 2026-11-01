#!/usr/bin/env python3
"""Check and install the latest sr-core and scene-render for this directory.

    ./doctor.py              install whatever is missing or behind, then test both tools together
    ./doctor.py --check      change nothing; exit 1 unless both are current and working
    ./doctor.py --no-build   take the newest published scene-render binary, never compile

"Latest" is the highest vX.Y.Z tag on origin, not GitHub's "Latest" release: a tag can exist with no
release behind it (v0.9.0 did, when its release job never started), and that tag is still the newest
version. sr-core installs from git because it is not on PyPI. scene-render installs from the release
tarball when there is one, its SHA-256 and commit verified, and otherwise builds the tag with the same
command CI uses.

Everything lands here and nothing outside this directory changes:

    .venv/                     sr-core[validate], and bin/scene-render linked to the version in use
    .tools/scene-render/<tag>/ each installed engine

Afterwards: source .venv/bin/activate, or call .venv/bin/scene-render and .venv/bin/sr-scene directly.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import NamedTuple, Optional

SR_CORE_URL = "https://github.com/pedroanisio/sr-core"
ENGINE_URL = "https://github.com/pedroanisio/scene-render"
ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
PYTHON = VENV / "bin" / "python"
ENGINE_LINK = VENV / "bin" / "scene-render"
ENGINES = ROOT / ".tools" / "scene-render"
BUILD = ROOT / ".tools" / "build"
# The shipped binary's recipe, from scene-render's .github/workflows/ci.yml.
BUILD_COMMAND = ("build", "--locked", "--release", "-p", "scene-render", "--features", "scene-render/pdf")
# The license files travel with a built binary as they do with a release tarball.
BUILD_KEEPS = ("LICENSE", "NOTICE", "COMMERCIAL.md", "DISCLAIMER.md", "THIRD-PARTY-NOTICES.md", "capabilities.json")
MIN_BUILD_FREE_GIB = 10
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class Failure(Exception):
    """A problem the doctor cannot get past; the message says what happened."""


class Release(NamedTuple):
    tag: str
    commit: str

    @property
    def version(self) -> str:
        return self.tag.removeprefix("v")


def run(*command: object, **options: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run([str(c) for c in command], text=True, capture_output=True, **options)


def must(*command: object, **options: object) -> str:
    done = run(*command, **options)
    if done.returncode != 0:
        words = " ".join(str(c) for c in command)
        raise Failure(f"{words} exited {done.returncode}\n{(done.stderr or done.stdout).strip()}")
    return done.stdout


def row(status: str, name: str, detail: str = "") -> None:
    print(f"  {status:<8}{name:<14}{detail}", flush=True)


def remote_releases(url: str) -> list[Release]:
    """The repository's vX.Y.Z tags, newest first, each with the commit it points at."""
    listing = must("git", "ls-remote", "--tags", url, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
    commits: dict[str, str] = {}
    for line in listing.splitlines():
        sha, ref = line.split("\t")
        # An annotated tag lists its tag object, then the commit as tag^{}, so the commit is written last.
        commits[ref.removeprefix("refs/tags/").removesuffix("^{}")] = sha
    tagged = [(m, tag) for tag in commits if (m := re.fullmatch(r"v(\d+)\.(\d+)\.(\d+)", tag))]
    tagged.sort(key=lambda item: tuple(int(n) for n in item[0].groups()), reverse=True)
    if not tagged:
        raise Failure(f"{url} has no vX.Y.Z tags")
    return [Release(tag, commits[tag]) for _, tag in tagged]


def asset_url(release: Release, suffix: str) -> str:
    return f"{ENGINE_URL}/releases/download/{release.tag}/scene-render-{release.tag}-linux-x86_64{suffix}"


def published_digest(release: Release) -> Optional[str]:
    """The release tarball's SHA-256, or None when the tag has no published binary."""
    try:
        with urllib.request.urlopen(asset_url(release, ".tar.gz.sha256"), timeout=30) as response:
            return response.read().decode().split()[0]
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise Failure(f"GitHub answered {error.code} for {release.tag}") from error
    except urllib.error.URLError as error:
        raise Failure(f"cannot reach GitHub: {error.reason}") from error


def installed_sr_core() -> Optional[str]:
    if not PYTHON.exists():
        return None
    done = run(PYTHON, "-c", "import sr_core; print(sr_core.__version__)", cwd=ROOT)
    return done.stdout.strip() if done.returncode == 0 else None


def installed_engine() -> Optional[str]:
    if not ENGINE_LINK.exists():
        return None
    done = run(ENGINE_LINK, "--version")
    found = re.fullmatch(r"scene-render (\S+)\s*", done.stdout)
    return found.group(1) if done.returncode == 0 and found else None


def ensure_venv() -> None:
    if not PYTHON.exists():
        print("creating .venv", flush=True)
        must(sys.executable, "-m", "venv", VENV)


def install_sr_core(release: Release) -> None:
    print(f"installing sr-core {release.version}", flush=True)
    # By commit, because a tag can move and this is the commit that was just resolved.
    must(PYTHON, "-m", "pip", "install", "--quiet", f"sr-core[validate] @ git+{SR_CORE_URL}@{release.commit}")
    found = installed_sr_core()
    if found != release.version:
        raise Failure(f"sr-core {release.version} was installed but {found} imports")


def stage_download(release: Release, digest: str, stage: Path) -> Path:
    tarball = stage / "package.tar.gz"
    print(f"downloading scene-render {release.tag}", flush=True)
    try:
        with urllib.request.urlopen(asset_url(release, ".tar.gz"), timeout=60) as response, tarball.open("wb") as out:
            shutil.copyfileobj(response, out)
    except urllib.error.URLError as error:
        raise Failure(f"download of {release.tag} failed: {error}") from error
    actual = hashlib.sha256(tarball.read_bytes()).hexdigest()
    if actual != digest:
        raise Failure(f"{release.tag} tarball is {actual}, its .sha256 says {digest}")
    with tarfile.open(tarball) as package:
        package.extractall(stage, filter="data")
    tarball.unlink()
    return stage / f"scene-render-{release.tag}-linux-x86_64"


def find_cargo() -> Optional[str]:
    return shutil.which("cargo") or shutil.which("cargo", path=str(Path.home() / ".cargo" / "bin"))


def stage_build(release: Release, stage: Path) -> Path:
    cargo = find_cargo()
    if cargo is None:
        raise Failure(f"{release.tag} has no published binary and cargo is not installed; "
                      "install Rust, or pass --no-build for the newest published binary")
    BUILD.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(BUILD).free / 2**30
    if free < MIN_BUILD_FREE_GIB:
        raise Failure(f"building needs {MIN_BUILD_FREE_GIB} GiB free and {free:.1f} GiB is; "
                      "free some space, or pass --no-build for the newest published binary")
    source = BUILD / "source"
    shutil.rmtree(source, ignore_errors=True)
    print(f"{release.tag} has no published binary: building it from source, which takes minutes", flush=True)
    must("git", "clone", "--quiet", "--depth", "1", "--branch", release.tag, ENGINE_URL, source)
    cloned = must("git", "-C", source, "rev-parse", "HEAD").strip()
    if cloned != release.commit:
        raise Failure(f"{release.tag} moved during install: cloned {cloned}, expected {release.commit}")
    # The target directory survives a failed build, so a rerun resumes it.
    env = {**os.environ, "CARGO_TARGET_DIR": str(BUILD / "target")}
    if subprocess.run([cargo, *BUILD_COMMAND], cwd=source, env=env).returncode != 0:
        raise Failure(f"cargo could not build {release.tag}; the output is above")
    package = stage / "package"
    package.mkdir()
    shutil.copy2(BUILD / "target" / "release" / "scene-render", package / "scene-render")
    for name in BUILD_KEEPS:
        if (source / name).exists():
            shutil.copy2(source / name, package / name)
    (package / "COMMIT").write_text(cloned + "\n")
    return package


def install_engine(release: Release) -> None:
    dest = ENGINES / release.tag
    if not (dest / "scene-render").exists():
        ENGINES.mkdir(parents=True, exist_ok=True)
        digest = published_digest(release)
        with tempfile.TemporaryDirectory(dir=ENGINES, prefix=".stage-") as stage:
            package = stage_download(release, digest, Path(stage)) if digest else stage_build(release, Path(stage))
            commit = (package / "COMMIT").read_text().strip()
            if commit != release.commit:
                raise Failure(f"{release.tag} is commit {release.commit}, its package says {commit}")
            reported = must(package / "scene-render", "--version").strip()
            if reported != f"scene-render {release.version}":
                raise Failure(f"{release.tag} binary reports {reported!r}")
            package.rename(dest)
        shutil.rmtree(BUILD, ignore_errors=True)
    # Replaced in one step, so the link never points at nothing.
    temporary = ENGINE_LINK.with_name(".scene-render.new")
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(os.path.relpath(dest / "scene-render", ENGINE_LINK.parent))
    temporary.replace(ENGINE_LINK)


def smoke_test() -> None:
    """A new scene from sr-core, checked by both tools, then one frame out of the engine."""
    sr_scene = VENV / "bin" / "sr-scene"
    with tempfile.TemporaryDirectory() as folder:
        scene, frame = Path(folder) / "smoke.scene.xml", Path(folder) / "smoke.png"
        scene.write_text(must(sr_scene, "new"))
        must(sr_scene, "check", "--schema", scene)
        must(ENGINE_LINK, "validate", scene)
        must(ENGINE_LINK, "render", scene, "--frame", "0", "--output", frame)
        if not frame.is_file() or frame.read_bytes()[:8] != PNG_SIGNATURE:
            raise Failure("scene-render render exited 0 but wrote no PNG")
        row("OK", "smoke test", "sr-core made a scene, both tools accepted it, the engine rendered a frame")
        # Only a warning: sr-core 1.9.0 reads report["files"] where the engine prints result.files, so this
        # route fails on every engine since v0.6.0 while `scene-render validate`, above, covers the same check.
        linked = run(sr_scene, "check", "--engine", ENGINE_LINK, scene)
        if linked.returncode == 0:
            row("OK", "sr-scene", "check --engine works")
        else:
            row("WARN", "sr-scene", "check --engine fails; use scene-render validate. "
                + (linked.stdout or linked.stderr).strip().split(": ", 1)[-1])


def report_environment() -> None:
    """What rendering leans on but this script does not install; none of it fails the run."""
    if shutil.which("ffmpeg") is None:
        row("WARN", "ffmpeg", "not found: scene-render encode needs it")
    elif "h264_nvenc" not in run("ffmpeg", "-hide_banner", "-encoders").stdout:
        row("WARN", "ffmpeg", "no NVENC encoders: encoding falls back to the CPU")
    else:
        row("OK", "ffmpeg", "with NVENC")
    if ENGINE_LINK.exists():
        chosen = [line for line in run(ENGINE_LINK, "gpus").stdout.splitlines() if line.startswith("*")]
        if chosen:
            row("OK", "gpu", chosen[0].removeprefix("* "))
        else:
            row("WARN", "gpu", "scene-render found no adapter")


def report(name: str, found: Optional[str], wanted: Release, newest: Release) -> bool:
    note = "" if wanted == newest else f"  (held back by --no-build: {newest.tag} has no published binary)"
    if found == wanted.version:
        row("OK", name, f"{found}{note}")
        return True
    row("BEHIND" if found else "MISSING", name, f"{found or 'not installed'}, latest is {wanted.version}{note}")
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Check and install the latest sr-core and scene-render here.")
    parser.add_argument("--check", action="store_true", help="change nothing; exit 1 unless everything is current")
    parser.add_argument("--no-build", action="store_true", help="use the newest published binary, never compile")
    args = parser.parse_args()

    sr_core = remote_releases(SR_CORE_URL)[0]
    engines = remote_releases(ENGINE_URL)
    engine = engines[0]
    if args.no_build:
        engine = next((release for release in engines if published_digest(release)), None)
        if engine is None:
            raise Failure("scene-render has no published binary")

    current = report("sr-core", installed_sr_core(), sr_core, sr_core)
    current &= report("scene-render", installed_engine(), engine, engines[0])
    if not current and args.check:
        return 1
    if not args.check:
        ensure_venv()
        if installed_sr_core() != sr_core.version:
            install_sr_core(sr_core)
        if installed_engine() != engine.version:
            install_engine(engine)
        if not current:
            report("sr-core", installed_sr_core(), sr_core, sr_core)
            report("scene-render", installed_engine(), engine, engines[0])

    smoke_test()
    report_environment()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Failure as failure:
        print(f"doctor: {failure}", file=sys.stderr)
        sys.exit(1)
