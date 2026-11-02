"""The extension points: catalogs of named things, libraries that fill them, plugins that bring code."""
from __future__ import annotations

import difflib
import importlib
import importlib.metadata
import importlib.util
import json
import os
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Generic, Iterator, Optional, Sequence, TypeVar

from srlocations.materials import Material
from srlocations.nodes import Group, Node, Prefab

T = TypeVar("T")
ENTRY_POINT_GROUP = "srlocations.plugins"
CATALOGS_VARIABLE = "SRLOCATIONS_CATALOGS"


class CatalogError(LookupError):
    pass


class Catalog(Generic[T]):
    """Names to things. A name is taken once unless a registration says override=True."""

    def __init__(self, kind: str) -> None:
        self.kind, self._items = kind, {}

    def add(self, name: str, item: T, override: bool = False) -> T:
        if name in self._items and not override:
            raise CatalogError(f"{self.kind} {name!r} is already registered; pass override=True to replace it")
        self._items[name] = item
        return item

    def register(self, name: str, override: bool = False) -> Callable[[T], T]:
        """The decorator form of add()."""
        return lambda item: self.add(name, item, override)

    def get(self, name: str) -> T:
        if name not in self._items:
            near = difflib.get_close_matches(name, self._items, n=3)
            raise CatalogError(f"no {self.kind} {name!r}" + (f"; did you mean {', '.join(near)}?" if near else ""))
        return self._items[name]

    def names(self) -> list[str]:
        return sorted(self._items)

    def __getitem__(self, name: str) -> T:
        return self.get(name)

    def __iter__(self) -> Iterator[str]:
        return iter(self._items)

    def __contains__(self, name: str) -> bool:
        return name in self._items


class Registry:
    def __init__(self) -> None:
        self.materials: Catalog[Material] = Catalog("material")
        self.prefabs: Catalog[Callable[..., Node]] = Catalog("prefab")
        self.rigs: Catalog[Callable[..., Any]] = Catalog("light rig")
        self.archetypes: Catalog[Callable[..., Any]] = Catalog("archetype")
        self.modes: Catalog[Callable[..., Any]] = Catalog("render mode")
        self.passes: Catalog[Any] = Catalog("look pass")  # Pass classes, by the name a look written as data uses
        self.cast: Catalog[Any] = Catalog("character")  # Performers
        self.poses: Catalog[Any] = Catalog("pose")  # a figure's pose by name, such as a Mannequin's `pose="sit"`
        self.kinds: Catalog[Any] = Catalog("body")  # a figure's body by name, such as a Mannequin's `kind="child"`
        self.framings: Catalog[Callable[..., Any]] = Catalog("framing")  # how location.frame() composes figures
        self.readers: dict[str, Callable[[Any], Any]] = {}  # a blueprint's section to what reads an entry into that catalog
        self.shared: dict[str, Any] = {}  # installed shared catalogs, by name
        self.resolved: dict[str, str] = {}  # an unpinned shared name to the name@version it stands for
        self.checks: list[Any] = []
        self.plugins = PluginManager(self)

    @classmethod
    def default(cls) -> "Registry":
        """A registry with the stock library, and any plugin installed through entry points."""
        from srlocations.catalog import SharedCatalog
        from srlocations.stock import StockPlugin
        registry = cls()
        registry.plugins.load(StockPlugin())
        registry.plugins.load_entry_points()
        for path in filter(None, os.environ.get(CATALOGS_VARIABLE, "").split(os.pathsep)):
            registry.use(SharedCatalog.open(path))
        return registry

    def create(self, name: str, /, **params: Any) -> Node:
        return self.prefabs.get(name)(**params)

    def use(self, library: Any) -> "Registry":
        """Install anything with install(registry): a Library or a SharedCatalog."""
        library.install(self)
        return self


@dataclass
class Assembly(Prefab):
    """A prefab made of data: other prefabs and solids named in a library file."""
    registry: Optional[Registry] = None
    parts: Sequence[dict] = ()

    def build(self) -> Sequence[Node]:
        return [node_from_spec(self.registry, part) for part in self.parts]


