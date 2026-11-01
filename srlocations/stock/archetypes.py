from __future__ import annotations

import random
from typing import Any

from srlocations.location import Archetype, Location
from srlocations.nodes import Box
from srlocations.registry import Registry

CAR_LENGTH = 5.0  # with room to park


class Street(Archetype):
    """A city street running along z: road, sidewalks, a row of buildings each side, trees, lamps, parked cars."""

    def build(self, registry: Registry, seed: int = 0, length: float = 80.0, night: bool = False, interiors: bool = False,
              **_: Any) -> Location:
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
                             interiors=interiors,
                             at=(side * (road / 2 + walk + 5), 0, z + width / 2), yaw=yaw)
                z += width + 0.3 + rng.uniform(0, 0.6)  # a roof's edge stands out 0.15 either side
            for tree in range(0, int(length), 18):
                location.add("stock.tree", seed=rng.randrange(10**6), at=(side * (road / 2 + 1.0), 0, tree + 6))
            for lamp in range(0, int(length), 18):
                location.add("stock.street-lamp", at=(side * (road / 2 + 0.4), 0, lamp + 15), yaw=-90 * side)
            parked: list[float] = []
            for car in range(rng.randint(2, 4)):
                paint, wanted = rng.choice(["stock.paint.blue", "stock.paint.red", "stock.paint.yellow"]), rng.uniform(4, length - 8)
                spots = [wanted + CAR_LENGTH * step for step in range(-4, 5)]  # a car takes the nearest space that is free
                free = [spot for spot in spots if 4 <= spot <= length - 8 and all(abs(spot - other) >= CAR_LENGTH for other in parked)]
                if free:
                    parked.append(min(free, key=lambda spot: abs(spot - wanted)))
                    location.add("stock.car", paint=paint, at=(side * (road / 2 - 1.1), 0, parked[-1]))
        location.rig("stock.night" if night else "stock.daylight")
        location.mark("crossing", (0, 0, 30)).mark("corner", (-5.2, 0, 12), facing=90)
        location.shot("street-level", (1.5, 1.6, -6), (0, 2.5, 40), lens=28)
        location.shot("overlook", (-3, 16, -14), (0, 0, 32), lens=30)
        return location
