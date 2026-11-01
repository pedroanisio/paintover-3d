"""Looks: a location drawn by the engine in passes of one document, so a style stays native and keeps working when a
camera moves. Each pass draws the whole set again in a group of its own. The engine has no custom shaders for 3D
surfaces, but a group's effects and blend mode apply to the 3D inside it, so a pass is geometry plus 2D shaders.

    Lit    every solid in its full material, lit as usual
    Flat   every solid unlit, in its colour
    Cel    every solid lit in white, stepped to two tones and multiplied over Flat: real cast shadows, drawn as shapes
    Ink    every surface unlit in a colour of its own, and a shader inks where colours meet: occlusion comes from the
           depth buffer, so lines stop behind what hides them

A Look can also change what a surface is made of, leaving the location alone: `textures` lays pictures over materials at a
real size, and `materials` replaces materials outright, with a Material or the name of one such as a catalog shader.

Those tables, and a Flat palette, are keyed by material name, and that name is shared: plaster can be a wall, a ceiling and
a plant pot. So a key can aim at the solid instead. "role:wall" takes what a node's `role` says, and "path:room/north/*"
takes the path a solid came through. A path beats a role, and a role beats a material name.

A tiled texture is measured in the world, not on each solid. The engine has no UV offset, so a box goes to the engine as a
small model whose UVs come from where its faces are (see sheets.py), and pieces of a wall built around a window line up.
"""
from __future__ import annotations

import colorsys
import hashlib
import json
import os
import tempfile
import warnings
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field, replace
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence, TypeVar, Union

from sr_core.scene import Scene

from srlocations.cast import colours
from srlocations.compiler import Compiler, RenderMode, Renderer, SceneCompiler, safe_id
from srlocations.geometry import Vec3
from srlocations.location import Location
from srlocations.materials import Material
from srlocations.nodes import Ambient, Light, Placed, Point, Skin
from srlocations.registry import CatalogError, Registry
from srlocations.sheets import sheet

SHADERS = Path(__file__).resolve().parent / "shaders"
UNLIT_WHITE, LIT_WHITE = "look-unlit-white", "look-lit-white"
OVERLAP = 0.002
KEPT = ("opacity", "alphaMode", "uvScaleX", "uvScaleY")  # what a flat surface takes from its material, beside the map
FITTING = 0.45  # a solid this close to a lamp's light is the lamp: its shade must not shadow its own bulb
ROLE, PATH = "role:", "path:"
AUTO = "auto"
PROBE = (160, 90)
PROBE_SKY = "#0000ff"  # no white surface comes out this colour, so what is sky can be left out
FALLBACK_CUT = 0.5
LIT_SHARE = 0.6


def channels(color: str) -> tuple[float, float, float]:
    text = color.lstrip("#")
    return int(text[0:2], 16) / 255, int(text[2:4], 16) / 255, int(text[4:6], 16) / 255


def vivid(color: str, saturation: float, value: float) -> str:
    """A colour with its saturation and value scaled, the quick way to a cartoon palette."""
    h, s, v = colorsys.rgb_to_hsv(*channels(color))
    r, g, b = colorsys.hsv_to_rgb(h, min(1.0, s * saturation), min(1.0, v * value))
    return f"#{round(r * 255):02x}{round(g * 255):02x}{round(b * 255):02x}"


T = TypeVar("T")


def aims(key: str, leaf: Optional[Placed]) -> bool:
    """Whether a table key picks out this solid, by one of its roles or by its path, where * and ? are wildcards."""
    if leaf is None:
        return False
    if key.startswith(ROLE):
        return key[len(ROLE):] in leaf.roles
    return key.startswith(PATH) and fnmatchcase(leaf.path, key[len(PATH):])


