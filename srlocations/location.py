"""A Location: the graph plus what a production needs from it, marks to stand on and shots to take."""
from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Optional, Sequence, Union

from srlocations.cast import Actor, Ensemble, Performer
from srlocations.collision import REACH, Clash, CollisionError, clashes, clear
from srlocations.geometry import Transform, Vec3, VecLike
from srlocations.nodes import Light, Node, Placed, Seat, Solid
from srlocations.paint import PaintLayer
from srlocations.registry import CatalogError, Registry


@dataclass(frozen=True)
class Mark:
    """A named place for a character or prop, on the location's floor."""
    name: str
    at: Vec3
    facing: float = 0.0


@dataclass(frozen=True)
class Shot:
    name: str
    eye: Vec3
    look_at: Vec3
    lens: float = 35.0


@dataclass(frozen=True)
class Issue:
    severity: str
    code: str
    message: str


class Check(ABC):
    """One rule a location must meet; plugins add their own to registry.checks."""

    @abstractmethod
    def run(self, location: "Location") -> Iterable[Issue]:
        ...


class LightRig(ABC):
    """A lighting setup that can be applied to any location."""

    @abstractmethod
    def lights(self) -> Iterable[Light]:
        ...

    background = "#000000"


class Archetype(ABC):
    """A generator: the same seed and parameters always give the same location."""

    @abstractmethod
    def build(self, registry: Registry, seed: int = 0, **params: Any) -> "Location":
        ...


