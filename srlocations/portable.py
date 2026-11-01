"""Portable documents. A compiled scene names files where they lie on this machine, which no other machine can use. A
package copies them beside the document, named by their content, and points the document at the copies, so the folder can
move anywhere an engine is. Renderer draws through a package too, so every render tests this. What a document reads comes
from sr-core's reading of the schema, not from a list kept here."""
from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from pathlib import Path, PurePosixPath
from typing import Mapping, Union
from urllib.parse import unquote

from sr_core.scene import Scene
from sr_core.vpkg import refs
from sr_core.vpkg.init import init
from sr_core.vpkg.manifest import MANIFEST, dump
from sr_core.vpkg.pack import pack

ASSETS = "assets"
CACHE_VARIABLE = "SRLOCATIONS_CACHE"


def cache_folder(kind: str) -> Path:
    """Where work that can be made again is kept between runs."""
    home = os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache"
    return Path(os.environ.get(CACHE_VARIABLE) or Path(home) / "srlocations") / kind


def bundle(path: Path) -> dict[str, Path]:
    """A file and all the files it reads, by their paths relative to it: a model's .mtl and pictures, a glTF's buffers."""
    found, waiting = {path.name: path}, [(path, PurePosixPath())]
    while waiting:
        current, folder = waiting.pop()
        for written in refs.dependencies(str(current)):
            if refs.SCHEME.match(written):
                continue
            relative = PurePosixPath(unquote(written.replace("\\", "/")))
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError(f"{current} reads {written}, outside its folder, which cannot travel with it")
            inside = folder / relative
            if str(inside) not in found:
                found[str(inside)] = path.parent / inside
                if not found[str(inside)].is_file():
                    raise FileNotFoundError(f"{current} reads {written}, which is not a file")
                waiting.append((found[str(inside)], inside.parent))
    return found


def digest(files: Mapping[str, Path]) -> str:
    """One value for a bundle: its names and contents, and not where it lies."""
    return hashlib.sha256("".join(f"{name}\0{hashlib.sha256(files[name].read_bytes()).hexdigest()}\n"
                                  for name in sorted(files)).encode()).hexdigest()


def carry(source: str, document: Path) -> str:
    """Copies one file the document reads into its assets, and returns the path the document should use for it. A file
    that reads others gets a folder of its own, so they keep the relative paths it names them by."""
    path = Path(source)
    if not path.is_file():
        raise FileNotFoundError(f"{document.name} reads {source}, which is not a file")
    files = bundle(path)
    if len(files) > 1:
        folder = f"{ASSETS}/{digest(files)[:32]}"
        for relative, file in files.items():
            target = document.parent / folder / relative
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(file, target)
        return f"{folder}/{path.name}"
    name = hashlib.sha256(path.read_bytes()).hexdigest()[:32] + path.suffix.lower()
    target = document.parent / ASSETS / name
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    return f"{ASSETS}/{name}"


def package(scene: Scene, document: Union[str, Path]) -> Path:
    """Writes the scene as `document`, with its files in an assets folder beside it. Several documents can share a folder.
    The scene itself keeps its paths. A remote URL stays one."""
    document = Path(document).resolve()
    document.parent.mkdir(parents=True, exist_ok=True)
    portable, carried = scene.copy(), {}
    for node in portable.iter():
        written = node.attributes()
        for attribute, elements in refs.INPUTS.items():
            value = written.get(attribute)
            if value and node.xml_name in elements and not refs.SCHEME.match(str(value)):
                carried.setdefault(value, carry(str(value), document))
                setattr(node, attribute, carried[value])
    document.write_bytes(portable.to_bytes(layout="pretty"))
    return document


def archive(scene: Scene, output: Union[str, Path], name: str) -> Path:
    """Packs the scene into one .vpkg.zip, sr-core's format: `scenerender-vpkg verify` checks it and `unpack` opens it."""
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary:
        folder = Path(temporary) / name  # the manifest records this folder's name, so it must not be a random one
        package(scene, folder / f"{name}.scene.xml")
        spec = init(str(folder))
        spec["package"] |= {"id": name, "title": name}
        (folder / MANIFEST).write_text(dump(spec))
        pack(str(folder), str(output))
    return output
