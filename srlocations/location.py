"""A Location: the graph plus what a production needs from it, marks to stand on and shots to take."""
from __future__ import annotations

import copy
import difflib
import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, fields, replace
from typing import TYPE_CHECKING, Any, Callable, Iterable, Mapping, Optional, Sequence, Union

from srlocations.camera import Follow, Shake, shaken, steady
from srlocations.cast import Actor, Ensemble, Performer
from srlocations.collision import GAP, Body, Clash, CollisionError, Contact, blocked, clashes, clear, fits, gap, limb_clashes
from srlocations.figures import Figure
from srlocations.geometry import Transform, Vec3, VecLike
from srlocations.motion import EASES, Key, MotionError, Track, cubic_bezier, value_at
from srlocations.nodes import Light, Node, Placed, Seat, Solid
from srlocations.paint import PaintLayer
from srlocations.registry import CatalogError, Registry

if TYPE_CHECKING:
    from srlocations.review import Report

SIGHT = 1.5  # how far above a mark with nobody on it a figure looks
SEATED = 0.35  # the furthest a figure sitting on a seat is from it
VECTORS = ("eye", "look_at", "at")


@dataclass(frozen=True)
class Mark:
    """A named place for a character or prop, on the location's floor. `framing` says how close a shot of it should be, as a
    name in registry.framings, for what reads `location.blocking()`."""
    name: str
    at: Vec3
    facing: float = 0.0
    framing: str = ""


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
    SHOT_KEYS, MARK_KEYS = ("eye", "look_at", "lens"), ("at", "facing")

    def __init__(self, name: str, registry: Optional[Registry] = None) -> None:
        self.name = name
        self.registry = registry or Registry.default()
        self.nodes: list[Node] = []
        self.marks: dict[str, Mark] = {}
        self.shots: dict[str, Shot] = {}
        self.paintings: list[PaintLayer] = []
        self.background = "#000000"
        self.motion: dict[Any, Track] = {}  # by a shot's or mark's name in a pair, or a node's id
        self.followed: dict[str, Follow] = {}  # shots that keep something in the middle of the frame
        self.sights: dict[str, Node] = {}  # shots from a figure's eyes
        self.framed: dict[str, tuple[str, tuple[str, ...], Optional[float]]] = {}  # shots composed by location.frame()
        self.shaken: dict[str, list[Shake]] = {}  # shots whose camera shakes, applied last
        self.origin: Optional["Location"] = None  # the location a moment was taken from
        self.contact = Contact()  # how far things may meet here; see collision.py

    def add(self, node: Union[Node, str], **params: Any) -> Node:
        """A node, or the name of a registered prefab and its parameters."""
        self.nodes.append(self.registry.create(node, **params) if isinstance(node, str) else node)
        return self.nodes[-1]

    def rig(self, rig: Union[LightRig, str], **params: Any) -> "Location":
        rig = self.registry.rigs.get(rig)(**params) if isinstance(rig, str) else rig
        self.nodes.extend(rig.lights())
        self.background = rig.background
        return self

    def mark(self, name: str, at: VecLike, facing: float = 0.0, framing: str = "") -> "Location":
        if framing and framing not in self.registry.framings:
            self.registry.framings.get(framing)
        self.marks[name] = Mark(name, Vec3.of(at), facing, framing)
        return self

    def shot(self, name: str, eye: VecLike, look_at: VecLike, lens: float = 35.0) -> "Location":
        self.shots[name] = Shot(name, Vec3.of(eye), Vec3.of(look_at), lens)
        return self

    def move(self, what: Union[Node, str], time: float, ease: Union[str, Sequence[float]] = "ease-in-out", **values: Any) -> "Location":
        """A key: `what` reaches these values at `time`, in seconds, having left its last key as `ease` says. `what` is a
        shot, a mark, or a node of this location or its name. A shot takes `eye`, `look_at` and `lens`, a mark `at` and
        `facing`, and a node any of its fields that keep its parts, such as `at`, `yaw`, or a figure's `pose`. With no values
        it stays as it is until `time`. What stands on a mark goes with the mark. "hold" jumps at the key, and "smooth" goes
        through a key without stopping. Four numbers, or "cubic-bezier(x1, y1, x2, y2)", are a curve as CSS draws one."""
        ease = ease if isinstance(ease, str) else cubic_bezier(*ease)
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
        for name, value in (node.keyed(values) if node else {k: Vec3.of(v) if k in VECTORS else v for k, v in values.items()}).items():
            track.key(name, start(name), Key(float(time), value, ease))
        return self

    def _target(self, what: Union[Node, str]) -> tuple[Any, Callable[[str], Any], Sequence[str]]:
        """How a thing that moves is filed, its value of a field now, and the fields it has."""
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

    def follow(self, shot: str, what: Union[Node, str], offset: VecLike = (0, 0, 0), lag: float = 0.0, dead: float = 0.0,
               ahead: float = 0.0) -> "Location":
        """Keeps a shot's camera on a node or a mark, at `offset` from it, wherever it goes. As an operator would, it can
        follow `lag` seconds late, let the target stray `dead` metres before turning, and look `ahead` seconds along its path."""
        self.followed[shot] = Follow(what, Vec3.of(offset), lag, dead, ahead)
        self.shots[shot] = self._followed(self.shots[shot], self)
        return self

    def _followed(self, shot: Shot, moment: "Location", time: float = 0.0) -> Shot:
        follow = self.followed[shot.name]
        if not follow.exact:
            return replace(shot, look_at=steady(self._path(follow.what), time, follow.lag, follow.dead, follow.ahead) + follow.offset)
        if isinstance(follow.what, str) and follow.what in moment.marks:
            return replace(shot, look_at=moment.marks[follow.what].at + follow.offset)
        found = next((new for old, new in zip(self.nodes, moment.nodes) if old is follow.what or old.name == follow.what), None)
        if found is None:
            raise MotionError(f"shot {shot.name!r} follows {follow.what!r}, and nothing here is called that")
        return replace(shot, look_at=Vec3.of(found.at) + follow.offset)

    def _path(self, what: Union[Node, str]) -> Callable[[float], Vec3]:
        """Where a mark or a node is at each time, from its keys alone, as at() would put it."""
        def keyed(key: Any, still: Vec3) -> Callable[[float], Vec3]:
            keys = self.motion[key].fields.get("at") if key in self.motion else None
            return (lambda time: Vec3.of(value_at(keys, time))) if keys else (lambda time: still)
        if isinstance(what, str) and what in self.marks:
            return keyed(("mark", what), self.marks[what].at)
        node = next((node for node in self.nodes if node is what or node.name == what), None)
        if node is None:
            raise MotionError(f"a shot follows {what!r}, and nothing here is called that")
        own = keyed(id(node), Vec3.of(node.at))
        if node.name not in self.marks:
            return own
        carried = keyed(("mark", node.name), self.marks[node.name].at)
        return lambda time: own(time) + carried(time) - self.marks[node.name].at

    def shake(self, shot: str, amount: float = 0.5, frequency: float = 1.0, start: float = 0.0, end: Optional[float] = None,
              decay: Optional[float] = None, drift: float = 0.0, seed: int = 0) -> "Location":
        """Shakes a shot's camera: held by hand, by default, or hit by a blow with `decay`; see camera.Shake. A shake is
        motion, so a location that moves no other way lasts until the shake is over."""
        if shot not in self.shots:
            raise MotionError(f"no shot {shot!r} to shake")
        shake = Shake(amount, frequency, start, end, decay, drift, seed)
        if shake.last is None and not self.duration(shot):
            raise MotionError(f"nothing in shot {shot!r} moves, so its shake needs an end or a decay")
        self.shaken.setdefault(shot, []).append(shake)
        if shake.last is not None and shake.last > self.duration(shot):
            self.move(shot, shake.last)
        return self

    def plant(self, figure: Union[Node, str], joint: str, start: float = 0.0, end: Optional[float] = None,
              keep: bool = True) -> "Location":
        """Keeps a figure's hand or foot where it is at `start` until `end`, or for good, while the rest of it moves: a foot
        stays down as the hips walk over it, and the knee bends to keep it there. With `keep` it stays turned as it was. A
        foot the hips leave out of reach follows them as far as the straight leg lets it. It is a key on the figure's
        `holds`, so each moment is solved from its own keys, and at `end` the joint goes back to where the pose puts it."""
        if end is not None and end <= start:
            raise MotionError(f"a plant ends after it starts, and {end} is not after {start}")
        found = self.figure(figure)
        key, _, allowed = self._target(found)
        if "holds" not in allowed:
            raise MotionError(f"{found.label} cannot hold a hand or a foot in place")
        index = next(place for place, node in enumerate(self.nodes) if node is found)
        hold = self.at(start).nodes[index].hold(joint, keep)
        track = self.motion.setdefault(key, Track())
        keys = track.fields.get("holds") or [Key(0.0, tuple(found.holds))]
        was = lambda time: next(old.value for old in reversed(keys) if old.time <= time)
        within = lambda time: start <= time and (end is None or time < end)
        cuts = sorted({old.time for old in keys} | {start} | (set() if end is None else {end}))
        track.fields["holds"] = [Key(time, tuple(other for other in was(time) if other.joint != hold.joint) + (hold,)
                                     if within(time) else was(time), "hold") for time in cuts]
        return self

    def onion(self, time: float, times: Sequence[float]) -> "Location":
        """A still to review a move in one picture: this location at `time`, with a ghost of each figure that moves at each
        of `times`, as an animator's onion skin shows the frames either side. A ghost is named "<figure>@<time>", has the
        "ghost" role for a look to aim at, and passes through everything."""
        still = self.at(time)
        moving = [index for index, node in enumerate(self.nodes)
                  if isinstance(node, Figure) and (id(node) in self.motion or ("mark", node.name) in self.motion)]
        if not moving:
            raise MotionError("no figure here moves, so there is nothing to show either side of a moment")
        ghosts = [self.at(when).nodes[index].ghosted(f"{self.nodes[index].label}@{when:g}")
                  for when in sorted(set(times) - {time}) for index in moving]
        still = copy.copy(still)
        still.nodes, still.motion, still.origin = [*still.nodes, *ghosts], {}, self
        return still

    def duration(self, shot: Optional[str] = None) -> float:
        """How long a shot lasts, in seconds: until the last thing in it stops. No moves, no time."""
        return max((track.end for key, track in self.motion.items()
                    if not (isinstance(key, tuple) and key[0] == "shot" and shot not in (None, key[1]))), default=0.0)

    def instants(self) -> list[float]:
        """When something reaches a key, and four times a second while a body moves: when to check a location that moves."""
        times = {0.0, *(time for track in self.motion.values() for time in track.times)}
        if any(isinstance(key, int) or key[0] == "mark" for key in self.motion):
            end = self.duration()
            times |= {step / 4 for step in range(int(end * 4) + 1)}
        return sorted(times)

    def at(self, time: float) -> "Location":
        """This location as it is at `time`, with nothing moving."""
        if not self.motion:
            return self
        moment = copy.copy(self)
        moment.motion, moment.followed, moment.sights, moment.framed, moment.origin = {}, {}, {}, {}, self
        marks = {name: replace(mark, **self.motion[("mark", name)].at(time)) if ("mark", name) in self.motion else mark
                 for name, mark in self.marks.items()}
        offset = lambda name: marks[name].at - self.marks[name].at if name in marks else Vec3()
        moment.marks = marks
        moment.nodes = [self._node_at(node, time, marks) for node in self.nodes]
        moment.paintings = [replace(layer, items=[item.carried(offset) for item in layer.items]) for layer in self.paintings]
        moment.shots = {name: self._shot_at(shot, time, moment) for name, shot in self.shots.items()}
        return moment

    def _node_at(self, node: Node, time: float, marks: Mapping[str, Mark]) -> Node:
        moved = node.posed(self.motion[id(node)].at(time)) if id(node) in self.motion else node
        if node.name in marks and marks[node.name] is not self.marks[node.name]:  # stand() names a figure after its mark
            before = self.marks[node.name]
            return replace(moved, at=Vec3.of(moved.at) + marks[node.name].at - before.at,
                           yaw=moved.yaw + marks[node.name].facing - before.facing)
        return moved

    def _shot_at(self, shot: Shot, time: float, moment: "Location") -> Shot:
        return shaken(self._taken_at(shot, time, moment), self.shaken.get(shot.name, ()), time)

    def _taken_at(self, shot: Shot, time: float, moment: "Location") -> Shot:
        """A shot at a time, before any shake."""
        keyed = self.motion.get(("shot", shot.name))
        shot = replace(shot, **keyed.at(time)) if keyed else shot
        if shot.name in self.sights:
            figure = next(new for old, new in zip(self.nodes, moment.nodes) if old is self.sights[shot.name])
            eye, look_at = figure.sight()
            return replace(shot, eye=eye, look_at=look_at)
        if shot.name in self.framed:
            framing, labels, lens = self.framed[shot.name]
            eye, look_at, chosen = self.registry.framings.get(framing)(*map(moment.figure, labels), lens=lens)
            return replace(shot, eye=eye, look_at=look_at, lens=chosen)
        return self._followed(shot, moment, time) if shot.name in self.followed else shot

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
        actor = Actor(performer, self.standing(mark), height, pose or {}, flip, shadow, mark)
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
        return [seat for node in self.nodes for seat in node.seating()]

    def settle(self, node: Node, keep: bool = False) -> Node:
        """Moves a node of this location until nothing passes through it, onto a seat if it sits. A body that cannot fit is
        taken back out of the location, unless `keep`, and CollisionError says what stopped it. What stands on its mark goes
        with it, and shots of it are taken again."""
        if not node.moves or not node.collides:
            return node
        start, spot = (node.at, node.yaw), Vec3.of(node.at)
        seat, knees = None, 0.0
        if node.sits:
            taken = [Vec3.of(other.at) for other in self.nodes if other.sits and other is not node]
            free = [seat for seat in self.seats() if (seat.at - spot).length <= self.contact.reach
                    and all((seat.at - other).length > 0.3 for other in taken)]
            if free:
                seat = min(free, key=lambda seat: (seat.at - spot).length)
                under, knees = node.sitting()  # a child climbs up to the seat, and perches on the edge of a deep one
                ahead = Transform.at(yaw=seat.facing).apply((0, 0, 1))
                slide = max(0.0, seat.depth - knees + 0.01)
                node.at = seat.at + Vec3(ahead.x * slide, max(0.0, seat.height - under), ahead.z * slide)
                node.yaw = seat.facing
        try:
            node.at = Vec3.of(node.at) + clear(node, self.nodes, self.contact)
        except CollisionError:
            node.at, node.yaw = start
            if not keep:
                self.nodes.remove(node)
            raise
        if seat and seat.back:
            self._lean(node, seat, knees)
        self._carry(node)
        self._reframe()
        return node

    def _lean(self, node: Node, seat: Seat, knees: float) -> None:
        """Slides a seated figure back onto the backrest, as far as its knees stay clear of the seat's front edge."""
        room = knees - seat.depth - 0.01
        turned = Transform.at(yaw=seat.facing).apply((0, 0, -1))
        limb = Body.of(node, self.contact).part(lambda path: path.rpartition("/")[2] in node.backing())
        others = self._set()
        if room <= 0 or limb is None:
            return
        travel, before = gap(limb, others, turned, room), node.at
        node.at = Vec3.of(node.at) + Vec3(turned.x * travel, turned.y * travel, turned.z * travel)
        if not fits(node, others, self.contact):
            node.at = before

    def settle_all(self) -> list[Node]:
        """Settles every body again, each from its mark if it has one: for when the set changed around them, or they came in
        by add() or a blueprint. One that no longer fits stays in and CollisionError says so, since a render would refuse it."""
        bodies = [node for node in self.nodes if node.moves]
        for node in bodies:
            if node.name in self.marks:
                node.at, node.yaw = self.marks[node.name].at, self.marks[node.name].facing
            self.settle(node, keep=True)
        return bodies

    def figures(self) -> list[Figure]:
        return [node for node in self.nodes if isinstance(node, Figure)]

    def figure(self, which: Union[Node, str]) -> Figure:
        """A figure of this location, or the one with this name."""
        found = which if isinstance(which, Figure) else next((node for node in self.figures() if node.label == which), None)
        if found is None:
            raise CatalogError(f"no figure {which!r}; this location has {', '.join(sorted(n.label for n in self.figures())) or 'none'}")
        return found

    def standing(self, mark: str) -> Vec3:
        """Where a body on a mark is: a settled figure may have moved off it, and a character stands with the figure."""
        figure = next((node for node in self.figures() if node.name == mark), None)
        return Vec3.of(figure.at) if figure else self.marks[mark].at

    def _carry(self, node: Node) -> None:
        """Characters on a figure's mark, moved to where the figure went."""
        for layer in self.paintings:
            for item in layer.items:
                for actor in getattr(item, "actors", ()):
                    if actor.mark == node.name:
                        actor.at = Vec3.of(node.at)

    def _reframe(self) -> None:
        """Takes again the shots that depend on where figures are."""
        for title, figure in self.sights.items():
            self.shots[title] = replace(self.shots[title], **dict(zip(("eye", "look_at"), figure.sight())))
        for title, (framing, labels, lens) in self.framed.items():
            eye, look_at, chosen = self.registry.framings.get(framing)(*map(self.figure, labels), lens=lens)
            self.shots[title] = Shot(title, eye, look_at, chosen)

    def seat_of(self, figure: Union[Node, str]) -> Optional[Seat]:
        """The seat a figure is on, if it sits on one."""
        found = self.figure(figure)
        at = Vec3.of(found.at)
        near = [seat for seat in self.seats() if math.hypot(seat.at.x - at.x, seat.at.z - at.z) <= SEATED]
        return min(near, key=lambda seat: (seat.at - at).length) if found.sits and near else None

    def _set(self) -> list[Body]:
        """Everything that is not a moving body."""
        return [body for body in (Body.of(other, self.contact) for other in self.nodes if other.collides and not other.moves) if body]

    def clashes(self, bodies_only: bool = False) -> list[Clash]:
        """What is passing through what, by the rules in collision.py, the first time it happens if this location moves."""
        for time in self.instants():
            found = list(clashes(self.at(time).nodes, bodies_only, self.contact))
            if found:
                return [replace(clash, time=time) for clash in found]
        return []

    def faults(self, figure: Union[Node, str]) -> list[Clash]:
        """Each limb of a figure that passes through the set or lies inside it, solid or not, where a clash names the deepest."""
        body = Body.of(self.figure(figure), self.contact)
        return [clash for limb in body.limbs() for clash in limb_clashes(limb, self._set(), self.contact)]

    def gap(self, figure: Union[Node, str], joint: str, way: VecLike, limit: float = GAP) -> float:
        """How far one limb of a figure moves along `way`, a unit direction, before it meets the set, in metres. Up to `limit`,
        so `limit` itself means nothing is there."""
        found = self.figure(figure)
        return gap(Body.of(found, self.contact).part(lambda path: path.rpartition("/")[2] == joint), self._set(), Vec3.of(way), limit)

    def _point(self, target: Union[VecLike, str, Node]) -> Vec3:
        """A place to look: a point, the eyes of a figure, or above a mark."""
        if isinstance(target, Figure) or (isinstance(target, str) and target in {node.label for node in self.figures()}):
            return self.figure(target).sight()[0]
        if isinstance(target, str):
            if target not in self.marks:
                raise CatalogError(f"no figure or mark {target!r}")
            return self.marks[target].at + Vec3(0, SIGHT, 0)
        return Vec3.of(target)

    def sees(self, figure: Union[Node, str], target: Union[VecLike, str, Node]) -> Optional[str]:
        """What stands between a figure's eyes and a point, a mark or another figure; None when nothing does."""
        found, point = self.figure(figure), self._point(target)
        bodies = [body for body in (Body.of(node, self.contact) for node in self.nodes
                                    if node.collides and node is not found and node is not target and node.label != target) if body]
        return blocked(found.sight()[0], point, bodies)

    def look(self, figure: Union[Node, str], target: Union[VecLike, str, Node]) -> Figure:
        """Turns a figure's head and eyes to a point, a mark or another figure, and takes again the shots through its eyes."""
        found = self.figure(figure).look_at(self._point(target))
        self._reframe()
        return found

    def repose(self, figure: Union[Node, str], pose: Any = None, adjust: Optional[Mapping[str, float]] = None, steps: int = 8) -> float:
        """Moves a figure toward a pose in `steps`, stopping where the set stops it, and gives the share of the way it got: 1
        when it arrived. A figure that is not solid goes straight there."""
        found = self.figure(figure)
        start, sits = dict(found.values()), found.sits
        goal, ends_sitting = found.aiming(pose, adjust)
        others = [body for body in (Body.of(node, self.contact) for node in self.nodes if node.collides and node is not found) if body]
        done = 0.0
        for count in range(1, steps + 1):
            share, held = count / steps, dict(found.values())
            found.take({key: start.get(key, 0.0) + (goal.get(key, 0.0) - start.get(key, 0.0)) * share for key in sorted({*start, *goal})},
                       ends_sitting if share == 1 else sits)
            if found.collides and not fits(found, others, self.contact):
                found.take(held, sits)
                break
            done = share
        self._reframe()
        return done

    def reach(self, figure: Union[Node, str], joint: str, target: Union[VecLike, str, Node], tolerance: float = 0.01,
              pole: Union[VecLike, str, Node, None] = None, keep: bool = False) -> float:
        """Reaches a figure's hand or foot to a point, a mark or another figure, and gives how far off it stopped. The elbow
        or knee points toward `pole`, and with `keep` the hand or foot stays turned as it was. A limb that would pass through
        the set is refused with CollisionError, and the figure stays as it was."""
        found = self.figure(figure)
        before, sits = dict(found.values()), found.sits
        missed = found.reach_to(joint, self._point(target), tolerance, None if pole is None else self._point(pole), keep)
        others = [body for body in (Body.of(node, self.contact) for node in self.nodes if node.collides and node is not found) if body]
        if found.collides and not fits(found, others, self.contact):
            found.take(before, sits)
            raise CollisionError(f"{found.label}'s {joint} cannot get to {self._point(target)} without passing through the set")
        self._reframe()
        return missed

    def pov(self, figure: Union[Node, str], name: Optional[str] = None, lens: float = 24.0) -> Shot:
        """A shot from a figure's eyes, looking where its head and eyes turn. It stays with the figure if the figure moves."""
        found = self.figure(figure)
        title = name or f"{found.label}-pov"
        self.shot(title, *found.sight(), lens)
        self.sights[title] = found
        return self.shots[title]

    def frame(self, framing: str, *figures: Union[Node, str], name: Optional[str] = None, lens: Optional[float] = None) -> Shot:
        """A shot composed around figures, by a name in registry.framings: "stock.close-up" takes one, and "stock.two-shot" and
        "stock.over-the-shoulder" take two. It stays composed if they move."""
        people = tuple(self.figure(figure) for figure in figures)
        title = name or "-".join((*(figure.label for figure in people), framing.rpartition(".")[2]))
        eye, look_at, chosen = self.registry.framings.get(framing)(*people, lens=lens)
        self.shots[title] = Shot(title, eye, look_at, chosen)
        self.framed[title] = framing, tuple(figure.label for figure in people), lens
        return self.shots[title]

    def blocking(self, shot: str, width: int = 1920, height: int = 1080) -> list[dict]:
        """Every mark as plain data for a 2D rig to read: where a body on it is, which way it faces, how it should be framed,
        and where that falls in this shot. See framing.py."""
        from srlocations.framing import blocking  # built on this module
        return blocking(self, shot, width, height)

    def report(self) -> "Report":
        """What a set review wants to know about each figure. See review.py."""
        from srlocations.review import report  # built on this module
        return report(self)

    def placed(self) -> list[Placed]:
        return [leaf for node in self.nodes for leaf in node.walk()]

    def solids(self) -> list[Placed]:
        return [leaf for leaf in self.placed() if isinstance(leaf.item, Solid)]

    def lights(self) -> list[Placed]:
        return [leaf for leaf in self.placed() if isinstance(leaf.item, Light)]

    def validate(self) -> list[Issue]:
        """What is wrong here, at each moment something reaches a key. A fault is told once, at the first moment it appears."""
        issues: dict[Issue, Issue] = {}
        for time in self.instants():
            moment = self.at(time)
            for issue in (issue for check in self.registry.checks for issue in check.run(moment)):
                issues.setdefault(issue, replace(issue, message=f"{issue.message}, at {time:g} s") if time else issue)
        return list(issues.values())
