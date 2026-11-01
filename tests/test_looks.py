"""Paint and looks. The tests at the end render, because occlusion and registration only exist in the pixels."""
import json
import struct
import subprocess
import sys
import zlib
from pathlib import Path

import pytest
from sr_core.scene import check

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "examples")]

from srlocations import (Blueprint, Box, CatalogError, Cel, Cone, Cylinder, Decal, Disc, Fill, Flat, Group, Ink, Location,
                         Lit, Look, Material, PaintLayer, Pass, Picture, Projection, Registry, Renderer, SceneCompiler, Sphere,
                         Stroke, Styled, StyledCompiler, Texture, WireframeCompiler)
from srlocations.geometry import Vec3
from srlocations.location import Shot
from srlocations.looks import SHADERS, lookup, touches, vivid
from srlocations.nodes import Ambient, Placed, Point, Sun
from srlocations.paint import curve, paint_over, png_size
from srlocations.stock.prefabs import Wall, door
from srlocations.stock.looks import ink_toon, paper_cutout

W, H = 320, 180
GREY, RED, BLUE, GREEN = "#808080", "#ff0000", "#0000ff", "#00ff00"


def flat_set() -> Location:
    made = Registry.default()
    for name, color in (("t.grey", GREY), ("t.red", RED), ("t.blue", BLUE)):
        made.materials.add(name, Material(color), override=True)
    location = Location("test", made)
    location.shot("front", (0, 1, -5), (0, 1, 3), lens=30)
    return location


def deep(scene, name: str) -> list:
    return [node for node in scene.iter() if node.xml_name == name]


def errors(scene) -> list:
    return [f for f in check(scene, schema=True) if f.severity == "error"]


def stage(mode, location: Location, shot: str, folder: Path) -> list[bytes]:
    """The rendered shot as rows of RGB pixels."""
    path = Renderer().render(location, shot, folder / "shot.png", mode)
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(path), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         capture_output=True, check=True).stdout
    return [raw[row * W * 3:(row + 1) * W * 3] for row in range(H)]


def pixel(rows: list[bytes], x: float, y: float) -> tuple[int, ...]:
    return tuple(rows[int(y)][int(x) * 3:int(x) * 3 + 3])


def near(found: tuple[int, ...], color: str, tolerance: int = 24) -> bool:
    wanted = tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))
    return all(abs(a - b) <= tolerance for a, b in zip(found, wanted))


def solid_png(path: Path, rgba: bytes, size: int = 4) -> Path:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))
    rows = (b"\0" + rgba * size) * size
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))
    return path


def test_a_curve_passes_through_its_points():
    assert curve([(0, 0), (1, 2), (3, 0)], smooth=False) == "M0.00 0.00L1.00 2.00L3.00 0.00"
    smooth = curve([(0, 0), (1, 2), (3, 0)])
    assert smooth.count("C") == 2 and smooth.split(" ")[-2:] == ["3.00", "0.00"] and "1.00 2.00C" in smooth
    assert curve([(0, 0), (1, 0), (0, 1)], closed=True).endswith("Z")


def test_a_straight_two_point_stroke_stays_straight():
    assert curve([(0, 0), (4, 4)]) == "M0.00 0.00L4.00 4.00"


def view() -> Projection:
    return Projection(Shot("s", Vec3(0, 1, -5), Vec3(0, 1, 3), 30), W, H)


def drawn(item) -> list:
    location = flat_set()
    location.paint("p").add(item)
    scene = SceneCompiler(W, H).compile(location, "front")
    return deep(scene, "shape")


def test_a_world_mark_lands_where_the_camera_says():
    shape = drawn(Stroke(points=[(0, 1, 0), (1, 1, 0)], smooth=False, width=0.1))[0]
    x, y = view().pixel(Vec3(0, 1, 0))
    assert shape.path.startswith(f"M{x:.2f} {y:.2f}")
    assert shape.strokeWidth == pytest.approx(0.1 * view().pixels_per_metre(Vec3(0, 1, 0)), abs=0.01)


def test_a_frame_mark_ignores_the_camera():
    shape = drawn(Stroke(points=[(0.5, 0.25), (1, 1)], frame=True, smooth=False, width=0.1))[0]
    assert shape.path.startswith(f"M{W / 2:.2f} {H / 4:.2f}") and shape.strokeWidth == pytest.approx(H * 0.1)