def lookup(table: Mapping[str, T], name: str, leaf: Optional[Placed] = None) -> Optional[T]:
    """The entry for a solid: a path key it matches, then a role key, and last the longest key its material name starts
    with, the longest winning at each step. The key "" matches every material."""
    keys = sorted(table, key=len, reverse=True)
    for kind in (PATH, ROLE):
        for key in keys:
            if key.startswith(kind) and aims(key, leaf):
                return table[key]
    for key in keys:
        if not key.startswith((PATH, ROLE)) and name.startswith(key):
            return table[key]
    return None


@dataclass(frozen=True)
class Texture:
    """A picture laid on surfaces at a real size: one repeat covers `tile` metres, whatever the size of the solid. With
    tile=None it fills each face once, as the engine does by default. It multiplies the colour under it, so a grey grain
    suits every object; `tint` replaces that colour."""
    path: Union[str, Path]
    tile: Optional[float] = 1.0
    tint: Optional[str] = None

    def __post_init__(self) -> None:
        if self.tile is not None and self.tile <= 0:
            raise ValueError(f"{self.path}: tile is {self.tile}, and it must be above 0")
        if not Path(self.path).is_file():
            raise FileNotFoundError(f"no texture {self.path}")


Paint = Callable[[Skin, Placed], Optional[tuple[str, dict[str, Any], Optional[Texture]]]]