def node_from_spec(registry: Registry, spec: dict) -> Node:
    params = dict(spec)
    name = params.pop("use")
    children = params.pop("children", None)
    if children is not None:
        return Group([node_from_spec(registry, c) for c in children], **params)
    return registry.create(name, **params)


@dataclass
class Library:
    """Data with no code: materials and assemblies, installable from a dict or a JSON file."""
    name: str
    materials: dict[str, Material] = field(default_factory=dict)
    assemblies: dict[str, Sequence[dict]] = field(default_factory=dict)

    @classmethod
    def from_file(cls, path: str | Path) -> "Library":
        data = json.loads(Path(path).read_text())
        materials = {name: Material(**values) for name, values in data.get("materials", {}).items()}
        return cls(data["name"], materials, data.get("assemblies", {}))

    def install(self, registry: Registry) -> None:
        for name, material in self.materials.items():
            registry.materials.add(f"{self.name}.{name}", material)
        for name, parts in self.assemblies.items():
            def make(parts: Sequence[dict] = parts, **params: Any) -> Assembly:
                return Assembly(registry=registry, parts=parts, **params)
            registry.prefabs.add(f"{self.name}.{name}", make)


class Plugin(ABC):
    """Code that extends a registry. `requires` names plugins that must be loaded first."""
    name = ""
    version = "0"
    requires: Sequence[str] = ()

    @abstractmethod
    def register(self, registry: Registry) -> None:
        """Add materials, prefabs, rigs, archetypes and checks."""


class PluginManager:
    def __init__(self, registry: Registry) -> None:
        self.registry, self.loaded = registry, {}

    def load(self, plugin: Plugin) -> Plugin:
        if plugin.name in self.loaded:
            return self.loaded[plugin.name]
        if not plugin.name:
            raise CatalogError(f"{type(plugin).__name__} has no name")
        missing = [name for name in plugin.requires if name not in self.loaded]
        if missing:
            raise CatalogError(f"plugin {plugin.name!r} requires {', '.join(missing)}, not loaded")
        plugin.register(self.registry)
        self.loaded[plugin.name] = plugin
        return plugin

    def load_module(self, module_name: str) -> Plugin:
        return self._from_module(importlib.import_module(module_name))

    def load_file(self, path: str | Path) -> Plugin:
        """A plugin as a single .py file: its one Plugin subclass is loaded."""
        path = Path(path)
        spec = importlib.util.spec_from_file_location(f"srlocations_plugin_{path.stem}", path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module  # a dataclass looks its module up here while it is being made
        spec.loader.exec_module(module)
        return self._from_module(module)

    def load_entry_points(self) -> list[Plugin]:
        """Plugins other packages declare in pyproject.toml under [project.entry-points."srlocations.plugins"]. Packages
        come in no useful order, so each loads once what it requires has. What can never load is refused by load()."""
        waiting = [self._from_entry(entry) for entry in importlib.metadata.entry_points(group=ENTRY_POINT_GROUP)]
        done: list[Plugin] = []
        while waiting:
            ready = next((p for p in waiting if all(name in self.loaded for name in p.requires)), waiting[0])
            done.append(self.load(ready))
            waiting.remove(ready)
        return done

    def _from_entry(self, entry: importlib.metadata.EntryPoint) -> Plugin:
        try:
            made = entry.load()
        except Exception as error:
            raise CatalogError(f"plugin entry point {entry.name!r} ({entry.value}) cannot be loaded: {error}") from error
        if not (isinstance(made, type) and issubclass(made, Plugin)):
            raise CatalogError(f"plugin entry point {entry.name!r}: {getattr(made, '__name__', made)} is not a Plugin")
        return made()

    def _from_module(self, module: Any) -> Plugin:
        found = [v for v in vars(module).values() if isinstance(v, type) and issubclass(v, Plugin)
                 and v is not Plugin and v.__module__ == module.__name__]
        if len(found) != 1:
            raise CatalogError(f"{module.__name__} defines {len(found)} Plugin subclasses, expected 1")
        return self.load(found[0]())