def test_a_mark_behind_the_camera_is_left_out_whole():
    assert drawn(Stroke(points=[(0, 1, 0), (0, 1, -9)])) == []
    assert drawn(Fill(points=[(0, 1, 0), (1, 1, 0), (0, 1, -9)])) == []
    assert drawn(Disc(center=(0, 1, -9), radius=1)) == []


def test_a_disc_gets_smaller_with_distance():
    def across(depth: float) -> float:
        path = drawn(Disc(center=(0, 1, depth), radius=0.5))[0].path
        xs = [float(number) for number in path.replace("M", " ").replace("C", " ").replace("Z", " ").split()[::2]]
        return max(xs) - min(xs)
    assert across(0) == pytest.approx(view().pixels_per_metre(Vec3(0, 1, 0)), abs=0.1)
    assert across(10) == pytest.approx(across(0) * 5 / 15, abs=0.1)


def test_a_standee_keeps_its_size_and_faces_every_camera():
    card = PaintLayer("c").fill([(-1, 0), (1, 0), (1, 2)])
    location = flat_set()
    location.shot("side", (9, 1, 0), (0, 1, 0), lens=30)
    location.paint("p").standee((0, 0, 0), card.items)
    for shot, eye in (("front", (0, 1, -5)), ("side", (9, 1, 0))):
        take = location.shots[shot]
        scale = Projection(take, W, H).pixels_per_metre(Vec3(0, 0, 0))
        path = deep(SceneCompiler(W, H).compile(location, shot), "shape")[0].path
        xs = [float(part.split(" ")[0]) for part in path.replace("Z", "").split("L")[1:]]
        assert xs[0] - float(path[1:].split(" ")[0]) == pytest.approx(2 * scale, abs=0.02)


def test_layers_keep_their_order_blend_opacity_and_shots():
    location = flat_set()
    location.shot("other", (0, 1, -4), (0, 1, 3))
    location.paint("under", blend="multiply", opacity=0.3).disc((0, 1, 0), 1)
    location.paint("only", shots=["other"]).disc((0, 1, 0), 1)
    location.paint("empty")
    scene = SceneCompiler(W, H).compile(location, "front")
    groups = deep(scene, "group")
    assert len(groups) == 1 and groups[0].blend == "multiply" and groups[0].opacity == 0.3
    assert len(deep(SceneCompiler(W, H).compile(location, "other"), "group")) == 2


@pytest.mark.parametrize("make", [lambda: SceneCompiler(W, H), lambda: WireframeCompiler(W, H),
                                  lambda: StyledCompiler(ink_toon(), W, H), lambda: StyledCompiler(paper_cutout(), W, H)])
def test_every_mode_paints_and_stays_valid(make, tmp_path):
    location = flat_set()
    location.add(Box((1, 1, 1), material="t.red"))
    layer = location.paint("p", blend="multiply").stroke([(0, 0, 0), (1, 1, 0), (2, 0, 0)]).disc((0, 1, 0), 0.2)
    layer.picture(solid_png(tmp_path / "over.png", b"\0\xff\0\xff"))
    scene = make().compile(location, "front")
    assert len(deep(scene, "shape")) >= 2 and errors(scene) == []


def test_picture_refuses_what_is_not_a_png(tmp_path):
    (tmp_path / "x.jpg").write_bytes(b"\xff\xd8\xff" + b"\0" * 30)
    with pytest.raises(ValueError, match="not a PNG"):
        png_size(tmp_path / "x.jpg")


def test_a_blueprint_can_hold_paint_and_decals(tmp_path):
    solid_png(tmp_path / "over.png", b"\0\xff\0\xff")
    spec = {"name": "x", "nodes": [{"use": "stock.decal", "material": "stock.default", "at": [0, 1, 0]}],
            "shots": [{"name": "s", "eye": [0, 1, -5], "look_at": [0, 1, 0]}],
            "paint": [{"name": "ink", "blend": "multiply", "items": [
                {"kind": "stroke", "points": [[0, 0, 0], [1, 1, 0]], "width": 0.02},
                {"kind": "disc", "center": [0, 1, 0], "radius": 0.2}, {"kind": "picture", "path": "over.png"}]}]}
    path = tmp_path / "x.location.json"
    path.write_text(json.dumps(spec))
    location = Blueprint.load(path).build()
    assert isinstance(location.nodes[0], Decal) and len(location.paintings[0].items) == 3
    assert errors(StyledCompiler(paper_cutout(), W, H).compile(location, "s")) == []
    spec["paint"][0]["items"] = [{"kind": "spray"}]
    path.write_text(json.dumps(spec))
    with pytest.raises(ValueError, match="not 'spray'"):
        Blueprint.load(path).build()


