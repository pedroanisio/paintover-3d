"""Looks aimed at solids and not at material names, which many solids share."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]

from srlocations import Box, Cel, Flat, Group, Look, Lit, Material, Mesh, Registry, SharedCatalog, Styled, StyledCompiler, Texture
from srlocations.looks import lookup
from srlocations.nodes import Placed
from srlocations.geometry import Transform
from srlocations.stock.prefabs import Building, Room, Wall, window
from srlocations.templates import PropTemplate
from test_looks import BLUE, GREEN, GREY, H, RED, W, deep, errors, flat_set, near, pixel, solid_png, stage
from test_mesh import spot, two_parts

LEFT, RIGHT, MIDDLE = (W * 0.3, H / 2), (W * 0.7, H / 2), (W / 2, H / 2)
RED_PNG = b"\xff\0\0\xff"


def pair(role: str = "wall"):
    """Two boxes in one material, the left one with a role."""
    location = flat_set()
    location.add(Box((1.2, 1.2, 0.2), material="t.grey", at=(-0.9, 1, 0), role=role, name="left"))
    location.add(Box((1.2, 1.2, 0.2), material="t.grey", at=(0.9, 1, 0), name="right"))
    location.rig("stock.daylight")
    return location


def leaves(node) -> dict[str, frozenset]:
    return {leaf.path: leaf.roles for leaf in node.walk()}


def test_a_solid_takes_the_roles_of_everything_above_it():
    node = Group([Group([Box(role="door panel", name="box")], name="in", role="front")], name="out", role="set")
    assert leaves(node) == {"out/in/box": {"door", "panel", "front", "set"}}


def test_a_solid_with_no_role_has_none():
    assert leaves(Group([Box(name="box")], name="out")) == {"out/box": frozenset()}


def test_a_prefab_passes_its_role_down():
    assert all("hall" in roles for roles in leaves(Wall(role="hall")).values())


def test_a_room_says_what_its_parts_are():
    parts = list(Room(north=[window(0.0)]).walk())
    roles = {role for leaf in parts for role in leaf.roles}
    assert roles == {"floor", "wall", "ceiling", "window"}
    assert all("wall" not in leaf.roles for leaf in parts if "glass" in leaf.item.material)
    assert all("stock.plaster" in leaf.item.material for leaf in parts if "wall" in leaf.roles)


def test_a_building_says_what_its_parts_are():
    parts = list(Building().walk())
    assert {role for leaf in parts for role in leaf.roles} == {"wall", "roof", "window"}
    assert all("window" in leaf.roles for leaf in parts if "stock.brick" not in leaf.item.material
               and "roof" not in leaf.roles)


def test_a_path_beats_a_role_and_a_role_beats_a_material():
    leaf = Placed(Box(material="stock.wood.oak"), Transform(), "room/north/box", frozenset({"wall"}))
    table = {"stock": 1, "stock.wood": 2, "role:wall": 3}
    assert lookup(table, "stock.wood.oak", leaf) == 3
    assert lookup({**table, "path:room/north/*": 4}, "stock.wood.oak", leaf) == 4
    assert lookup({**table, "path:room/south/*": 4}, "stock.wood.oak", leaf) == 3
    assert lookup({**table, "role:floor": 5}, "stock.wood.oak", leaf) == 3
    assert lookup({"stock": 1, "stock.wood": 2, "role:floor": 3}, "stock.wood.oak", leaf) == 2


def test_the_longest_of_two_keys_of_a_kind_wins():
    leaf = Placed(Box(), Transform(), "room/north/box", frozenset({"wall", "brick"}))
    assert lookup({"role:wall": 1, "role:brick": 2}, "x", leaf) == 2
    assert lookup({"path:room/*": 1, "path:room/north/*": 2}, "x", leaf) == 2


def test_with_no_solid_only_material_keys_count():
    assert lookup({"role:wall": 1, "path:*": 2}, "role:wall") is None
    assert lookup({"role:wall": 1, "": 2}, "stock") == 2


def test_a_material_key_never_reads_a_role_key_as_a_prefix():
    leaf = Placed(Box(), Transform(), "box", frozenset())
    assert lookup({"role:wall": 1}, "role:wall.x", leaf) is None


@pytest.mark.parametrize("passes", [[Flat()], [Lit()]], ids=["flat", "lit"])
def test_a_role_changes_one_of_two_solids_of_one_material(tmp_path, passes):
    look = Look(passes, sky="#000000", materials={"role:wall": "t.red"})
    rows = stage(Styled(look, W, H, 1), pair(), "front", tmp_path)
    r, g, b = pixel(rows, *LEFT)
    assert r > 2 * g and r > 2 * b
    other = pixel(rows, *RIGHT)
    assert abs(other[0] - other[1]) < 24


def test_a_texture_can_aim_at_a_role(tmp_path):
    picture = solid_png(tmp_path / "red.png", RED_PNG)
    look = Look([Flat()], sky="#000000", textures={"role:wall": Texture(picture, tile=1.0, tint="#ffffff")})
    rows = stage(Styled(look, W, H, 1), pair(), "front", tmp_path)
    assert near(pixel(rows, *LEFT), RED) and near(pixel(rows, *RIGHT), GREY)


def test_a_palette_can_aim_at_a_role(tmp_path):
    rows = stage(Styled(Look([Flat({"role:wall": BLUE})], sky="#000000"), W, H, 1), pair(), "front", tmp_path)
    assert near(pixel(rows, *LEFT), BLUE) and near(pixel(rows, *RIGHT), GREY)


def test_a_key_can_aim_at_a_path(tmp_path):
    rows = stage(Styled(Look([Flat({"path:r*": BLUE})], sky="#000000"), W, H, 1), pair(), "front", tmp_path)
    assert near(pixel(rows, *LEFT), GREY) and near(pixel(rows, *RIGHT), BLUE)


def test_a_role_and_a_material_key_can_share_a_look(tmp_path):
    look = Look([Flat()], sky="#000000", materials={"t.grey": "t.blue", "role:wall": "t.red"})
    rows = stage(Styled(look, W, H, 1), pair(), "front", tmp_path)
    assert near(pixel(rows, *LEFT), RED) and near(pixel(rows, *RIGHT), BLUE)


def test_cel_reads_the_material_a_role_gave_it():
    location = pair()
    location.registry.materials.add("t.lamp", Material("#ffffff", glow="#ffffff"))
    scene = StyledCompiler(Look([Cel()], materials={"role:wall": "t.lamp"}), W, H).compile(location, "front")
    used = {node.material for node in deep(scene, "object3D")}
    assert used == {"look-unlit-white", "look-lit-white"}


def test_the_document_stays_valid():
    location = pair()
    look = Look([Flat({"role:wall": BLUE}), Lit()], materials={"role:wall": "t.red", "path:right": "t.blue"})
    assert errors(StyledCompiler(look, W, H).compile(location, "front")) == []


def test_a_key_that_finds_nothing_warns_and_still_compiles():
    with pytest.warns(UserWarning, match="role:roof"):
        StyledCompiler(Look([Flat({"role:roof": BLUE})]), W, H).compile(pair(), "front")
    with pytest.warns(UserWarning, match="path:nowhere"):
        StyledCompiler(Look([Lit()], materials={"path:nowhere": "t.red"}), W, H).compile(pair(), "front")


def test_a_key_that_finds_something_does_not_warn(recwarn):
    StyledCompiler(Look([Flat({"role:wall": BLUE})]), W, H).compile(pair(), "front")
    assert [w for w in recwarn if "finds nothing" in str(w.message)] == []


def test_a_look_keeps_its_aim_as_a_file(tmp_path):
    made = Registry.default()
    picture = solid_png(tmp_path / "red.png", RED_PNG)
    look = Look([Flat({"role:floor": BLUE})], name="aimed", materials={"path:room/*": "stock.wood.oak"},
                textures={"role:wall": Texture(picture, tile=0.5)})
    back = Look.load(look.save(tmp_path / "aimed.look.json", made), made)
    assert back.passes[0].palette == {"role:floor": BLUE}
    assert back.materials == {"path:room/*": "stock.wood.oak"} and list(back.textures) == ["role:wall"]


def test_a_published_look_keeps_its_aim(tmp_path):
    made = Registry.default()
    picture = solid_png(tmp_path / "red.png", RED_PNG)
    shared = SharedCatalog.create(tmp_path / "shared", "shared")
    shared.publish_look("aimed", Look([Flat({"role:floor": BLUE})], textures={"role:wall": Texture(picture, tile=0.5)}), made)
    back = shared.look("aimed", registry=made)
    assert back.passes[0].palette == {"role:floor": BLUE} and list(back.textures) == ["role:wall"]
    assert shared.verify() == []


def test_a_frozen_prop_keeps_its_roles(tmp_path):
    made = Registry.default()
    shared = SharedCatalog.create(tmp_path / "shared", "shared")
    shared.publish_prop("room", Room(north=[window(0.0)]), made)
    made.use(shared)
    roles = {role for leaf in made.create("shared.room").walk() for role in leaf.roles}
    assert roles == {"floor", "wall", "ceiling", "window"}


def test_a_prop_with_no_roles_writes_none(tmp_path):
    """A published prop's digest covers its parts, so one without roles must come out as it always did."""
    shared = SharedCatalog.create(tmp_path / "shared", "shared")
    entry = shared.publish_prop("plain", Group([Box(material="stock.default")], name="plain"), Registry.default())
    assert all("role" not in part for part in entry.payload["parts"])


