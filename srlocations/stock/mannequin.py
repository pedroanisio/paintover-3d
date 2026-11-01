"""A jointed mannequin, to review a set with a body in it: sight lines, sitting height, reach, how big a room reads.

The skeleton is the humanoid one animation packages share: the 55 bones of Unity's Humanoid. `Joint.known_as` gives each
one's name in Unity and its nearest bone in Mixamo, Maya HumanIK and Unreal's mannequin, whose bodies have no eyes or jaw.
Its controls are Unity's 95 muscles, each with `Dof.muscle` its name there, plus the six channels of the root, on the
hips: 101 parameters, all in `PARAMETERS`.

A parameter is written "joint.control", in degrees, or metres for the hips' `right`, `up` and `forward`:

    Mannequin(pose="sit", adjust={"head.turn_left_right": 30, "right_lower_arm.stretch": -100})

A control's name reads from its negative end to its positive end, so `front_back` is forward below 0 and back above it,
and an angle means the same motion on either side of the body. Zero everywhere is the T-stance that software
characterises in: standing, arms out, palms down, fingers straight, every joint turned as the body is. That rest is not
Unity's muscle zero, and Unity publishes no table of its default ranges, so the ranges here are this SDK's own working
ranges measured from the T-stance. They are a guard against a broken pose, not anatomy. `limits=False` lifts them.

Rotations apply in the order a joint lists its controls, the first outermost, so a twist is always about the bone. Bones
scale with `height`, from Drillis and Contini's proportions; a hip offset is in plain metres. The figure faces +z at yaw
0, as a mark's `facing` and a shot do, so it faces the other way from a stock chair: sit it at the chair's yaw plus 180.

`kind` picks a body from KINDS. Each is a set of multiples of the adult man in JOINTS, so a child has a bigger head and
shorter legs for its height, and every pose works on all of them. `seed` varies a body within its kind, always the same way
for the same seed, and without a `kind` it picks one too. These are review proportions, not a growth chart.
"""
from __future__ import annotations

import difflib
import random
from dataclasses import dataclass, field, replace
from typing import Iterator, Mapping, Optional, Sequence, Union

from srlocations.collision import Egg, Hull
from srlocations.geometry import Transform, Vec3, rotation
from srlocations.nodes import Node, Prefab
from srlocations.surfaces import Surface

MOVES = {"right": Vec3(1, 0, 0), "up": Vec3(0, 1, 0), "forward": Vec3(0, 0, 1)}
SIDES = {-1: ("left", "Left"), 1: ("right", "Right")}
FINGERS = ("thumb", "index", "middle", "ring", "little")
PHALANGES = ("proximal", "intermediate", "distal")
EYE_CLEARANCE = 0.02  # a shot from the eyes starts this far ahead of them, as a share of the height, or it is inside the head
Triple = tuple[float, float, float]


class PoseError(ValueError):
    pass


@dataclass(frozen=True)
class Dof:
    """One control. `turn` is what it does at the joint, for the right side of the body: yaw, pitch and roll as anywhere in
    the SDK, or a key of MOVES. `sign` says which way. `muscle` is its name in Unity, with {side} for a sided joint."""
    name: str
    turn: str
    low: float
    high: float
    sign: int = 1
    muscle: str = ""


@dataclass(frozen=True)
class Bulk:
    """The solid on a joint: an egg at `centre` in the joint's frame. Both are fractions of the figure's height."""
    centre: Triple
    radii: Triple