class Stage:
    """What the passes of one document share."""

    def __init__(self, scene: Scene, root: Any, compiler: "StyledCompiler", location: Location, shot: str = "") -> None:
        self.scene, self.root, self.compiler, self.location, self.shot = scene, root, compiler, location, shot
        self.look = compiler.look
        self.solids = [leaf for leaf in location.solids() if leaf.item.drawn_in(self.look.name)]
        self._library: Any = None  # the schema refuses an empty <materials> or <effects>
        self._effects: Any = None
        self._materials: set[str] = set()
        self.tables = [self.look.materials, self.look.textures, *(table for step in self.look.passes for table in step.tables())]

    def aimed(self, leaf: Placed) -> str:
        """Sets a material id apart when a look aims at this solid, since the name alone no longer says what it becomes."""
        keys = sorted({key for table in self.tables for key in table if aims(key, leaf)})
        return f"-{hashlib.sha256(' '.join(keys).encode()).hexdigest()[:8]}" if keys else ""

    def unused(self) -> list[str]:
        """The keys aimed at solids that are not in this location."""
        keys = {key for table in self.tables for key in table if key.startswith((PATH, ROLE))}
        return sorted(key for key in keys if not any(aims(key, leaf) for leaf in self.solids))

    def material(self, material_id: str, **attributes: Any) -> str:
        if material_id not in self._materials:
            self._materials.add(material_id)
            self._library = self._library or self.scene.add_materials()
            self._library.add_material(id=material_id, **attributes)
        return material_id

    @property
    def effects(self) -> Any:
        self._effects = self._effects or self.scene.add_effects()
        return self._effects

    def shader(self, effect_id: str, name: str, **params: float) -> str:
        effect = self.effects.add_effect(id=effect_id, type="shader", src=str(SHADERS / f"{name}.fs"))
        for key, value in params.items():
            effect.add_param(name=key, value=str(value))
        return effect_id

    def effect(self, effect_id: str, kind: str, **attributes: Any) -> str:
        self.effects.add_effect(id=effect_id, type=kind, **attributes)
        return effect_id

    def material_of(self, name: str, own: Optional[Material] = None, leaf: Optional[Placed] = None) -> Material:
        """The material a solid has in this look. `own` is one from a model file, which the registry does not hold."""
        chosen = lookup(self.look.materials, name, leaf)
        if chosen is None:
            chosen = own or name
        return self.location.registry.materials.get(chosen) if isinstance(chosen, str) else chosen

    def texture_of(self, name: str, own: Optional[Material] = None, leaf: Optional[Placed] = None) -> Optional[Texture]:
        """The look's texture for a material, else the picture the material already has."""
        chosen = lookup(self.look.textures, name, leaf)
        if chosen is not None:
            return chosen
        map_path = self.material_of(name, own, leaf).maps.get("baseColorMap")
        return Texture(map_path, tile=None) if map_path else None

    def lay(self, group: Any, leaf: Placed, index: int, prefix: str, material_id: str, attributes: dict[str, Any],
            texture: Optional[Texture], shadow: bool) -> None:
        """One solid in one material. A tiled texture goes on surface by surface, each with its own UV scale."""
        if texture is None or texture.tile is None:
            mapped = {"baseColorMap": str(Path(texture.path).resolve())} if texture else {}
            chosen = self.material(material_id, **{**attributes, **mapped})
            self.compiler.draw(group, leaf, index, prefix, chosen, shadow=shadow, grow=OVERLAP)
            return
        if leaf.item.faces():
            chosen = self.material(material_id, **{**attributes, "baseColorMap": str(Path(texture.path).resolve()),
                                                   "uvScaleX": 1, "uvScaleY": 1})
            model = sheet(leaf.item, leaf.world, texture.tile, OVERLAP)
            model.declare(self.scene)
            self.compiler.draw(group, Placed(model, leaf.world, leaf.path), index, prefix, chosen, shadow=shadow)
            return
        for number, (part, across, up) in enumerate(leaf.item.spans()):
            scale = {"uvScaleX": max(round(across / texture.tile, 2), 0.01),
                     "uvScaleY": max(round(up / texture.tile, 2), 0.01)}
            chosen = self.material(f"{material_id}-{scale['uvScaleX']}x{scale['uvScaleY']}".replace(".", "_"),
                                   **{**attributes, "baseColorMap": str(Path(texture.path).resolve()), **scale})
            world = leaf.world if part is leaf.item else leaf.world.then(part.transform)
            self.compiler.draw(group, Placed(part, world, leaf.path), index, f"{prefix}{number}-", chosen, shadow=shadow,
                               grow=OVERLAP)

    def coat(self, group: Any, leaf: Placed, index: int, prefix: str, paint: Paint, shadow: bool) -> None:
        """A solid in what `paint` makes of each of its skins. Paint that returns None leaves that skin as the file has it.
        A model's parts are one object to the engine, so they share one draw and their textures run on the model's UVs."""
        painted = [(skin, paint(skin, leaf)) for skin in leaf.item.skins()]
        skin, first = painted[0]
        if first and not skin.slot:
            self.lay(group, leaf, index, prefix, *first, shadow)
            return
        swaps = {skin.slot: self.material(chosen[0], **{**chosen[1], **self._mapped(chosen[2], leaf)})
                 for skin, chosen in painted if chosen and skin.slot}
        self.compiler.draw(group, leaf, index, prefix, swaps, shadow=shadow)

    def _mapped(self, texture: Optional[Texture], leaf: Placed) -> dict[str, Any]:
        if texture is None:
            return {}
        _, across, up = leaf.item.spans()[0]
        tiling = {} if texture.tile is None else {"uvScaleX": max(round(across / texture.tile, 2), 0.01),
                                                  "uvScaleY": max(round(up / texture.tile, 2), 0.01)}
        return {"baseColorMap": str(Path(texture.path).resolve()), **tiling}

    def group(self, group_id: str, effects: Sequence[str] = (), **attributes: Any) -> Any:
        if effects:
            attributes["effects"] = " ".join(effects)
        return self.root.add_group(id=group_id, **attributes)


def touches(leaf: Placed, point: Vec3) -> bool:
    low, high = leaf.item.bounds(leaf.world)
    gap = sum(max(a - p, 0.0, p - b) ** 2 for a, p, b in zip(low, point, high))
    return gap < FITTING ** 2


class Pass(ABC):
    """One drawing of the set. A plugin adds a look by subclassing this, or by building a Look from these."""

    @abstractmethod
    def add(self, stage: Stage) -> None:
        ...

    def relight(self, light: Light) -> Light:
        """Lights are shared by a whole document, so a pass that needs different light changes it here for all."""
        return light

    def tables(self) -> Sequence[Mapping[str, Any]]:
        """Its own tables keyed as a look's are, so a key in them can aim at a solid."""
        return ()

    def spec(self) -> dict[str, Any]:
        """This pass as data, the keyword arguments of its class. A pass that is not a dataclass overrides this."""
        return asdict(self)