class Location:
    def __init__(self, name: str, registry: Optional[Registry] = None) -> None:
        self.name = name
        self.registry = registry or Registry.default()
        self.nodes: list[Node] = []
        self.marks: dict[str, Mark] = {}
        self.shots: dict[str, Shot] = {}
        self.paintings: list[PaintLayer] = []
        self.background = "#000000"

    def add(self, node: Union[Node, str], **params: Any) -> Node:
        """A node, or the name of a registered prefab and its parameters."""
        self.nodes.append(self.registry.create(node, **params) if isinstance(node, str) else node)
        return self.nodes[-1]

    def rig(self, rig: Union[LightRig, str], **params: Any) -> "Location":
        rig = self.registry.rigs.get(rig)(**params) if isinstance(rig, str) else rig
        self.nodes.extend(rig.lights())
        self.background = rig.background
        return self

    def mark(self, name: str, at: VecLike, facing: float = 0.0) -> "Location":
        self.marks[name] = Mark(name, Vec3.of(at), facing)
        return self

    def shot(self, name: str, eye: VecLike, look_at: VecLike, lens: float = 35.0) -> "Location":
        self.shots[name] = Shot(name, Vec3.of(eye), Vec3.of(look_at), lens)
        return self

    def paint(self, name: str, blend: str = "normal", opacity: float = 1.0, shots: Sequence[str] = (),
              looks: Sequence[str] = (), depth: bool = False) -> PaintLayer:
        """A new layer over the picture, on top of those before it. With `depth` the set hides it."""
        self.paintings.append(PaintLayer(name, blend, opacity, shots, looks=looks, depth=depth))
        return self.paintings[-1]

    def cast(self, character: Union[Performer, str], mark: str, height: float = 1.7,
             pose: Optional[Mapping[str, str]] = None, flip: bool = False, shadow: float = 0.3,
             looks: Sequence[str] = (), shots: Sequence[str] = (), depth: bool = True) -> Actor:
        """Stands a character on a mark. `character` is a Performer or a name from registry.cast. `looks` and `shots` limit
        it, by name, and actors with the same limits share a layer, ordered by distance in each shot. The set hides what is
        behind it unless `depth` is False."""
        if mark not in self.marks:
            raise CatalogError(f"no mark {mark!r}; this location has {', '.join(sorted(self.marks)) or 'none'}")
        performer = self.registry.cast.get(character) if isinstance(character, str) else character
        actor = Actor(performer, self.marks[mark].at, height, pose or {}, flip, shadow)
        for layer in self.paintings:
            if layer.name == "cast" and (*layer.looks,) == (*looks,) and (*layer.shots,) == (*shots,) and layer.depth == depth:
                break
        else:
            layer = self.paint("cast", shots=shots, looks=looks, depth=depth).add(Ensemble())
        layer.items[0].actors.append(actor)
        return actor

    def stand(self, *marks: str, prefab: str = "stock.mannequin", **params: Any) -> list[Node]:
        """A prefab on each mark, or on all of them, turned the way the mark faces: a body to review a set with. Each is
        settled: a sitting figure takes the seat beside its mark, and anything else moves clear of what is on the mark."""
        missing = sorted(set(marks) - set(self.marks))
        if missing:
            raise CatalogError(f"no mark {missing[0]!r}; this location has {', '.join(sorted(self.marks)) or 'none'}")
        make = self.registry.prefabs.get(prefab)
        return [self.settle(self.add(make(at=self.marks[name].at, yaw=self.marks[name].facing, name=name, **params)))
                for name in marks or self.marks]

    def seats(self) -> list[Seat]:
        """Every place to sit in the location, in the world."""
        def under(node: Node, parent: Transform) -> Iterable[Seat]:
            world = parent.then(node.transform)
            for seat in node.seats():
                ahead = world.apply(Transform.at(seat.at, seat.facing).apply((0, 0, 1))) - world.apply(seat.at)
                yield Seat(world.apply(seat.at), math.degrees(math.atan2(ahead.x, ahead.z)), seat.height, seat.depth)
            for part in node.parts():
                yield from under(part, world)
        return [seat for node in self.nodes for seat in under(node, Transform())]

    def settle(self, node: Node) -> Node:
        """Moves a node of this location until nothing passes through it, onto a seat if it sits. A body that cannot fit is
        taken back out of the location and CollisionError says what stopped it."""
        if not node.moves or not node.collides:
            return node
        start, spot = (node.at, node.yaw), Vec3.of(node.at)
        if node.sits:
            taken = [Vec3.of(other.at) for other in self.nodes if other.sits and other is not node]
            free = [seat for seat in self.seats() if (seat.at - spot).length <= REACH
                    and all((seat.at - other).length > 0.3 for other in taken)]
            if free:
                seat = min(free, key=lambda seat: (seat.at - spot).length)
                under, knees = node.sitting()  # a child climbs up to the seat, and perches on the edge of a deep one
                ahead = Transform.at(yaw=seat.facing).apply((0, 0, 1))
                slide = max(0.0, seat.depth - knees + 0.01)
                node.at = seat.at + Vec3(ahead.x * slide, max(0.0, seat.height - under), ahead.z * slide)
                node.yaw = seat.facing
        try:
            node.at = Vec3.of(node.at) + clear(node, self.nodes)
        except CollisionError:
            node.at, node.yaw = start
            self.nodes.remove(node)
            raise
        return node

    def clashes(self, bodies_only: bool = False) -> list[Clash]:
        """What is passing through what, by the rules in collision.py."""
        return list(clashes(self.nodes, bodies_only))

    def pov(self, figure: Union[Node, str], name: Optional[str] = None, lens: float = 24.0) -> Shot:
        """A shot from a figure's eyes, as it stands now, looking where its head and eyes turn. `figure` is a node or a name."""
        found = figure if isinstance(figure, Node) else next((node for node in self.nodes if node.name == figure), None)
        if found is None or not hasattr(found, "sight"):
            raise CatalogError(f"no figure {figure!r}; this location has {', '.join(sorted(n.name for n in self.nodes if hasattr(n, 'sight') and n.name)) or 'none'}")
        self.shot(name or f"{found.label}-pov", *found.sight(), lens)
        return self.shots[name or f"{found.label}-pov"]

    def placed(self) -> list[Placed]:
        return [leaf for node in self.nodes for leaf in node.walk()]

    def solids(self) -> list[Placed]:
        return [leaf for leaf in self.placed() if isinstance(leaf.item, Solid)]

    def lights(self) -> list[Placed]:
        return [leaf for leaf in self.placed() if isinstance(leaf.item, Light)]

    def validate(self) -> list[Issue]:
        return [issue for check in self.registry.checks for issue in check.run(self)]