@dataclass(frozen=True)
class Joint:
    """One bone. `offset` is from its parent at rest, in fractions of the height. `rest` is a yaw, pitch and roll it keeps
    at zero, which only a thumb needs. `ball` is the radius of the sphere drawn at the joint. `side` is -1 on the left."""
    name: str
    parent: Optional[str]
    offset: Triple
    dofs: tuple[Dof, ...] = ()
    bulk: Optional[Bulk] = None
    ball: float = 0.0
    side: int = 0
    rest: Triple = (0.0, 0.0, 0.0)
    known_as: Mapping[str, str] = field(default_factory=dict)
    region: str = "torso"  # what a Build lengthens it with

    def turned(self, kind: str, angle: float) -> float:
        """An angle given for the right side as it is on this joint: a mirror keeps pitch and reverses yaw and roll."""
        return -angle if self.side < 0 and kind != "pitch" else angle


@dataclass(frozen=True)
class Build:
    """A body, in multiples of the adult man `JOINTS` describes. `height` is in metres. The lengths are each part's share of
    the height, the widths are across the body, and `girth` is how thick the limbs and torso are."""
    height: float = 1.75
    head: float = 1.0
    torso: float = 1.0
    legs: float = 1.0
    arms: float = 1.0
    shoulders: float = 1.0
    hips: float = 1.0
    waist: float = 1.0
    girth: float = 1.0

    @property
    def fit(self) -> float:
        """What keeps the parts adding up to the height when their shares change."""
        return STACK[0] / (self.legs * STACK[1] + self.torso * STACK[2] + self.head * STACK[3])

    def varied(self, rng: random.Random) -> "Build":
        """Another body of this kind."""
        return replace(self, height=self.height * rng.uniform(0.93, 1.07), legs=self.legs * rng.uniform(0.97, 1.03),
                       arms=self.arms * rng.uniform(0.97, 1.03), shoulders=self.shoulders * rng.uniform(0.93, 1.07),
                       hips=self.hips * rng.uniform(0.93, 1.07), waist=self.waist * rng.uniform(0.88, 1.2),
                       girth=self.girth * rng.uniform(0.85, 1.22))


STACK = (1.0, 0.55, 0.318, 0.132)  # the man's height, then what his legs, torso and head add to it
KINDS = {
    "man": Build(),
    "woman": Build(1.63, head=1.03, legs=1.01, arms=0.97, shoulders=0.87, hips=1.08, waist=0.86, girth=0.9),
    "teen": Build(1.55, head=1.08, legs=1.0, arms=0.98, shoulders=0.88, hips=0.92, waist=0.92, girth=0.84),
    "child": Build(1.2, head=1.3, legs=0.93, arms=0.95, shoulders=0.8, hips=0.84, waist=1.0, girth=0.86),
    "toddler": Build(0.85, head=1.85, legs=0.72, torso=1.05, arms=0.86, shoulders=0.82, hips=0.86, waist=1.12, girth=1.05),
}


def _torso(label: str, bend: float, side: float, twist: float) -> tuple[Dof, ...]:
    return (Dof("front_back", "pitch", -bend, bend, muscle=f"{label} Front-Back"),
            Dof("left_right", "roll", -side, side, -1, f"{label} Left-Right"),
            Dof("twist_left_right", "yaw", -twist, twist, muscle=f"{label} Twist Left-Right"))


def _head(label: str) -> tuple[Dof, ...]:
    return (Dof("nod_down_up", "pitch", -40, 40, muscle=f"{label} Nod Down-Up"),
            Dof("tilt_left_right", "roll", -40, 40, -1, f"{label} Tilt Left-Right"),
            Dof("turn_left_right", "yaw", -40, 40, muscle=f"{label} Turn Left-Right"))


HIPS = (Dof("right", "right", -5, 5), Dof("up", "up", -2, 2), Dof("forward", "forward", -5, 5),
        Dof("front_back", "pitch", -180, 180), Dof("left_right", "roll", -180, 180, -1),
        Dof("twist_left_right", "yaw", -180, 180))
