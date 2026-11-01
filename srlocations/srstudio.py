"""srstudio's cast on this SDK's marks. srstudio has its own environment and its own pin of sr-core, so it is not imported:
its interpreter runs a small worker that writes a document of the character alone, and this SDK's engine renders that to a
transparent cut-out. Nothing is written into srstudio. Name the interpreter with the SRSTUDIO_PYTHON variable, or pass it:

    registry.plugins.load(SrstudioCast())
    location.cast("srstudio.rex", "host", height=1.2, pose={"mouth": "smile"})

Cut-outs are kept in a cache folder by the hash of their document, so a redrawn character renders again and nothing else
does.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Optional, Union

from srlocations.cast import Cutout, Performer, alpha_box
from srlocations.compiler import Renderer
from srlocations.portable import cache_folder
from srlocations.registry import CatalogError, Plugin, Registry

PYTHON_VARIABLE = "SRSTUDIO_PYTHON"
WORKER = Path(__file__).resolve().parent / "_srstudio_worker.py"
ZOOM = 1.5  # of srstudio's 1080 by 1920 frame: past what a figure fills in a 720p shot, so it is only ever scaled down
MEASURE_ZOOM = 0.25  # the figure is found in a small render, since finding it means reading every pixel in Python


def ask(python: str, job: dict) -> Any:
    done = subprocess.run([python, "-B", "-P", str(WORKER)], input=json.dumps(job), text=True, capture_output=True,
                          env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}, cwd=tempfile.gettempdir())
    if done.returncode != 0:
        raise CatalogError(f"srstudio could not do {job['do']}:\n{done.stderr.strip()[-600:]}")
    return json.loads(done.stdout)


@dataclass(frozen=True)
class SrstudioPerformer(Performer):
    """One card of srstudio's cast. A pose holds any of eyes, mouth, arms and brows, in the words of the character's style,
    over the pose on its card."""
    python: str
    slug: str

    def cutout(self, pose: Mapping[str, str]) -> Cutout:
        return _cutout(self.python, self.slug, tuple(sorted(pose.items())))


@lru_cache(maxsize=256)
def _cutout(python: str, slug: str, pose: tuple[tuple[str, str], ...]) -> Cutout:
    renderer = Renderer()
    with tempfile.TemporaryDirectory() as folder:
        written = ask(python, {"do": "draw", "character": slug, "pose": dict(pose), "folder": folder,
                               "zooms": {"full": ZOOM, "small": MEASURE_ZOOM}})
        name = hashlib.sha256(Path(written["full"]).read_bytes()).hexdigest()[:32]
        store = cache_folder("cast")
        store.mkdir(parents=True, exist_ok=True)
        picture, measured = store / f"{name}.png", store / f"{name}.json"
        if not picture.exists() or not measured.exists():
            small = renderer.draw(written["small"], Path(folder) / "small.png")
            box = [round(value * ZOOM / MEASURE_ZOOM) for value in alpha_box(small)]
            drawn = renderer.draw(written["full"], store / f"{name}-{os.getpid()}.png")  # beside it: a rename stays on one disk
            measured.write_text(json.dumps(box))
            drawn.replace(picture)
    return Cutout(picture, tuple(json.loads(measured.read_text())))


@dataclass
class SrstudioCast(Plugin):
    """Registers each srstudio character as srstudio.<slug>."""
    python: Optional[Union[str, Path]] = None
    name = "srstudio"
    version = "0.1.0"
    characters: dict[str, Any] = field(default_factory=dict)

    def register(self, registry: Registry) -> None:
        python = self.python or os.environ.get(PYTHON_VARIABLE)
        if not python:
            raise CatalogError(f"set {PYTHON_VARIABLE} to the interpreter of an environment with srstudio installed")
        self.characters = ask(str(python), {"do": "cast"})
        for slug in self.characters:
            registry.cast.add(f"srstudio.{slug}", SrstudioPerformer(str(python), slug))
