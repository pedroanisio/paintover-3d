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

from srlocations import (Cel, Flat, Group, Ink, Lit, Look, Material, Mesh, MeshError, Projection, Registry, Renderer,
                         SceneCompiler, Shaded, Styled, Texture, Vec3, Wireframe, WireframeCompiler, read_model)
from srlocations.location import Location, Shot
from srlocations.mesh import MODEL, tone
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