@dataclass
class Flat(Pass):
    """Solid colour with no lighting. `palette` replaces colours by material name or the start of one, by role or by path."""
    palette: dict[str, str] = field(default_factory=dict)
    saturation: float = 1.0
    value: float = 1.0
    grain: float = 0.0

    def tables(self) -> Sequence[Mapping[str, Any]]:
        return (self.palette,)

    def color(self, name: str, material: Material, leaf: Optional[Placed] = None) -> str:
        chosen = lookup(self.palette, name, leaf)
        return chosen or vivid(material.glow if material.glow else material.color, self.saturation, self.value)

    def add(self, stage: Stage) -> None:
        effects = [stage.effect("flat-grain", "noise", amount=self.grain, saturation=0)] if self.grain else []
        group = stage.group("flat", effects)

        def paint(skin: Skin, leaf: Placed) -> tuple[str, dict[str, Any], Optional[Texture]]:
            material, texture = stage.material_of(skin.name, skin.own, leaf), stage.texture_of(skin.name, skin.own, leaf)
            kept = {key: value for key, value in material.attributes().items() if key in KEPT}
            color = texture.tint if texture and texture.tint else self.color(skin.name, material, leaf)
            return f"flat-{safe_id(skin.name)}{stage.aimed(leaf)}", {"baseColor": color, "unlit": True, **kept}, texture

        for index, leaf in enumerate(stage.solids):
            stage.coat(group, leaf, index, "flat-", paint, False)


@dataclass
class Lit(Pass):
    """Each solid in its full material under the location's lights: Shaded, as a pass, so a look can change materials."""

    def add(self, stage: Stage) -> None:
        group = stage.group("lit")

        def paint(skin: Skin, leaf: Placed) -> Optional[tuple[str, dict[str, Any], Optional[Texture]]]:
            texture, swapped = lookup(stage.look.textures, skin.name, leaf), lookup(stage.look.materials, skin.name, leaf)
            if skin.own and texture is None and swapped is None:
                return None
            attributes = stage.material_of(skin.name, skin.own, leaf).attributes()
            if texture and texture.tint:
                attributes["baseColor"] = texture.tint
            return f"lit-{safe_id(skin.name)}{stage.aimed(leaf)}", attributes, texture

        for index, leaf in enumerate(stage.solids):
            stage.coat(group, leaf, index, "lit-", paint, leaf.item.casts_shadow)


@dataclass
class Cel(Pass):
    """Light and shade in two tones. `cut` is the brightness of the line between them, 0 to 1, or "auto" to measure it from
    the shot (see measured_cut). The location's own lights do the work, turned from a soft fill into hard keys: ambient
    scaled by `fill`, and every other light casting shadows."""
    cut: Union[float, str] = 0.5
    shade: str = "#9a93b8"
    fill: float = 0.25

    def __post_init__(self) -> None:
        if isinstance(self.cut, str) and self.cut != AUTO:
            raise ValueError(f"Cel cut {self.cut!r}: a cut is a number or {AUTO!r}")

    def relight(self, light: Light) -> Light:
        if isinstance(light, Ambient):
            return replace(light, intensity=light.intensity * self.fill)
        return replace(light, shadows=True, softness=0.0)

    def add(self, stage: Stage) -> None:
        r, g, b = channels(self.shade)
        cut = measured_cut(self, stage) if self.cut == AUTO else self.cut
        self.tones(stage, stage.group("cel", [stage.shader("cel-steps", "cel", cut=cut, shadeR=r, shadeG=g, shadeB=b)],
                                      blend="multiply"))

    def tones(self, stage: Stage, group: Any) -> None:
        """The set in white under this pass's light, before it is stepped."""
        lit = stage.material(LIT_WHITE, baseColor="#ffffff", roughness=1, metallic=0)
        unlit = stage.material(UNLIT_WHITE, baseColor="#ffffff", unlit=True)
        lamps = [leaf.world.position for leaf in stage.location.lights() if isinstance(leaf.item, Point)]
        for index, leaf in enumerate(stage.solids):
            material = stage.material_of(leaf.item.material, leaf=leaf)
            bright = material.glow or material.opacity < 1 or material.extra.get("unlit")  # lights, glass and views take no shade
            shadow = leaf.item.casts_shadow and not any(touches(leaf, lamp) for lamp in lamps)
            stage.compiler.draw(group, leaf, index, "cel-", unlit if bright else lit, shadow=shadow, grow=OVERLAP)


