"""Imported models. Where a model lands and what colour its parts come out only exist in the pixels, so these render."""
import base64
import json
import math
import struct
import sys
from pathlib import Path

import pytest
from sr_core.vpkg import archive as vpkg

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]

from srlocations import (Box, Cel, Flat, Group, Ink, Lit, Look, Material, Mesh, MeshError, Projection, Registry, Renderer,
                         SceneCompiler, Shaded, Styled, Texture, Vec3, Wireframe, WireframeCompiler, read_model)
from srlocations.location import Location, Shot
from srlocations.collision import overlap
from srlocations.geometry import Transform
from srlocations.mesh import MODEL, PIECES, tone
from srlocations.nodes import Sun
from srlocations.portable import bundle, package
from test_looks import BLUE, GREEN, GREY, H, RED, W, deep, errors, flat_set, near, pixel, solid_png, stage

CORNERS = [(-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1), (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)]
FACES = [(1, 4, 3, 2), (5, 6, 7, 8), (1, 2, 6, 5), (2, 3, 7, 6), (3, 4, 8, 7), (4, 1, 5, 8)]


def obj_box(lines: list[str], name: str, material: str, center, half, count: int) -> int:
    lines += [f"o {name}", f"usemtl {material}"]
    lines += [f"v {center[0] + a * half[0]} {center[1] + b * half[1]} {center[2] + c * half[2]}" for a, b, c in CORNERS]
    lines += ["f " + " ".join(str(count + i) for i in face) for face in FACES]
    return count + 8


def two_parts(folder: Path, name: str = "pair") -> Path:
    """A red box at the model's origin and a green one 1.5 m along its +z, standing on y=0."""
    (folder / f"{name}.mtl").write_text("newmtl paint\nKd 1 0 0\nnewmtl other\nKd 0 1 0\n")
    lines = [f"mtllib {name}.mtl"]
    count = obj_box(lines, "first", "paint", (0, 0.5, 0), (0.5, 0.5, 0.5), 0)
    obj_box(lines, "second", "other", (0, 0.5, 1.5), (0.5, 0.5, 0.5), count)
    path = folder / f"{name}.obj"
    path.write_text("\n".join(lines) + "\n")
    return path


def gltf_document(buffer: dict) -> dict:
    return {"asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0]}], "buffers": [buffer],
            "nodes": [{"name": "root", "children": [1], "translation": [0, 0.5, 0]},
                      {"name": "body", "mesh": 0, "scale": [2, 1, 1]}],
            "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 1, "material": 0}]}],
            "materials": [{"name": "skin", "pbrMetallicRoughness": {"baseColorFactor": [0, 0, 1, 1]}}],
            "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": 96},
                            {"buffer": 0, "byteOffset": 96, "byteLength": 72}],
            "accessors": [{"bufferView": 0, "componentType": 5126, "count": 8, "type": "VEC3", "min": [-.5] * 3, "max": [.5] * 3},
                          {"bufferView": 1, "componentType": 5125, "count": 36, "type": "SCALAR"}]}


def cube_bytes() -> bytes:
    points = b"".join(struct.pack("<3f", *(value * 0.5 for value in corner)) for corner in CORNERS)
    triangles = [(a - 1, b - 1, c - 1) for face in FACES for a, b, c in ((face[0], face[1], face[2]), (face[0], face[2], face[3]))]
    return points + b"".join(struct.pack("<3I", *triangle) for triangle in triangles)


def glb_cube(folder: Path) -> Path:
    data = cube_bytes()
    text = json.dumps(gltf_document({"byteLength": len(data)})).encode()
    text += b" " * (-len(text) % 4)
    body = struct.pack("<II", len(text), 0x4E4F534A) + text + struct.pack("<II", len(data), 0x004E4942) + data
    path = folder / "cube.glb"
    path.write_bytes(b"glTF" + struct.pack("<II", 2, 12 + len(body)) + body)
    return path


def lit_set(folder: Path, *nodes) -> Location:
    location = flat_set()
    for node in nodes:
        location.add(node)
    location.rig("stock.interior")
    return location


def spot(location: Location, shot: str, point) -> tuple[float, float]:
    return Projection(location.shots[shot], W, H).pixel(Vec3.of(point))


FLAT = Styled(Look([Flat()], sky=GREY), W, H, supersample=1)