MIDDLE = (
    Joint("hips", None, (0, 0.55, 0), HIPS, Bulk((0, -0.006, 0), (0.092, 0.05, 0.07))),
    Joint("spine", "hips", (0, 0.04, 0), _torso("Spine", 40, 40, 40), Bulk((0, 0.04, 0), (0.078, 0.062, 0.058)), 0.03),
    Joint("chest", "spine", (0, 0.085, 0), _torso("Chest", 40, 40, 40), Bulk((0, 0.038, 0), (0.09, 0.06, 0.066))),
    Joint("upper_chest", "chest", (0, 0.075, 0), _torso("UpperChest", 30, 30, 30),
          Bulk((0, 0.03, 0), (0.122, 0.078, 0.076))),
    Joint("neck", "upper_chest", (0, 0.118, 0), _head("Neck"), Bulk((0, 0.018, 0), (0.027, 0.036, 0.027))),
    Joint("head", "neck", (0, 0.03, 0), _head("Head"), Bulk((0, 0.042, 0.006), (0.05, 0.06, 0.058)), 0.024),
    Joint("left_eye", "head", (-0.017, 0.046, 0.05),
          (Dof("down_up", "pitch", -10, 15, muscle="Left Eye Down-Up"), Dof("in_out", "yaw", -20, 20, muscle="Left Eye In-Out")),
          Bulk((0, 0, 0.004), (0.008, 0.008, 0.008)), side=-1),
    Joint("right_eye", "head", (0.017, 0.046, 0.05),
          (Dof("down_up", "pitch", -10, 15, muscle="Right Eye Down-Up"),
           Dof("in_out", "yaw", -20, 20, muscle="Right Eye In-Out")), Bulk((0, 0, 0.004), (0.008, 0.008, 0.008)), side=1),
    Joint("jaw", "head", (0, 0.016, 0.012),
          (Dof("close", "pitch", -30, 5, muscle="Jaw Close"), Dof("left_right", "yaw", -10, 10, muscle="Jaw Left-Right")),
          Bulk((0, -0.008, 0.016), (0.03, 0.017, 0.03))),
)
LEG = (
    ("upper_leg", "hips", (0.05, -0.02, 0),
     (Dof("front_back", "pitch", -125, 30, -1, "{side} Upper Leg Front-Back"),
      Dof("in_out", "roll", -30, 60, muscle="{side} Upper Leg In-Out"),
      Dof("twist_in_out", "yaw", -45, 45, muscle="{side} Upper Leg Twist In-Out")),
     Bulk((0, -0.122, 0), (0.05, 0.135, 0.052)), 0.03),
    ("lower_leg", "upper_leg", (0, -0.245, 0),
     (Dof("stretch", "pitch", -150, 5, muscle="{side} Lower Leg Stretch"),
      Dof("twist_in_out", "yaw", -30, 30, muscle="{side} Lower Leg Twist In-Out")),
     Bulk((0, -0.122, -0.006), (0.04, 0.132, 0.045)), 0.034),
    ("foot", "lower_leg", (0, -0.246, 0),
     (Dof("up_down", "pitch", -30, 50, -1, "{side} Foot Up-Down"),
      Dof("twist_in_out", "yaw", -30, 30, muscle="{side} Foot Twist In-Out")),
     Bulk((0, -0.014, 0.03), (0.034, 0.024, 0.074)), 0.024),
    ("toes", "foot", (0, -0.024, 0.098), (Dof("up_down", "pitch", -60, 40, -1, "{side} Toes Up-Down"),),
     Bulk((0, 0, 0.018), (0.033, 0.013, 0.03))),
)
ARM = (
    ("shoulder", "upper_chest", (0.02, 0.055, 0),
     (Dof("down_up", "roll", -15, 30, muscle="{side} Shoulder Down-Up"),
      Dof("front_back", "yaw", -15, 15, muscle="{side} Shoulder Front-Back")),
     Bulk((0.055, 0, 0), (0.06, 0.02, 0.03))),
    ("upper_arm", "shoulder", (0.11, 0.013, 0),
     (Dof("down_up", "roll", -100, 90, muscle="{side} Arm Down-Up"),
      Dof("front_back", "yaw", -135, 100, muscle="{side} Arm Front-Back"),
      Dof("twist_in_out", "pitch", -90, 90, muscle="{side} Arm Twist In-Out")),
     Bulk((0.093, 0, 0), (0.105, 0.035, 0.037)), 0.034),
    ("lower_arm", "upper_arm", (0.186, 0, 0),
     (Dof("stretch", "yaw", -150, 5, muscle="{side} Forearm Stretch"),
      Dof("twist_in_out", "pitch", -90, 90, muscle="{side} Forearm Twist In-Out")),
     Bulk((0.073, 0, 0), (0.082, 0.028, 0.03)), 0.027),
    ("hand", "lower_arm", (0.146, 0, 0),
     (Dof("down_up", "roll", -80, 80, muscle="{side} Hand Down-Up"), Dof("in_out", "yaw", -40, 40, muscle="{side} Hand In-Out")),
     Bulk((0.03, 0, 0), (0.038, 0.012, 0.029)), 0.016),
)
FINGER_ROOTS = {"thumb": (0.012, -0.004, 0.021), "index": (0.058, 0, 0.019), "middle": (0.06, 0, 0.0065),
                "ring": (0.058, 0, -0.0065), "little": (0.054, 0, -0.018)}