def test_a_decal_centres_its_outline_and_cannot_cast_a_shadow():
    decal = Decal(((0, 0), (2, 0), (2, 1), (0, 1)))
    assert decal.half_extents() == pytest.approx(Vec3(1, 0.5, 0.002)) and decal.casts_shadow is False
    assert decal.geometry(100)["path"].startswith("M-100.00 50.00L100.00 50.00")


def test_a_box_has_six_slabs_flush_with_its_faces():
    box = Box((2, 4, 6))
    slabs = box.facets()
    assert len(slabs) == 6
    for slab, normal in slabs:
        normal = tuple(normal)
        axis = [i for i, v in enumerate(normal) if v][0]
        outer = tuple(slab.at)[axis] + normal[axis] * tuple(slab.half_extents())[axis]
        assert outer == pytest.approx(normal[axis] * (2, 4, 6)[axis] / 2)
        others = [tuple(slab.size)[i] for i in range(3) if i != axis]
        assert others == [(2, 4, 6)[i] for i in range(3) if i != axis]


def test_round_solids_get_a_cap_for_each_flat_end():
    assert len(Cylinder(1, 2).facets()) == 3 and len(Cone(1, 2).facets()) == 2 and len(Sphere(1).facets()) == 1


def surfaces(location: Location, **params) -> list:
    return Ink(**params).surfaces(type("S", (), {"solids": location.solids()})())


def test_sections_of_a_wall_are_one_surface_but_two_objects_are_not():
    location = flat_set()
    location.add(Wall(6, 3, [door(0)], "t.grey", name="wall", yaw=30))
    faces = surfaces(location)
    pieces = len(location.solids())
    assert pieces >= 3 and len({key for _, key in faces}) < len(faces)
    front = Group([Box((1, 1, 0.2), at=(0, 0, 0), material="t.red", name="a")], name="one")
    other = Group([Box((1, 1, 0.2), at=(1, 0, 0), material="t.red", name="b")], name="two")
    location = flat_set()
    location.add(front), location.add(other)
    a, b = [{key for leaf, key in surfaces(location) if leaf.path.startswith(name)} for name in ("one", "two")]
    assert not a & b


def test_a_plane_on_a_rounding_boundary_is_still_one_surface():
    """Slab centres used to land on x.xx5, so coplanar faces rounded apart and fought in two colours."""
    location = flat_set()
    location.add(Group([Box((1, 1, 1), at=(0, 0.5, 0), material="t.red", name="a"),
                        Box((1, 1, 1), at=(1, 0.5, 0), material="t.red", name="b")], name="set"))
    tops = {key for leaf, key in surfaces(location) if "[0.0, 1.0, 0.0]" in key}
    assert len(tops) == 1


@pytest.mark.parametrize("creases", [True, False])
def test_ink_does_not_move_a_solid(creases):
    """A solid's own transform is already in its world: applying it again put outlines in the wrong place."""
    location = flat_set()
    location.add(Cylinder(1, 2, material="t.red", at=(3, 1, 2)))
    body = [leaf for leaf, _ in surfaces(location, creases=creases) if leaf.item is location.solids()[0].item]
    assert body[0].world.position == pytest.approx(Vec3(3, 1, 2))


def test_cel_makes_hard_keys_and_leaves_the_location_alone():
    cel = Cel(fill=0.5)
    assert cel.relight(Ambient(0.8)).intensity == 0.4
    sun = Sun(3, shadows=False, softness=0.6)
    assert (cel.relight(sun).shadows, cel.relight(sun).softness) == (True, 0.0) and sun.shadows is False


def test_a_lamp_does_not_shadow_its_own_bulb():
    location = flat_set()
    shade, far = Box((0.3, 0.3, 0.3), at=(0, 2, 0)), Box((1, 1, 1), at=(5, 2, 0))
    location.add(Group([shade, far]))
    location.add(Point(5, at=(0, 2, 0)))
    leaves = location.solids()
    assert touches(leaves[0], Vec3(0, 2, 0)) and not touches(leaves[1], Vec3(0, 2, 0))
    location.add(Box((1, 1, 1), material="t.red"))
    scene = StyledCompiler(Look([Cel()]), W, H).compile(location, "front")
    assert [o.castShadow for o in deep(scene, "object3D")[:2]] == [False, True]


