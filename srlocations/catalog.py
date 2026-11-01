"""A shared catalog of props and shaders: a directory any number of projects can read and publish to.

    <root>/catalog.json                  its name
    <root>/shaders/<name>/<version>.json
    <root>/props/<name>/<version>.json
    <root>/files/<sha256>.<ext>          textures, stored by content

Share it as a git repository or a network folder. A published version never changes: publishing the same content again
does nothing, and different content under a taken version is refused. Publishing a prop freezes it to plain data, so a
prop built by a plugin's code can be used by a project without that plugin, and it pins the exact shaders it was made
with. Point a registry at a catalog with registry.use(SharedCatalog.open(path)), or with the SRLOCATIONS_CATALOGS
variable, and its items appear as <catalog>.<name>, the newest version, and <catalog>.<name>@<version>.

Props are reused in two ways. A frozen prop (publish_prop) is fixed geometry that can name shader slots. A template
(publish_template, see templates.py) has parameters, variants and slots too, and can nest other props.
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
from srlocations.materials import Material
from srlocations.nodes import Box, Cone, Cylinder, Light, Node, Placed, Point, Prefab, Round, Solid, Sphere, Spot
from srlocations.registry import CatalogError, Registry
from srlocations.templates import PLACEMENT, Number, Param, PropTemplate, TemplateError, evaluate

SCHEMA = 1
KINDS = {"shader": "shaders", "prop": "props"}
NAME = re.compile(r"[a-z0-9][a-z0-9._-]*")
VERSION = re.compile(r"(\d+)\.(\d+)\.(\d+)")
STORED_FILE = re.compile(r"[0-9a-f]{64}(\.[a-z0-9]+)?")
SOLIDS = {"box": Box, "cylinder": Cylinder, "cone": Cone, "sphere": Sphere}
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
    item = leaf.item
    if isinstance(item, Solid):
        if item.primitive not in SOLIDS:
            raise CatalogError(f"{leaf.path}: a {item.primitive!r} solid cannot be frozen")
        part = {**common, "solid": item.primitive, "material": material, "casts_shadow": item.casts_shadow,
                "dimensions": {k: round(v, 6) for k, v in item.dimensions().items()}}
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
    place = {"at": part["at"], "basis": tuple(tuple(row) for row in part["basis"])}
    if "light" in part:
        options = {"cone": part["cone"]} if "cone" in part else {}
        return LIGHTS[part["light"]](part["intensity"], color=part["color"], shadows=part["shadows"],
                                     softness=part["softness"], reach=part["reach"], **options, **place)
    kind, size = SOLIDS[part["solid"]], part["dimensions"]
    look = {"material": material, "casts_shadow": part["casts_shadow"], **place}
    if kind is Box:
        return Box((size["width"], size["height"], size["depth"]), **look)
    if kind is Sphere:
        return Sphere(size["radius"], segments=part["segments"], **look)
    return kind(size["radius"], size["height"], segments=part["segments"], **look)


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

    def shader(self, slot: str) -> str:
        return self.shaders.get(slot) or f"{self.catalog}.{self.slots[slot]}"

    def build(self) -> Sequence[Node]:
        return [_thaw(part, self.shader(part["slot"]) if part.get("slot") else f"{self.catalog}.{part['material']}")
                if "solid" in part else _thaw(part, "") for part in self.frozen]


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
        if "prop" in part:
            return self._nest(part, scope, budget, place)
        if "light" in part:
            return self._light(part, scope, place)
        return self._solid(part, scope, place)

    def _nest(self, part: dict, scope: dict[str, Number], budget: Budget, place: dict[str, Any]) -> Node:
        if self.depth >= MAX_DEPTH:
            raise TemplateError(f"{self.entry}: props are nested deeper than {MAX_DEPTH}")
        params = {name: evaluate(value, scope) for name, value in part.get("params", {}).items()}
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
        look = {"material": self.shader(part["shader"]), "casts_shadow": part.get("casts_shadow", True), **place}
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
    def open(cls, root: Union[str, Path]) -> "SharedCatalog":
        manifest = Path(root) / "catalog.json"
        if not manifest.exists():
            raise CatalogError(f"no shared catalog at {root}")
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
        for registry in self._installed:  # usable at once, but a name in use keeps the version it stands for
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
                   for material in sorted({leaf.item.material for leaf in solids})}
        parts = [_freeze(leaf, shaders[leaf.item.material] if isinstance(leaf.item, Solid) else None) for leaf in leaves]
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
        """Publishes a parametric prop. It is built at its defaults, its limits and every variant first, so a template
        that cannot make a prop is refused here and not on someone else's machine."""
        template.check()
        slots = {slot: self._adopt(material, registry, version) for slot, material in template.slots.items()}
        payload = {"template": True, "params": {name: asdict(p) for name, p in template.params.items()},
                   "slots": slots, "variants": self._resolved_variants(template, registry, version),
                   "parts": self._resolved_parts(template.parts, registry, version)}
        entry = Entry("prop", template.name, version, _digest(payload), payload)
        lows = {n: p.min for n, p in template.params.items() if p.min is not None}
        highs = {n: p.max for n, p in template.params.items() if p.max is not None}
        trials: list[dict] = [{}, lows, highs, *({"variant": name} for name in template.variants)]
        solids: list[Placed] = []
        for trial in trials:
            built = [leaf for leaf in self.instance(entry, **trial).walk() if isinstance(leaf.item, Solid)]
            solids = solids or built
        if not solids:
            raise CatalogError(f"prop {template.name!r} has no solids at its defaults")
        return self._publish("prop", template.name, version, payload, template.tags, template.description,
                             _extent(solids))

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
        data = json.loads(path.read_text())
        if _digest(data["payload"]) != data["digest"]:
            raise CatalogError(f"{path} does not match its digest: the file was changed after publishing")
        return Entry(data["kind"], data["name"], data["version"], data["digest"], data["payload"], tuple(data["tags"]),
                     data["description"], tuple(data["size"]) if data["size"] else None)

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

    def verify(self) -> list[Issue]:
        """Everything a reader relies on: digests, stored textures, shader values and the shaders props pin."""
        issues: list[Issue] = []
        for kind in KINDS:
            for path in sorted((self.root / KINDS[kind]).glob("*/*.json")):
                try:
                    entry = self._read(path)
                except CatalogError as error:
                    issues.append(Issue("error", "catalog-digest", str(error)))
                    continue
                issues.extend(self._verify_shader(entry) if kind == "shader" else self._verify_prop(entry))
        return issues

    def _verify_shader(self, entry: Entry) -> Iterable[Issue]:
        for stored in entry.payload["maps"].values():
            path = self.root / "files" / stored
            if not STORED_FILE.fullmatch(stored) or not path.exists():
                yield Issue("error", "catalog-file", f"{entry.ref}: texture {stored} is missing")
            elif hashlib.sha256(path.read_bytes()).hexdigest() != stored.split(".")[0]:
                yield Issue("error", "catalog-file", f"{entry.ref}: texture {stored} was changed")
        try:
            self._material(entry).validate()
        except Exception as error:
            yield Issue("error", "catalog-shader", f"{entry.ref}: {error}")

    def _verify_prop(self, entry: Entry) -> Iterable[Issue]:
        shaders, props = set(entry.payload.get("slots", {}).values()), set()
        def collect(parts: Sequence[dict]) -> None:
            for part in parts:
                collect(part.get("parts", ()))
                if "material" in part:
                    shaders.add(part["material"])
                if "prop" in part:
                    props.add(part["prop"])
                    shaders.update(v for v in part.get("shaders", {}).values() if not v.startswith("$"))
        collect(entry.payload["parts"])
        missing = [r for r in sorted(shaders) if not self._exists("shader", r)]
        missing += [r for r in sorted(props) if not self._exists("prop", r)]
        for ref in missing:
            yield Issue("error", "catalog-reference", f"{entry.ref} uses {ref}, which is not in the catalog")
        if entry.payload.get("template") and not missing:
            try:
                list(self.instance(entry).walk())
            except CatalogError as error:
                yield Issue("error", "catalog-template", f"{entry.ref}: {error}")

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
        for kind, wanted in (("shader", pins.get("shaders", {})), ("prop", pins.get("props", {}))):
            chosen = self._chosen(kind, wanted)
            for entry in self.entries(kind):
                self._register(registry, entry, chosen[entry.name].version == entry.version)
        registry.shared[self.name] = self
        self._installed.append(registry)

    def _catalog_of(self, registry: Registry, kind: str):
        return registry.materials if kind == "shader" else registry.prefabs

    def _register(self, registry: Registry, entry: Entry, plain: bool) -> None:
        """An entry under name@version and, when `plain`, under its bare name too."""
        item = self._material(entry) if entry.kind == "shader" else self._factory(entry)
        target = self._catalog_of(registry, entry.kind)
        target.add(f"{self.name}.{entry.ref}", item)
        if plain:
            target.add(f"{self.name}.{entry.name}", item)
            if entry.kind == "shader":
                registry.resolved[f"{self.name}.{entry.name}"] = f"{self.name}.{entry.ref}"

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
                      shaders=swapped, nested=nested, **place)
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
