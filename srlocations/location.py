"""A Location: the graph plus what a production needs from it, marks to stand on and shots to take."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Iterable, Optional, Sequence, Union

from srlocations.geometry import Vec3, VecLike
from srlocations.nodes import Light, Node, Placed, Solid
from srlocations.paint import PaintLayer
from srlocations.registry import Registry


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
              looks: Sequence[str] = ()) -> PaintLayer:
        """A new layer over the picture, on top of those before it."""
        self.paintings.append(PaintLayer(name, blend, opacity, shots, looks=looks))
        return self.paintings[-1]

    def placed(self) -> list[Placed]:
        return [leaf for node in self.nodes for leaf in node.walk()]

    def solids(self) -> list[Placed]:
        return [leaf for leaf in self.placed() if isinstance(leaf.item, Solid)]

    def lights(self) -> list[Placed]:
        return [leaf for leaf in self.placed() if isinstance(leaf.item, Light)]

    def validate(self) -> list[Issue]:
        return [issue for check in self.registry.checks for issue in check.run(self)]
