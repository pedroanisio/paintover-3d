"""A shared catalog of props, shaders, looks and locations: a directory any number of projects can read and publish to.

    <root>/catalog.json                  its name
    <root>/shaders/<name>/<version>.json
    <root>/props/<name>/<version>.json
    <root>/looks/<name>/<version>.json
    <root>/locations/<name>/<version>.json
    <root>/files/<sha256>.<ext>          textures, stored by content
    <root>/models/<digest>/...           an imported model and the files it reads, keeping their relative paths

Share it as a git repository or a network folder. A published version never changes: publishing the same content again
does nothing, and different content under a taken version is refused. Publishing a prop freezes it to plain data, so a
prop built by a plugin's code can be used by a project without that plugin, and it pins the exact shaders it was made
with. Point a registry at a catalog with registry.use(SharedCatalog.open(path)), or with the SRLOCATIONS_CATALOGS
variable, and its items appear as <catalog>.<name>, the newest version, and <catalog>.<name>@<version>.

Props are reused in two ways. A frozen prop (publish_prop) is fixed geometry that can name shader slots. A template
(publish_template, see templates.py) has parameters, variants and slots too, and can nest other props.

A look (publish_look) is a house style: its passes, with its textures and materials stored here. It becomes a render mode
named <catalog>.<name>, and any version answers to that name, so paint limited to a look stays on it across versions.

A location (publish_location) is a blueprint with this catalog's names pinned to exact versions, so it builds the same
for everyone. It needs nothing but the catalog and the stock library: catalog.location(name) builds it.

catalog.browse() writes a page of what is here. catalog.seal(), SharedCatalog.fetch() and CatalogServer take it to other
machines, and say whether it arrived unchanged (see exchange.py).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
from dataclasses import asdict, dataclass, field
from difflib import get_close_matches
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional, Sequence, Union

from srlocations.geometry import Vec3
from srlocations.location import Issue, Location
from srlocations.looks import Look, Styled, Texture
from srlocations.materials import Material
from srlocations.mesh import MODEL, Mesh
from srlocations.nodes import Backdrop, Box, Cone, Cylinder, Light, Node, Placed, Point, Prefab, Round, Solid, Sphere, Spot
from srlocations.paint import Decal
from srlocations.portable import bundle, digest
from srlocations.registry import CatalogError, Registry
from srlocations.surfaces import Surface
from srlocations.templates import PLACEMENT, Number, Param, PropTemplate, TemplateError, evaluate

SCHEMA = 1
KINDS = {"shader": "shaders", "prop": "props", "look": "looks", "location": "locations"}
NAME = re.compile(r"[a-z0-9][a-z0-9._-]*")
VERSION = re.compile(r"(\d+)\.(\d+)\.(\d+)")
STORED_FILE = re.compile(r"[0-9a-f]{64}(\.[a-z0-9]+)?")
STORED_MODEL = re.compile(r"[0-9a-f]{64}")
SOLIDS = {"box": Box, "cylinder": Cylinder, "cone": Cone, "sphere": Sphere, "parametric": Surface, "extrude": Decal,
          "mesh": Mesh, "plane": Backdrop}
LIGHTS = {"point": Point, "spot": Spot}
MAX_LEAVES = 20000  # in one prop, nested props included: a catalog is shared data, so a size is enforced on it
MAX_DEPTH = 8
Pins = dict[str, dict[str, str]]


def _order(version: str) -> tuple[int, ...]:
    return tuple(int(n) for n in version.split("."))


def _digest(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _rounded(values: Iterable[float]) -> list[float]:
    return [round(float(v), 6) + 0.0 for v in values]


def _freeze(leaf: Placed, material: Optional[str] = None) -> dict:
    """A placed leaf as plain data, in the prop's frame."""
    common = {"at": _rounded(leaf.world.position), "basis": [_rounded(row) for row in leaf.world.basis]}
    if leaf.roles:  # only when there are some, so a prop without them keeps its digest
        common["role"] = " ".join(sorted(leaf.roles))
    item = leaf.item
    if isinstance(item, Solid):
        if item.primitive not in SOLIDS:
            raise CatalogError(f"{leaf.path}: a {item.primitive!r} solid cannot be frozen")
        part = {**common, "solid": item.primitive, "material": material, "casts_shadow": item.casts_shadow,
                "dimensions": {k: round(v, 6) for k, v in item.dimensions().items()}}
        if isinstance(item, (Surface, Decal)):
            # A name is kept, so sectors of one shape can go on sharing it, and ink no line between them.
            return {**part, "surface": item.spec(), **({"name": item.name} if item.name else {})}
        return part if not hasattr(item, "segments") else {**part, "segments": item.segments}
    if item.kind not in LIGHTS:
        raise CatalogError(f"{leaf.path}: a prop can carry point and spot lights, not {item.kind!r}")
    part = {**common, "light": item.kind, "intensity": item.intensity, "color": item.color, "shadows": item.shadows,
            "softness": item.softness, "reach": item.reach}
    return part if item.kind == "point" else {**part, "cone": item.cone}