@dataclass
class Tones(Cel):
    """What Cel sees before it steps it, for measuring a shot."""

    def add(self, stage: Stage) -> None:
        self.tones(stage, stage.group("cel"))


def measured_cut(cel: Cel, stage: Stage) -> float:
    """The line between light and shade for this shot. The engine draws it small, and the brightest tenth of the surfaces
    in view says what lit means here, so a dim room and a bright street both get shade that means something. It comes from
    a render, so a look that must not change between engines keeps a number."""
    look = Look([Tones(cut=0.5, shade=cel.shade, fill=cel.fill)], sky=PROBE_SKY, name=stage.look.name)
    scene = MeasuringCompiler(look, *PROBE, supersample=1).compile(stage.location, stage.shot)
    with tempfile.TemporaryDirectory() as folder:
        try:
            picture = Renderer().still(scene, Path(folder) / "probe.png")
        except (OSError, RuntimeError) as error:
            warnings.warn(f"Cel cannot measure {stage.shot!r}, so it uses {FALLBACK_CUT}: {error}", stacklevel=2)
            return FALLBACK_CUT
        return cut_for(brightness(picture))


def brightness(picture: Union[str, Path]) -> list[float]:
    """How bright each pixel of the set is, as cel.fs weighs it. Sky is left out."""
    return [(0.3 * r + 0.59 * g + 0.11 * b) / 255 for r, g, b in colours(picture) if r > 4 or g > 4 or b < 250]


def cut_for(tones: Sequence[float]) -> float:
    """A cut from the brightness of each pixel of the set: a share of what its lit surfaces reach. Everything in one tone
    comes out above the cut, so a set with no light and shade to tell apart is not all shade."""
    if not tones:
        return FALLBACK_CUT
    ordered = sorted(tones)
    return round(ordered[int(len(ordered) * 0.9)] * LIT_SHARE, 2)


