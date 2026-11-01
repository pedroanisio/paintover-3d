from typing import Iterable

from srlocations.geometry import Vec3
from srlocations.location import Check, Issue, Location


def _inside(point: Vec3, low: Vec3, high: Vec3) -> bool:
    return all(l <= p <= h for p, l, h in zip(point, low, high))


class MaterialsExist(Check):
    def run(self, location: Location) -> Iterable[Issue]:
        for name in sorted({leaf.item.material for leaf in location.solids()}):
            if name not in location.registry.materials:
                yield Issue("error", "material-unknown", f"no material {name!r}")


class LooksKnown(Check):
    """Paint or a decal limited to a look that nothing is called is a typo that shows up as missing paint."""

    def run(self, location: Location) -> Iterable[Issue]:
        named = {look for layer in location.paintings for look in layer.looks}
        named |= {look for leaf in location.solids() for look in getattr(leaf.item, "looks", ())}
        for look in sorted(named):
            if look not in location.registry.modes:
                yield Issue("warning", "look-unknown", f"paint is limited to {look!r}, which is not a registered mode")


class ShotsClear(Check):
    """A camera inside a solid renders that solid's inside, or nothing."""

    def run(self, location: Location) -> Iterable[Issue]:
        for shot in location.shots.values():
            for leaf in location.solids():
                if _inside(shot.eye, *leaf.item.bounds(leaf.world)):
                    yield Issue("error", "shot-inside-solid", f"shot {shot.name!r} starts inside {leaf.path}")


class MarksClear(Check):
    """A mark must have standing room: head height above it free of solids."""
    STANDING = (0.15, 1.0, 1.6)

    def run(self, location: Location) -> Iterable[Issue]:
        for mark in location.marks.values():
            for leaf in location.solids():
                low, high = leaf.item.bounds(leaf.world)
                if any(_inside(mark.at + Vec3(0, y, 0), low, high) for y in self.STANDING):
                    yield Issue("warning", "mark-blocked", f"mark {mark.name!r} is blocked by {leaf.path}")
