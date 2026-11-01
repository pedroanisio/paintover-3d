"""A mannequin in every set, to spot what an empty set hides. It reports each limb that passes through the set, not only the
deepest, then the driver's posture as joint angles. Run: .venv/bin/python examples/fit_check.py. Pictures go into renders/fit/."""
import math
import sys
from dataclasses import replace
from pathlib import Path
from typing import Callable, Iterator, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "examples")]

from grand_tourer_paper import PAPER, SKY
from paintover import living_room, town
from use_cases import office

from srlocations import Location, Node, Registry, Renderer, SharedCatalog, Styled, Surface
from srlocations.collision import TOUCH, Body, deepest
from srlocations.geometry import Transform, Vec3
from srlocations.stock.looks import paper_cutout
from srlocations.stock.mannequin import Mannequin
from srlocations.surfaces import _traced

OUT = ROOT / "renders/fit"
SEAT = 0.05  # where the front seats stand along the car
SOFT = 0.03  # how far a body may sink into a cushion before it counts
CUSHIONS = ("studio.leather.cognac",)
HIPS_ON_SEAT = (0.34, 0.03)  # height above the cabin floor and distance back from the seat's centre
RESTING = 0.02  # a body further than this from what should carry it is not sitting on it
WHEEL, RIM, RAKE = Vec3(-0.37, 0.69, 0.36), 0.2, 20.0  # the centre, the radius and the lean of the steering wheel
GRIP = 0.1  # a wrist further than this from the rim is not holding it
COMFORT = {"trunk to thigh": (90, 115), "knee": (99, 138), "ankle": (85, 110), "elbow": (86, 164), "trunk recline": (15, 30)}  # degrees
LEGS = {"left_upper_leg.front_back": -76, "right_upper_leg.front_back": -76, "left_lower_leg.stretch": -54, "right_lower_leg.stretch": -54,
        "left_foot.up_down": 0, "right_foot.up_down": 0}
ARMS = {"upper_arm.down_up": -85, "upper_arm.front_back": -33, "lower_arm.stretch": -79, "lower_arm.twist_in_out": -10}  # solved to reach the rim
DRIVER = {"hips.front_back": 24, **{f"{side}_{name}": value for side in ("left", "right") for name, value in ARMS.items()}, **LEGS}
PASSENGER = {"hips.front_back": 24, **LEGS, "left_upper_leg.front_back": -78, "right_upper_leg.front_back": -78}


def seated(location: Location, name: str, x: float, seat: float, pose: str, adjust: dict, height: float) -> Mannequin:
    """A figure with its hips on a seat of the car, which faces +z. Hips rest 0.55 of a figure's height above its origin."""
    up, back = HIPS_ON_SEAT
    return location.add(Mannequin(pose=pose, adjust=adjust, height=height, grounded=False, solid=False,
                                  at=(x, up - 0.55 * height, seat - back), name=name))


def inside(point: Vec3, surface: Surface, world: Transform) -> bool:
    """Whether a point is in a closed surface: a ray up from it crosses the surface an odd number of times."""
    rows = [[world.apply(p) for p in row] for row in _traced(surface.x, surface.y, surface.z, surface.u, surface.v)]
    crossings = 0
    for v in range(len(rows) - 1):
        for u in range(len(rows[0]) - 1):
            for a, b, c in ((rows[v][u], rows[v][u + 1], rows[v + 1][u + 1]), (rows[v][u], rows[v + 1][u + 1], rows[v + 1][u])):
                area = (b.x - a.x) * (c.z - a.z) - (c.x - a.x) * (b.z - a.z)
                if not area:
                    continue
                s = ((point.x - a.x) * (c.z - a.z) - (c.x - a.x) * (point.z - a.z)) / area
                t = ((b.x - a.x) * (point.z - a.z) - (point.x - a.x) * (b.z - a.z)) / area
                if s >= 0 and t >= 0 and s + t <= 1 and a.y + s * (b.y - a.y) + t * (c.y - a.y) > point.y:
                    crossings += 1
    return crossings % 2 == 1