def test_flat_colours():
    flat = Flat({"stock.wood": "#111111", "stock.wood.oak": "#222222"})
    assert flat.color("stock.wood.oak", Material("#ffffff")) == "#222222"
    assert flat.color("stock.wood.ash", Material("#ffffff")) == "#111111"
    assert Flat().color("x", Material("#404040", glow="#ffcc00")) == "#ffcc00"
    assert vivid("#808080", 2, 1) == "#808080" and vivid("#ff0000", 1, 0.5) == "#800000"


def test_a_look_compiles_to_the_same_bytes_every_time():
    location = Registry.default().archetypes.get("stock.street")().build(Registry.default(), seed=4, length=20)
    first, second = [StyledCompiler(ink_toon(), W, H).compile(location, "street-level").to_bytes() for _ in range(2)]
    assert first == second


def test_an_empty_location_is_still_a_valid_document():
    location = Location("empty")
    location.shot("s", (0, 1, -5), (0, 1, 0))
    assert errors(StyledCompiler(ink_toon(), W, H).compile(location, "s")) == []


def test_a_plugin_can_add_a_pass_that_changes_the_light():
    class Dim(Pass):
        def add(self, stage):
            pass

        def relight(self, light):
            return Ambient(0.1)
    location = flat_set()
    location.add(Ambient(5))
    scene = StyledCompiler(Look([Dim()]), W, H).compile(location, "front")
    assert deep(scene, "light")[0].intensity == 0.1


def test_the_stock_looks_are_render_modes():
    registry = Registry.default()
    assert isinstance(registry.modes.get("stock.ink-toon")(width=W, height=H), Styled)
    assert isinstance(registry.modes.get("stock.paper-cutout")(), Styled)
    assert sorted(p.name for p in SHADERS.glob("*.fs")) == ["cel.fs", "clean.fs", "ink.fs"]


def wall_set() -> Location:
    location = flat_set()
    location.add(Box((12, 8, 0.2), at=(0, 1, 3), material="t.grey", name="wall"))
    return location


def test_a_decal_is_hidden_by_what_stands_in_front_of_it(tmp_path):
    location = wall_set()
    location.add(Decal(((-1.5, -0.8), (1.5, -0.8), (1.5, 0.8), (-1.5, 0.8)), material="t.red", at=(0, 1, 2.89)))
    location.add(Box((1, 2, 0.2), at=(-0.75, 1, 1), material="t.blue", name="post"))
    rows = stage(Styled(Look([Flat()]), W, H, 1), location, "front", tmp_path)
    camera = view()
    assert near(pixel(rows, *camera.pixel(Vec3(0.9, 1, 2.89))), RED)
    assert near(pixel(rows, *camera.pixel(Vec3(-0.75, 1, 1))), BLUE)


def test_a_world_mark_stays_on_its_point_in_two_shots(tmp_path):
    """The promise of a paintover: a green mark at a sphere's centre, seen from two sides, is still on the sphere."""
    location = flat_set()
    location.add(Sphere(1, material="t.red", at=(1, 1, 1)))
    location.shot("side", (5, 2, -3), (0, 1, 1), lens=30)
    location.paint("p").disc((1, 1, 1), 0.2, color=GREEN)
    mode = Styled(Look([Flat()]), W, H, 1)
    for shot in ("front", "side"):
        rows = stage(mode, location, shot, tmp_path)
        camera = Projection(location.shots[shot], W, H)
        x, y = camera.pixel(Vec3(1, 1, 1))
        assert near(pixel(rows, x, y), GREEN)
        rim = camera.pixels_per_metre(Vec3(1, 1, 1)) * 0.6
        assert near(pixel(rows, x + rim, y), RED) and near(pixel(rows, x - rim, y), RED)


def test_a_picture_covers_the_whole_frame(tmp_path):
    location = wall_set()
    location.paint("final").picture(solid_png(tmp_path / "over.png", b"\0\xff\0\xff"))
    rows = stage(Styled(Look([Flat()]), W, H, 1), location, "front", tmp_path)
    assert all(near(pixel(rows, x, y), GREEN) for x, y in ((1, 1), (W - 2, 1), (1, H - 2), (W - 2, H - 2), (W / 2, H / 2)))