@dataclass
class Ink(Pass):
    """Lines where surfaces meet. `width` is in pixels. `vary` swells them, `wobble` moves them, both in hand-drawn ways.
    `creases=False` leaves only outlines. `shadow` adds the soft edge a paper cut-out leaves on what is behind it. `rings`
    draws lines this many metres apart across each curved solid, around a cylinder, cone or sphere and across a Surface's
    v, the way an engraving shows a form turning. A model cannot be divided, so it keeps its outline. They need `creases`."""
    color: str = "#000000"
    width: float = 2.0
    vary: float = 0.0
    wobble: float = 0.0
    creases: bool = True
    shadow: float = 0.0
    shadow_offset: tuple[float, float] = (5.0, -6.0)
    rings: float = 0.0

    def spec(self) -> dict[str, Any]:
        """Without rings this is the data it always was, so a look published before they existed keeps its digest."""
        return {key: value for key, value in asdict(self).items() if key != "rings" or value}

    def surfaces(self, stage: Stage) -> list[tuple[Placed, str]]:
        """Each surface and its key. Pieces of one object in one plane share a key, so a wall built in sections is one
        surface with no lines across it, while two objects never share one."""
        drawn = []
        for leaf in stage.solids:
            owner = leaf.path.rpartition("/")[0] or leaf.path
            for facet, normal in leaf.item.facets() if self.creases else [(leaf.item, Vec3(0, 0, 0))]:
                world = leaf.world if facet is leaf.item else leaf.world.then(facet.transform)
                if normal == Vec3(0, 0, 0):
                    key = leaf.path
                    bands = facet.bands(self.rings) if self.rings and self.creases else []
                    if bands:
                        drawn += [(Placed(band, world, leaf.path), f"{key}|{number}") for number, band in enumerate(bands)]
                        continue
                else:
                    turned = leaf.world.apply(normal) - leaf.world.position
                    reach = sum(abs(a * b) for a, b in zip(leaf.item.half_extents(), normal))
                    plane = sum(a * b for a, b in zip(turned, leaf.world.position)) + reach  # of the real surface
                    key = f"{owner}|{leaf.item.material}|{[round(v, 3) + 0.0 for v in turned]}|{plane:.3f}"
                drawn.append((Placed(facet, world, leaf.path), key))
        return drawn

    def add(self, stage: Stage) -> None:
        r, g, b = channels(self.color)
        width, height = stage.compiler.width, stage.compiler.height
        lines = stage.shader("ink-lines", "ink", pixelsX=width, pixelsY=height, radius=self.width / 2, vary=self.vary,
                             wobble=self.wobble, inkR=r, inkG=g, inkB=b, shadow=self.shadow,
                             shadowX=self.shadow_offset[0], shadowY=self.shadow_offset[1])
        clean = stage.shader("ink-clean", "clean", pixelsX=width, pixelsY=height)
        group = stage.group("ink", [clean, lines])
        for index, (leaf, key) in enumerate(self.surfaces(stage)):
            def keyed(key: str) -> str:
                digest = hashlib.sha256(key.encode()).hexdigest()
                return stage.material(f"ink-{digest[:12]}", baseColor=f"#{digest[:6]}", unlit=True)

            slots = [skin.slot for skin in leaf.item.skins() if skin.slot]  # a model's parts differ, so a line divides them
            chosen = {slot: keyed(f"{key}|{slot}") for slot in slots} if slots else keyed(key)
            stage.compiler.draw(group, leaf, index, "ink-", chosen, shadow=False)


@dataclass
class Look:
    """A style: its passes, bottom first. `warp` shakes every pass together, as a hand-cut edge does. `name` is what paint
    and decals limit themselves to. `textures` and `materials` map material names or their beginnings, "role:" keys and
    "path:" keys to what those surfaces become in this look; the location itself does not change."""
    passes: Sequence[Pass]
    sky: Optional[str] = None
    warp: float = 0.0
    name: str = "custom"
    materials: dict[str, Union[str, Material]] = field(default_factory=dict)
    textures: dict[str, Texture] = field(default_factory=dict)

    def spec(self, registry: Registry) -> dict[str, Any]:
        """This look as JSON-ready data. Each pass is named by its entry in registry.passes."""
        kinds = {registry.passes.get(name): name for name in registry.passes.names()}
        for step in self.passes:
            if type(step) not in kinds:
                raise CatalogError(f"{type(step).__name__} is not in registry.passes, so a look using it cannot be data")
        return {"passes": [{"kind": kinds[type(step)], **step.spec()} for step in self.passes], "sky": self.sky,
                "warp": self.warp, "materials": {key: value if isinstance(value, str) else asdict(value)
                                                 for key, value in self.materials.items()},
                "textures": {key: {"path": str(value.path), "tile": value.tile, "tint": value.tint}
                             for key, value in self.textures.items()}}

    @classmethod
    def from_spec(cls, spec: Mapping[str, Any], registry: Registry, base: Path = Path("."), name: str = "") -> "Look":
        """A look from data. Paths are relative to `base`. A material is a name or the fields of a Material."""
        title = name or spec.get("name", "custom")
        unknown = set(spec) - {"name", "passes", "sky", "warp", "materials", "textures"}
        if unknown:
            raise ValueError(f"look {title!r} has no {', '.join(sorted(unknown))}")

        def step(values: Mapping[str, Any]) -> Pass:
            params = dict(values)
            kind = registry.passes.get(params.pop("kind", ""))
            try:
                return kind(**params)
            except TypeError as error:
                raise ValueError(f"look {title!r}: {error}") from error

        def material(value: Union[str, Mapping[str, Any]]) -> Union[str, Material]:
            if isinstance(value, str):
                return value
            maps = {key: str(base / path) for key, path in value.get("maps", {}).items()}
            return Material(**{**value, "maps": maps})

        return cls([step(values) for values in spec["passes"]], spec.get("sky"), spec.get("warp", 0.0), title,
                   {key: material(value) for key, value in spec.get("materials", {}).items()},
                   {key: Texture(**{**value, "path": base / value["path"]}) for key, value in spec.get("textures", {}).items()})

    @classmethod
    def load(cls, path: Union[str, Path], registry: Registry) -> "Look":
        """A look from a .look.json file, its paths relative to the file and named by the file if it does not say."""
        path = Path(path)
        return cls.from_spec(json.loads(path.read_text()), registry, path.resolve().parent,
                             path.name.removesuffix(".json").removesuffix(".look"))

    def save(self, path: Union[str, Path], registry: Registry) -> Path:
        """Writes a .look.json, its textures named relative to the file so the folder can move."""
        path = Path(path).resolve()
        spec = self.spec(registry)
        for texture in spec["textures"].values():
            texture["path"] = os.path.relpath(Path(texture["path"]).resolve(), path.parent)
        for material in (value for value in spec["materials"].values() if isinstance(value, dict)):
            material["maps"] = {key: os.path.relpath(Path(file).resolve(), path.parent) for key, file in material["maps"].items()}
        path.write_text(json.dumps({"name": self.name, **spec}, indent=2) + "\n")
        return path

    def register(self, registry: Registry, override: bool = False) -> "Look":
        """Makes this look a render mode, under its name."""
        registry.modes.add(self.name, lambda **params: Styled(self, **params), override)
        return self