FINGER_LENGTHS = {"thumb": (0.024, 0.02, 0.016), "index": (0.022, 0.014, 0.011), "middle": (0.024, 0.016, 0.012),
                  "ring": (0.022, 0.015, 0.012), "little": (0.018, 0.011, 0.01)}
FINGER_SPREAD = {"thumb": (25, -1), "index": (20, -1), "middle": (7.5, -1), "ring": (7.5, 1), "little": (20, 1)}
CURLS = {"thumb": (-50, -50, -80), "index": (-90, -100, -80), "middle": (-90, -100, -80), "ring": (-90, -100, -80),
         "little": (-90, -100, -80)}
THUMB_REST = (-42.0, 0.0, -12.0)


def _finger(name: str) -> Iterator[tuple]:
    """The three bones of a finger, each with its stretch; the spread is at the root."""
    label, parent, offset = name.title(), "hand", FINGER_ROOTS[name]
    for number, (bone, length, curl) in enumerate(zip(PHALANGES, FINGER_LENGTHS[name], CURLS[name]), 1):
        controls = [Dof("stretched", "roll", curl, 20 if number == 1 else 0, muscle=f"{{side}} {label} {number} Stretched")]
        if number == 1:
            reach, way = FINGER_SPREAD[name]
            controls.append(Dof("spread", "yaw", -reach, reach, way, f"{{side}} {label} Spread"))
        thick = 0.0075 if name == "thumb" else 0.0062
        yield (f"{name}_{bone}", parent, offset, tuple(controls),
               Bulk((length / 2, 0, 0), (length * 0.72, thick, thick)), 0.0,
               THUMB_REST if name == "thumb" and number == 1 else (0.0, 0.0, 0.0))
        parent, offset = f"{name}_{bone}", (length, 0, 0)


