"""How faithfully a take follows the points it was read from, as numbers: whether each gesture keeps its time, its speed
and its acceleration, and what reading it added (ripple, sliding feet, controls held at their ranges).

Both sides are compared about the pelvis, the midpoint of the hips, and in lengths of leg (hip to knee to ankle), so a
take read onto a figure of another size compares as it was read. Distances are then given in metres of the take's figure.
A point missing from a frame leaves that joint out of the frames that need it."""
import math
from dataclasses import dataclass, field, replace
from typing import Mapping, Optional, Sequence

from .geometry import Transform, Vec3
from .interchange import Take
from .kinematics import scaled
from .stock.mannequin import FOOTED, Mannequin, _margin

LIMBS = ("left_lower_arm", "right_lower_arm", "left_hand", "right_hand",
         "left_lower_leg", "right_lower_leg", "left_foot", "right_foot")  # elbows, wrists, knees and ankles
HIPS = ("left_upper_leg", "right_upper_leg")
FEET = ("left_foot", "right_foot")
PEAK = 0.95  # the share of frames below a peak: a 95th percentile, so one bad frame does not set it
LAGS = 6  # frames either way a take may run late or early
FALLING = 0.25  # seconds a centre of mass may stay outside its support, as in a step, before the pose is one nobody holds
BEARING = 0.05  # metres above the floor that a foot still counts as bearing weight: points read from a picture miss its
# height by a few centimetres, and a figure's floor drop sets only its lowest point down, so the other foot floats
SIGMA = 0.1  # seconds: how near a beat must fall to count, as the Beat Align Score weighs it
RIPPLE = (4.0, 6.0)  # Hz: above the beat and its first harmonic hits, where reading wobbles a held joint


@dataclass(frozen=True)
class Fidelity:
    """`lag` is the seconds the take runs behind its points (early is negative). `speed` and `acceleration` are the take's
    peaks over the points' (1 keeps them, below 1 flattens them). `beats` is how well the moments where the body stops
    agree, 1 when every one falls together, as Bailando's Beat Align Score taken both ways. `ripple` is what the take adds
    in RIPPLE, `miss` the median distance from the points, both in metres; `slide` is how fast a foot on the floor moves
    across it, in metres a second: the median, over the frames a foot or its toes are within FOOTED of the floor then and
    either side, of how fast the lower of the two goes. `fallen` is the share of frames in a run of FALLING or longer with
    the centre of mass outside the outline of the parts within BEARING of the floor: a pose nobody could stand in. `held`
    is the share of frames each control was held at its range. Each but `held` and `slide` is the median over LIMBS,
    which `by_limb` holds one by one."""
    lag: float
    speed: float
    acceleration: float
    beats: float
    ripple: float
    miss: float
    slide: float
    fallen: float = 0.0
    held: Mapping[str, float] = field(default_factory=dict)
    by_limb: Mapping[str, Mapping[str, float]] = field(default_factory=dict)


Track = list[Optional[Vec3]]


def positions(take: Take, figure: Optional[Mannequin] = None,
              joints: Sequence[str] = LIMBS + HIPS) -> list[dict[str, Vec3]]:
    """Where each of `joints` turns in each frame of a take, on `figure`, by default the stock man, standing at the origin."""
    figure = Mannequin() if figure is None else figure
    out = []
    for pose in take.poses:
        posed = replace(figure, pose=pose, solid=False)
        frames = posed.frames()
        out.append({name: posed.transform.then(frames[name]).position for name in joints})
    return out


def _posed(take: Take, figure: Optional[Mannequin], joints: Sequence[str]) -> list[tuple[dict[str, Vec3], dict[str, Vec3], Optional[float]]]:
    """Each frame's joints, the lowest point of each foot with its toes, as the middle of the lower part's bottom, and how
    far inside its support its centre of mass is, the support counting what is within BEARING of the floor."""
    figure = Mannequin() if figure is None else figure
    out = []
    for pose in take.poses:
        posed = replace(figure, pose=pose, solid=False)
        frames = posed.frames()
        lows: dict[str, list[tuple[float, Vec3]]] = {foot: [] for foot in FEET}
        for leaf in posed.walk():
            part = leaf.path.rpartition("/")[2]
            for foot in FEET:
                if part in (foot, foot.replace("foot", "toes")):
                    low, high = leaf.item.bounds(leaf.world)
                    lows[foot].append((low.y, Vec3((low.x + high.x) / 2, low.y, (low.z + high.z) / 2)))
        out.append(({name: posed.transform.then(frames[name]).position for name in joints},
                    {foot: min(found, key=lambda pair: pair[0])[1] for foot, found in lows.items() if found}, _bearing(posed, frames)))
    return out


