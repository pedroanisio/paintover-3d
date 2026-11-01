"""A third-party plugin: one file, loaded by path. Nothing in srlocations knows about it."""
from dataclasses import dataclass
from typing import Iterable, Sequence

from srlocations import (Ambient, Archetype, Box, Check, Issue, Light, LightRig, Location, Material, Node, Plugin, Point,
                         Prefab, Registry)


@dataclass
class Bulkhead(Prefab):
    """A corridor ring: floor, walls and ceiling, with a glowing strip down each side."""
    width: float = 3.6
    height: float = 3.0
    glow: str = "scifi.neon.cyan"

    def build(self) -> Sequence[Node]:
        w, h = self.width, self.height
        ring = "scifi.hull"
        return [Box(size=(w + 0.4, 0.2, 1.9), at=(0, -0.1, 0), material="scifi.deck"),
                Box(size=(w + 0.4, 0.2, 1.9), at=(0, h + 0.1, 0), material=ring),
                Box(size=(0.2, h, 1.9), at=(-w / 2 - 0.1, h / 2, 0), material=ring),
                Box(size=(0.2, h, 1.9), at=(w / 2 + 0.1, h / 2, 0), material=ring),
                Box(size=(0.05, 0.08, 1.7), at=(-w / 2 + 0.03, h - 0.5, 0), material=self.glow, casts_shadow=False),
                Box(size=(0.05, 0.08, 1.7), at=(w / 2 - 0.03, h - 0.5, 0), material=self.glow, casts_shadow=False),
                Point(5.0, at=(0, h - 0.25, 0), color="#7fe9ff", reach=5.0, name="strip")]


class HullLights(LightRig):
    background = "#020308"

    def lights(self) -> Iterable[Light]:
        return [Ambient(0.3, color="#5a6a90", name="hull-fill")]


class Corridor(Archetype):
    def build(self, registry: Registry, seed: int = 0, sections: int = 14, **_) -> Location:
        location = Location("scifi-corridor", registry)
        for index in range(sections):
            location.add("scifi.bulkhead", at=(0, 0, index * 2.0),
                         glow="scifi.neon.magenta" if index % 4 == 3 else "scifi.neon.cyan")
        location.rig("scifi.hull-lights")
        location.mark("hero", (0, 0, 6))
        location.shot("down-the-hall", (0.5, 1.5, 0.2), (0, 1.3, 20), lens=24)
        return location


class CorridorIsLit(Check):
    """A plugin can bring its own rules."""

    def run(self, location: Location) -> Iterable[Issue]:
        if location.name == "scifi-corridor" and len(location.lights()) < 3:
            yield Issue("warning", "scifi-dark", "a corridor needs at least three lights")


class SciFi(Plugin):
    name = "scifi"
    version = "1.0.0"
    requires = ("stock",)

    def register(self, registry: Registry) -> None:
        registry.materials.add("scifi.hull", Material("#59626e", 0.45, 0.1))
        registry.materials.add("scifi.deck", Material("#2e333b", 0.35, 0.1))
        registry.materials.add("scifi.neon.cyan", Material("#001014", glow="#37e0ff", glow_strength=6.0))
        registry.materials.add("scifi.neon.magenta", Material("#140010", glow="#ff3fb4", glow_strength=6.0))
        registry.prefabs.add("scifi.bulkhead", Bulkhead)
        registry.rigs.add("scifi.hull-lights", HullLights)
        registry.archetypes.add("scifi.corridor", Corridor)
        registry.checks.append(CorridorIsLit())
