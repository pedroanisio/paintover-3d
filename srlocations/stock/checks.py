from typing import Iterable

from srlocations.collision import GAP, Body, blocked
from srlocations.geometry import Transform, Vec3
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
    """A figure in a solid is an error, because no film would keep it. Two set pieces sharing a volume may be a mistake.
    In a location that moves, clashes() looks often enough between keys that nothing passes through unseen."""
    over_time = True

    def run(self, location: Location) -> Iterable[Issue]:
        for clash in location.clashes():
            yield Issue("error", "body-clash", str(clash)) if clash.moving else Issue("warning", "solids-overlap", str(clash))


class FiguresOnMarks(Check):
    """A body settles where there is room, which may not be its mark. A character on the mark goes with it, so a picture and a
    stand-in agree, and a shot aimed at the mark may not."""
    MOVED = 0.02

    def run(self, location: Location) -> Iterable[Issue]:
        origin = location.origin or location  # a moment's nodes are new, so what moves is found by place, as _shot_at does
        moving = {new.label for old, new in zip(origin.nodes, location.nodes) if id(old) in origin.motion}  # it left on purpose
        for figure in location.figures():
            if figure.name in location.marks and figure.label not in moving:
                off = (Vec3.of(figure.at) - location.marks[figure.name].at).length
                if off > self.MOVED:
                    yield Issue("warning", "figure-off-mark", f"{figure.label} settled {off * 100:.0f} cm from its mark")
        for layer in location.paintings:
            for actor in (actor for item in layer.items for actor in getattr(item, "actors", ())):
                if actor.mark in location.marks and (Vec3.of(actor.at) - location.standing(actor.mark)).length > self.MOVED:
                    yield Issue("warning", "cast-off-figure", f"the character on {actor.mark!r} is not where the figure on it is")


class FiguresResting(Check):
    """Overlap says nothing about support. A figure can pass every collision check with its back a hand off the backrest."""

    def run(self, location: Location) -> Iterable[Issue]:
        for figure in filter(lambda figure: figure.collides, location.figures()):
            rest, seat = location.contact.rest, location.seat_of(figure)
            below = min((location.gap(figure, joint, (0, -1, 0)) for joint in figure.footing()), default=0.0)
            if rest < below < GAP or (seat and below > rest):
                yield Issue("warning", "figure-not-resting", f"{figure.label} is {below * 100:.0f} cm above what should carry it")
            if seat and seat.back:
                behind = Transform.at(yaw=seat.facing).apply((0, 0, -1))
                back = min(location.gap(figure, joint, behind) for joint in figure.backing())
                if back > rest:
                    yield Issue("warning", "figure-not-resting", f"{figure.label}'s back is {back * 100:.0f} cm off the backrest")


class FiguresUntangled(Check):
    """A pose is checked against its ranges one control at a time, so an arm can still go through the chest. It is a warning,
    since rigid segments overlap at a bent joint that a real body folds around."""

    def run(self, location: Location) -> Iterable[Issue]:
        for figure in location.figures():
            for fault in figure.tangled():
                yield Issue("warning", "figure-tangled", f"{figure.label}: {fault}")


class SightsClear(Check):
    """A shot composed around figures should see them. Those it is composed around do not block it, or a shoulder in the
    foreground of an over-the-shoulder would."""

    def run(self, location: Location) -> Iterable[Issue]:
        for title, (_, labels, _) in location.framed.items():
            bodies = [body for body in (Body.of(node, location.contact) for node in location.nodes
                                        if node.collides and node.label not in labels) if body]
            for label in labels:
                blocker = blocked(location.shots[title].eye, location.figure(label).sight()[0], bodies)
                if blocker:
                    yield Issue("warning", "sight-blocked", f"shot {title!r} cannot see {label}: {blocker} is in the way")


class MarksClear(Check):
    """A mark must have standing room: head height above it free of solids."""
    STANDING = (0.15, 1.0, 1.6)

    def run(self, location: Location) -> Iterable[Issue]:
        for mark in location.marks.values():
            for leaf in location.solids():
                low, high = leaf.item.bounds(leaf.world)
                if not leaf.item.hollow and any(_inside(mark.at + Vec3(0, y, 0), low, high) for y in self.STANDING):
                    yield Issue("warning", "mark-blocked", f"mark {mark.name!r} is blocked by {leaf.path}")
