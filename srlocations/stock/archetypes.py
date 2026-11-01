from __future__ import annotations

import random
from typing import Any

from srlocations.location import Archetype, Location
from srlocations.nodes import Box
from srlocations.registry import Registry


class Street(Archetype):
    """A city street running along z: road, sidewalks, a row of buildings each side, trees, lamps, parked cars."""

    def build(self, registry: Registry, seed: int = 0, length: float = 80.0, night: bool = False, **_: Any) -> Location:
        rng = random.Random(seed)
        location = Location(f"street-{seed}", registry)
        road, walk = 8.0, 3.0
        location.add(Box(size=(200, 0.2, length + 120), at=(0, -0.2, length / 2), material="stock.concrete", name="ground"))
        location.add(Box(size=(road, 0.1, length + 120), at=(0, -0.05, length / 2), material="stock.asphalt", name="road"))
        for z in range(0, int(length), 6):
            location.add(Box(size=(0.15, 0.02, 2.5), at=(0, 0.01, z), material="stock.plaster.white", name="dash",
                             casts_shadow=False))
        facades = ["stock.brick.red", "stock.brick.tan", "stock.concrete", "stock.plaster.cream"]
        for side, yaw in ((-1, -90), (1, 90)):  # a building's windows are on its -z face
            z = 0.0
            while z < length:
                width = rng.uniform(9, 15)
                location.add("stock.building", width=width, depth=10, floors=rng.randint(3, 8),
                             facade=rng.choice(facades), lit=0.55 if night else 0.0, seed=rng.randrange(10**6),
                             at=(side * (road / 2 + walk + 5), 0, z + width / 2), yaw=yaw)
                z += width + rng.uniform(0, 0.6)
            for tree in range(0, int(length), 18):
                location.add("stock.tree", seed=rng.randrange(10**6), at=(side * (road / 2 + 1.0), 0, tree + 6))
            for lamp in range(0, int(length), 18):
                location.add("stock.street-lamp", at=(side * (road / 2 + 0.4), 0, lamp + 15), yaw=-90 * side)
            for car in range(rng.randint(2, 4)):
                location.add("stock.car", paint=rng.choice(["stock.paint.blue", "stock.paint.red", "stock.paint.yellow"]),
                             at=(side * (road / 2 - 1.1), 0, rng.uniform(4, length - 8)))
        location.rig("stock.night" if night else "stock.daylight")
        location.mark("crossing", (0, 0, 30)).mark("corner", (-5.2, 0, 12), facing=90)
        location.shot("street-level", (1.5, 1.6, -6), (0, 2.5, 40), lens=28)
        location.shot("overlook", (-3, 16, -14), (0, 0, 32), lens=30)
        return location
