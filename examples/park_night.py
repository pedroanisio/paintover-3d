"""The published night park as plates for a 2D dancer composited over it: one wide plate with every light on, a base
with every lamp off (moon, sky and mist only), and one light-only layer for the street lamp and for each row of path
lights, which added to the base give the plate back. set.json beside them holds what a compositor needs, every number
projected from the published shot. It needs only the catalog and ffmpeg.
Run: .venv/bin/python examples/park_night.py [folder] [width]"""
import json
import math
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from srlocations import Blueprint, Projection, Registry, Renderer, Shaded, SharedCatalog, Vec3
from srlocations.geometry import aim

SHOT, MARK, HEIGHT, CROP = "dance", "dancer", 1920, 1080  # the plate's height and the width of the frame panned over it
FIGURE = 1.6  # metres, the dancer's standing height
REACH = 400  # px either side of the dance spot where the figure's limbs go
F_STOP = 0.6  # wide open, so what is behind the dancer goes soft


def switched(payload: dict, lit: set[str]) -> dict:
    """The blueprint with every lamp not named in `lit` swapped for its switched-off prop."""
    def node(spec: dict) -> dict:
        name, use = spec.get("name", ""), spec["use"]
        if (name == "lamp" or name.startswith("row-")) and name not in lit:
            prop, version = use.split("@")
            return {**spec, "use": f"{prop}.off@{version}"}
        return spec
    return {**payload, "nodes": [node(spec) for spec in payload["nodes"]]}


def rgb(path: Path, width: int) -> bytes:
    done = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                          capture_output=True, check=True)
    assert len(done.stdout) == width * HEIGHT * 3, path
    return done.stdout


def light_only(on: Path, base: Path, out: Path) -> None:
    """What turning a light on adds, per channel and clamped at zero, so `base + layer` is `on` again."""
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(on), "-i", str(base), "-filter_complex",
                    "[0:v]format=gbrp[a];[1:v]format=gbrp[b];[a][b]blend=all_mode=subtract,format=rgb24", "-frames:v", "1",
                    str(out)], check=True)


def added_back(base: Path, layers: list[Path], state: Path, width: int) -> dict:
    """How far the base with the layers added is from the picture it should give: the largest difference in any channel,
    and the share of channels more than 2 apart."""
    total = list(rgb(base, width))
    for layer in layers:
        total = [min(255, a + b) for a, b in zip(total, rgb(layer, width))]
    gaps = [abs(a - b) for a, b in zip(total, rgb(state, width))]
    return {"largest": max(gaps), "share_over_2": round(sum(gap > 2 for gap in gaps) / len(gaps), 6)}


def luminance(path: Path, width: int, spot: tuple[float, float], top: float) -> dict:
    """Relative luminance (WCAG 2) of the plate behind the figure: `REACH` px either side of the dance spot, from the head
    row to the floor row, with the contrast a pure black limb has against its darkest and its tenth-percentile pixel."""
    data = rgb(path, width)
    linear = [c / 255 / 12.92 if c / 255 <= 0.04045 else ((c / 255 + 0.055) / 1.055) ** 2.4 for c in range(256)]
    left, right = max(0, round(spot[0] - REACH)), min(width, round(spot[0] + REACH))
    values = sorted(0.2126 * linear[data[i]] + 0.7152 * linear[data[i + 1]] + 0.0722 * linear[data[i + 2]]
                    for y in range(round(top), round(spot[1])) for i in range((y * width + left) * 3, (y * width + right) * 3, 3))
    low, tenth, middle = values[0], values[len(values) // 10], values[len(values) // 2]
    return {"region": {"x": [left, right], "y": [round(top), round(spot[1])]}, "min": round(low, 4), "p10": round(tenth, 4),
            "median": round(middle, 4), "black_contrast_at_min": round((low + 0.05) / 0.05, 2),
            "black_contrast_at_p10": round((tenth + 0.05) / 0.05, 2), "meets_4_5_at_p10": (tenth + 0.05) / 0.05 >= 4.5}


def numbers(location, rig: dict, width: int, layers: dict[str, list[str]]) -> dict:
    """The plate's geometry, from the shot through the SDK's model of the engine's camera."""
    shot, mark = location.shots[SHOT], location.marks[MARK]
    view = Projection(shot, width, HEIGHT)
    spot = view.pixel(mark.at)
    head = view.pixel(mark.at + Vec3(0, FIGURE, 0))
    across = view.pixel(mark.at + Vec3(*(view.basis[i][0] for i in range(3))))  # one metre along the camera's x
    yaw, _ = aim(shot.eye, shot.look_at)
    far = shot.eye + Vec3(math.sin(math.radians(yaw)) * 1e6, 0, math.cos(math.radians(yaw)) * 1e6)
    lights = {leaf.path.split("/")[0]: leaf.world.position for leaf in location.lights()}
    centre = (width - CROP) / 2

    def where(point: Vec3) -> dict:
        x, y = view.pixel(point)
        return {"px": [round(x, 1), round(y, 1)], "height_m": round(point.y, 3), "world_m": [round(v, 3) for v in point]}

    travel = (math.sin(math.radians(rig["azimuth"] + 180)) * math.cos(math.radians(rig["elevation"])),
              -math.sin(math.radians(rig["elevation"])),
              math.cos(math.radians(rig["azimuth"] + 180)) * math.cos(math.radians(rig["elevation"])))
    return {
        "plate": {"width": width, "height": HEIGHT, "frame": [CROP, HEIGHT]},
        "camera": {"eye_m": list(shot.eye), "look_at_m": list(shot.look_at), "lens_mm": shot.lens,
                   "focal_px": round(view.focal, 3), "depth_of_field": {"f_stop": F_STOP, "focus_m": round(view.to_camera(mark.at).z, 3)}},
        "dance_spot": {"world_m": list(mark.at), "px": [round(spot[0], 1), round(spot[1], 1)], "floor_y": round(spot[1], 1),
                       "px_per_metre_horizontal": round(math.dist(spot, across), 2),
                       "px_per_metre_vertical": round((spot[1] - head[1]) / FIGURE, 2),
                       "figure_1_6_m_px": round(spot[1] - head[1], 1), "head_y": round(head[1], 1)},
        "horizon_y": round(view.pixel(far)[1], 1),
        "pan": {"frame_centre_x": [CROP / 2, width - CROP / 2], "frame_left_x": [0, width - CROP],
                "dance_spot_offset_px": [round(CROP / 2 - spot[0], 1), round(width - CROP / 2 - spot[0], 1)],
                "dance_spot_offset_m": [round((CROP / 2 - spot[0]) / math.dist(spot, across), 3),
                                        round((width - CROP / 2 - spot[0]) / math.dist(spot, across), 3)],
                "centred_frame_left_x": round(centre, 1)},
        "key_light": {"name": "lamp", **where(lights["lamp"])},
        "rim": {"kind": "directional (moon)", "azimuth_deg": rig["azimuth"], "elevation_deg": rig["elevation"],
                "camera_yaw_deg": round(yaw, 3), "colour": rig["sun"], "strength_lux": rig["strength"],
                "travel_direction_world": [round(v, 4) for v in travel],
                "from": f"behind the dancer, {abs(round(rig['azimuth'] - yaw, 1))} degrees "
                        f"{'left' if rig['azimuth'] < yaw else 'right'} of the camera's axis and {rig['elevation']} up, "
                        "shining toward the camera"},
        "layers_order": "the lamp, then the rows near to far; add them to the base in this order, each with the ones before it",
        "layers": {name: {"files": files, "blend": "add",
                          "lights": {path: where(position) for path, position in lights.items()
                                     if path == name or path.startswith(f"{name}-")}}
                   for name, files in layers.items()},
    }


def source() -> dict:
    """The branch and commit of this checkout, and whether it has changes not committed, for set.json."""
    def git(*args: str) -> str:
        done = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True)
        return done.stdout.strip() if done.returncode == 0 else ""
    return {"repository": "srlocations", "branch": git("rev-parse", "--abbrev-ref", "HEAD"), "commit": git("rev-parse", "HEAD"),
            "uncommitted_changes": bool(git("status", "--porcelain", "--untracked-files=no"))}


