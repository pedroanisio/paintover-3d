from typing import Iterable

from srlocations.geometry import Vec3
from srlocations.location import Check, Issue, Location
from srlocations.mesh import MODEL, SLOT, Mesh


def _inside(point: Vec3, low: Vec3, high: Vec3) -> bool:
    return all(l <= p <= h for p, l, h in zip(point, low, high))


class MaterialsExist(Check):
    def run(self, location: Location) -> Iterable[Issue]:
        for name in sorted({skin.name for leaf in location.solids() for skin in leaf.item.skins() if not skin.own}):
            if name not in location.registry.materials:
                yield Issue("error", "material-unknown", f"no material {name!r}")


class ModelSlots(Check):
    """The engine only warns about an override that names no material, so a misspelled slot would just keep the file's look."""

    def run(self, location: Location) -> Iterable[Issue]:
        for leaf in location.solids():
            mesh = leaf.item
            if not isinstance(mesh, Mesh) or not mesh.materials:
                continue
            if mesh.material != MODEL:
                yield Issue("warning", "model-slots-ignored", f"{leaf.path} has one material, which replaces its `materials`")
                continue
            model = mesh.model()
            for slot in sorted(mesh.materials):
                if not SLOT.fullmatch(slot):
                    yield Issue("warning", "model-slot-unnamed", f"{leaf.path}: the engine cannot address a slot called {slot!r}")
                elif model and slot not in model.tones:
                    yield Issue("warning", "model-slot-unknown",
                                f"{leaf.path} has no material {slot!r}; it has {', '.join(sorted(model.tones)) or 'none'}")


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
                if not leaf.item.hollow and _inside(shot.eye, *leaf.item.bounds(leaf.world)):
                    yield Issue("error", "shot-inside-solid", f"shot {shot.name!r} starts inside {leaf.path}")


class SolidsClear(Check):
    """A figure in a solid is an error, because no film would keep it. Two set pieces sharing a volume may be a mistake."""

    def run(self, location: Location) -> Iterable[Issue]:
        for clash in location.clashes():
            yield Issue("error", "body-clash", str(clash)) if clash.moving else Issue("warning", "solids-overlap", str(clash))


class MarksClear(Check):
    """A mark must have standing room: head height above it free of solids."""
    STANDING = (0.15, 1.0, 1.6)

    def run(self, location: Location) -> Iterable[Issue]:
        for mark in location.marks.values():
            for leaf in location.solids():
                low, high = leaf.item.bounds(leaf.world)
                if not leaf.item.hollow and any(_inside(mark.at + Vec3(0, y, 0), low, high) for y in self.STANDING):
                    yield Issue("warning", "mark-blocked", f"mark {mark.name!r} is blocked by {leaf.path}")