def limb_faults(location: Location, figure: Node) -> Iterator[str]:
    """Every limb of a figure that passes through the set, or lies wholly inside it."""
    body = Body.of(figure)
    sets = [other for other in (Body.of(node) for node in location.nodes if node is not figure and not isinstance(node, Mannequin)) if other]
    soft = {leaf.path for leaf in location.solids() if leaf.item.material.split("@")[0] in CUSHIONS}
    firm = [part for other in sets for part in (_part(other, lambda path: path in soft), _part(other, lambda path: path not in soft)) if part]
    for path in dict.fromkeys(entry[2] for entry in body.hulls):
        if ".ball" in path or any(finger in path for finger in ("thumb", "index", "middle", "ring", "little", "eye", "jaw")):
            continue
        limb = _part(body, lambda name: name == path)
        worst = max((found for other in firm if (found := deepest(limb, other)) is not None and found.depth > (SOFT if found.second in soft else TOUCH)),
                    key=lambda clash: clash.depth, default=None)
        centre = limb.hulls[0][0].centre
        buried = [leaf.path for leaf in location.solids() if isinstance(leaf.item, Surface) and leaf.item.material.split("@")[0] not in CUSHIONS
                  and "/" in leaf.path and not leaf.path.startswith(figure.label) and all(leaf.item.closed[:1]) and leaf.item.bounds(leaf.world)[0].x <= centre.x <= leaf.item.bounds(leaf.world)[1].x
                  and leaf.item.bounds(leaf.world)[0].y <= centre.y <= leaf.item.bounds(leaf.world)[1].y and leaf.item.bounds(leaf.world)[0].z <= centre.z <= leaf.item.bounds(leaf.world)[1].z
                  and inside(centre, leaf.item, leaf.world)]
        if buried:
            yield f"{path} is buried in {buried[0]}"
        elif worst is not None:
            yield str(worst)


def _part(body: Body, keep: Callable[[str], bool]) -> Optional[Body]:
    """The hulls of a body whose paths pass `keep`, so a cushion and a firewall need not forgive the same amount."""
    hulls = [entry for entry in body.hulls if keep(entry[2])]
    if not hulls:
        return None
    return Body(body.node, hulls, Vec3(*(min(getattr(entry[1][0], a) for entry in hulls) for a in "xyz")),
                Vec3(*(max(getattr(entry[1][1], a) for entry in hulls) for a in "xyz")))


def gap(location: Location, figure: Node, joint: str, way: Vec3) -> float:
    """How far one limb of a figure moves along `way` before it meets the set, in metres. Limit: 30 cm."""
    limb = _part(Body.of(figure), lambda path: path.endswith(f"/{joint}"))
    sets = [other for other in (Body.of(node) for node in location.nodes if node is not figure and not isinstance(node, Mannequin)) if other]
    return next((step / 200 for step in range(61) if any(deepest(limb, other, Vec3(*(axis * step / 200 for axis in way))) for other in sets)), 0.3)


def to_rim(point: Vec3) -> float:
    """How far a point is from the middle of the wheel's rim, in metres."""
    lean = math.radians(RAKE)
    return min((point - WHEEL - Vec3(RIM * math.cos(math.radians(turn)), RIM * math.sin(math.radians(turn)) * math.cos(lean),
                                     RIM * math.sin(math.radians(turn)) * math.sin(lean))).length for turn in range(360))


def angle(a: Vec3, joint: Vec3, b: Vec3) -> float:
    u, v = a - joint, b - joint
    return math.degrees(math.acos(max(-1.0, min(1.0, sum(p * q for p, q in zip(u, v)) / (u.length * v.length)))))