def test_an_obj_is_read_in_the_sdk_frame_and_keeps_its_material_names(tmp_path):
    model = read_model(two_parts(tmp_path))
    assert (model.low, model.high) == (Vec3(-0.5, 0, -2), Vec3(0.5, 1, 0.5))  # the model's +z comes out as -z
    assert model.tones == {"paint": "#ff0000", "other": "#00ff00"}


def test_a_node_limits_what_is_read(tmp_path):
    model = read_model(two_parts(tmp_path), "first")
    assert (model.low, model.high) == (Vec3(-0.5, 0, -0.5), Vec3(0.5, 1, 0.5))
    assert list(model.tones) == ["paint"]
    with pytest.raises(MeshError, match="first, second"):
        read_model(two_parts(tmp_path), "third")


def test_a_glb_is_read_through_its_node_transforms(tmp_path):
    model = read_model(glb_cube(tmp_path))
    assert (model.low, model.high) == (Vec3(-1, 0, -0.5), Vec3(1, 1, 0.5))
    assert model.tones == {"skin": tone(0, 0, 1)}


def test_a_gltf_can_keep_its_buffer_inline_or_beside_it(tmp_path):
    data = cube_bytes()
    inline = tmp_path / "inline.gltf"
    inline.write_text(json.dumps(gltf_document({"byteLength": len(data),
                                                "uri": "data:application/octet-stream;base64," + base64.b64encode(data).decode()})))
    (tmp_path / "beside.bin").write_bytes(data)
    beside = tmp_path / "beside.gltf"
    beside.write_text(json.dumps(gltf_document({"byteLength": len(data), "uri": "beside.bin"})))
    assert read_model(inline).high == read_model(beside).high == Vec3(1, 1, 0.5)


def test_a_chosen_node_drops_its_own_transform_as_the_engine_does(tmp_path):
    assert read_model(glb_cube(tmp_path), "body").high == Vec3(0.5, 0.5, 0.5)
    assert read_model(glb_cube(tmp_path), "root").high == Vec3(1, 0.5, 0.5)


def test_scale_reaches_the_bounds_and_the_engine(tmp_path):
    mesh = Mesh(two_parts(tmp_path), scale=(2, 3, 1), at=(1, 0, 0))
    low, high = mesh.bounds(mesh.transform)
    assert (low, high) == (Vec3(0, 0, -2), Vec3(2, 3, 0.5))
    drawn = deep(SceneCompiler().compile(with_shot(mesh), "s"), "object3D")[0]
    assert (drawn.scaleX, drawn.scaleY) == (2, 3)


def with_shot(*nodes) -> Location:
    location = Location("t", Registry.default())
    for node in nodes:
        location.add(node)
    location.shot("s", (0, 1, -6), (0, 1, 0), lens=30)
    return location


def test_a_model_lands_where_the_sdk_says_it_does(tmp_path):
    location = flat_set()
    location.add(Mesh(two_parts(tmp_path), at=(0, 0, 3), yaw=90))  # yawed, so the second box lies to one side
    rows = stage(FLAT, location, "front", tmp_path)
    first, second = spot(location, "front", (0, 0.5, 3)), spot(location, "front", (-1.5, 0.5, 3))
    assert near(pixel(rows, *first), RED) and near(pixel(rows, *second), GREEN)
    assert near(pixel(rows, *spot(location, "front", (1.5, 0.5, 3))), GREY)


def test_a_mesh_keeps_its_own_materials_when_shaded(tmp_path):
    location = lit_set(tmp_path, Mesh(two_parts(tmp_path)))
    drawn = deep(SceneCompiler().compile(location, "front"), "object3D")[0]
    assert drawn.material is None and drawn.materialOverride is None and drawn.primitive == "mesh"
    assert location.validate() == []


def test_one_material_replaces_them_all(tmp_path):
    location = flat_set()
    location.add(Mesh(two_parts(tmp_path), at=(0, 0, 3), material="t.blue", yaw=90))
    rows = stage(FLAT, location, "front", tmp_path)
    assert near(pixel(rows, *spot(location, "front", (0, 0.5, 3))), BLUE)
    assert near(pixel(rows, *spot(location, "front", (-1.5, 0.5, 3))), BLUE)


