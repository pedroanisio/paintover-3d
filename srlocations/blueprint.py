"""A location written as data: JSON a person, a tool or a model can produce with no Python."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from srlocations.cast import Portrait
from srlocations.catalog import SharedCatalog
from srlocations.collision import Contact
from srlocations.location import Location
from srlocations.looks import Look
from srlocations.paint import PaintLayer
from srlocations.registry import Registry, node_from_spec


class Blueprint:
    def __init__(self, data: dict, base: Path = Path(".")) -> None:
        self.data, self.base = data, base

    @classmethod
    def load(cls, path: str | Path) -> "Blueprint":
        return cls(json.loads(Path(path).read_text()), Path(path).resolve().parent)

    def build(self, registry: Optional[Registry] = None) -> Location:
        registry = registry or Registry.default()
        for source in self.data.get("catalogs", ()):  # {"path": relative to this file, "pins": as SharedCatalog.pins}
            SharedCatalog.open(self.base / source["path"]).install(registry, source.get("pins"))
        location = Location(self.data["name"], registry)
        location.contact = Contact(**self.data.get("contact", {}))
        for section, read in registry.readers.items():  # "poses" and "kinds", by name, as the plugin that reads them says
            for name, spec in self.data.get(section, {}).items():
                getattr(registry, section).add(name, read(spec), override=True)
        for name, spec in self.data.get("looks", {}).items():  # {name: as Look.from_spec}, usable as a render mode by name
            Look.from_spec(spec, registry, self.base, name).register(registry, override=True)
        for spec in self.data.get("nodes", ()):
            location.add(node_from_spec(location.registry, self._rooted(spec)))
        if "rig" in self.data:
            rig = dict(self.data["rig"])
            location.rig(rig.pop("use"), **rig)
        for mark in self.data.get("marks", ()):
            location.mark(**mark)
        for spec in self.data.get("stand", ()):  # {"mark": ..., and what a figure takes, such as "pose" and "kind"}
            spec = dict(spec)
            location.stand(spec.pop("mark"), **spec)
        location.settle_all()
        for shot in self.data.get("shots", ()):
            location.shot(**shot)
        for spec in self.data.get("moves", ()):  # {"what": a shot, a mark or a node's name, "time": seconds, and as move()}
            location.move(**spec)
        location.paintings.extend(PaintLayer.from_spec(spec, self.base, location.marks) for spec in self.data.get("paint", ()))
        for spec in self.data.get("cast", ()):  # {"character": a registry.cast name or {"image": a file}, "mark": ..., ...}
            spec = dict(spec)
            character = spec.pop("character")
            location.cast(character if isinstance(character, str) else Portrait(self.base / character["image"]), **spec)
        return location

    def _rooted(self, spec: dict) -> dict:
        """A node's spec with any file named relative to this blueprint."""
        rooted = {**spec, "children": [self._rooted(child) for child in spec["children"]]} if "children" in spec else dict(spec)
        if "path" in rooted:
            rooted["path"] = self.base / rooted["path"]
        return rooted
