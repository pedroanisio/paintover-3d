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
"""
from __future__ import annotations

import colorsys
import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence, TypeVar, Union

from sr_core.scene import Scene

from srlocations.compiler import Compiler, Projection, RenderMode, SceneCompiler, safe_id
from srlocations.geometry import Vec3
from srlocations.location import Location
from srlocations.materials import Material
from srlocations.nodes import Ambient, Light, Placed, Point
from srlocations.paint import paint_over

SHADERS = Path(__file__).resolve().parent / "shaders"
UNLIT_WHITE, LIT_WHITE = "look-unlit-white", "look-lit-white"
OVERLAP = 0.002
KEPT = ("opacity", "alphaMode", "uvScaleX", "uvScaleY")  # what a flat surface takes from its material, beside the map
FITTING = 0.45  # a solid this close to a lamp's light is the lamp: its shade must not shadow its own bulb


def channels(color: str) -> tuple[float, float, float]:
    text = color.lstrip("#")
    return int(text[0:2], 16) / 255, int(text[2:4], 16) / 255, int(text[4:6], 16) / 255


def vivid(color: str, saturation: float, value: float) -> str:
    """A colour with its saturation and value scaled, the quick way to a cartoon palette."""
    h, s, v = colorsys.rgb_to_hsv(*channels(color))
    r, g, b = colorsys.hsv_to_rgb(h, min(1.0, s * saturation), min(1.0, v * value))
    return f"#{round(r * 255):02x}{round(g * 255):02x}{round(b * 255):02x}"


T = TypeVar("T")


def lookup(table: Mapping[str, T], name: str) -> Optional[T]:
    """The entry for a material name: the longest key it starts with. The key "" matches every material."""
    for prefix in sorted(table, key=len, reverse=True):
        if name.startswith(prefix):
            return table[prefix]
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


class Stage:
    """What the passes of one document share."""

    def __init__(self, scene: Scene, root: Any, compiler: "StyledCompiler", location: Location) -> None:
        self.scene, self.root, self.compiler, self.location = scene, root, compiler, location
        self.look = compiler.look
        self.solids = [leaf for leaf in location.solids() if leaf.item.drawn_in(self.look.name)]
        self._library: Any = None  # the schema refuses an empty <materials> or <effects>
        self._effects: Any = None
        self._materials: set[str] = set()

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

    def material_of(self, name: str) -> Material:
        """The material a solid has in this look."""
        chosen = lookup(self.look.materials, name)
        if chosen is None:
            chosen = name
        return self.location.registry.materials.get(chosen) if isinstance(chosen, str) else chosen

    def texture_of(self, name: str) -> Optional[Texture]:
        """The look's texture for a material, else the picture the material already has."""
        chosen = lookup(self.look.textures, name)
        if chosen is not None:
            return chosen
        map_path = self.material_of(name).maps.get("baseColorMap")
        return Texture(map_path, tile=None) if map_path else None

    def lay(self, group: Any, leaf: Placed, index: int, prefix: str, material_id: str, attributes: dict[str, Any],
            texture: Optional[Texture], shadow: bool) -> None:
        """One solid in one material. A tiled texture goes on surface by surface, each with its own UV scale."""
        if texture is None or texture.tile is None:
            mapped = {"baseColorMap": str(Path(texture.path).resolve())} if texture else {}
            chosen = self.material(material_id, **{**attributes, **mapped})
            self.compiler.draw(group, leaf, index, prefix, chosen, shadow=shadow, grow=OVERLAP)
            return
        for number, (part, across, up) in enumerate(leaf.item.spans()):
            scale = {"uvScaleX": max(round(across / texture.tile, 2), 0.01),
                     "uvScaleY": max(round(up / texture.tile, 2), 0.01)}
            chosen = self.material(f"{material_id}-{scale['uvScaleX']}x{scale['uvScaleY']}".replace(".", "_"),
                                   **{**attributes, "baseColorMap": str(Path(texture.path).resolve()), **scale})
            world = leaf.world if part is leaf.item else leaf.world.then(part.transform)
            self.compiler.draw(group, Placed(part, world, leaf.path), index, f"{prefix}{number}-", chosen, shadow=shadow,
                               grow=OVERLAP)

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