def test_cel_shadows_are_two_tones_and_follow_the_light(tmp_path):
    location = flat_set()
    location.add(Box((30, 0.2, 30), at=(0, -0.1, 0), material="t.grey", name="ground"))
    location.add(Box((1, 2, 1), at=(0, 1, 0), material="t.red", name="post"))
    location.add(Sun(3, yaw=90, pitch=-45))
    location.add(Ambient(0.8))
    location.shot("above", (0, 9, -7), (0, 0, 0), lens=30)
    rows = stage(Styled(Look([Flat(), Cel(cut=0.5, shade="#404040")]), W, H, 2), location, "above", tmp_path)
    camera = Projection(location.shots["above"], W, H)
    shadow = pixel(rows, *camera.pixel(Vec3(1.5, 0, 0)))
    lit = pixel(rows, *camera.pixel(Vec3(-3, 0, 0)))
    assert near(lit, GREY) and near(shadow, "#222222", 16)
    row = rows[int(camera.pixel(Vec3(1.5, 0, 0))[1])]
    tones = {row[i] for i in range(0, W * 3, 3)}
    assert sum(1 for tone in tones if sum(row[i] == tone for i in range(0, W * 3, 3)) > 4) <= 3


def test_ink_stops_behind_what_hides_it(tmp_path):
    """Lines come from the depth buffer: a far box's edge is inked until a near box covers it."""
    location = flat_set()
    location.add(Box((4, 2, 0.5), at=(0, 1, 3), material="t.grey", name="far"))
    location.add(Box((1, 3, 0.5), at=(0, 1, 0), material="t.blue", name="near"))
    rows = stage(Styled(Look([Flat(), Ink(width=2)]), W, H, 2), location, "front", tmp_path)
    camera = view()
    top = camera.pixel(Vec3(1.5, 2, 2.75))
    assert sum(near(pixel(rows, top[0], top[1] + d), "#000000", 70) for d in (-1, 0, 1)) >= 1
    hidden = camera.pixel(Vec3(0, 2, 2.75))
    assert all(near(pixel(rows, hidden[0], hidden[1] + d), BLUE) for d in (-1, 0, 1))


def test_ink_draws_a_crease_inside_one_box(tmp_path):
    location = flat_set()
    location.add(Box((2, 2, 2), at=(0, 1, 0), yaw=40, material="t.grey", name="cube"))
    plain = stage(Styled(Look([Flat()]), W, H, 2), location, "front", tmp_path)
    inked = stage(Styled(Look([Flat(), Ink()]), W, H, 2), location, "front", tmp_path)
    corner = location.solids()[0].world.apply((1, 0, -1))
    x, y = view().pixel(corner)
    assert near(pixel(plain, x, y), GREY)
    assert any(near(pixel(inked, x + d, y), "#000000", 70) for d in (-2, -1, 0, 1, 2))


def test_the_example_sets_validate_in_every_look():
    import paintover
    registry = Registry.default()
    room, town = paintover.living_room(registry), paintover.town(registry)
    assert room.validate() == [] and town.validate() == []
    for location, shot in ((room, "corner"), (town, "town")):
        for look in (ink_toon(paintover.HOME), paper_cutout(paintover.TOWN)):
            assert errors(StyledCompiler(look, W, H).compile(location, shot)) == []


def half_png(path: Path) -> Path:
    """Left half red, right half blue, in 8 x 8 pixels: one repeat shows as one red and one blue band."""
    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))
    rows = (b"\0" + b"\xff\0\0" * 4 + b"\0\0\xff" * 4) * 8
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 8, 8, 8, 2, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))
    return path


def materials(scene) -> dict:
    return {node.id: node for node in deep(scene, "material")}


def test_a_look_changes_a_surface_without_changing_the_location(tmp_path):
    location = flat_set()
    location.add(Box((4, 3, 0.2), at=(0, 1.5, 3), material="t.grey"))
    before = (location.registry.materials.get("t.grey"), len(location.solids()), location.solids()[0].item.material)
    picture = solid_png(tmp_path / "red.png", b"\xff\0\0\xff")
    look = Look([Flat()], textures={"t.": Texture(picture, tile=1.0)}, materials={"t.grey": "t.blue"})
    scene = StyledCompiler(look, W, H).compile(location, "front")
    assert not errors(scene)
    assert all(material.baseColorMap == str(picture.resolve()) for material in materials(scene).values())
    assert (location.registry.materials.get("t.grey"), len(location.solids()), location.solids()[0].item.material) == before