def _extent(solids: Sequence[Placed]) -> list[float]:
    bounds = [leaf.item.bounds(leaf.world) for leaf in solids]
    low = Vec3(*(min(getattr(b[0], a) for b in bounds) for a in "xyz"))
    high = Vec3(*(max(getattr(b[1], a) for b in bounds) for a in "xyz"))
    return _rounded(high - low)


class Budget:
    """How many leaves one prop may still make, shared with the props nested in it."""

    def __init__(self) -> None:
        self.left = MAX_LEAVES

    def spend(self, count: int) -> None:
        self.left -= count
        if self.left < 0:
            raise TemplateError(f"a prop cannot have more than {MAX_LEAVES} parts")


def _thaw(part: dict, material: str) -> Node:
    place = {"at": part["at"], "basis": tuple(tuple(row) for row in part["basis"]), "role": part.get("role", "")}
    if "light" in part:
        options = {"cone": part["cone"]} if "cone" in part else {}
        return LIGHTS[part["light"]](part["intensity"], color=part["color"], shadows=part["shadows"],
                                     softness=part["softness"], reach=part["reach"], **options, **place)
    kind, size = SOLIDS[part["solid"]], part["dimensions"]
    look = {"material": material, "casts_shadow": part["casts_shadow"], **place}
    if kind in (Surface, Decal):
        return kind(**part["surface"], **look, **({"name": part["name"]} if "name" in part else {}))
    if kind is Box:
        return Box((size["width"], size["height"], size["depth"]), **look)
    if kind is Backdrop:
        return Backdrop(size["width"], size["height"], **look)
    if kind is Sphere:
        return Sphere(size["radius"], segments=part["segments"], **look)
    return kind(size["radius"], size["height"], segments=part["segments"], **look)


def _model_path(root: Path, stored: dict) -> Path:
    """Where a published model lies. A prop is shared data, so its names are not trusted to stay inside the catalog."""
    if not STORED_MODEL.fullmatch(stored["folder"]) or stored["file"] not in stored["files"]:
        raise CatalogError(f"{stored['folder']!r}/{stored['file']!r} is not a stored model")
    for relative in stored["files"]:
        if Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise CatalogError(f"{relative!r} is not a stored model's file")
    return root / "models" / stored["folder"] / stored["file"]


@dataclass
class FrozenProp(Prefab):
    """A published prop: geometry as data, with no code behind it."""
    catalog: str = ""
    entry: str = ""
    version: str = ""
    frozen: Sequence[dict] = ()
    slots: dict[str, str] = field(default_factory=dict)  # slot to its default shader, as name@version
    shaders: dict[str, str] = field(default_factory=dict)  # slot to the shader this instance uses instead
    nested: bool = False  # inside another prop, which pins its version
    root: Optional[Path] = None  # of the catalog, where a prop's models lie

    def shader(self, slot: str) -> str:
        return self.shaders.get(slot) or f"{self.catalog}.{self.slots[slot]}"

    def _model(self, part: dict) -> Mesh:
        stored, chosen = part["model"], self.shader(part["slot"]) if part.get("slot") else part["material"]
        return Mesh(_model_path(self.root, stored), scale=stored["scale"], node=stored["node"], size=stored["size"],
                    hollow=stored["hollow"], casts_shadow=part["casts_shadow"], at=part["at"], role=part.get("role", ""),
                    basis=tuple(tuple(row) for row in part["basis"]),
                    material=MODEL if chosen is None else chosen if part.get("slot") else f"{self.catalog}.{chosen}",
                    materials={slot: f"{self.catalog}.{ref}" for slot, ref in stored["slots"].items()})

    def build(self) -> Sequence[Node]:
        parts = [self._model(part) if "model" in part else
                 _thaw(part, self.shader(part["slot"]) if part.get("slot") else f"{self.catalog}.{part['material']}")
                 if "solid" in part else _thaw(part, "") for part in self.frozen]
        for index, part in enumerate(parts):  # a path tells one part from another, and ink draws its lines between them
            part.name = part.name or f"part-{index}"
        return parts