def test_slots_replace_one_part_and_leave_the_other(tmp_path):
    location = flat_set()
    location.add(Mesh(two_parts(tmp_path), at=(0, 0, 3), materials={"other": "t.blue"}, yaw=90))
    rows = stage(FLAT, location, "front", tmp_path)
    assert near(pixel(rows, *spot(location, "front", (0, 0.5, 3))), RED)
    assert near(pixel(rows, *spot(location, "front", (-1.5, 0.5, 3))), BLUE)


def test_shaded_writes_only_the_slots_it_replaces(tmp_path):
    location = lit_set(tmp_path, Mesh(two_parts(tmp_path), materials={"other": "t.blue"}))
    drawn = deep(SceneCompiler().compile(location, "front"), "object3D")[0]
    assert drawn.materialOverride == "other:t-blue" and drawn.material is None


def test_a_flat_pass_reads_part_colours_from_the_file_and_a_palette_can_change_them(tmp_path):
    location = flat_set()
    location.add(Mesh(two_parts(tmp_path, "sofa"), at=(0, 0, 3), yaw=90))
    rows = stage(Styled(Look([Flat({"sofa.other": BLUE})], sky=GREY), W, H, supersample=1), location, "front", tmp_path)
    assert near(pixel(rows, *spot(location, "front", (0, 0.5, 3))), RED)
    assert near(pixel(rows, *spot(location, "front", (-1.5, 0.5, 3))), BLUE)


def test_a_look_can_texture_one_part_of_a_model(tmp_path):
    location = flat_set()
    location.add(Mesh(two_parts(tmp_path, "sofa"), at=(0, 0, 3), yaw=90))
    painted = solid_png(tmp_path / "blue.png", b"\x00\x00\xff\xff")
    mode = Styled(Look([Flat(saturation=0)], textures={"sofa.paint": Texture(painted, tile=None)}), W, H, supersample=1)
    found = [m for m in deep(mode.compiler().compile(location, "front"), "material") if m.baseColorMap]
    assert len(found) == 1 and found[0].id == "flat-sofa-paint"


def test_lit_leaves_a_model_alone_until_a_look_names_a_part(tmp_path):
    location = lit_set(tmp_path, Mesh(two_parts(tmp_path, "sofa")))
    plain = deep(Styled(Look([Lit()]), W, H).compiler().compile(location, "front"), "object3D")[0]
    assert plain.material is None and plain.materialOverride is None
    swapped = Styled(Look([Lit()], materials={"sofa.other": Material(BLUE)}), W, H).compiler().compile(location, "front")
    assert deep(swapped, "object3D")[0].materialOverride == "other:lit-sofa-other"


def test_ink_divides_a_models_parts(tmp_path):
    location = flat_set()
    location.add(Mesh(two_parts(tmp_path), at=(0, 0, 3)))
    drawn = deep(Styled(Look([Ink()]), W, H).compiler().compile(location, "front"), "object3D")[0]
    pairs = dict(pair.split(":") for pair in drawn.materialOverride.split())
    assert set(pairs) == {"paint", "other"} and pairs["paint"] != pairs["other"]


def test_every_pass_compiles_to_a_valid_document(tmp_path):
    location = lit_set(tmp_path, Mesh(two_parts(tmp_path)))
    look = Look([Lit(), Flat(), Cel(), Ink()])
    assert errors(Styled(look, W, H).compiler().compile(location, "front")) == []
    assert errors(SceneCompiler().compile(location, "front")) == []


def test_a_wireframe_draws_a_models_edges_and_not_its_box(tmp_path):
    path = two_parts(tmp_path)
    mesh = Mesh(path)
    assert len(mesh.edges()) == 24  # two boxes, twelve edges each: the square faces' diagonals are not creases
    location = with_shot(mesh)
    rows = stage(Wireframe(W, H), location, "s", tmp_path)
    assert any(any(row) for row in rows)
    assert errors(WireframeCompiler(W, H).compile(location, "s")) == []


def test_a_misspelled_slot_is_reported(tmp_path):
    registry = Registry.default()
    location = Location("slots", registry)
    location.add(Mesh(two_parts(tmp_path), materials={"nope": "stock.fabric.rust", "two words": "stock.fabric.rust"}))
    codes = {issue.code for issue in location.validate()}
    assert {"model-slot-unknown", "model-slot-unnamed"} <= codes