def test_flat_keeps_a_materials_own_picture_and_its_uv_scale(tmp_path):
    location = flat_set()
    picture = solid_png(tmp_path / "red.png", b"\xff\0\0\xff")
    location.registry.materials.add("t.map", Material("#ffffff", maps={"baseColorMap": str(picture)}, extra={"uvScaleX": 2}))
    location.add(Box((4, 3, 0.2), at=(0, 1.5, 3), material="t.map"))
    found = materials(StyledCompiler(Look([Flat()]), W, H).compile(location, "front"))["flat-t-map"]
    assert found.baseColorMap == str(picture.resolve()) and found.uvScaleX == 2 and found.unlit


def test_a_map_shows_in_a_cartoon_look(tmp_path):
    location = flat_set()
    picture = solid_png(tmp_path / "red.png", b"\xff\0\0\xff")
    location.registry.materials.add("t.map", Material("#ffffff", maps={"baseColorMap": str(picture)}))
    location.add(Box((6, 4, 0.2), at=(0, 1, 3), material="t.map"))
    rows = stage(Styled(Look([Flat()], sky=GREEN), W, H, 1), location, "front", tmp_path)
    assert near(pixel(rows, W / 2, H / 2), RED) and near(pixel(rows, 3, 3), GREEN)


def test_a_texture_multiplies_the_colour_unless_tinted(tmp_path):
    location = flat_set()
    location.add(Box((6, 4, 0.2), at=(0, 1, 3), material="t.grey"))
    picture = solid_png(tmp_path / "white.png", b"\xff\xff\xff\xff")
    plain = stage(Styled(Look([Flat()], textures={"": Texture(picture)}), W, H, 1), location, "front", tmp_path)
    tinted = stage(Styled(Look([Flat()], textures={"": Texture(picture, tint=BLUE)}), W, H, 1), location, "front", tmp_path)
    assert near(pixel(plain, W / 2, H / 2), GREY) and near(pixel(tinted, W / 2, H / 2), BLUE)


def bands(rows: list[bytes], y: float, x0: int = 0, x1: int = W) -> int:
    """How many times the row changes from red to blue or back."""
    tints = [pixel(rows, x, y) for x in range(x0, x1)]
    names = ["r" if red > blue + 60 else "b" if blue > red + 60 else "" for red, _, blue in tints]
    names = [name for name in names if name]
    return sum(a != b for a, b in zip(names, names[1:]))


def test_a_texture_keeps_its_real_size_on_solids_of_any_size(tmp_path):
    picture = half_png(tmp_path / "half.png")
    look = Look([Flat()], textures={"": Texture(picture, tile=1.0)})
    counts = []
    for width in (2.0, 6.0):
        location = flat_set()
        location.shot("square", (0, 1, -5), (0, 1, 3), lens=14)
        location.add(Box((width, 3, 0.2), at=(0, 1, 3), material="t.grey"))
        counts.append(bands(stage(Styled(look, W, H, 1), location, "square", tmp_path), H / 2))
    assert counts[1] - counts[0] == 8  # four repeats more, each a pair of bands, wherever in the picture the box begins


def test_a_box_gives_each_face_its_real_size_across_and_up():
    box = Box((6, 1, 2))
    assert sorted((round(a, 3), round(b, 3)) for _, a, b in box.spans()) == [
        (2, 1), (2, 1), (6, 1), (6, 1), (6, 2), (6, 2)]


@pytest.mark.parametrize("solid", [Box((3, 1, 2)), Cylinder(0.5, 2), Cone(0.5, 1.5), Sphere(0.6)])
def test_tiled_panels_cover_their_solid_and_stay_inside_it(solid):
    low, high = solid.bounds(solid.transform)
    for part, across, up in solid.spans():
        assert across > 0 and up > 0
        world = solid.transform if part is solid else solid.transform.then(part.transform)
        part_low, part_high = part.bounds(world)
        assert all(a >= b - 0.002 for a, b in zip(part_low, low)) and all(a <= b + 0.002 for a, b in zip(part_high, high))