def fidelity(points: Sequence[Mapping[str, Sequence[float]]], take: Take, figure: Optional[Mannequin] = None) -> Fidelity:
    """How faithfully `take` follows `points`, the frames load_keypoints() read it from, in the same names and frame."""
    if len(points) != len(take.poses):
        raise ValueError(f"{len(points)} frames of points and {len(take.poses)} poses: compare a take with what it was read from")
    fps = take.fps
    made, soles, balances = zip(*_posed(take, figure, LIMBS + HIPS)) if take.poses else ((), (), ())
    source = [{name: Vec3(*at) for name, at in frame.items()} for frame in points]
    leg = _leg(made)
    theirs, ours = _relative(source, _leg(source)), _relative(made, leg)
    limbs: dict[str, dict[str, float]] = {}
    for name in LIMBS:
        a, b = [frame.get(name) for frame in theirs], [frame.get(name) for frame in ours]
        va, vb = _speeds(a, fps), _speeds(b, fps)
        aa, ab = _speeds(_steps(a, fps), fps), _speeds(_steps(b, fps), fps)
        off = [_minus(p, q) for p, q in zip(b, a)]
        apart = [v.length for v in off if v is not None]
        limbs[name] = {"lag": _lag(va, vb) / fps, "speed": _ratio(vb, va), "acceleration": _ratio(ab, aa),
                       "ripple": _ripple(off, fps) * leg, "miss": _median(apart) * leg if apart else math.nan}
    kinetic = lambda frames: _minima(_smoothed(_mean([_speeds([frame.get(name) for frame in frames], fps) for name in LIMBS])))
    beats = (_bas(kinetic(theirs), kinetic(ours), fps) + _bas(kinetic(ours), kinetic(theirs), fps)) / 2
    count = len(take.poses)
    return Fidelity(**{key: _median([limb[key] for limb in limbs.values()]) for key in ("lag", "speed", "acceleration", "ripple", "miss")},
                    beats=beats, slide=_slide(soles, fps), fallen=_fallen(balances, fps), held={key: len(frames) / count for key, frames in take.clamped.items()},
                    by_limb=limbs)


def _minus(a: Optional[Vec3], b: Optional[Vec3]) -> Optional[Vec3]:
    return None if a is None or b is None else a - b


def _leg(frames: Sequence[Mapping[str, Vec3]]) -> float:
    lengths = [(f[f"{side}_lower_leg"] - f[f"{side}_upper_leg"]).length + (f[f"{side}_foot"] - f[f"{side}_lower_leg"]).length
               for f in frames for side in ("left", "right") if all(f"{side}_{part}" in f for part in ("upper_leg", "lower_leg", "foot"))]
    if not lengths:
        raise ValueError("no frame has a hip, a knee and an ankle on the same side, so there is no leg to scale by")
    return _median(lengths)


def _relative(frames: Sequence[Mapping[str, Vec3]], leg: float) -> list[dict[str, Vec3]]:
    out = []
    for frame in frames:
        if not all(hip in frame for hip in HIPS):
            out.append({})
            continue
        pelvis = scaled(frame[HIPS[0]] + frame[HIPS[1]], 0.5)
        out.append({name: scaled(at - pelvis, 1 / leg) for name, at in frame.items() if name in LIMBS})
    return out


def _steps(track: Track, fps: float) -> Track:
    """Velocity at each frame, by the frames either side."""
    return [None] + [None if a is None or b is None else scaled(b - a, fps / 2) for a, b in zip(track, track[2:])] + [None] * min(1, len(track) - 1)


def _speeds(track: Track, fps: float) -> list[Optional[float]]:
    return [None if v is None else v.length for v in _steps(track, fps)]


def _median(values: Sequence[float]) -> float:
    ordered = sorted(v for v in values if not math.isnan(v))
    if not ordered:
        return math.nan
    middle = len(ordered) // 2
    return ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2


def _peak(values: Sequence[Optional[float]]) -> float:
    ordered = sorted(v for v in values if v is not None)
    return ordered[min(len(ordered) - 1, int(PEAK * len(ordered)))] if ordered else math.nan


def _ratio(ours: Sequence[Optional[float]], theirs: Sequence[Optional[float]]) -> float:
    both = [(a, b) for a, b in zip(ours, theirs) if a is not None and b is not None]
    top = _peak([b for _, b in both])
    return _peak([a for a, _ in both]) / top if top else math.nan


def _lag(theirs: Sequence[Optional[float]], ours: Sequence[Optional[float]]) -> float:
    """The shift of `ours` that best matches `theirs`, by cross-correlation: frames late (+) or early (-). Not a number for
    a joint that does not move, which has no time to keep."""
    def centred(values):
        known = [v for v in values if v is not None]
        mean = sum(known) / len(known) if known else 0.0
        return [None if v is None else v - mean for v in values]
    a, b = centred(theirs), centred(ours)
    if not any(v and abs(v) > 1e-9 for v in a) or not any(v and abs(v) > 1e-9 for v in b):
        return math.nan
    def score(shift):
        return sum(x * b[i + shift] for i, x in enumerate(a[LAGS:len(a) - LAGS], LAGS)
                   if x is not None and b[i + shift] is not None)
    return max(range(-LAGS, LAGS + 1), key=lambda shift: (score(shift), -abs(shift)))


