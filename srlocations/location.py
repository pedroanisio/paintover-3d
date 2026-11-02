"""A Location: the graph plus what a production needs from it, marks to stand on and shots to take."""
from __future__ import annotations

import copy
import difflib
import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, fields, replace
from typing import Any, Callable, Iterable, Mapping, Optional, Sequence, Union

from srlocations.cast import Actor, Ensemble, Performer
from srlocations.collision import REACH, Body, Clash, CollisionError, clashes, clear
from srlocations.geometry import Transform, Vec3, VecLike
from srlocations.motion import EASES, Key, MotionError, Track, shape, value_at
from srlocations.nodes import Light, Node, Placed, Seat, Solid
from srlocations.paint import PaintItem, PaintLayer
from srlocations.registry import CatalogError, Registry

VECTORS = ("eye", "look_at", "at")


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
    """One rule a location must meet; plugins add their own to registry.checks. A check is run on the location as it is
    at each key of its motion, unless it says `over_time`, and then it is run once on the moving location itself."""
    over_time = False

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


def _held(pose: Mapping[str, str]) -> tuple[tuple[str, str], ...]:
    """A character's pose as one value, which a key does not blend part by part."""
    return tuple(sorted(dict(pose).items()))


class Location:
    SHOT_KEYS, MARK_KEYS, ACTOR_KEYS = ("eye", "look_at", "lens"), ("at", "facing"), ("pose", "height", "flip", "shadow")

    def __init__(self, name: str, registry: Optional[Registry] = None) -> None:
        self.name = name
        self.registry = registry or Registry.default()
        self.nodes: list[Node] = []
        self.marks: dict[str, Mark] = {}
        self.shots: dict[str, Shot] = {}
        self.paintings: list[PaintLayer] = []
        self.background = "#000000"
        self.motion: dict[Any, Track] = {}  # by a shot's or mark's name in a pair, or a node's id
        self.followed: dict[str, tuple[Union[Node, str], Vec3]] = {}  # shots that keep something in the middle of the frame
        self.sights: dict[str, Node] = {}  # shots from a figure's eyes
        self.origin: Optional["Location"] = None  # the location a moment was taken from

    def add(self, node: Union[Node, str], **params: Any) -> Node:
        """A node, or the name of a registered prefab and its parameters. Parameters given with a node replace its own."""
        if isinstance(node, str):
            node = self.registry.create(node, **params)
        elif params:
            try:
                node = replace(node, **params)
            except TypeError as error:
                raise TypeError(f"{type(node).__name__} has no field among {', '.join(sorted(params))}: {error}") from None
        self.nodes.append(node)
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

    def move(self, what: Union[Node, Actor, str], time: float, ease: str = "ease-in-out", **values: Any) -> "Location":
        """A key: `what` reaches these values at `time`, in seconds, having left its last key as `ease` says. `what` is a
        shot, a mark, or a node of this location or its name, or an actor from cast(). A shot takes `eye`, `look_at` and
        `lens`, a mark `at` and `facing`, a node any of its fields, such as `at`, `yaw`, or a figure's `pose`, and an actor
        `pose`, `height`, `flip` and `shadow`, which its mark carries. A character's pose is a picture, so it changes when it
        arrives, whatever the ease. A node whose parts change is drawn in each shape for its frames. With no values it stays
        as it is until `time`. What stands on a mark goes with the mark. "hold" jumps at the key, and "smooth" goes
        through a key without stopping."""
        if time <= 0:
            raise MotionError(f"a key comes after the start, and {time} does not")
        if ease not in EASES:
            near = difflib.get_close_matches(ease, EASES, n=1)
            raise MotionError(f"no ease {ease!r}" + (f"; did you mean {near[0]}?" if near else f"; there are {', '.join(EASES)}"))
        key, start, allowed = self._target(what)
        track = self.motion.setdefault(key, Track())
        if not values:
            values = {name: value_at(keys, time) for name, keys in track.fields.items()} or {allowed[0]: start(allowed[0])}
            ease = "linear"
        for name in values:
            if name not in allowed:
                near = difflib.get_close_matches(name, allowed, n=1)
                raise MotionError(f"cannot move {name!r}" + (f"; did you mean {near[0]}?" if near else f"; try {', '.join(allowed)}"))
        node = what if isinstance(what, Node) else None
        node = node or next((n for n in self.nodes if id(n) == key), None)
        if isinstance(what, Actor):
            values = {name: _held(value) if name == "pose" else value for name, value in values.items()}
        for name, value in (node.keyed(values) if node else {k: Vec3.of(v) if k in VECTORS else v for k, v in values.items()}).items():
            track.key(name, start(name), Key(float(time), value, ease))
        return self

    def _target(self, what: Union[Node, Actor, str]) -> tuple[Any, Callable[[str], Any], Sequence[str]]:
        """How a thing that moves is filed, its value of a field now, and the fields it has."""
        if isinstance(what, Actor):
            if not any(actor is what for layer in self.paintings for item in layer.items if isinstance(item, Ensemble)
                       for actor in item.actors):
                raise MotionError("that actor is not cast here; move the one cast() gave back")
            return ("actor", id(what)), lambda name: _held(what.pose) if name == "pose" else getattr(what, name), self.ACTOR_KEYS
        if isinstance(what, str):
            found = [kind for kind, names in (("shot", self.shots), ("mark", self.marks)) if what in names]
            if len(found) > 1:
                raise MotionError(f"{what!r} is a shot and a mark, so pass one a new name")
            if found:
                source, keys = (self.shots, self.SHOT_KEYS) if found[0] == "shot" else (self.marks, self.MARK_KEYS)
                return (found[0], what), lambda name: getattr(source[what], name), keys
            what = next((node for node in self.nodes if node.name == what), what)
            if isinstance(what, str):
                raise MotionError(f"nothing here is called {what!r}: no shot, no mark and no node at the top of this location")
        if not any(node is what for node in self.nodes):
            raise MotionError(f"{what.label} is not at the top of this location, so it cannot move alone; add it directly")
        names = tuple(f.name for f in fields(what) if f.init)
        return id(what), lambda name: what.keyed({name: getattr(what, name)})[name], ("at", *(n for n in names if n != "at"))

    def follow(self, shot: str, what: Union[Node, str], offset: VecLike = (0, 0, 0)) -> "Location":
        """Keeps a shot's camera on a node or a mark, at `offset` from it, wherever it goes."""
        self.followed[shot] = what, Vec3.of(offset)
        self.shots[shot] = self._followed(self.shots[shot], self)
        return self

    def _followed(self, shot: Shot, moment: "Location") -> Shot:
        what, offset = self.followed[shot.name]
        if isinstance(what, str) and what in moment.marks:
            return replace(shot, look_at=moment.marks[what].at + offset)
        found = next((new for old, new in zip(self.nodes, moment.nodes) if old is what or old.name == what), None)
        if found is None:
            raise MotionError(f"shot {shot.name!r} follows {what!r}, and nothing here is called that")
        return replace(shot, look_at=Vec3.of(found.at) + offset)

    def duration(self, shot: Optional[str] = None) -> float:
        """How long a shot lasts, in seconds: until the last thing in it stops. No moves, no time."""
        return max((track.end for key, track in self.motion.items()
                    if not (isinstance(key, tuple) and key[0] == "shot" and shot not in (None, key[1]))), default=0.0)

    STRIDE = 0.03  # metres: no part of a moving body goes further than this between two checks

    def instants(self, walked: Optional[dict[float, dict[int, tuple[Node, list[Placed]]]]] = None) -> list[float]:
        """When to check a location that moves: at every key, and between them often enough that no part of anything
        moving goes further than STRIDE from one check to the next, so it cannot pass through something unseen. `walked`
        is filled with what moves at each time looked at, by its index in nodes, and its leaves."""
        walked = {} if walked is None else walked
        times = sorted({0.0, *(time for track in self.motion.values() for time in track.times)})
        if not any(isinstance(key, int) or key[0] == "mark" for key in self.motion):
            return times
        found, places = [times[0]], {times[0]: self._places(times[0], walked)}
        pending = [(a, b) for a, b in zip(times, times[1:])][::-1]
        while pending:
            start, end = pending.pop()
            if end not in places:
                places[end] = self._places(end, walked)
            if end - start > 1e-3 and self._apart(places[start], places[end]) > self.STRIDE:
                middle = (start + end) / 2
                pending += [(middle, end), (start, middle)]
                continue
            found.append(end)
        return found

    def _moving(self, node: Node) -> bool:
        return id(node) in self.motion or ("mark", node.name) in self.motion

    def _places(self, time: float, walked: dict[float, dict[int, tuple[Node, list[Placed]]]]) -> list[Vec3]:
        """Where each part of what moves is at a time: the corners of its bounds, so a turn counts as well as a slide."""
        marks, places = self._marks_at(time), []
        walked[time] = {}
        for index, node in enumerate(self.nodes):
            if not self._moving(node):
                continue
            node = self._node_at(node, time, marks)
            walked[time][index] = (node, list(node.walk()))
            for leaf in walked[time][index][1]:
                if isinstance(leaf.item, Solid):
                    low, high = leaf.item.bounds(leaf.world)
                    places += [low, high]
        return places

    @staticmethod
    def _apart(before: Sequence[Vec3], after: Sequence[Vec3]) -> float:
        if len(before) != len(after):
            return math.inf
        return max((math.dist(a, b) for a, b in zip(before, after)), default=0.0)

    def at(self, time: float) -> "Location":
        """This location as it is at `time`, with nothing moving."""
        if not self.motion:
            return self
        moment = copy.copy(self)
        moment.motion, moment.followed, moment.sights, moment.origin = {}, {}, {}, self
        marks = self._marks_at(time)
        offset = lambda name: marks[name].at - self.marks[name].at if name in marks else Vec3()
        moment.marks = marks
        moment.nodes = [self._node_at(node, time, marks) for node in self.nodes]
        moment.paintings = [replace(layer, items=[self._item_at(item, time, offset) for item in layer.items])
                            for layer in self.paintings]
        moment.shots = {name: self._shot_at(shot, time, moment) for name, shot in self.shots.items()}
        return moment

    def _marks_at(self, time: float) -> dict[str, Mark]:
        return {name: replace(mark, **self.motion[("mark", name)].at(time)) if ("mark", name) in self.motion else mark
                for name, mark in self.marks.items()}

    def _node_at(self, node: Node, time: float, marks: Mapping[str, Mark]) -> Node:
        moved = node.posed(self.motion[id(node)].at(time)) if id(node) in self.motion else node
        if node.name in marks and marks[node.name] is not self.marks[node.name]:  # stand() names a figure after its mark
            before = self.marks[node.name]
            return replace(moved, at=Vec3.of(moved.at) + marks[node.name].at - before.at,
                           yaw=moved.yaw + marks[node.name].facing - before.facing)
        return moved

    def _item_at(self, item: PaintItem, time: float, offset: Callable[[str], Vec3]) -> PaintItem:
        """Paint as it is at a time: carried by its mark, and an actor with its own keys."""
        carried = item.carried(offset)
        if not isinstance(item, Ensemble):
            return carried
        actors = []
        for old, new in zip(item.actors, carried.actors):
            keyed = self.motion[("actor", id(old))].at(time) if ("actor", id(old)) in self.motion else {}
            actors.append(replace(new, **{name: dict(value) if name == "pose" else value for name, value in keyed.items()}))
        return replace(carried, actors=actors)

    def _shot_at(self, shot: Shot, time: float, moment: "Location") -> Shot:
        keyed = self.motion.get(("shot", shot.name))
        shot = replace(shot, **keyed.at(time)) if keyed else shot
        if shot.name in self.sights:
            figure = next(new for old, new in zip(self.nodes, moment.nodes) if old is self.sights[shot.name])
            eye, look_at = figure.sight()
            return replace(shot, eye=eye, look_at=look_at)
        return self._followed(shot, moment) if shot.name in self.followed else shot

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
        actor = Actor(performer, self.marks[mark].at, height, pose or {}, flip, shadow, mark)
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
        """What is passing through what, by the rules in collision.py, each at the first time it happens if this location
        moves, earliest first."""
        known: dict = {}  # what stands still is the same node at every moment, and its body is found once
        walked: dict = {}  # and what moves was built and walked once already, to find the instants
        found: dict[tuple[str, str], Clash] = {}
        for index, time in enumerate(self.instants(walked)):
            nodes = list(self.at(time).nodes)
            for place, (node, leaves) in walked.get(time, {}).items():
                nodes[place] = node
                known[id(node)] = Body.of(node, leaves)
            among = None if index == 0 else {id(new) for old, new in zip(self.nodes, nodes) if self._moving(old)}
            for clash in clashes(nodes, bodies_only, among, known):
                found.setdefault((clash.first, clash.second), replace(clash, time=time))
            for node, _ in walked.get(time, {}).values():
                del known[id(node)]
        return list(found.values())

    def pov(self, figure: Union[Node, str], name: Optional[str] = None, lens: float = 24.0) -> Shot:
        """A shot from a figure's eyes, as it stands now, looking where its head and eyes turn. `figure` is a node or a name."""
        found = figure if isinstance(figure, Node) else next((node for node in self.nodes if node.name == figure), None)
        if found is None or not hasattr(found, "sight"):
            raise CatalogError(f"no figure {figure!r}; this location has {', '.join(sorted(n.name for n in self.nodes if hasattr(n, 'sight') and n.name)) or 'none'}")
        title = name or f"{found.label}-pov"
        self.shot(title, *found.sight(), lens)
        self.sights[title] = found
        return self.shots[title]

    def placed(self) -> list[Placed]:
        """Every leaf. In a moment, what moved knows where it stood when the shot began, as a clip's frames do."""
        if self.origin is None:
            return [leaf for node in self.nodes for leaf in node.walk()]
        placed = []
        for old, new in zip(self.origin.nodes, self.nodes):
            leaves = list(new.walk())
            if new is not old:
                before = list(old.walk())
                kept = shape(before) == shape(leaves)
                leaves = [replace(leaf, start=began.world) for leaf, began in zip(leaves, before)] if kept else \
                    [replace(leaf, reshaped=number) for number, leaf in
                     enumerate(leaf for leaf in leaves if not isinstance(leaf.item, Light))] + \
                    [leaf for leaf in leaves if isinstance(leaf.item, Light)]
            placed += leaves
        return placed

    def solids(self) -> list[Placed]:
        return [leaf for leaf in self.placed() if isinstance(leaf.item, Solid)]

    def lights(self) -> list[Placed]:
        return [leaf for leaf in self.placed() if isinstance(leaf.item, Light)]

    def validate(self) -> list[Issue]:
        """What is wrong here, at each moment something reaches a key. A fault is told once, at the first moment it appears.
        A check `over_time` looks between the keys itself, and runs once."""
        issues: dict[Issue, Issue] = {}
        for time in sorted({0.0, *(time for track in self.motion.values() for time in track.times)}):
            moment = self.at(time)
            for issue in (issue for check in self.registry.checks if not (check.over_time and time)
                          for issue in check.run(self if check.over_time else moment)):
                issues.setdefault(issue, replace(issue, message=f"{issue.message}, at {time:g} s") if time else issue)
        return list(issues.values())