def test_a_frozen_model_keeps_its_role(tmp_path):
    made = Registry.default()
    shared = SharedCatalog.create(tmp_path / "shared", "shared")
    shared.publish_prop("pair", Mesh(two_parts(tmp_path), role="statue"), made)
    made.use(shared)
    assert all(roles == {"statue"} for roles in leaves(made.create("shared.pair")).values())


def test_a_template_part_can_have_a_role(tmp_path):
    made = Registry.default()
    shared = SharedCatalog.create(tmp_path / "shared", "shared")
    template = PropTemplate.from_data({"name": "crate", "slots": {"body": "stock.wood.oak"}, "params": {},
                                       "parts": [{"solid": "box", "size": [1, 1, 1], "shader": "body", "role": "lid"}]})
    shared.publish_template(template, made)
    made.use(shared)
    assert all(roles == {"lid", "crate"} for roles in leaves(made.create("shared.crate", role="crate")).values())


def test_a_role_reaches_every_part_of_a_model(tmp_path):
    location = flat_set()
    location.add(Mesh(two_parts(tmp_path), at=(-0.9, 0.5, 0.5), role="statue", name="left"))
    location.add(Mesh(two_parts(tmp_path), at=(0.9, 0.5, 0.5), name="right"))
    location.rig("stock.daylight")
    rows = stage(Styled(Look([Flat()], sky="#000000", materials={"role:statue": "t.blue"}), W, H, 1), location, "front",
                 tmp_path)
    assert near(pixel(rows, *spot(location, "front", (-0.9, 1, 0))), BLUE)
    assert near(pixel(rows, *spot(location, "front", (0.9, 1, 0))), GREEN)  # the file's nearer part


def test_a_placed_prop_can_be_given_a_role(tmp_path):
    made = Registry.default()
    shared = SharedCatalog.create(tmp_path / "shared", "shared")
    shared.publish_prop("crate", Box(material="stock.default"), made)
    made.use(shared)
    assert all("crate" in roles for roles in leaves(made.create("shared.crate", role="crate")).values())