def _mean(series: Sequence[Sequence[Optional[float]]]) -> list[Optional[float]]:
    out = []
    for values in zip(*series):
        known = [v for v in values if v is not None]
        out.append(sum(known) / len(known) if known else None)
    return out


def _smoothed(values: Sequence[Optional[float]]) -> list[Optional[float]]:
    """A Gaussian of one frame, so a stop is one minimum and not a few."""
    weights = (0.054, 0.242, 0.399, 0.242, 0.054)
    out = []
    for i in range(len(values)):
        near = [(w, values[i + k - 2]) for k, w in enumerate(weights) if 0 <= i + k - 2 < len(values) and values[i + k - 2] is not None]
        out.append(sum(w * v for w, v in near) / sum(w for w, _ in near) if near and values[i] is not None else None)
    return out


def _minima(values: Sequence[Optional[float]]) -> list[int]:
    """Frames where the body is slowest about them: where a gesture stops, Bailando's kinematic beats."""
    return [i for i in range(1, len(values) - 1) if None not in values[i - 1:i + 2] and values[i] < values[i - 1] and values[i] <= values[i + 1]]


def _bas(beats: Sequence[int], against: Sequence[int], fps: float) -> float:
    if not beats or not against:
        return math.nan
    return sum(math.exp(-min(((a - b) / fps) ** 2 for b in against) / (2 * SIGMA ** 2)) for a in beats) / len(beats)


def _band(values: Sequence[float], fps: float) -> list[float]:
    """RIPPLE alone, forward and back so nothing moves in time: a band-pass biquad from the Audio EQ Cookbook (R. Bristow-
    Johnson), at the geometric centre of the band, run twice each way."""
    low, high = RIPPLE
    centre = math.sqrt(low * high)
    w = 2 * math.pi * centre / fps
    alpha = math.sin(w) / (2 * centre / (high - low))
    a0 = 1 + alpha
    b, a = (alpha / a0, 0.0, -alpha / a0), (-2 * math.cos(w) / a0, (1 - alpha) / a0)
    def run(xs):
        out, x1, x2, y1, y2 = [], 0.0, 0.0, 0.0, 0.0
        for x in xs:
            y = b[0] * x + b[1] * x1 + b[2] * x2 - a[0] * y1 - a[1] * y2
            out.append(y)
            x1, x2, y1, y2 = x, x1, y, y1
        return out
    for _ in range(2):
        values = run(values)[::-1]
        values = run(values)[::-1]
    return values


def _ripple(off: Sequence[Optional[Vec3]], fps: float) -> float:
    """The root mean square of `off` in RIPPLE, over the longest run of frames with no gap."""
    if fps <= 2 * RIPPLE[1]:
        return math.nan
    runs, run = [], []
    for v in off:
        if v is None:
            runs, run = runs + [run], []
        else:
            run.append(v)
    run = max(runs + [run], key=len)
    if len(run) < fps:
        return math.nan
    axes = [_band([getattr(v, axis) for v in run], fps) for axis in "xyz"]
    return math.sqrt(sum(x * x + y * y + z * z for x, y, z in zip(*axes)) / len(run))


def _slide(soles: Sequence[Mapping[str, Vec3]], fps: float) -> float:
    speeds = []
    for foot in FEET:
        track = [frame.get(foot) for frame in soles]
        for before, now, after in zip(track, track[1:], track[2:]):
            if None not in (before, now, after) and max(before.y, now.y, after.y) <= FOOTED:
                speeds.append(math.hypot(after.x - before.x, after.z - before.z) * fps / 2)
    return _median(speeds) if speeds else 0.0


def _bearing(figure: Mannequin, frames: Mapping[str, Transform]) -> Optional[float]:
    """`Mannequin.balance()` with the floor raised so its FOOTED reaches BEARING."""
    if not figure.grounded or figure.sits:
        return None
    centre = figure._centre(frames)
    return _margin((centre.x, centre.z), figure._support(frames, BEARING - FOOTED))


def _fallen(balances: Sequence[Optional[float]], fps: float) -> float:
    if not balances:
        return 0.0
    runs, run = [], 0
    for margin in list(balances) + [None]:
        if margin is not None and margin < 0:
            run += 1
        else:
            runs, run = runs + [run], 0
    return sum(run for run in runs if run >= FALLING * fps) / len(balances)