@dataclass
class Flat(Pass):
    """Solid colour with no lighting. `palette` replaces colours by material name or by the start of one."""
    palette: dict[str, str] = field(default_factory=dict)
    saturation: float = 1.0
    value: float = 1.0
    grain: float = 0.0

    def color(self, name: str, material: Material) -> str:
        chosen = lookup(self.palette, name)
        return chosen or vivid(material.glow if material.glow else material.color, self.saturation, self.value)

    def add(self, stage: Stage) -> None:
        effects = [stage.effect("flat-grain", "noise", amount=self.grain, saturation=0)] if self.grain else []
        group = stage.group("flat", effects)
        for index, leaf in enumerate(stage.solids):
            name = leaf.item.material
            material, texture = stage.material_of(name), stage.texture_of(name)
            kept = {key: value for key, value in material.attributes().items() if key in KEPT}
            color = texture.tint if texture and texture.tint else self.color(name, material)
            stage.lay(group, leaf, index, "flat-", f"flat-{safe_id(name)}", {"baseColor": color, "unlit": True, **kept},
                      texture, False)


@dataclass
class Lit(Pass):
    """Each solid in its full material under the location's lights: Shaded, as a pass, so a look can change materials."""

    def add(self, stage: Stage) -> None:
        group = stage.group("lit")
        for index, leaf in enumerate(stage.solids):
            name = leaf.item.material
            texture = lookup(stage.look.textures, name)
            attributes = stage.material_of(name).attributes()
            if texture and texture.tint:
                attributes["baseColor"] = texture.tint
            stage.lay(group, leaf, index, "lit-", f"lit-{safe_id(name)}", attributes, texture, leaf.item.casts_shadow)


@dataclass
class Cel(Pass):
    """Light and shade in two tones. `cut` is the brightness of the line between them, 0 to 1. The location's own lights
    do the work, turned from a soft fill into hard keys: ambient scaled by `fill`, and every other light casting shadows."""
    cut: float = 0.5
    shade: str = "#9a93b8"
    fill: float = 0.25

    def relight(self, light: Light) -> Light:
        if isinstance(light, Ambient):
            return replace(light, intensity=light.intensity * self.fill)
        return replace(light, shadows=True, softness=0.0)

    def add(self, stage: Stage) -> None:
        r, g, b = channels(self.shade)
        group = stage.group("cel", [stage.shader("cel-steps", "cel", cut=self.cut, shadeR=r, shadeG=g, shadeB=b)],
                            blend="multiply")
        lit = stage.material(LIT_WHITE, baseColor="#ffffff", roughness=1, metallic=0)
        unlit = stage.material(UNLIT_WHITE, baseColor="#ffffff", unlit=True)
        lamps = [leaf.world.position for leaf in stage.location.lights() if isinstance(leaf.item, Point)]
        for index, leaf in enumerate(stage.solids):
            material = stage.material_of(leaf.item.material)
            bright = material.glow or material.opacity < 1  # lights and glass take no shade
            shadow = leaf.item.casts_shadow and not any(touches(leaf, lamp) for lamp in lamps)
            stage.compiler.draw(group, leaf, index, "cel-", unlit if bright else lit, shadow=shadow, grow=OVERLAP)


@dataclass
class Ink(Pass):
    """Lines where surfaces meet. `width` is in pixels. `vary` swells them, `wobble` moves them, both in hand-drawn ways.
    `creases=False` leaves only outlines. `shadow` adds the soft edge a paper cut-out leaves on what is behind it."""
    color: str = "#000000"
    width: float = 2.0
    vary: float = 0.0
    wobble: float = 0.0
    creases: bool = True
    shadow: float = 0.0
    shadow_offset: tuple[float, float] = (5.0, -6.0)

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
            digest = hashlib.sha256(key.encode()).hexdigest()
            chosen = stage.material(f"ink-{digest[:12]}", baseColor=f"#{digest[:6]}", unlit=True)
            stage.compiler.draw(group, leaf, index, "ink-", chosen, shadow=False)


@dataclass
class Look:
    """A style: its passes, bottom first. `warp` shakes every pass together, as a hand-cut edge does. `name` is what paint
    and decals limit themselves to. `textures` and `materials` map material names, or their beginnings, to what those
    surfaces become in this look; the location itself does not change."""
    passes: Sequence[Pass]
    sky: Optional[str] = None
    warp: float = 0.0
    name: str = "custom"
    materials: dict[str, Union[str, Material]] = field(default_factory=dict)
    textures: dict[str, Texture] = field(default_factory=dict)


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
        stage = Stage(scene, composition, self, location)
        if self.look.warp:
            warp = stage.effect("look-warp", "turbulent-displace", amount=self.look.warp, size=60)
            stage.root = composition.add_group(id="look", effects=warp)
        for step in self.look.passes:
            step.add(stage)
        paint_over(scene, composition, location.paintings, shot, Projection(take, self.width, self.height), self.mode)
        return scene


@dataclass
class Styled(RenderMode):
    """A location drawn in a Look."""
    look: Look
    width: int = 1280
    height: int = 720
    supersample: int = 2

    def compiler(self) -> Compiler[Scene]:
        return StyledCompiler(self.look, self.width, self.height, supersample=self.supersample)