def test_one_material_over_named_slots_is_reported(tmp_path):
    location = Location("slots", Registry.default())
    location.add(Mesh(two_parts(tmp_path), material="stock.fabric.rust", materials={"red": "stock.fabric.teal"}))
    assert "model-slots-ignored" in {issue.code for issue in location.validate()}


def test_a_smooth_model_still_has_an_outline_in_a_wireframe(tmp_path):
    rings = [[(0.5 * math.cos(math.tau * i / 32), y, 0.5 * math.sin(math.tau * i / 32)) for i in range(32)] for y in (0, 1)]
    lines = [f"v {x} {y} {z}" for ring in rings for x, y, z in ring]
    lines += [f"f {i + 1} {i + 33} {(i + 1) % 32 + 33} {(i + 1) % 32 + 1}" for i in range(32)]
    path = tmp_path / "tube.obj"
    path.write_text("\n".join(lines) + "\n")
    drawn = Mesh(path).edges()
    upright = [line for line in drawn if abs(line[0][1] - line[1][1]) == 1]
    assert 2 <= len(upright) <= 8  # a few down each side, and not one of the thirty-two facets
    assert len(drawn) - len(upright) == 64  # and the open rims


def test_a_model_of_a_format_read_only_by_the_engine_needs_a_size(tmp_path):
    path = tmp_path / "scan.fbx"
    path.write_bytes(b"x")
    with pytest.raises(MeshError, match="give the Mesh a size"):
        Mesh(path)
    mesh = Mesh(path, size=(2, 1, 4))
    assert mesh.bounds(mesh.transform) == (Vec3(-1, 0, -2), Vec3(1, 1, 2))
    assert len(mesh.edges()) == 6 and mesh.skins()[0].own is not None  # two rims and four pillars


def test_a_mesh_refuses_a_missing_file_and_an_unknown_format(tmp_path):
    with pytest.raises(FileNotFoundError):
        Mesh(tmp_path / "nothing.obj")
    (tmp_path / "x.stl").write_text("solid")
    with pytest.raises(MeshError, match="the engine reads"):
        Mesh(tmp_path / "x.stl")


def test_a_hollow_model_is_a_set_cameras_can_stand_in(tmp_path):
    path = two_parts(tmp_path)
    inside = Location("t", flat_set().registry)
    inside.add(Mesh(path, at=(0, 0, 0), scale=6, hollow=True))
    inside.shot("in", (0, 1, 0), (0, 1, 3)).mark("here", (0, 0, 0))
    assert inside.validate() == []
    blocked = Location("t", flat_set().registry)
    blocked.add(Mesh(path, at=(0, 0, 0), scale=6))
    blocked.shot("in", (0, 1, 0), (0, 1, 3))
    assert [i.code for i in blocked.validate()] == ["shot-inside-solid"]


def touches(mesh: Mesh, world: Transform, at, size=0.2) -> bool:
    probe = Box(size=(size, size, size)).hulls(Transform.at(at))[0]
    return any(overlap(probe, piece) for piece in mesh.hulls(world))


def test_a_models_body_is_each_of_its_pieces_and_not_its_box(tmp_path):
    mesh, world = Mesh(two_parts(tmp_path)), Transform.at((1, 0, 2), yaw=90)  # the second box lands 1.5 m along -x
    assert len(mesh.hulls(world)) == 2
    assert touches(mesh, world, (1, 0.5, 2)) and touches(mesh, world, (-0.5, 0.5, 2))
    assert not touches(mesh, world, (0.25, 0.5, 2))  # between them, inside their box
    scaled = Mesh(two_parts(tmp_path), scale=2)  # boxes 1 m on a side, 3 m apart, the gap 2 m to 1 m off along -z
    assert touches(scaled, Transform(), (0, 1.5, -2.6)) and not touches(scaled, Transform(), (0, 1, -1.5))