def main() -> None:
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "renders/park-night"
    width = int(sys.argv[2]) if len(sys.argv) > 2 else 2400
    folder.mkdir(parents=True, exist_ok=True)
    catalog = SharedCatalog.open(ROOT / "catalog")
    payload = catalog.get("location", "park-night").payload
    rows = sorted({spec["name"].rsplit("-", 1)[0] for spec in payload["nodes"] if spec.get("name", "").startswith("row-")})
    everything = {spec["name"] for spec in payload["nodes"] if spec.get("name", "") == "lamp" or spec.get("name", "").startswith("row-")}

    def built(lit: set[str]):
        return Blueprint(switched(payload, lit)).build(Registry.default().use(catalog))

    location = built(everything)
    print("issues:", location.validate() or "none")
    focus = Projection(location.shots[SHOT], width, HEIGHT).to_camera(location.marks[MARK].at).z
    mode = Shaded(width, HEIGHT, camera={"depthOfField": True, "fStop": F_STOP, "focusDistance": round(focus * 100, 1),
                                         "screenSpaceReflections": True})
    renderer = Renderer()
    # Each state is the one before with one more light on: the base, the lamp, then the rows near to far with the lamp on,
    # the last of which is the plate. Each layer is what its light adds to the state before, so adding the layers to the
    # base in this order gives each state back, and the engine's tone curve cannot make the sum drift.
    states = [("base", set()), ("lamp-on", {"lamp"})]
    for row in rows:
        states.append((f"{row}-on", states[-1][1] | {name for name in everything if name.startswith(f"{row}-")}))
    states[-1] = ("plate", states[-1][1])
    for name, lit in states:
        print(renderer.render(built(lit), SHOT, folder / f"{name}.png", mode).name)
    layers, exact = {}, {}
    for (before, _), (after, _), light in zip(states, states[1:], ("lamp", *rows)):
        light_only(folder / f"{after}.png", folder / f"{before}.png", folder / f"{light}.png")
        layers[light] = [f"{light}.png"]
        exact[after] = added_back(folder / "base.png", [folder / f"{name}.png" for name in layers], folder / f"{after}.png", width)
        print(f"base + layers to {light} against {after}.png:", exact[after])
    found = numbers(location, payload["rig"], width, layers)
    found["source"] = source()
    found["states"] = {name: {"file": f"{name}.png", "lit": sorted(lit), "base_plus_layers": exact.get(name)} for name, lit in states}
    spot, head = found["dance_spot"]["px"], found["dance_spot"]["head_y"]
    found["behind_the_figure"] = {name: luminance(folder / f"{name}.png", width, spot, head)
                                  for name in ("plate", "lamp-on", "base")}
    (folder / "set.json").write_text(json.dumps(found, indent=2) + "\n")
    print((folder / "set.json").name)


if __name__ == "__main__":
    main()