def test_every_box_face_stands_its_picture_upright(tmp_path):
    """Horizontal stripes must stay horizontal on a wall facing x as on one facing z: u across, v up."""
    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))
    rows = (b"\0" + b"\xff\0\0" * 8) * 4 + (b"\0" + b"\0\0\xff" * 8) * 4
    picture = tmp_path / "stripes.png"
    picture.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 8, 8, 8, 2, 0, 0, 0))
                        + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))
    location = flat_set()
    location.add(Box((0.2, 3, 8), at=(-0.1, 1, 3), material="t.grey"))  # a side wall, its +x face toward the camera
    location.shot("side", (5, 1, 3), (0, 1, 3), lens=20)
    shot = stage(Styled(Look([Flat()], textures={"": Texture(picture, tile=1.0)}), W, H, 1), location, "side", tmp_path)
    down = [pixel(shot, W / 2, y) for y in range(H)]
    along = [pixel(shot, x, H * 0.4) for x in range(W)]  # H / 2 is y = 1, exactly where two stripes meet
    changes = lambda line: sum((a[0] > a[2]) != (b[0] > b[2]) for a, b in zip(line, line[1:]))
    assert changes(down) >= 3 and changes(along) == 0


def test_a_look_can_use_a_catalog_shader_by_name():
    location = flat_set()
    location.registry.materials.add("studio.copper@1", Material("#c06030", metallic=1.0, roughness=0.3))
    location.add(Box((4, 3, 0.2), at=(0, 1.5, 3), material="t.grey"))
    scene = StyledCompiler(Look([Lit()], materials={"t.grey": "studio.copper@1"}), W, H).compile(location, "front")
    found = materials(scene)["lit-t-grey"]
    assert found.baseColor == "#c06030" and found.metallic == 1
    assert not errors(scene)


def test_a_look_can_use_a_material_of_its_own(tmp_path):
    location = flat_set()
    location.add(Box((6, 4, 0.2), at=(0, 1, 3), material="t.grey"))
    rows = stage(Styled(Look([Flat()], materials={"t.": Material(RED)}), W, H, 1), location, "front", tmp_path)
    assert near(pixel(rows, W / 2, H / 2), RED)


def test_lit_keeps_the_rig_and_casts_shadows():
    location = flat_set()
    location.add(Box((4, 3, 0.2), at=(0, 1.5, 3), material="t.grey"))
    location.rig("stock.interior")
    scene = StyledCompiler(Look([Lit()]), W, H).compile(location, "front")
    assert deep(scene, "light") and deep(scene, "object3D")[0].castShadow


def test_the_longest_prefix_wins_and_nothing_matches_nothing():
    table = {"": "any", "stock.": "stock", "stock.wood": "wood"}
    assert [lookup(table, n) for n in ("x", "stock.glass", "stock.wood.oak")] == ["any", "stock", "wood"]
    assert lookup({"a": 1}, "b") is None


def test_a_texture_says_what_is_wrong_with_it(tmp_path):
    with pytest.raises(FileNotFoundError):
        Texture(tmp_path / "missing.png")
    with pytest.raises(ValueError):
        Texture(solid_png(tmp_path / "red.png", b"\xff\0\0\xff"), tile=0)


def test_textured_looks_compile_the_same_twice(tmp_path):
    location = flat_set()
    location.add(Box((4, 3, 2), at=(0, 1.5, 3), material="t.grey"))
    location.add(Cylinder(0.5, 2, at=(2, 1, 1), material="t.red"))
    look = Look([Flat(), Ink()], textures={"": Texture(solid_png(tmp_path / "red.png", b"\xff\0\0\xff"), tile=0.5)})
    first, second = (StyledCompiler(look, W, H).compile(location, "front").to_bytes() for _ in range(2))
    assert first == second and not errors(StyledCompiler(look, W, H).compile(location, "front"))


def paints(location: Location, compiler) -> list:
    return [node.id for node in deep(compiler.compile(location, "front"), "group") if node.id.startswith("paint-")]


def test_paint_shows_only_in_its_looks():
    location = flat_set()
    location.add(Box((4, 3, 0.2), at=(0, 1.5, 3), material="t.grey"))
    location.paint("any").disc((0.5, 0.5), 0.1, frame=True)
    location.paint("toon only", looks=["stock.ink-toon"]).disc((0.5, 0.5), 0.1, frame=True)
    location.paint("shaded only", looks=["stock.shaded"]).disc((0.5, 0.5), 0.1, frame=True)
    location.paint("wire only", looks=["stock.wireframe"]).disc((0.5, 0.5), 0.1, frame=True)
    assert paints(location, StyledCompiler(ink_toon(), W, H)) == ["paint-0", "paint-1"]
    assert paints(location, SceneCompiler(W, H)) == ["paint-0", "paint-2"]
    assert paints(location, WireframeCompiler(W, H)) == ["paint-0", "paint-3"]
    assert paints(location, StyledCompiler(Look([Flat()], name="other"), W, H)) == ["paint-0"]