def test_a_model_in_one_piece_is_its_convex_hull(tmp_path):
    path = tmp_path / "wedge.obj"  # a right triangle in x and y, 1 m deep along z
    points = [(0, 0, -0.5), (1, 0, -0.5), (0, 1, -0.5), (0, 0, 0.5), (1, 0, 0.5), (0, 1, 0.5)]
    faces = [(1, 3, 2), (4, 5, 6), (1, 2, 5, 4), (2, 3, 6, 5), (3, 1, 4, 6)]
    path.write_text("".join(f"v {x} {y} {z}\n" for x, y, z in points) + "".join("f " + " ".join(map(str, f)) + "\n" for f in faces))
    mesh = Mesh(path)
    assert len(mesh.hulls(Transform())) == 1
    assert touches(mesh, Transform(), (0.2, 0.2, 0)) and not touches(mesh, Transform(), (0.85, 0.85, 0))


def test_a_model_of_many_pieces_is_one_hull_round_them_all(tmp_path):
    lines: list[str] = []
    count = 0
    for number in range(PIECES + 1):
        count = obj_box(lines, f"leaf{number}", "paint", (number * 0.1, 0.5, 0), (0.02, 0.02, 0.02), count)
    path = tmp_path / "leaves.obj"
    path.write_text("\n".join(lines) + "\n")
    mesh = Mesh(path)
    assert len(mesh.hulls(Transform())) == 1
    assert touches(mesh, Transform(), (3, 0.5, 0), size=0.02)  # between two leaves, inside the one hull


def test_a_model_given_a_size_is_its_box(tmp_path):
    path = tmp_path / "scan.fbx"
    path.write_bytes(b"x")
    mesh = Mesh(path, size=(2, 1, 4))
    assert len(mesh.hulls(Transform())) == 1 and touches(mesh, Transform(), (0.9, 0.9, 1.9))


def textured_model(folder: Path) -> Path:
    (folder / "maps").mkdir(exist_ok=True)
    solid_png(folder / "maps" / "wood.png", b"\xff\x00\x00\xff")
    (folder / "chair.mtl").write_text("newmtl paint\nKd 1 1 1\nmap_Kd maps/wood.png\n")
    lines = ["mtllib chair.mtl"]
    obj_box(lines, "seat", "paint", (0, 0.5, 0), (0.5, 0.5, 0.5), 0)
    path = folder / "chair.obj"
    path.write_text("\n".join(lines) + "\n")
    return path


def test_a_bundle_finds_what_a_model_reads(tmp_path):
    files = bundle(textured_model(tmp_path))
    assert sorted(files) == ["chair.mtl", "chair.obj", "maps/wood.png"]


def test_a_model_reading_outside_its_folder_is_refused(tmp_path):
    (tmp_path / "in").mkdir()
    path = tmp_path / "in" / "x.obj"
    path.write_text("mtllib ../secret.mtl\n")
    with pytest.raises(ValueError, match="outside its folder"):
        bundle(path)


def test_a_model_missing_a_file_it_reads_is_refused(tmp_path):
    path = tmp_path / "x.obj"
    path.write_text("mtllib gone.mtl\n")
    with pytest.raises(FileNotFoundError, match="gone.mtl"):
        bundle(path)


def test_a_package_keeps_a_models_files_together(tmp_path):
    (tmp_path / "source").mkdir()
    location = with_shot(Mesh(textured_model(tmp_path / "source")))
    scene = SceneCompiler().compile(location, "s")
    document = package(scene, tmp_path / "out" / "doc.scene.xml")
    held = sorted(str(p.relative_to(tmp_path / "out")) for p in (tmp_path / "out").rglob("*") if p.is_file())
    folder = held[0].split("/")[1]
    assert held == sorted(["doc.scene.xml", *(f"assets/{folder}/{name}" for name in ("chair.obj", "chair.mtl", "maps/wood.png"))])
    assert f"assets/{folder}/chair.obj" in document.read_text()


def test_a_moved_package_with_a_model_renders_the_same(tmp_path):
    (tmp_path / "source").mkdir()
    location = with_shot(Mesh(textured_model(tmp_path / "source")))
    location.add(Sun(2))
    renderer = Renderer()
    scene = SceneCompiler(W, H, supersample=1).compile(location, "s")
    document = package(scene, tmp_path / "out" / "doc.scene.xml")
    first = renderer.draw(document, tmp_path / "first.png")
    (tmp_path / "out").rename(tmp_path / "moved")
    for path in (tmp_path / "source").rglob("*"):
        path.unlink() if path.is_file() else None
    second = renderer.draw(tmp_path / "moved" / "doc.scene.xml", tmp_path / "second.png")
    assert first.read_bytes() == second.read_bytes()