@dataclass
class TemplateProp(FrozenProp):
    """A published template with its parameters set."""
    source: Optional["SharedCatalog"] = None
    template: Sequence[dict] = ()
    values: dict[str, Number] = field(default_factory=dict)
    budget: Optional[Budget] = None
    depth: int = 0

    def build(self) -> Sequence[Node]:
        return list(self._expand(self.template, self.values, self.budget or Budget()))

    def _expand(self, parts: Sequence[dict], scope: dict[str, Number], budget: Budget) -> Iterator[Node]:
        for part in parts:
            if "when" in part and not evaluate(part["when"], scope):
                continue
            if "repeat" in part:
                count = evaluate(part["repeat"], scope)
                if count != int(count) or count < 0:
                    raise TemplateError(f"{self.entry}: repeat {part['repeat']!r} is {count}, not a whole number")
                for index in range(int(count)):
                    budget.spend(1)
                    inner = {**scope, part["as"]: index} if "as" in part else scope
                    yield from self._expand(part.get("parts", ()), inner, budget)
                continue
            budget.spend(1)
            yield self._node(part, scope, budget)

    def _node(self, part: dict, scope: dict[str, Number], budget: Budget) -> Node:
        place: dict[str, Any] = {"at": [evaluate(value, scope) for value in part.get("at", (0, 0, 0))]}
        place |= {key: evaluate(part[key], scope) for key in ("yaw", "pitch", "roll") if key in part}
        place["role"] = part.get("role", "")
        if "prop" in part:
            return self._nest(part, scope, budget, place)
        if "light" in part:
            return self._light(part, scope, place)
        return self._solid(part, scope, place)

    def _nest(self, part: dict, scope: dict[str, Number], budget: Budget, place: dict[str, Any]) -> Node:
        if self.depth >= MAX_DEPTH:
            raise TemplateError(f"{self.entry}: props are nested deeper than {MAX_DEPTH}")
        params = {name: evaluate(value, scope, text=True) for name, value in part.get("params", {}).items()}
        shaders = {slot: self.shader(value[1:]) if value.startswith("$") else f"{self.catalog}.{value}"
                   for slot, value in part.get("shaders", {}).items()}
        return self.source.instance(self.source.pinned(part["prop"]), nested=True, budget=budget,
                                    depth=self.depth + 1, shaders=shaders, **params, **place)

    def _light(self, part: dict, scope: dict[str, Number], place: dict[str, Any]) -> Node:
        kind = LIGHTS.get(part["light"])
        if kind is None:
            raise TemplateError(f"{self.entry}: a prop can carry point and spot lights, not {part['light']!r}")
        options = {"cone": evaluate(part["cone"], scope)} if "cone" in part else {}
        if "reach" in part:
            options["reach"] = evaluate(part["reach"], scope)
        return kind(evaluate(part.get("intensity", 1), scope), color=part.get("color", "#ffffff"), **options, **place)

    def _solid(self, part: dict, scope: dict[str, Number], place: dict[str, Any]) -> Node:
        def size(key: str) -> float:
            value = evaluate(part[key], scope)
            if value <= 0:
                raise TemplateError(f"{self.entry}: {key} {part[key]!r} comes to {value}, which is not positive")
            return value
        slot = part["shader"]
        look = {"material": self.shader(scope[slot[1:]] if slot.startswith("$") else slot),
                "casts_shadow": part.get("casts_shadow", True), **place}
        if part["solid"] == "box":
            sizes = [evaluate(value, scope) for value in part["size"]]
            if len(sizes) != 3 or min(sizes) <= 0:
                raise TemplateError(f"{self.entry}: box size {part['size']} comes to {sizes}, which is not positive")
            return Box(sizes, **look)
        extra = {"segments": part["segments"]} if "segments" in part else {}
        if part["solid"] == "sphere":
            return Sphere(size("radius"), **extra, **look)
        return SOLIDS[part["solid"]](size("radius"), size("height"), **extra, **look)


@dataclass(frozen=True)
class Entry:
    kind: str
    name: str
    version: str
    digest: str
    payload: dict
    tags: tuple[str, ...] = ()
    description: str = ""
    size: Optional[tuple[float, float, float]] = None  # a prop's width, height and depth in metres

    @property
    def ref(self) -> str:
        return f"{self.name}@{self.version}"