class StyledCompiler(SceneCompiler):
    """Compiles a location through a Look. The lights stay in the document for any pass that uses them."""

    def __init__(self, look: Look, width: int = 1280, height: int = 720, fps: int = 30, duration: float = 1,
                 supersample: int = 2) -> None:
        super().__init__(width, height, fps, duration, supersample)
        self.look, self.mode = look, look.name

    def _relit(self, leaf: Placed) -> Placed:
        light = leaf.item
        for step in self.look.passes:
            light = step.relight(light)
        return Placed(light, leaf.world, leaf.path)

    def compile(self, location: Location, shot: str) -> Scene:
        take = location.shots[shot]
        scene = Scene(version="auto")
        scene.add_project(width=self.width, height=self.height, fps=str(self.fps), duration=self.duration,
                          background=self.look.sky or location.background, supersample=self.supersample)
        self._lights(scene, [self._relit(leaf) for leaf in location.lights()])
        composition = scene.add_composition()
        self._camera(composition, take)
        stage = Stage(scene, composition, self, location, shot)
        self._declare(scene, stage.solids)
        for key in stage.unused():  # one look serves many locations, so a key they lack is not an error
            warnings.warn(f"look {self.look.name!r}: {key!r} finds nothing in {location.name!r}", stacklevel=2)
        warp = ""
        if self.look.warp:
            warp = stage.effect("look-warp", "turbulent-displace", amount=self.look.warp, size=60)
            stage.root = composition.add_group(id="look", effects=warp)
        for step in self.look.passes:
            step.add(stage)
        self._paint(scene, composition, location, take, stage.solids, warp)
        return scene


class MeasuringCompiler(StyledCompiler):
    """A location with no paint on it."""

    def _paint(self, *args: Any, **kwargs: Any) -> None:
        pass



@dataclass
class Styled(RenderMode):
    """A location drawn in a Look."""
    look: Look
    width: int = 1280
    height: int = 720
    supersample: int = 2

    def compiler(self) -> Compiler[Scene]:
        return StyledCompiler(self.look, self.width, self.height, supersample=self.supersample)
