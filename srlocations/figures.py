"""A Figure is a body that acts on a set: what `stand`, `settle`, `pov` and the checks need from one, whatever rig it has. A
character is not a Figure. It is a picture in a paint layer, reached through `Performer`, and it shares a figure's mark and
`looks=`, which is how one takes over from the other look by look.
"""
from __future__ import annotations

import math
from abc import abstractmethod
from dataclasses import dataclass, field, replace
from typing import Any, Mapping, Optional, Sequence

from srlocations.geometry import Vec3, VecLike
from srlocations.kinematics import Hold
from srlocations.nodes import Prefab


def angle(a: Vec3, joint: Vec3, b: Vec3) -> float:
    """The angle at `joint` between two points, in degrees."""
    u, v = a - joint, b - joint
    return math.degrees(math.acos(max(-1.0, min(1.0, sum(p * q for p, q in zip(u, v)) / (u.length * v.length)))))


@dataclass
class Figure(Prefab):
    """A body. `solid` False lets it pass through a set, on purpose; see collision.py."""
    solid: bool = field(default=True, kw_only=True)
    moves = True

    @property
    def collides(self) -> bool:
        return self.solid

    @abstractmethod
    def sight(self) -> tuple[Vec3, Vec3]:
        """Where it sees from in the location, and a point it is looking at."""

    @abstractmethod
    def values(self) -> Mapping[str, float]:
        """Its pose, as controls."""

    @abstractmethod
    def take(self, values: Mapping[str, float], sits: bool = False) -> None:
        """Holds these controls from now on."""

    @abstractmethod
    def aiming(self, pose: Any = None, adjust: Optional[Mapping[str, float]] = None) -> tuple[Mapping[str, float], bool]:
        """The controls a pose and some changes come to, and whether a figure in them sits."""

    def reach_to(self, joint: str, point: VecLike, tolerance: float = 0.01, pole: Optional[VecLike] = None,
                 keep: bool = False) -> float:
        """Turns a limb until `joint` is at a point in the location, and gives how far off it stopped. The middle joint
        points toward `pole`, and with `keep` the end keeps the way it is turned."""
        raise NotImplementedError(f"{type(self).__name__} cannot reach")

    def ghosted(self, name: str) -> "Figure":
        """A copy of it to show where it was or will be: named `name`, with the "ghost" role, passing through everything."""
        return replace(self, name=name, role=" ".join(filter(None, (self.role, "ghost"))), solid=False)

    def hold(self, joint: str, keep: bool = True, flat: bool = False) -> Hold:
        """A hold that keeps `joint` where it is now in the location, for a figure with `holds`. With `flat` a foot is set
        down level on the floor, below where it is."""
        raise NotImplementedError(f"{type(self).__name__} cannot hold a joint")

    def stepping(self, lead: str) -> Mapping[str, float]:
        """A walk's contact pose, with the `lead` foot, "left" or "right", forward, for `location.walk()`."""
        raise NotImplementedError(f"{type(self).__name__} cannot walk")

    def passing(self, lead: str) -> Mapping[str, float]:
        """A walk's passing pose, halfway to the contact where `lead` is forward, its leg lifting as it swings."""
        raise NotImplementedError(f"{type(self).__name__} cannot walk")

    def stride(self) -> float:
        """How far apart its feet are along the way in a walk's contact pose, in metres."""
        raise NotImplementedError(f"{type(self).__name__} cannot walk")

    def look_at(self, point: VecLike) -> "Figure":
        """Turns to look at a point in the location, as far as it can. A figure that cannot turn stays as it is."""
        return self

    def posture(self) -> dict[str, float]:
        """The angles a seating study reports, in degrees."""
        return {}

    def tangled(self) -> Sequence[str]:
        """Its own limbs that pass through each other."""
        return ()

    def backing(self) -> Sequence[str]:
        """The joints that lean on a backrest."""
        return ()

    def footing(self) -> Sequence[str]:
        """The joints that carry it, as it is posed."""
        return ()

    def arm_reach(self) -> float:
        """How far its hands get from its shoulders, in metres."""
        return 0.0

    def shoulders(self) -> Sequence[Vec3]:
        """Where in the location `arm_reach` is measured from."""
        return ()

    def stature(self) -> float:
        """How tall it stands, in metres: here the top of its solids above its feet."""
        tops = [leaf.item.bounds(leaf.world)[1].y for leaf in self.walk() if hasattr(leaf.item, "bounds")]
        return max(tops, default=Vec3.of(self.at).y) - Vec3.of(self.at).y
