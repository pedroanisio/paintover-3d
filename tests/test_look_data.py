"""Looks as data: a .look.json, a blueprint's looks, and a house style published to a shared catalog."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]

from srlocations import (Blueprint, Box, CatalogError, Cel, Decal, Flat, Group, Ink, Lit, Look, Material, Mesh, Pass, Registry,
                         Renderer, SharedCatalog, Styled, Texture, WireframeCompiler)
from srlocations.stock.looks import ink_toon, paper_cutout
from test_looks import BLUE, GREY, H, RED, W, deep, errors, flat_set, near, pixel, solid_png, stage
from test_mesh import spot, textured_model, two_parts

RED_PNG = b"\xff\0\0\xff"


def registry() -> Registry:
    return Registry.default()


def house(folder: Path) -> Look:
    return Look([Flat({"stock.wood": "#aa5500"}, saturation=1.3, grain=0.04), Cel(cut=0.4), Ink(width=2.5, shadow_offset=(1.0, 2.0))],
                sky="#123456", warp=1.5, name="house",
                materials={"stock.plaster": "stock.wood.oak", "stock.glass": Material("#ff0000", opacity=0.5)},
                textures={"stock.wood": Texture(solid_png(folder / "grain.png", RED_PNG), tile=0.5, tint="#00ff00")})


def test_a_look_survives_a_trip_through_a_file(tmp_path):
    made = registry()
    path = house(tmp_path).save(tmp_path / "house.look.json", made)
    back = Look.load(path, made)
    assert back.name == "house" and back.sky == "#123456" and back.warp == 1.5
    assert [type(step) for step in back.passes] == [Flat, Cel, Ink]
    assert back.passes[0].saturation == 1.3 and back.passes[2].width == 2.5
    assert back.materials["stock.plaster"] == "stock.wood.oak"
    assert back.materials["stock.glass"].opacity == 0.5
    assert back.textures["stock.wood"].tile == 0.5 and back.textures["stock.wood"].tint == "#00ff00"


def test_a_saved_look_names_its_textures_relative_to_itself(tmp_path):
    (tmp_path / "looks").mkdir()
    made = registry()
    path = house(tmp_path).save(tmp_path / "looks" / "house.look.json", made)
    assert json.loads(path.read_text())["textures"]["stock.wood"]["path"] == "../grain.png"
    moved = tmp_path / "moved"
    moved.mkdir()
    (tmp_path / "looks").rename(moved / "looks")
    (tmp_path / "grain.png").rename(moved / "grain.png")
    assert Path(Look.load(moved / "looks" / "house.look.json", made).textures["stock.wood"].path).is_file()


def test_the_stock_looks_are_data_and_draw_the_same_from_it(tmp_path):
    made = registry()
    location = flat_set()
    location.add(Box((2, 1, 1), material="t.red", at=(0, 0.5, 3)))
    location.rig("stock.interior")
    for look in (ink_toon({"t.red": BLUE}), paper_cutout()):
        back = Look.from_spec(json.loads(json.dumps(look.spec(made))), made, name=look.name)
        first = Styled(look, W, H).compiler().compile(location, "front").to_bytes()
        assert first == Styled(back, W, H).compiler().compile(location, "front").to_bytes()


def test_a_look_file_names_an_unknown_pass_with_a_suggestion():
    with pytest.raises(CatalogError, match="did you mean stock.flat"):
        Look.from_spec({"passes": [{"kind": "stock.flatt"}]}, registry())


def test_a_look_file_refuses_a_key_it_does_not_have():
    with pytest.raises(ValueError, match="has no skye"):
        Look.from_spec({"passes": [], "skye": "#000000"}, registry())


def test_a_pass_with_a_wrong_parameter_says_which_look(tmp_path):
    with pytest.raises(ValueError, match="look 'x'.*colour"):
        Look.from_spec({"passes": [{"kind": "stock.ink", "colour": RED}]}, registry(), name="x")


def test_a_missing_texture_is_refused(tmp_path):
    with pytest.raises(FileNotFoundError):
        Look.from_spec({"passes": [], "textures": {"": {"path": "gone.png"}}}, registry(), tmp_path)


def test_a_plugin_pass_can_be_data_once_registered():
    class Blank(Pass):
        def add(self, stage):
            pass

        def spec(self):
            return {}

    made = registry()
    with pytest.raises(CatalogError, match="not in registry.passes"):
        Look([Blank()]).spec(made)
    made.passes.add("acme.blank", Blank)
    assert Look([Blank()]).spec(made)["passes"] == [{"kind": "acme.blank"}]
    assert isinstance(Look.from_spec(Look([Blank()]).spec(made), made).passes[0], Blank)


def blueprint(extra: dict) -> dict:
    return {"name": "room", "nodes": [{"use": "stock.table", "at": [0, 0, 3]}], "rig": {"use": "stock.interior"},
            "shots": [{"name": "front", "eye": [0, 1, -5], "look_at": [0, 1, 3], "lens": 30}], **extra}


def test_a_blueprint_can_define_a_look_and_render_in_it(tmp_path):
    solid_png(tmp_path / "grain.png", RED_PNG)
    data = blueprint({"looks": {"home": {"passes": [{"kind": "stock.flat"}], "sky": "#00ff00",
                                         "textures": {"stock.wood": {"path": "grain.png", "tile": 0.5}}}}})
    made = registry()
    location = Blueprint(data, tmp_path).build(made)
    assert "home" in made.modes
    scene = Renderer().compile(location, "front", "home", width=W, height=H)
    assert errors(scene) == [] and any(m.baseColorMap for m in deep(scene, "material"))


def test_a_blueprint_can_be_built_twice_on_a_registry(tmp_path):
    data = blueprint({"looks": {"home": {"passes": [{"kind": "stock.flat"}]}}})
    made = registry()
    Blueprint(data, tmp_path).build(made)
    Blueprint(data, tmp_path).build(made)


def test_paint_limited_to_a_blueprint_look_is_known(tmp_path):
    data = blueprint({"looks": {"home": {"passes": [{"kind": "stock.flat"}]}},
                      "paint": [{"name": "over", "looks": ["home"], "items": [{"kind": "disc", "center": [0, 1, 3]}]}]})
    assert Blueprint(data, tmp_path).build(registry()).validate() == []


def test_a_blueprint_names_a_model_relative_to_itself(tmp_path):
    two_parts(tmp_path)
    data = blueprint({"nodes": [{"use": "stock.mesh", "path": "pair.obj", "at": [0, 0, 3]},
                                {"name": "kept", "use": "", "children": [{"use": "stock.mesh", "path": "pair.obj"}]}]})
    location = Blueprint(data, tmp_path).build(registry())
    assert location.solids()[0].item.path == tmp_path / "pair.obj"
    assert location.solids()[1].item.path == tmp_path / "pair.obj"


def catalog(tmp_path: Path) -> SharedCatalog:
    return SharedCatalog.create(tmp_path / "shared", "studio")


def test_a_published_look_comes_back_whole_with_its_files(tmp_path):
    shared, made = catalog(tmp_path), registry()
    entry = shared.publish_look("house", house(tmp_path), made, tags=["toon"], description="Our style")
    (tmp_path / "grain.png").unlink()
    back = SharedCatalog.open(tmp_path / "shared").look("house")
    assert back.name == "studio.house" and back.warp == 1.5
    assert Path(back.textures["stock.wood"].path).parent == tmp_path / "shared" / "files"
    assert isinstance(back.materials["stock.plaster"], Material)
    assert back.materials["stock.plaster"] == made.materials.get("stock.wood.oak")
    assert entry.ref == "house@1.0.0" and shared.search("our style")[0].name == "house"
    assert shared.verify() == []


def test_a_published_look_is_a_render_mode_by_plain_name_and_by_version(tmp_path):
    shared, made = catalog(tmp_path), registry()
    shared.publish_look("flat", Look([Flat()], sky=GREY), made)
    shared.publish_look("flat", Look([Flat()], sky=RED), made, version="1.1.0")
    fresh = registry().use(SharedCatalog.open(tmp_path / "shared"))
    location = flat_set()
    location.registry = fresh
    location.shot("front", (0, 1, -5), (0, 1, 3))
    newest = fresh.modes.get("studio.flat")(width=W, height=H)
    assert newest.look.sky == RED and newest.look.name == "studio.flat"
    assert fresh.modes.get("studio.flat@1.0.0")(width=W, height=H).look.sky == GREY
    assert fresh.modes.get("studio.flat@1.0.0")().look.name == "studio.flat"  # paint limited to the look stays on it


def test_a_look_can_be_pinned(tmp_path):
    shared, made = catalog(tmp_path), registry()
    shared.publish_look("flat", Look([Flat()], sky=GREY), made)
    shared.publish_look("flat", Look([Flat()], sky=RED), made, version="1.1.0")
    fresh = registry()
    SharedCatalog.open(tmp_path / "shared").install(fresh, {"looks": {"flat": "1.0.0"}})
    assert fresh.modes.get("studio.flat")().look.sky == GREY


def test_publishing_a_look_twice_is_nothing_and_changing_it_is_refused(tmp_path):
    shared, made = catalog(tmp_path), registry()
    shared.publish_look("flat", Look([Flat()], sky=GREY), made)
    shared.publish_look("flat", Look([Flat()], sky=GREY), made)
    with pytest.raises(CatalogError, match="bump the version"):
        shared.publish_look("flat", Look([Flat()], sky=RED), made)


def test_a_look_using_a_plugin_pass_cannot_be_published(tmp_path):
    class Blank(Flat):
        pass

    shared, made = catalog(tmp_path), registry()
    made.passes.add("acme.blank", Blank)
    with pytest.raises(CatalogError, match="acme.blank"):
        shared.publish_look("x", Look([Blank()]), made)


def test_a_look_is_usable_as_soon_as_it_is_published(tmp_path):
    shared, made = catalog(tmp_path), registry()
    made.use(shared)
    shared.publish_look("flat", Look([Flat()], sky=GREY), made)
    assert made.modes.get("studio.flat")().look.sky == GREY


def test_verify_catches_a_changed_look_texture(tmp_path):
    shared, made = catalog(tmp_path), registry()
    shared.publish_look("house", house(tmp_path), made)
    stored = shared.get("look", "house").payload["textures"]["stock.wood"]["path"]
    (tmp_path / "shared" / "files" / stored).write_bytes(b"changed")
    assert [issue.code for issue in shared.verify()] == ["catalog-file"]


def test_a_look_with_an_impossible_shader_ref_is_caught(tmp_path):
    shared, made = catalog(tmp_path), registry()
    shared.publish_look("house", house(tmp_path), made)
    for path in (tmp_path / "shared" / "shaders").rglob("*.json"):
        path.unlink()
    assert "catalog-reference" in [issue.code for issue in shared.verify()]


def test_a_location_with_looks_or_a_cast_cannot_be_published(tmp_path):
    shared = catalog(tmp_path)
    for key, value in (("looks", {"x": {"passes": []}}), ("cast", [{"character": "a", "mark": "b"}])):
        with pytest.raises(CatalogError, match=f"has {key}, which can name files"):
            shared.publish_location("room", {"name": "room", key: value})


def test_a_decal_is_published_and_comes_back(tmp_path):
    shared, made = catalog(tmp_path), registry()
    made.materials.add("t.red", Material(RED))
    outline = ((-1.0, -0.5), (1.0, -0.5), (0.0, 0.5))
    shared.publish_prop("sign", Group([Decal(outline, material="t.red", smooth=True, looks=("house",), thickness=0.01)]), made)
    fresh = registry().use(SharedCatalog.open(tmp_path / "shared"))
    decal = fresh.create("studio.sign").build()[0]
    assert isinstance(decal, Decal) and tuple(map(tuple, decal.outline)) == outline
    assert decal.smooth and decal.thickness == 0.01 and decal.drawn_in("house") and not decal.drawn_in("other")
    assert decal.material.startswith("studio.from.t.red")
    assert shared.verify() == []


def test_a_mesh_is_published_with_every_file_it_reads(tmp_path):
    (tmp_path / "source").mkdir()
    shared, made = catalog(tmp_path), registry()
    shared.publish_prop("chair", Mesh(textured_model(tmp_path / "source"), scale=2, yaw=90), made)
    for path in (tmp_path / "source").rglob("*.*"):
        path.unlink()
    fresh = registry().use(SharedCatalog.open(tmp_path / "shared"))
    mesh = fresh.create("studio.chair").build()[0]
    assert isinstance(mesh, Mesh) and mesh.material == "stock.model" and mesh.factors.x == 2
    assert mesh.path.parent.parent == tmp_path / "shared" / "models"
    assert (mesh.path.parent / "maps" / "wood.png").is_file()
    assert shared.verify() == []
    assert shared.get("prop", "chair").size == (2.0, 2.0, 2.0)


def test_a_published_mesh_keeps_its_replaced_parts(tmp_path):
    shared, made = catalog(tmp_path), registry()
    made.materials.add("t.blue", Material(BLUE))
    path = two_parts(tmp_path)
    shared.publish_prop("pair", Mesh(path, materials={"other": "t.blue"}, at=(0, 0, 3), yaw=90), made)
    location = flat_set()
    location.registry.use(SharedCatalog.open(tmp_path / "shared"))
    location.add("studio.pair")
    assert location.validate() == []
    rows = stage(Styled(Look([Flat()], sky=GREY), W, H, supersample=1), location, "front", tmp_path)
    assert near(pixel(rows, *spot(location, "front", (0, 0.5, 3))), RED)
    assert near(pixel(rows, *spot(location, "front", (-1.5, 0.5, 3))), BLUE)


def test_a_wholly_replaced_mesh_can_expose_a_shader_slot(tmp_path):
    shared, made = catalog(tmp_path), registry()
    made.materials.add("t.red", Material(RED))
    made.materials.add("t.blue", Material(BLUE))
    shared.publish_prop("pair", Mesh(two_parts(tmp_path), material="t.red"), made, slots={"body": "t.red"})
    fresh = registry().use(SharedCatalog.open(tmp_path / "shared"))
    shared.publish_shader("blue", Material(BLUE))
    assert fresh.create("studio.pair", shaders={"body": "studio.blue"}).build()[0].material == "studio.blue"


def test_verify_catches_a_changed_model_file(tmp_path):
    (tmp_path / "source").mkdir()
    shared, made = catalog(tmp_path), registry()
    shared.publish_prop("chair", Mesh(textured_model(tmp_path / "source")), made)
    stored = next((tmp_path / "shared" / "models").rglob("chair.mtl"))
    stored.write_text("changed")
    assert [issue.code for issue in shared.verify()] == ["catalog-file"]


def test_a_prop_cannot_name_a_model_outside_the_catalog(tmp_path):
    (tmp_path / "source").mkdir()
    shared, made = catalog(tmp_path), registry()
    entry = shared.publish_prop("chair", Mesh(textured_model(tmp_path / "source")), made)
    part = json.loads(json.dumps(entry.payload["parts"][0]))
    part["model"]["folder"] = "../.."
    from srlocations import FrozenProp
    with pytest.raises(CatalogError, match="not a stored model"):
        FrozenProp(frozen=[part], catalog="studio", root=shared.root).build()