class SharedCatalog:
    def __init__(self, root: Union[str, Path], name: str) -> None:
        self.root, self.name = Path(root).resolve(), name
        self._installed: list[Registry] = []
        self._pinned: dict[str, Entry] = {}

    @classmethod
    def create(cls, root: Union[str, Path], name: str) -> "SharedCatalog":
        """Opens the catalog at root, making it if it is not there."""
        if not NAME.fullmatch(name) or "." in name:
            raise CatalogError(f"{name!r} is not a catalog name: use lower-case letters, digits, - and _")
        manifest = Path(root) / "catalog.json"
        if manifest.exists():
            return cls.open(root)
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(json.dumps({"schema": SCHEMA, "name": name}, indent=2) + "\n")
        return cls(root, name)

    @classmethod
    def open(cls, root: Union[str, Path], signers: Union[str, Path, None] = None) -> "SharedCatalog":
        """With `signers`, an allowed-signers file, refuses a catalog that they did not seal or that changed since."""
        manifest = Path(root) / "catalog.json"
        if not manifest.exists():
            raise CatalogError(f"no shared catalog at {root}")
        if signers:
            from srlocations.exchange import require_seal
            require_seal(root, signers)
        data = json.loads(manifest.read_text())
        if data.get("schema") != SCHEMA:
            raise CatalogError(f"{root} has catalog schema {data.get('schema')}; this SDK reads {SCHEMA}")
        return cls(root, data["name"])

    def _path(self, kind: str, name: str, version: str) -> Path:
        """Every lookup comes through here, and templates hold refs, so a name never gets to leave the catalog."""
        if not NAME.fullmatch(name) or ".." in name:
            raise CatalogError(f"{name!r} is not an item name: use lower-case letters, digits, ., - and _")
        if not VERSION.fullmatch(version):
            raise CatalogError(f"{version!r} is not a version: use major.minor.patch")
        return self.root / KINDS[kind] / name / f"{version}.json"

    def _exists(self, kind: str, ref: str) -> bool:
        name, _, version = ref.partition("@")
        try:
            return self._path(kind, name, version).exists()
        except CatalogError:
            return False

    def _write_once(self, path: Path, text: str) -> None:
        """Creates the file whole, or fails if another publisher got there first."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False, suffix=".tmp") as out:
            out.write(text)
        try:
            os.link(out.name, path)
        except FileExistsError:
            raise CatalogError(f"{path.name} was published by someone else just now; check it and bump the version")
        finally:
            os.unlink(out.name)

    def _publish(self, kind: str, name: str, version: str, payload: dict, tags: Sequence[str], description: str,
                 size: Optional[Sequence[float]] = None) -> Entry:
        entry = Entry(kind, name, version, _digest(payload), payload, tuple(tags), description,
                      tuple(size) if size else None)
        path = self._path(kind, name, version)
        if path.exists():
            taken = self.get(kind, name, version)
            if taken.digest != entry.digest:
                raise CatalogError(f"{kind} {entry.ref} is already published with other content; bump the version")
            return taken
        self._write_once(path, json.dumps({"schema": SCHEMA, **asdict(entry)}, indent=2, sort_keys=True) + "\n")
        for registry in self._installed if kind != "location" else ():  # usable at once, but a name in use stays put
            self._register(registry, entry, f"{self.name}.{name}" not in self._catalog_of(registry, kind))
        return entry

    def _store_file(self, source: str) -> str:
        data = Path(source).read_bytes()
        stored = hashlib.sha256(data).hexdigest() + Path(source).suffix.lower()
        target = self.root / "files" / stored
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        return stored

    def _store_model(self, mesh: Mesh, shaders: dict[str, str]) -> dict:
        files = bundle(mesh.path)
        folder = digest(files)
        for relative, source in files.items():
            target = self.root / "models" / folder / relative
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
        return {"folder": folder, "file": mesh.path.name, "node": mesh.node, "hollow": mesh.hollow,
                "files": {relative: hashlib.sha256(source.read_bytes()).hexdigest() for relative, source in files.items()},
                "scale": _rounded(mesh.factors), "size": _rounded(mesh.size) if mesh.size else None,
                "slots": {slot: shaders[name] for slot, name in mesh.materials.items()}}

    def publish_shader(self, name: str, material: Material, version: str = "1.0.0", tags: Sequence[str] = (),
                       description: str = "") -> Entry:
        material.validate()
        stored = {attribute: self._store_file(path) for attribute, path in material.maps.items()}
        return self._publish("shader", name, version, asdict(material) | {"maps": stored}, tags, description)

    def publish_prop(self, name: str, node: Node, registry: Registry, version: str = "1.0.0",
                     tags: Sequence[str] = (), description: str = "",
                     slots: Optional[dict[str, str]] = None) -> Entry:
        """Freezes a node into the catalog, with every shader it uses. `slots` names materials a user can swap."""
        leaves = list(node.walk())
        solids = [leaf for leaf in leaves if isinstance(leaf.item, Solid)]
        if not solids:
            raise CatalogError(f"prop {name!r} has no solids")
        shaders = {material: self._adopt(material, registry, version)
                   for material in sorted({skin.name for leaf in solids for skin in leaf.item.skins() if not skin.own}
                                          | {name for leaf in solids if isinstance(leaf.item, Mesh)
                                             for name in leaf.item.materials.values()})}
        parts = [_freeze(leaf, shaders.get(leaf.item.material) if isinstance(leaf.item, Solid) else None) for leaf in leaves]
        for part, leaf in zip(parts, leaves):
            if isinstance(leaf.item, Mesh):
                part["model"] = self._store_model(leaf.item, shaders)
        payload: dict[str, Any] = {"parts": parts}
        if slots:
            unused = sorted(set(slots.values()) - set(shaders))
            if unused:
                raise CatalogError(f"prop {name!r} does not use {', '.join(unused)}")
            by_material = {material: slot for slot, material in slots.items()}
            for part, leaf in zip(parts, leaves):
                if isinstance(leaf.item, Solid) and leaf.item.material in by_material:
                    part["slot"] = by_material[leaf.item.material]
            payload["slots"] = {slot: shaders[material] for slot, material in slots.items()}
        return self._publish("prop", name, version, payload, tags, description, _extent(solids))

    def publish_template(self, template: PropTemplate, registry: Registry, version: str = "1.0.0") -> Entry:
        """Publishes a parametric prop. It is built at its defaults, its limits, every variant and every choice first, so
        a template that cannot make a prop is refused here and not on someone else's machine."""
        template.check()
        slots = {slot: self._adopt(material, registry, version) for slot, material in template.slots.items()}
        payload = {"template": True, "params": {name: p.spec() for name, p in template.params.items()},
                   "slots": slots, "variants": self._resolved_variants(template, registry, version),
                   "parts": self._resolved_parts(template.parts, registry, version)}
        entry = Entry("prop", template.name, version, _digest(payload), payload)
        lows = {n: p.min for n, p in template.params.items() if p.min is not None}
        highs = {n: p.max for n, p in template.params.items() if p.max is not None}
        trials: list[dict] = [{}, lows, highs, *({"variant": name} for name in template.variants),
                              *({n: value} for n, p in template.params.items() for value in p.trials())]
        solids: list[Placed] = []
        for trial in trials:
            built = [leaf for leaf in self.instance(entry, **trial).walk() if isinstance(leaf.item, Solid)]
            solids = solids or built
        if not solids:
            raise CatalogError(f"prop {template.name!r} has no solids at its defaults")
        return self._publish("prop", template.name, version, payload, template.tags, template.description,
                             _extent(solids))

    def publish_look(self, name: str, look: Look, registry: Registry, version: str = "1.0.0", tags: Sequence[str] = (),
                     description: str = "") -> Entry:
        """Publishes a house style with every picture and material it names, so it needs nothing but this catalog. A pass
        from a plugin is refused, since a reader may not have the plugin."""
        spec = look.spec(registry)
        foreign = sorted({step["kind"] for step in spec["passes"] if not step["kind"].startswith("stock.")})
        if foreign:
            raise CatalogError(f"look {name!r} uses {', '.join(foreign)}, which a reader of this catalog may not have")
        payload = {**spec, "textures": {key: {**value, "path": self._store_file(value["path"])}
                                        for key, value in spec["textures"].items()},
                   "materials": {key: {"shader": self._adopt(value, registry, version)} if isinstance(value, str)
                                 else {**value, "maps": {attribute: self._store_file(path)
                                                         for attribute, path in value["maps"].items()}}
                                 for key, value in spec["materials"].items()}}
        self._look(Entry("look", name, version, _digest(payload), payload), registry)
        return self._publish("look", name, version, payload, tags, description)

    def _stored(self, stored: str) -> str:
        if not STORED_FILE.fullmatch(stored):
            raise CatalogError(f"{stored!r} is not a stored file name")
        return str(self.root / "files" / stored)

    def _look(self, entry: Entry, registry: Optional[Registry] = None) -> Look:
        def material(value: dict) -> Material:
            if "shader" in value:
                name, _, version = value["shader"].partition("@")
                return self._material(self.get("shader", name, version))
            return Material(**{**value, "maps": {key: self._stored(stored) for key, stored in value["maps"].items()}})

        look = Look.from_spec({**entry.payload, "materials": {}, "textures": {}}, registry or Registry.default(),
                              name=f"{self.name}.{entry.name}")
        look.materials = {key: material(value) for key, value in entry.payload["materials"].items()}
        look.textures = {key: Texture(**{**value, "path": self._stored(value["path"])})
                         for key, value in entry.payload["textures"].items()}
        return look

    def look(self, name: str, version: Optional[str] = None, registry: Optional[Registry] = None) -> Look:
        """A published look, the newest unless a version is named."""
        return self._look(self.get("look", name, version), registry)

    def publish_location(self, name: str, blueprint: dict, version: str = "1.0.0", tags: Sequence[str] = (),
                         description: str = "") -> Entry:
        """Publishes a blueprint, as data or as read from a .location.json. It is built first with nothing but the stock
        library and this catalog, so a location that leans on a plugin or a file is refused here."""
        for key in ("paint", "looks", "cast"):
            if key in blueprint:
                raise CatalogError(f"location {name!r} has {key}, which can name files and so cannot be published")
        payload = {key: self._pin(value) for key, value in blueprint.items() if key != "catalogs"} | {"name": name}
        entry = Entry("location", name, version, _digest(payload), payload)
        errors = [issue.message for issue in self._built(entry).validate() if issue.severity == "error"]
        if errors:
            raise CatalogError(f"location {name!r} cannot be published: {errors[0]}")
        return self._publish("location", name, version, payload, tags, description)

    def _pin(self, value: Any, key: str = "") -> Any:
        """A copy of blueprint data with every name from this catalog made name@version."""
        if isinstance(value, dict):
            return {k: self._pin(v, k) for k, v in value.items()}
        if isinstance(value, list):
            return value if key == "looks" else [self._pin(v, key) for v in value]
        if isinstance(value, str) and value.startswith(f"{self.name}.") and "@" not in value:
            kind = "prop" if key == "use" else "shader"
            return f"{self.name}.{self.get(kind, value.removeprefix(f'{self.name}.')).ref}"
        return value

    def _built(self, entry: Entry, registry: Optional[Registry] = None) -> Location:
        from srlocations.blueprint import Blueprint
        return Blueprint(entry.payload).build((registry or Registry.default()).use(self))

    def location(self, name: str, version: Optional[str] = None, registry: Optional[Registry] = None) -> Location:
        """A published location, built. It is a new Location each time, yours to add to."""
        return self._built(self.get("location", name, version), registry)

    def _resolved_variants(self, template: PropTemplate, registry: Registry, version: str) -> dict:
        resolved = {}
        for name, values in template.variants.items():
            resolved[name] = dict(values)
            if "shaders" in values:
                resolved[name]["shaders"] = {slot: self._adopt(material, registry, version)
                                             for slot, material in values["shaders"].items()}
        return resolved

    def _resolved_parts(self, parts: Sequence[dict], registry: Registry, version: str) -> list[dict]:
        """A copy of the parts with every nested prop and shader pinned to the version it is published against."""
        resolved = []
        for part in parts:
            part = dict(part)
            if "parts" in part:
                part["parts"] = self._resolved_parts(part["parts"], registry, version)
            if "prop" in part:
                name, _, pinned = part["prop"].partition("@")
                nested = self.get("prop", name, pinned or None)
                for given, what, known in ((part.get("params", {}), "parameter", nested.payload.get("params", {})),
                                           (part.get("shaders", {}), "shader slot", nested.payload.get("slots", {}))):
                    for key in given:
                        if key not in known:
                            raise self._unknown(nested, what, key, known)
                part["prop"] = nested.ref
                part["shaders"] = {slot: value if value.startswith("$") else self._adopt(value, registry, version)
                                   for slot, value in part.get("shaders", {}).items()}
            resolved.append(part)
        return resolved

    def _adopt(self, material: str, registry: Registry, version: str) -> str:
        """The catalog's name@version for a material a prop uses, publishing it here if it is from elsewhere."""
        prefix = f"{self.name}."
        if material.startswith(prefix):
            return registry.resolved.get(material, material).removeprefix(prefix)
        name, value = f"from.{material.replace('@', '-')}", registry.materials.get(material)
        same = _digest(asdict(value)) if not value.maps else None
        for entry in self.entries("shader"):
            if entry.name == name and entry.digest == same:
                return entry.ref
        return self.publish_shader(name, value, version, description=f"Copied from {material}").ref

    def get(self, kind: str, name: str, version: Optional[str] = None) -> Entry:
        """One entry, the newest when no version is given. A file that no longer matches its digest is refused."""
        if version is None:
            versions = [e.version for e in self.entries(kind) if e.name == name]
            if not versions:
                raise CatalogError(f"no {kind} {name!r} in catalog {self.name!r}")
            version = max(versions, key=_order)
        path = self._path(kind, name, version)
        if not path.exists():
            raise CatalogError(f"no {kind} {name}@{version} in catalog {self.name!r}")
        return self._read(path)

    def _read(self, path: Path) -> Entry:
        try:
            data = json.loads(path.read_text())
            if _digest(data["payload"]) != data["digest"]:
                raise CatalogError(f"{path} does not match its digest: the file was changed after publishing")
            return Entry(data["kind"], data["name"], data["version"], data["digest"], data["payload"], tuple(data["tags"]),
                         data["description"], tuple(data["size"]) if data["size"] else None)
        except (ValueError, KeyError, TypeError) as error:
            raise CatalogError(f"{path} is not a catalog entry: {error}") from None

    def entries(self, kind: Optional[str] = None) -> list[Entry]:
        kinds = [kind] if kind else list(KINDS)
        paths = [p for k in kinds for p in sorted((self.root / KINDS[k]).glob("*/*.json"))]
        return sorted((self._read(p) for p in paths), key=lambda e: (e.kind, e.name, _order(e.version)))

    def search(self, text: str = "", kind: Optional[str] = None, tags: Sequence[str] = ()) -> list[Entry]:
        """The newest version of each item with `text` in its name, description or tags, and all of `tags`."""
        newest = {(e.kind, e.name): e for e in self.entries(kind)}
        needle = text.lower()
        return [e for e in newest.values() if set(tags) <= set(e.tags)
                and needle in " ".join((e.name, e.description, *e.tags)).lower()]

    def seal(self, key: Union[str, Path]) -> Path:
        """Signs what this catalog holds now with an SSH key, so a reader can tell if it changes."""
        from srlocations.exchange import seal
        return seal(self.root, key)

    @classmethod
    def fetch(cls, source: Union[str, Path], folder: Union[str, Path], token: Optional[str] = None,
              signers: Union[str, Path, None] = None) -> "SharedCatalog":
        """Brings a catalog from a URL or a folder to `folder` (see exchange.py)."""
        from srlocations.exchange import fetch
        return fetch(source, folder, token, signers)

    def browse(self, output: Union[str, Path, None] = None, thumbnails: bool = True) -> Path:
        """Writes a page of what is here, into `browse/` unless told otherwise."""
        from srlocations.browse import page
        return page(self, output, thumbnails)

    def verify(self, signers: Union[str, Path, None] = None) -> list[Issue]:
        """Everything a reader relies on: digests, stored textures, shader values, what props pin, and that every
        location still builds. With `signers`, also that they sealed exactly this."""
        issues: list[Issue] = []
        if signers:
            from srlocations.exchange import check_seal
            issues += check_seal(self.root, signers)
        checks = {"shader": self._verify_shader, "prop": self._verify_prop, "look": self._verify_look,
                  "location": self._verify_location}
        for kind in KINDS:
            for path in sorted((self.root / KINDS[kind]).glob("*/*.json")):
                try:
                    entry = self._read(path)
                except CatalogError as error:
                    issues.append(Issue("error", "catalog-digest", str(error)))
                    continue
                issues.extend(checks[kind](entry))
        return issues

    def _verify_stored(self, entry: Entry, files: Iterable[str]) -> Iterable[Issue]:
        for stored in files:
            path = self.root / "files" / stored
            if not STORED_FILE.fullmatch(stored) or not path.exists():
                yield Issue("error", "catalog-file", f"{entry.ref}: texture {stored} is missing")
            elif hashlib.sha256(path.read_bytes()).hexdigest() != stored.split(".")[0]:
                yield Issue("error", "catalog-file", f"{entry.ref}: texture {stored} was changed")

    def _verify_model(self, entry: Entry, stored: dict) -> Iterable[Issue]:
        for relative, expected in stored["files"].items():
            path = self.root / "models" / stored["folder"] / relative
            if not path.is_file():
                yield Issue("error", "catalog-file", f"{entry.ref}: model file {relative} is missing")
            elif hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                yield Issue("error", "catalog-file", f"{entry.ref}: model file {relative} was changed")

    def _verify_look(self, entry: Entry) -> Iterable[Issue]:
        materials = entry.payload["materials"].values()
        yield from self._verify_stored(entry, [*(value["path"] for value in entry.payload["textures"].values()),
                                               *(stored for value in materials for stored in value.get("maps", {}).values())])
        for ref in sorted(value["shader"] for value in materials if "shader" in value):
            if not self._exists("shader", ref):
                yield Issue("error", "catalog-reference", f"{entry.ref} uses {ref}, which is not in the catalog")
        try:
            self._look(entry)
        except (CatalogError, OSError, ValueError) as error:
            yield Issue("error", "catalog-look", f"{entry.ref}: {error}")

    def _verify_shader(self, entry: Entry) -> Iterable[Issue]:
        yield from self._verify_stored(entry, entry.payload["maps"].values())
        try:
            self._material(entry).validate()
        except Exception as error:
            yield Issue("error", "catalog-shader", f"{entry.ref}: {error}")

    def _verify_prop(self, entry: Entry) -> Iterable[Issue]:
        shaders, props, models = set(entry.payload.get("slots", {}).values()), set(), []
        def collect(parts: Sequence[dict]) -> None:
            for part in parts:
                collect(part.get("parts", ()))
                if part.get("material"):
                    shaders.add(part["material"])
                if "model" in part:
                    shaders.update(part["model"]["slots"].values())
                    models.append(part["model"])
                if "prop" in part:
                    props.add(part["prop"])
                    shaders.update(v for v in part.get("shaders", {}).values() if not v.startswith("$"))
        collect(entry.payload["parts"])
        for stored in models:
            yield from self._verify_model(entry, stored)
        missing = [r for r in sorted(shaders) if not self._exists("shader", r)]
        missing += [r for r in sorted(props) if not self._exists("prop", r)]
        for ref in missing:
            yield Issue("error", "catalog-reference", f"{entry.ref} uses {ref}, which is not in the catalog")
        if entry.payload.get("template") and not missing:
            try:
                list(self.instance(entry).walk())
            except CatalogError as error:
                yield Issue("error", "catalog-template", f"{entry.ref}: {error}")

    def _verify_location(self, entry: Entry) -> Iterable[Issue]:
        try:
            found = self._built(entry).validate()
        except CatalogError as error:
            yield Issue("error", "catalog-location", f"{entry.ref}: {error}")
            return
        yield from (Issue("error", "catalog-location", f"{entry.ref}: {i.message}") for i in found if i.severity == "error")

    def _material(self, entry: Entry) -> Material:
        values = dict(entry.payload)
        for stored in values["maps"].values():
            if not STORED_FILE.fullmatch(stored):
                raise CatalogError(f"{entry.ref}: {stored!r} is not a stored file name")
        values["maps"] = {key: str(self.root / "files" / stored) for key, stored in values["maps"].items()}
        return Material(**values)

    def _chosen(self, kind: str, wanted: dict[str, str]) -> dict[str, Entry]:
        """Each item's entry: its pin when it has one, otherwise its newest version."""
        chosen: dict[str, Entry] = {}
        for entry in self.entries(kind):  # oldest first, so the newest is left standing
            if entry.name not in wanted:
                chosen[entry.name] = entry
            elif entry.version == wanted[entry.name]:
                chosen[entry.name] = entry
        missing = sorted(set(wanted) - set(chosen))
        if missing:
            raise CatalogError(f"catalog {self.name!r} has no pinned {kind} {', '.join(missing)}")
        return chosen

    def install(self, registry: Registry, pins: Optional[Pins] = None) -> None:
        """Adds every item to the registry, under its plain name, its pinned or newest version, and name@version."""
        installed = registry.shared.get(self.name)
        if installed is not None:
            if installed.root != self.root:
                raise CatalogError(f"two catalogs are named {self.name!r}: {installed.root} and {self.root}")
            return
        pins = pins or {}
        for kind, wanted in (("shader", pins.get("shaders", {})), ("prop", pins.get("props", {})),
                             ("look", pins.get("looks", {}))):
            chosen = self._chosen(kind, wanted)
            for entry in self.entries(kind):
                self._register(registry, entry, chosen[entry.name].version == entry.version)
        registry.shared[self.name] = self
        self._installed.append(registry)

    def _catalog_of(self, registry: Registry, kind: str):
        return {"shader": registry.materials, "look": registry.modes}.get(kind, registry.prefabs)

    def _register(self, registry: Registry, entry: Entry, plain: bool) -> None:
        """An entry under name@version and, when `plain`, under its bare name too."""
        item = (self._material(entry) if entry.kind == "shader"
                else self._mode(entry, registry) if entry.kind == "look" else self._factory(entry))
        target = self._catalog_of(registry, entry.kind)
        target.add(f"{self.name}.{entry.ref}", item)
        if plain:
            target.add(f"{self.name}.{entry.name}", item)
            if entry.kind == "shader":
                registry.resolved[f"{self.name}.{entry.name}"] = f"{self.name}.{entry.ref}"

    def _mode(self, entry: Entry, registry: Registry):
        return lambda **params: Styled(self._look(entry, registry), **params)

    def _factory(self, entry: Entry):
        return lambda **params: self.instance(entry, **params)

    def pinned(self, ref: str) -> Entry:
        """A published version by name@version. It can never change, so it is read once."""
        if ref not in self._pinned:
            name, _, version = ref.partition("@")
            self._pinned[ref] = self.get("prop", name, version)
        return self._pinned[ref]

    def instance(self, entry: Entry, shaders: Optional[dict[str, str]] = None, variant: Optional[str] = None,
                 nested: bool = False, budget: Optional[Budget] = None, depth: int = 0, **given: Any) -> FrozenProp:
        """A prop placed and set up: parameters, then `variant`, then `shaders` by slot."""
        payload = entry.payload
        place = {key: given.pop(key) for key in PLACEMENT if key in given}
        place.setdefault("name", entry.name)
        declared = {name: Param(**param) for name, param in payload.get("params", {}).items()}
        chosen: dict[str, Any] = dict(payload.get("variants", {}).get(variant, {}))
        if variant is not None and variant not in payload.get("variants", {}):
            raise self._unknown(entry, "variant", variant, payload.get("variants", {}))
        swapped = {slot: f"{self.name}.{ref}" for slot, ref in chosen.pop("shaders", {}).items()} | (shaders or {})
        for slot in swapped:
            if slot not in payload.get("slots", {}):
                raise self._unknown(entry, "shader slot", slot, payload.get("slots", {}))
        for name in given:
            if name not in declared:
                raise self._unknown(entry, "parameter", name, declared)
        values = {name: param.check(name, given.get(name, chosen.get(name, param.default)))
                  for name, param in declared.items()}
        common = dict(catalog=self.name, entry=entry.name, version=entry.version, slots=payload.get("slots", {}),
                      shaders=swapped, nested=nested, root=self.root, **place)
        if not payload.get("template"):
            if budget is not None:
                budget.spend(len(payload["parts"]))
            return FrozenProp(frozen=payload["parts"], **common)
        return TemplateProp(source=self, template=payload["parts"], values=values, budget=budget, depth=depth, **common)

    def _unknown(self, entry: Entry, what: str, name: str, known: Iterable[str]) -> CatalogError:
        near = get_close_matches(name, list(known), n=3)
        hint = f"; did you mean {', '.join(near)}?" if near else f"; it has {', '.join(sorted(known)) or 'none'}"
        return CatalogError(f"{entry.ref} has no {what} {name!r}{hint}")

    def pins(self, location: Location) -> Pins:
        """The exact versions a location uses from this catalog; keep them to get the same location later."""
        props = {node.entry: node.version for top in location.nodes for node in top.descend()
                 if isinstance(node, FrozenProp) and node.catalog == self.name and not node.nested}
        prefix, shaders = f"{self.name}.", {}
        for leaf in location.solids():
            pinned = location.registry.resolved.get(leaf.item.material)
            if pinned:  # a prop's own shaders carry their version already
                name, version = pinned.removeprefix(prefix).split("@")
                shaders[name] = version
        return {"props": props, "shaders": shaders}