def _known_as(bare: str, side: int) -> dict[str, str]:
    """What the packages call a bone. Mixamo and HumanIK differ only by a prefix. Eyes and the jaw are not in their bodies."""
    upper = SIDES[side][1] if side else ""
    tail, end = ("l" if side < 0 else "r"), bare.partition("_")
    named = {"unity": "".join(word.title() for word in f"{upper} {bare}".replace("_", " ").split())}
    fixed = {"hips": ("Hips", "pelvis"), "spine": ("Spine", "spine_01"), "chest": ("Spine1", "spine_03"),
             "upper_chest": ("Spine2", "spine_05"), "neck": ("Neck", "neck_01"), "head": ("Head", "head")}
    limbs = {"shoulder": ("Shoulder", "clavicle"), "upper_arm": ("Arm", "upperarm"), "lower_arm": ("ForeArm", "lowerarm"),
             "hand": ("Hand", "hand"), "upper_leg": ("UpLeg", "thigh"), "lower_leg": ("Leg", "calf"),
             "foot": ("Foot", "foot"), "toes": ("ToeBase", "ball")}
    if bare in fixed:
        human, unreal = fixed[bare]
    elif bare in limbs:
        human, unreal = upper + limbs[bare][0], f"{limbs[bare][1]}_{tail}"
    elif end[0] in FINGERS:
        number = PHALANGES.index(end[2]) + 1
        human = f"{upper}Hand{end[0].title()}{number}"
        unreal = f"{'pinky' if end[0] == 'little' else end[0]}_0{number}_{tail}"
    else:
        return named
    return {**named, "mixamo": f"mixamorig:{human}", "humanik": human, "ue5": unreal}


def _sided(specs: Sequence[tuple], side: int, region: str) -> list[Joint]:
    """Joints described on the right, on one side of the body."""
    made = []
    for bare, parent, offset, dofs, bulk, *extra in specs:
        sided = f"{SIDES[side][0]}_{bare}"
        ball, rest = extra[0] if extra else 0.0, extra[1] if len(extra) > 1 else (0.0, 0.0, 0.0)
        mirrored = [(a * side, b, c) for a, b, c in (offset, bulk.centre)]
        made.append(Joint(sided, parent if parent in ("hips", "upper_chest") else f"{SIDES[side][0]}_{parent}", mirrored[0],
                          tuple(Dof(d.name, d.turn, d.low, d.high, d.sign, d.muscle.format(side=SIDES[side][1])) for d in dofs),
                          Bulk(mirrored[1], bulk.radii), ball, side, rest, known_as=_known_as(bare, side), region=region))
    return made


HAND = tuple(spec for name in FINGERS for spec in _finger(name))
JOINTS: tuple[Joint, ...] = (
    *(Joint(j.name, j.parent, j.offset, j.dofs, j.bulk, j.ball, j.side, known_as=_known_as(j.name, 0),
            region="head" if j.name in ("head", "left_eye", "right_eye", "jaw") else "torso") for j in MIDDLE),
    *_sided(LEG, -1, "leg"), *_sided(LEG, 1, "leg"), *_sided(ARM, -1, "arm"), *_sided(ARM, 1, "arm"),
    *_sided(HAND, -1, "arm"), *_sided(HAND, 1, "arm"))
BY_NAME = {joint.name: joint for joint in JOINTS}
PARAMETERS: dict[str, Dof] = {f"{joint.name}.{dof.name}": dof for joint in JOINTS for dof in joint.dofs}
ALIASES = {other: joint.name for joint in JOINTS for other in joint.known_as.values()}


def both(controls: Mapping[str, float]) -> dict[str, float]:
    """The same values on the left and the right, with keys that name no side: both({"upper_arm.down_up": -70})."""
    return {f"{side}_{key}": value for key, value in controls.items() for side in ("left", "right")}


def curled(amount: float) -> dict[str, float]:
    """All ten fingers closed by a share of their range, 0 to 1."""
    return {f"{side}_{name}_{bone}.stretched": amount * curl for side in ("left", "right") for name in FINGERS
            for bone, curl in zip(PHALANGES, CURLS[name])}


