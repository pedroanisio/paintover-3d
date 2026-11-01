"""Portable documents. A compiled scene names files where they lie on this machine, which no other machine can use. A
package copies them beside the document, named by their content, and points the document at the copies, so the folder can
move anywhere an engine is. Renderer draws through a package too, so every render tests this. What a document reads comes
from sr-core's reading of the schema, not from a list kept here."""
from __future__ import annotations

import hashlib
import shutil
import tempfile
from pathlib import Path
from typing import Union

from sr_core.scene import Scene
from sr_core.vpkg import refs
from sr_core.vpkg.init import init
from sr_core.vpkg.manifest import MANIFEST, dump
from sr_core.vpkg.pack import pack

ASSETS = "assets"


def carry(source: str, document: Path) -> str:
    """Copies one file the document reads into its assets, and returns the path the document should use for it."""
    path = Path(source)
    if not path.is_file():
        raise FileNotFoundError(f"{document.name} reads {source}, which is not a file")
    name = hashlib.sha256(path.read_bytes()).hexdigest()[:32] + path.suffix.lower()
    target = document.parent / ASSETS / name
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    return f"{ASSETS}/{name}"


def package(scene: Scene, document: Union[str, Path]) -> Path:
    """Writes the scene as `document`, with its files in an assets folder beside it. Several documents can share a folder.
    The scene itself keeps its paths. A remote URL stays one. Paths inside a file, as a glTF has, are not followed."""
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