def posture(figure: Mannequin) -> dict[str, float]:
    """The joint angles a seating study reports, in degrees."""
    at = {name: figure.transform.apply(frame.position) for name, frame in figure.frames().items()}
    trunk = at["upper_chest"] - at["hips"]
    return {"trunk to thigh": angle(at["upper_chest"], at["hips"], at["left_lower_leg"]),
            "knee": angle(at["left_upper_leg"], at["left_lower_leg"], at["left_foot"]),
            "ankle": angle(at["left_lower_leg"], at["left_foot"], at["left_toes"]),
            "elbow": angle(at["left_upper_arm"], at["left_lower_arm"], at["left_hand"]),
            "trunk recline": math.degrees(math.atan2(-trunk.z, trunk.y))}


def occupy(location: Location) -> tuple[Mannequin, Mannequin]:
    return (seated(location, "driver", -0.37, SEAT, "drive", DRIVER, 1.78), seated(location, "passenger", 0.37, SEAT, "drive", PASSENGER, 1.7))


def review(location: Location) -> int:
    """Prints what is wrong with the occupants, and returns how many faults it found."""
    figures, faults = [node for node in location.nodes if isinstance(node, Mannequin)], 0
    for figure in figures:
        for fault in limb_faults(location, figure):
            print("  FAULT", fault)
            faults += 1
    for figure in figures:
        for name, value in posture(figure).items():
            low, high = COMFORT[name]
            good = low <= value <= high
            faults += 0 if good else 1
            print(f"  {figure.label:<10}{name:<16}{value:6.1f}  wanted {low} to {high}{'' if good else '  OUT OF RANGE'}")
        for name, joint, way in (("back to seat", "chest", Vec3(0, 0, -1)), ("shoulders to seat", "upper_chest", Vec3(0, 0, -1)),
                                 ("hips to seat", "hips", Vec3(0, -1, 0)), ("thigh to seat", "left_upper_leg", Vec3(0, -1, 0))):
            distance = gap(location, figure, joint, way)
            faults += 0 if distance <= RESTING else 1
            print(f"  {figure.label:<10}{name:<18}{distance * 100:4.1f}  cm{'' if distance <= RESTING else '  NOT RESTING'}")
        print(f"  {figure.label:<10}{'head room':<18}{gap(location, figure, 'head', Vec3(0, 1, 0)) * 100:4.1f}  cm")
    for side in ("left", "right") if any(figure.label == "driver" for figure in figures) else ():
        driver = next(figure for figure in figures if figure.label == "driver")
        distance = to_rim(driver.transform.apply(driver.frames()[f"{side}_hand"].position))
        faults += 0 if distance <= GRIP else 1
        print(f"  driver    {side + ' wrist to rim':<18}{distance * 100:4.1f}  cm{'' if distance <= GRIP else '  NOT HOLDING IT'}")
    return faults


def main() -> None:
    renderer, registry = Renderer(), Registry.default()
    parked = SharedCatalog.open(ROOT / "catalog").location("grand-tourer", registry=registry)
    occupy(parked)
    parked.shot("side", (3.6, 0.72, -0.25), (0, 0.62, -0.25), lens=30)
    print("car faults:", review(parked))
    look = replace(paper_cutout(PAPER), sky=SKY)
    for shot in parked.shots:
        print(renderer.render(parked, shot, OUT / f"grand-tourer-{shot}.png", Styled(look, 1422, 711)).name)
    home, street, work = living_room(registry), town(registry), office(registry)
    for location, marks in ((home, ("host", "guest")), (street, ("left", "middle", "right"))):
        location.paintings.clear()  # the paper figures stand where the real bodies go
        for mark in marks:
            location.stand(mark, pose="stand")
    work.stand("detective", pose="sit")
    work.stand("client", pose="sit")
    for location, shot in ((home, "wide"), (home, "corner"), (street, "town"), *((work, name) for name in work.shots)):
        print(location.name, "clashes:", [str(clash) for clash in location.clashes(bodies_only=True)] or "none")
        print(renderer.render(location, shot, OUT / f"{location.name}-{shot}.png", "stock.shaded").name)


if __name__ == "__main__":
    main()