RELAXED = {**both({"upper_arm.down_up": -80, "upper_arm.twist_in_out": -10, "lower_arm.stretch": -10}), **curled(0.2)}
POSES: dict[str, dict[str, float]] = {
    "t": {},
    "a": both({"upper_arm.down_up": -45}),
    "stand": RELAXED,
    "sit": {**curled(0.3), **both({"upper_leg.front_back": -88, "lower_leg.stretch": -88, "foot.up_down": 12,
                                   "upper_arm.down_up": -100, "upper_arm.front_back": 10, "lower_arm.stretch": -80,
                                   "lower_arm.twist_in_out": -20, "hand.down_up": -20})},
    "walk": {**curled(0.2), "hips.twist_left_right": 5, "spine.twist_left_right": -5, "chest.twist_left_right": -5,
             "right_upper_leg.front_back": -24, "right_lower_leg.stretch": -8, "right_foot.up_down": -14,
             "left_upper_leg.front_back": 16, "left_lower_leg.stretch": -24, "left_foot.up_down": 16,
             "left_toes.up_down": -28, **both({"upper_arm.down_up": -80}), "left_upper_arm.front_back": -22,
             "left_lower_arm.stretch": -32, "right_upper_arm.front_back": 22, "right_lower_arm.stretch": -14},
    "point": {**RELAXED, **curled(0.15), "head.turn_left_right": 10, "right_upper_arm.down_up": 2,
              "right_upper_arm.front_back": -82, "right_upper_arm.twist_in_out": 0, "right_lower_arm.stretch": -5,
              "right_index_proximal.stretched": 0, "right_index_intermediate.stretched": 0,
              "right_index_distal.stretched": 0, **{f"right_{name}_{bone}.stretched": curl for name in FINGERS[2:]
                                                    for bone, curl in zip(PHALANGES, CURLS[name])}},
    "drive": {**curled(0.6), "hips.front_back": 18, "spine.front_back": -6, "neck.nod_down_up": -6, "head.nod_down_up": -6,
              **both({"upper_leg.front_back": -68, "lower_leg.stretch": -48, "foot.up_down": -10, "upper_arm.down_up": -95,
                      "upper_arm.front_back": -40, "lower_arm.stretch": -20, "lower_arm.twist_in_out": 40})},
}


def joint_named(name: str) -> Joint:
    """A joint by this SDK's name or by what Unity, Mixamo, HumanIK or Unreal call the bone."""
    joint = BY_NAME.get(ALIASES.get(name, name))
    if joint is None:
        near = difflib.get_close_matches(name, [*BY_NAME, *ALIASES], n=3)
        raise PoseError(f"no joint {name!r}" + (f"; did you mean {', '.join(near)}?" if near else ""))
    return joint


def _number(value: float) -> str:
    return f"{value:.5f}".rstrip("0").rstrip(".")


def _egg(radii: Triple) -> dict[str, str]:
    x, y, z = (_number(radius) for radius in radii)
    return {"x": f"{x} * cos(u) * cos(v)", "y": f"{y} * sin(v)", "z": f"{z} * sin(u) * cos(v)"}


@dataclass
class Limb(Surface):
    """A part of a figure. A stand-in does not take up a mark or block a camera, so checks see through it."""
    u: Sequence[float] = (0, 360)
    v: Sequence[float] = (-90, 90)
    samples: Sequence[int] = (20, 12)
    closed: Sequence[bool] = (True, False)
    looks: Sequence[str] = ()
    radii: Triple = (0.0, 0.0, 0.0)
    hollow = True

    def drawn_in(self, look: str) -> bool:
        return not self.looks or look in self.looks

    def hulls(self, world: Transform) -> list[Hull]:
        return [Egg(world, self.radii)]