def test_paint_limited_to_a_look_changes_the_pixels(tmp_path):
    location = flat_set()
    location.add(Box((6, 4, 0.2), at=(0, 1, 3), material="t.grey"))
    location.paint("mark", looks=["one"]).disc((0.5, 0.5), 0.2, color=RED, frame=True)
    one = stage(Styled(Look([Flat()], name="one"), W, H, 1), location, "front", tmp_path)
    two = stage(Styled(Look([Flat()], name="two"), W, H, 1), location, "front", tmp_path)
    assert near(pixel(one, W / 2, H / 2), RED) and near(pixel(two, W / 2, H / 2), GREY)


def test_shots_and_looks_limit_a_layer_together():
    location = flat_set()
    location.add(Box((4, 3, 0.2), at=(0, 1.5, 3), material="t.grey"))
    location.shot("other", (0, 1, -4), (0, 1, 3))
    location.paint("both", shots=["other"], looks=["one"]).disc((0.5, 0.5), 0.1, frame=True)
    assert paints(location, StyledCompiler(Look([Flat()], name="one"), W, H)) == []
    assert paints(location, StyledCompiler(Look([Flat()], name="two"), W, H)) == []


def test_a_decal_shows_only_in_its_looks(tmp_path):
    location = flat_set()
    location.add(Box((6, 4, 0.2), at=(0, 1, 3), material="t.grey"))
    square = ((-1, -1), (1, -1), (1, 1), (-1, 1))
    location.add(Decal(square, material="t.red", looks=["one"], at=(0, 1, 2.89)))
    one = stage(Styled(Look([Flat()], name="one"), W, H, 1), location, "front", tmp_path)
    two = stage(Styled(Look([Flat()], name="two"), W, H, 1), location, "front", tmp_path)
    assert near(pixel(one, W / 2, H / 2), RED) and near(pixel(two, W / 2, H / 2), GREY)
    assert len(deep(SceneCompiler(W, H).compile(location, "front"), "object3D")) == 1
    assert not errors(SceneCompiler(W, H).compile(location, "front"))


def test_a_look_limit_comes_through_a_blueprint(tmp_path):
    spec = {"name": "b", "paint": [{"name": "toon", "looks": ["stock.ink-toon"],
                       "items": [{"kind": "disc", "center": [0.5, 0.5], "radius": 0.1, "frame": True}]}]}
    location = Blueprint(spec).build(Registry.default())
    assert location.paintings[0].looks == ["stock.ink-toon"]


def test_an_unknown_look_name_is_a_warning_and_a_known_one_is_not():
    location = flat_set()
    location.add(Box((4, 3, 0.2), at=(0, 1.5, 3), material="t.grey"))
    location.paint("typo", looks=["stock.ink-tune"]).disc((0.5, 0.5), 0.1, frame=True)
    location.add(Decal(((0, 0), (1, 0), (1, 1)), material="t.red", looks=["stock.shaded", "nope"], at=(0, 1, 2.8)))
    issues = [issue for issue in location.validate() if issue.code == "look-unknown"]
    assert len(issues) == 2 and {issue.severity for issue in issues} == {"warning"}
    assert "stock.ink-tune" in issues[1].message + issues[0].message


def test_every_stock_look_is_named_after_its_mode():
    registry = Registry.default()
    for name in ("stock.ink-toon", "stock.paper-cutout"):
        assert registry.modes.get(name)().look.name == name


def test_the_textured_example_runs_end_to_end(tmp_path):
    import texture_looks
    assert texture_looks.textures()["hatch"].is_file()
    registry = Registry.default()
    styles = texture_looks.looks(texture_looks.textures())
    room = texture_looks.living_room(registry, ("example.comic",))
    texture_looks.annotate(room)
    for look in styles.values():
        assert not errors(StyledCompiler(look, W, H).compile(room, "wide"))
    assert not errors(SceneCompiler(W, H).compile(room, "wide"))
