"""One call that says how a set fits the bodies in it: `location.report()`.

The checks answer yes or no. A review wants the numbers behind them: headroom, what a figure can reach and see, how far it is
from what should carry it, and the angles of its joints. These are measurements, and none of them is a verdict, because the
comfortable range of a joint depends on the task and is not this SDK's to state.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from srlocations.collision import GAP, Body, Egg, overlap
from srlocations.figures import Figure
from srlocations.geometry import Transform, Vec3
from srlocations.mesh import Mesh

if TYPE_CHECKING:
    from srlocations.location import Location

HEADROOM = 1.5  # the furthest up a report looks, in metres
BOXED = 1.5  # how near a model must be to matter that it is judged by the convex hulls of its pieces


@dataclass
class FigureReport:
    name: str
    height: float
    off_mark: Optional[float]  # metres from its mark, None if it has no mark
    headroom: float  # metres above its head, HEADROOM when nothing is there
    arm_reach: float  # metres from shoulder to wrist
    within_reach: list[str]  # what is in reach of its hands
    sight_lines: dict[str, Optional[str]]  # another figure or a mark, and what is in the way
    resting: dict[str, float]  # metres from what should carry it, by limb
    posture: dict[str, float]  # degrees
    faults: list[str]  # every limb that passes through the set
    tangled: list[str]  # its limbs that pass through each other
    boxed: list[str] = field(default_factory=list)  # models near it, judged by their pieces' hulls and so by more than their shape

    def lines(self) -> list[str]:
        out = [f"{self.name} ({self.height:.2f} m)"]
        if self.off_mark is not None:
            out.append(f"  off its mark     {self.off_mark * 100:.0f} cm")
        out.append(f"  headroom         {self.headroom * 100:.0f} cm" + (" or more" if self.headroom >= HEADROOM else ""))
        out.append(f"  arm reach        {self.arm_reach * 100:.0f} cm: {', '.join(self.within_reach) or 'nothing in reach'}")
        out.extend(f"  sees {name:<12} {'clear' if blocker is None else 'blocked by ' + blocker}" for name, blocker in self.sight_lines.items())
        out.extend(f"  {name:<16} {value * 100:.1f} cm" for name, value in self.resting.items())
        out.extend(f"  {name:<16} {value:.0f} degrees" for name, value in self.posture.items())
        out.extend(f"  FAULT {fault}" for fault in (*self.faults, *self.tangled))
        out.extend(f"  judged by its hulls: {name}" for name in self.boxed)
        return out


@dataclass
class Report:
    location: str
    figures: list[FigureReport]

    def __str__(self) -> str:
        return "\n".join((self.location, *(line for figure in self.figures for line in figure.lines())))


def _within_reach(location: "Location", figure: Figure) -> list[str]:
    """Top-level pieces of the set a hand can get to, measured from the shoulders."""
    reach = figure.arm_reach()
    spheres = [Egg(Transform.at(shoulder), (reach, reach, reach)) for shoulder in figure.shoulders()]
    found = []
    for node in location.nodes:
        body = Body.of(node, location.contact) if node.collides and node is not figure and not node.moves else None
        if body and any(overlap(sphere, piece.hull) for sphere in spheres for piece in body.hulls):
            found.append(node.label)
    return list(dict.fromkeys(found))


def _head(figure: Figure) -> str:
    """The joint headroom is measured above, or none for a figure with no head, which is then measured as a whole."""
    return "head" if any(leaf.path.rpartition("/")[2] == "head" for leaf in figure.walk()) else ""


def _boxed(location: "Location", figure: Figure) -> list[str]:
    at = Vec3.of(figure.at)
    return [leaf.path for leaf in location.solids() if isinstance(leaf.item, Mesh) and not leaf.item.hollow
            and (leaf.world.position - at).length <= BOXED]


def _resting(location: "Location", figure: Figure) -> dict[str, float]:
    measured = {joint: location.gap(figure, joint, (0, -1, 0)) for joint in figure.footing()}
    seat = location.seat_of(figure)
    if seat and seat.back:
        behind = Transform.at(yaw=seat.facing).apply((0, 0, -1))
        measured.update({f"{joint} to back": location.gap(figure, joint, behind) for joint in figure.backing()})
    return {name: value for name, value in measured.items() if value < GAP}


def report(location: "Location") -> Report:
    figures = location.figures()
    others = {*(figure.label for figure in figures), *location.marks}
    return Report(location.name, [
        FigureReport(figure.label, figure.stature(),
                     (Vec3.of(figure.at) - location.marks[figure.name].at).length if figure.name in location.marks else None,
                     location.gap(figure, _head(figure), (0, 1, 0), HEADROOM), figure.arm_reach(), _within_reach(location, figure),
                     {name: location.sees(figure, name) for name in sorted(others - {figure.label})}, _resting(location, figure),
                     figure.posture(), [str(clash) for clash in location.faults(figure)],
                     list(figure.tangled()), _boxed(location, figure)) for figure in figures])