@dataclass
class Mannequin(Prefab):
    """A figure in a pose: the name of one in POSES, or parameters. `adjust` changes parameters on top of it. Its origin is
    on the floor under the hips: with `grounded` its lowest part rests there, whatever the pose, and without it the hips
    stay at their height above the origin, for a figure on a stool or in the air. `looks` limits it to some, as paint.
    `kind` is a body from KINDS and `seed` varies it, or picks one too; `height` overrides what they give."""
    pose: Union[str, Mapping[str, float]] = "stand"
    adjust: Mapping[str, float] = field(default_factory=dict)
    height: Optional[float] = None
    kind: Optional[str] = None
    seed: Optional[int] = None
    grounded: bool = True
    limits: bool = True
    solid: bool = True  # False lets it pass through a set, on purpose; see collision.py
    looks: Sequence[str] = ()
    body: str = "stock.mannequin.body"
    joint: str = "stock.mannequin.joint"
    left: str = "stock.mannequin.left"
    right: str = "stock.mannequin.right"
    moves = True

    @property
    def build_of(self) -> Build:
        """The body this figure has."""
        rng = random.Random(self.seed)
        kind = self.kind if self.kind or self.seed is None else rng.choice(list(KINDS))
        if kind is not None and kind not in KINDS:
            near = difflib.get_close_matches(kind, KINDS, n=3)
            raise PoseError(f"no kind {kind!r}; " + (f"did you mean {', '.join(near)}?" if near else f"there are {', '.join(KINDS)}"))
        body = KINDS[kind or "man"]
        return body if self.seed is None else body.varied(rng)

    @property
    def collides(self) -> bool:
        return self.solid

    @property
    def sits(self) -> bool:
        return self.pose == "sit"

    def sight(self) -> tuple[Vec3, Vec3]:
        """Where it sees from in the location, just clear of its eyes, and a point it is looking at."""
        left, right = (self.transform.then(self.frames()[f"{side}_eye"]) for side in ("left", "right"))
        ahead = left.apply((0, 0, 1)) - left.position + right.apply((0, 0, 1)) - right.position
        way = Vec3(*(part / ahead.length for part in ahead))
        middle, clear = (left.position + right.position), self.height * self.build_of.head * EYE_CLEARANCE
        eye = Vec3(middle.x / 2 + way.x * clear, middle.y / 2 + way.y * clear, middle.z / 2 + way.z * clear)
        return eye, eye + way

    def __post_init__(self) -> None:
        self.height = self.build_of.height if self.height is None else self.height
        if self.height <= 0:
            raise PoseError(f"a figure's height is above 0, not {self.height}")
        self.values()

    def sitting(self) -> tuple[float, float]:
        parts = self._parts(self.frames())
        return (min(part.bounds(part.transform)[0].y for part in parts if part.name == "hips" or part.name.endswith("_upper_leg")),
                min(part.bounds(part.transform)[0].z for part in parts if part.name.endswith("_lower_leg")))

    def _offset(self, joint: Joint, unit: float) -> Vec3:
        """Where a joint is on its parent, for this body."""
        body, (x, y, z) = self.build_of, joint.offset
        if joint.name == "hips":
            y *= body.legs
        elif joint.name.endswith("upper_leg"):
            x *= body.hips
        elif joint.name.endswith(("shoulder", "upper_arm")):
            x, y = x * body.shoulders, y * body.torso
        else:
            along = {"leg": body.legs, "arm": body.arms, "head": body.head, "torso": body.torso}[joint.region]
            x, y, z = x * along, y * along, z * along
        return Vec3(x * unit, y * unit, z * unit)

    def _bulk(self, joint: Joint) -> tuple[Triple, Triple]:
        """The solid on a joint for this body, centre and radii as shares of the height: long along the bone, thick across it."""
        body, centre, radii = self.build_of, list(joint.bulk.centre), list(joint.bulk.radii)
        if joint.region == "head":
            return tuple(c * body.head for c in centre), tuple(r * body.head for r in radii)
        axis = 2 if joint.name.endswith(("foot", "toes")) else 0 if joint.region == "arm" else 1
        length = {"leg": body.legs, "arm": body.arms, "torso": body.torso}[joint.region]
        for index in range(3):
            centre[index] *= length if index == axis else 1
            radii[index] *= length if index == axis else body.girth
        wide = {"hips": body.hips, "spine": body.waist, "upper_chest": body.shoulders}.get(joint.name, 1.0)
        if joint.name.endswith("shoulder"):
            centre[0], wide = centre[0] * body.shoulders, body.shoulders
        radii[0] *= wide
        return tuple(centre), tuple(radii)

    def values(self) -> dict[str, float]:
        """Every parameter this pose sets, by its full name, checked."""
        if isinstance(self.pose, str) and self.pose not in POSES:
            near = difflib.get_close_matches(self.pose, POSES, n=3)
            raise PoseError(f"no pose {self.pose!r}; " + (f"did you mean {', '.join(near)}?" if near
                                                          else f"there are {', '.join(POSES)}"))
        given = {**(POSES[self.pose] if isinstance(self.pose, str) else self.pose), **self.adjust}
        checked: dict[str, float] = {}
        for key, value in given.items():
            joint, _, control = key.rpartition(".")
            name = f"{joint_named(joint).name}.{control}" if joint else control
            if name not in PARAMETERS:
                near = difflib.get_close_matches(name, PARAMETERS, n=3)
                raise PoseError(f"no parameter {key!r}" + (f"; did you mean {', '.join(near)}?" if near else ""))
            dof = PARAMETERS[name]
            if self.limits and not dof.low <= value <= dof.high:
                raise PoseError(f"{name} is {value}, outside {dof.low} to {dof.high}; limits=False lifts this")
            checked[name] = float(value)
        return checked

    def _solved(self) -> dict[str, Transform]:
        """Each joint in the figure's frame, before it is set on the floor."""
        values, frames, unit = self.values(), {}, self.height * self.build_of.fit
        for joint in JOINTS:
            yaw, pitch, roll = joint.rest
            place = self._offset(joint, unit)
            local = Transform(place, rotation(joint.turned("yaw", yaw), pitch, joint.turned("roll", roll)))
            for dof in joint.dofs:
                amount = values.get(f"{joint.name}.{dof.name}", 0.0) * dof.sign
                if dof.turn in MOVES:
                    way = MOVES[dof.turn]
                    local = Transform(local.position + Vec3(way.x * amount, way.y * amount, way.z * amount), local.basis)
                else:
                    local = local.then(Transform.at(**{dof.turn: joint.turned(dof.turn, amount)}))
            frames[joint.name] = frames[joint.parent].then(local) if joint.parent else local
        return frames

    def _parts(self, frames: Mapping[str, Transform]) -> list[Limb]:
        parts, h = [], self.height * self.build_of.fit
        common = {"casts_shadow": True, "looks": self.looks}
        tint = {-1: self.left, 0: self.joint, 1: self.right}
        for joint in JOINTS:
            frame = frames[joint.name]
            if joint.bulk:
                centre, shares = self._bulk(joint)
                place = frame.then(Transform(Vec3(*(part * h for part in centre))))
                small = joint.name.endswith("_eye")
                radii = tuple(r * h for r in shares)
                parts.append(Limb(**_egg(radii), radii=radii, at=place.position, basis=place.basis,
                                  name=joint.name, material=self.joint if small else self.body,
                                  samples=(12, 8) if small or joint.bulk.radii[1] < 0.01 else (20, 12), **common))
            if joint.ball:
                radius = joint.ball * h * self.build_of.girth
                parts.append(Limb(**_egg((radius, radius, radius)), radii=(radius,) * 3, at=frame.position, basis=frame.basis,
                                  name=f"{joint.name}.ball", material=tint[joint.side], samples=(14, 10), **common))
        return parts

    def _drop(self, frames: Mapping[str, Transform]) -> float:
        """How far the lowest part of the figure is above the floor."""
        return min(part.bounds(part.transform)[0].y for part in self._parts(frames)) if self.grounded else 0.0

    def frames(self) -> dict[str, Transform]:
        """Each joint in the figure's frame, as it stands; `transform.then()` of one is where it is in the location."""
        solved = self._solved()
        drop = self._drop(solved)
        return {name: Transform(frame.position - Vec3(0, drop, 0), frame.basis) for name, frame in solved.items()}

    def build(self) -> Sequence[Node]:
        return self._parts(self.frames())
