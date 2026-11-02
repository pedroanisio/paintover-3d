"""A mannequin in every set, to spot what an empty set hides. It reports each limb that passes through the set, not only the
deepest, then the driver's posture as joint angles. Run: .venv/bin/python examples/fit_check.py. Pictures go into renders/fit/."""
import math
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "examples")]

from grand_tourer_paper import PAPER, SKY
from paintover import living_room, town
from use_cases import office

from srlocations import Contact, Location, Registry, Renderer, SharedCatalog, Styled
from srlocations.geometry import Vec3
from srlocations.stock.looks import paper_cutout
from srlocations.stock.mannequin import Mannequin

OUT = ROOT / "renders/fit"
SEAT = 0.05  # where the front seats stand along the car
CUSHIONED = Contact(cushions=("studio.leather.cognac",))
HIPS_ON_SEAT = (0.34, 0.03)  # height above the cabin floor and distance back from the seat's centre
RESTING = 0.02  # a body further than this from what should carry it is not sitting on it
WHEEL, RIM, RAKE = Vec3(-0.37, 0.69, 0.36), 0.2, 20.0  # the centre, the radius and the lean of the steering wheel
GRIP = 0.1  # a wrist further than this from the rim is not holding it
COMFORT = {"trunk to thigh": (90, 115), "knee": (99, 138), "ankle": (85, 110), "elbow": (86, 164), "trunk recline": (15, 30)}  # degrees; unverified targets, not from a source this project has read
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


def to_rim(point: Vec3) -> float:
    """How far a point is from the middle of the wheel's rim, in metres."""
    lean = math.radians(RAKE)
    return min((point - WHEEL - Vec3(RIM * math.cos(math.radians(turn)), RIM * math.sin(math.radians(turn)) * math.cos(lean),
                                     RIM * math.sin(math.radians(turn)) * math.sin(lean))).length for turn in range(360))


def occupy(location: Location) -> tuple[Mannequin, Mannequin]:
    return (seated(location, "driver", -0.37, SEAT, "drive", DRIVER, 1.78), seated(location, "passenger", 0.37, SEAT, "drive", PASSENGER, 1.7))


def review(location: Location) -> int:
    """Prints what is wrong with the occupants, and returns how many faults it found."""
    location.contact = CUSHIONED
    figures, faults = location.figures(), 0
    for figure in figures:
        for fault in location.faults(figure):
            print("  FAULT", fault)
            faults += 1
    for figure in figures:
        for name, value in figure.posture().items():
            low, high = COMFORT[name]
            good = low <= value <= high
            faults += 0 if good else 1
            print(f"  {figure.label:<10}{name:<16}{value:6.1f}  wanted {low} to {high}{'' if good else '  OUT OF RANGE'}")
        for name, joint, way in (("back to seat", "chest", Vec3(0, 0, -1)), ("shoulders to seat", "upper_chest", Vec3(0, 0, -1)),
                                 ("hips to seat", "hips", Vec3(0, -1, 0)), ("thigh to seat", "left_upper_leg", Vec3(0, -1, 0))):
            distance = location.gap(figure, joint, way)
            faults += 0 if distance <= RESTING else 1
            print(f"  {figure.label:<10}{name:<18}{distance * 100:4.1f}  cm{'' if distance <= RESTING else '  NOT RESTING'}")
        print(f"  {figure.label:<10}{'head room':<18}{location.gap(figure, 'head', (0, 1, 0)) * 100:4.1f}  cm")
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