def test_an_archive_with_a_model_verifies_and_two_copies_of_a_model_give_one_archive(tmp_path):
    for name in ("a", "b"):
        (tmp_path / name).mkdir()
        location = with_shot(Mesh(textured_model(tmp_path / name)))
        Renderer().archive(location, "s", tmp_path / f"{name}.vpkg.zip", Shaded(W, H))
    assert vpkg.verify(str(tmp_path / "a.vpkg.zip")).ok
    assert (tmp_path / "a.vpkg.zip").read_bytes() == (tmp_path / "b.vpkg.zip").read_bytes()


def facing_away(folder: Path, two_sided: bool) -> Path:
    """One upright red quad, 2 m wide and 2 m tall, whose front looks along the model's -z: away from a camera on the set's -z
    side, since a model lands with z negated."""
    points = [(-1, 0, 0), (1, 0, 0), (1, 2, 0), (-1, 2, 0)]
    data = b"".join(struct.pack("<3f", *point) for point in points) + struct.pack("<6H", 0, 2, 1, 0, 3, 2)
    document = {"asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0]}], "nodes": [{"mesh": 0}],
                "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 1, "material": 0}]}],
                "materials": [{"name": "skin", "doubleSided": two_sided,
                               "pbrMetallicRoughness": {"baseColorFactor": [1, 0, 0, 1]}}],
                "buffers": [{"uri": "data:application/octet-stream;base64," + base64.b64encode(data).decode(),
                             "byteLength": len(data)}],
                "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": 48},
                                {"buffer": 0, "byteOffset": 48, "byteLength": 12}],
                "accessors": [{"bufferView": 0, "componentType": 5126, "count": 4, "type": "VEC3",
                               "min": [-1, 0, 0], "max": [1, 2, 0]},
                              {"bufferView": 1, "componentType": 5123, "count": 6, "type": "SCALAR"}]}
    path = folder / f"quad-{two_sided}.gltf"
    path.write_text(json.dumps(document))
    return path


def behind(folder: Path, two_sided: bool) -> Location:
    location = flat_set()
    location.add(Mesh(facing_away(folder, two_sided), at=(0, 0, 0)))
    location.rig("stock.interior")
    location.background = "#00ff00"
    return location


SKY = "#00ff00"
EVERY_PASS = [Look([Lit()], sky=SKY), Look([Flat()], sky=SKY), Look([Cel()], sky=SKY), Look([Lit(), Ink(width=2)], sky=SKY)]


@pytest.mark.parametrize("look", EVERY_PASS, ids=["lit", "flat", "cel", "ink"])
def test_a_face_that_shows_from_behind_shows_in_every_pass(tmp_path, look):
    rows = stage(Styled(look, W, H, 1), behind(tmp_path, True), "front", tmp_path)
    assert not near(pixel(rows, W / 2, H / 2), SKY)


@pytest.mark.parametrize("look", EVERY_PASS, ids=["lit", "flat", "cel", "ink"])
def test_a_face_that_does_not_stays_away_in_every_pass(tmp_path, look):
    rows = stage(Styled(look, W, H, 1), behind(tmp_path, False), "front", tmp_path)
    assert near(pixel(rows, W / 2, H / 2), SKY)


def test_ink_draws_round_a_face_seen_from_behind(tmp_path):
    rows = stage(Styled(Look([Lit(), Ink(width=3)], sky=SKY), W, H, 1), behind(tmp_path, True), "front", tmp_path)
    assert sum(sum(value) < 90 for row in rows for value in zip(*[iter(row)] * 3)) > 100


def test_paint_is_held_out_by_a_face_seen_from_behind(tmp_path):
    location = behind(tmp_path, True)
    location.paint("spot", depth=True).disc((0, 1, 2), 0.5, color=BLUE)
    rows = stage(Shaded(W, H, 1), location, "front", tmp_path)
    assert not near(pixel(rows, W / 2, H / 2), BLUE)


def test_a_model_says_which_of_its_materials_show_from_behind(tmp_path):
    assert Mesh(facing_away(tmp_path, True)).two_sided(Registry.default().materials)
    assert not Mesh(facing_away(tmp_path, False)).two_sided(Registry.default().materials)
