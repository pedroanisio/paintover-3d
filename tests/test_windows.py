"""Something to see through a window: a picture hung outside a room, and rooms behind a building's front."""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]

from test_looks import H, W, deep, errors, flat_set, near, pixel, stage

from srlocations import Backdrop, Box, Cel, Flat, Ink, Lit, Location, Look, Registry, Renderer, SharedCatalog, Styled, Wireframe
from srlocations.nodes import Ambient, Sun
from srlocations.stock.materials import PALETTE
from srlocations.stock.prefabs import Building, Room, Wall, window

PLAIN = Look([Lit()], sky="#ff00ff", name="plain")
DAY = "stock.view.day"


def cards(node) -> list:
    return [leaf for leaf in node.walk() if isinstance(leaf.item, Backdrop)]


def is_sky(rgb) -> bool:
    return rgb[2] > rgb[0] and rgb[2] > 100 and rgb[1] > 100  # the picture's blue, not the magenta behind it


def looking_at(wall: str) -> tuple:
    return {"north": ((0, 1.6, 0), (0, 1.95, 2.5)), "south": ((0, 1.6, 0), (0, 1.95, -2.5)),
            "east": ((0, 1.6, 0), (3, 1.95, 0)), "west": ((0, 1.6, 0), (-3, 1.95, 0))}[wall]


@pytest.mark.parametrize("wall", ["north", "south", "east", "west"])
def test_each_wall_of_a_room_shows_its_view_outside_it(tmp_path, wall):
    location = flat_set()
    location.add(Room(6, 5, ceiling=None, **{wall: [window(0, 2.0, view=DAY)]}))
    location.add(Ambient(30))
    eye, target = looking_at(wall)
    location.shot("out", eye, target, lens=40)
    shot = stage(Styled(Look([Flat()], sky="#ff00ff", name="f"), W, H, 1), location, "out", tmp_path)
    assert is_sky(pixel(shot, W / 2, H / 2)), pixel(shot, W / 2, H / 2)


def test_a_view_hangs_beyond_the_wall_on_the_outside():
    room = Room(6, 5, north=[window(0, view=DAY)], south=[window(0, view=DAY)], east=[window(0, view=DAY)],
                west=[window(0, view=DAY)])
    found = sorted((round(leaf.world.position.x, 3), round(leaf.world.position.z, 3)) for leaf in cards(room))
    assert found == [(-5.575, 0), (0, -5.075), (0, 5.075), (5.575, 0)]


def test_no_view_no_card():
    assert not cards(Room(6, 5, north=[window(0)]))


def test_two_windows_share_a_card_and_two_views_do_not_fight():
    shared = cards(Wall(8, openings=[window(-2, view=DAY), window(2, view=DAY)]))
    assert len(shared) == 1 and shared[0].item.width > 4
    apart = cards(Wall(8, openings=[window(-2, view=DAY), window(2, view="stock.view.dusk")]))
    assert len(apart) == 2 and apart[0].world.position.z != apart[1].world.position.z


def test_the_picture_stands_the_right_way_up(tmp_path):
    location = flat_set()
    location.add(Backdrop(8, 4, at=(0, 1, 3), material=DAY))
    location.add(Ambient(30))
    shot = stage(Styled(Look([Flat()], sky="#ff00ff", name="f"), W, H, 1), location, "front", tmp_path)
    top, bottom = pixel(shot, W / 2, H * 0.22), pixel(shot, W / 2, H * 0.72)
    assert top[2] > top[1] and bottom[1] > bottom[2]  # sky over land


def test_a_card_seen_from_behind_is_not_there(tmp_path):
    location = flat_set()
    location.add(Backdrop(8, 4, at=(0, 1, 3), material=DAY, yaw=180))
    shot = stage(Styled(Look([Flat()], sky="#ff00ff", name="f"), W, H, 1), location, "front", tmp_path)
    assert near(pixel(shot, W / 2, H / 2), "#ff00ff")


def test_a_view_is_never_in_the_way():
    location = Location("t", Registry.default())
    location.add(Room(6, 5, north=[window(0, view=DAY)]))
    location.add(Box((0.5, 0.5, 0.5), at=(0, 0.25, 5.15), material="stock.concrete"))
    assert not [clash for clash in location.clashes() if "view" in str(clash)]
    location.mark("out there", (0, 0, 5.075))
    location.shot("through", (0, 1.5, 7), (0, 1.5, 0))
    assert not [issue for issue in location.validate() if "view" in str(issue)]


def test_a_card_takes_no_shade_and_casts_none():
    location = flat_set()
    location.add(Room(6, 5, north=[window(0, view=DAY)]))
    location.add(Sun(3, pitch=-40))
    scene = Renderer().compile(location, "front", Styled(Look([Flat(), Cel()], name="c"), W, H, 1))
    drawn = {node.id: node for node in deep(scene, "object3D")}
    card = next(node for name, node in drawn.items() if name.startswith("cel-") and "view" in name)
    assert card.material == "cel-unlit-white" or "unlit" in card.material
    assert str(card.castShadow).lower() == "false"


def test_a_wireframe_leaves_a_card_out():
    assert Backdrop(8, 4).edges() == []


def test_a_look_can_aim_at_a_view():
    location = flat_set()
    location.add(Room(6, 5, north=[window(0, view=DAY)]))
    look = Look([Flat({"role:view": "#00ff00"})], name="f")
    assert errors(Renderer().compile(location, "front", Styled(look, W, H, 1))) == []


def test_stock_views_are_real_and_valid():
    for name in ("view.day", "view.dusk", "view.night", "interior.lit", "interior.lit.side", "interior.dark", "curtain"):
        PALETTE[name].validate()
    for name in ("view.day", "view.dusk", "view.night"):
        assert Path(PALETTE[name].maps["baseColorMap"]).is_file()


def test_the_pictures_are_installed_with_the_package():
    text = (ROOT / "pyproject.toml").read_text()
    assert "stock/views/*.png" in text


def test_a_package_carries_the_picture(tmp_path):
    location = flat_set()
    location.add(Room(6, 5, north=[window(0, view=DAY)]))
    document = Renderer().package(location, "front", tmp_path / "moved", Styled(PLAIN, W, H, 1))
    assert list(document.parent.rglob("*.png"))


def test_a_room_with_a_view_survives_the_catalog(tmp_path):
    catalog, registry = SharedCatalog.create(tmp_path / "shelf", "shelf"), Registry.default()
    catalog.publish_prop("lounge", Room(6, 5, north=[window(0, view=DAY)]), registry)
    assert catalog.verify() == []
    registry = Registry.default()
    catalog.install(registry)
    location = Location("t", registry)
    location.add("shelf.lounge")
    card = [leaf for leaf in location.solids() if isinstance(leaf.item, Backdrop)]
    assert len(card) == 1 and card[0].item.width > 6 and "view" in card[0].roles


def test_a_front_with_rooms_keeps_the_same_windows_and_roles():
    plain, roomy = Building(12, 10, 3, lit=0.5, seed=4), Building(12, 10, 3, lit=0.5, seed=4, interiors=True)
    windows = lambda building: sum(leaf.item.material != "x" and "window" in leaf.roles for leaf in building.walk())
    assert windows(plain) == windows(roomy) == 3 * 5
    glows = lambda building: [leaf.item.material for leaf in building.walk() if "window" in leaf.roles]
    assert sum(name == "stock.glow.window" for name in glows(plain)) \
        == sum(leaf.item.material == "stock.interior.lit" for leaf in roomy.walk())


def test_a_building_without_interiors_is_the_block_it_was():
    built = Building(12, 10, 3, seed=4).walk()
    assert sum("wall" in leaf.roles for leaf in built) == 1


def test_a_room_stays_inside_its_building_and_its_parts_do_not_clash():
    location = Location("t", Registry.default())
    building = location.add(Building(12, 10, 3, seed=4, interiors=True))
    assert location.clashes() == []
    low, high = building.bounds(building.transform) if hasattr(building, "bounds") else (None, None)
    for leaf in building.walk():
        if "interior" in leaf.roles:
            near_side, far_side = leaf.item.bounds(leaf.world)
            assert near_side.z >= -5 and far_side.z <= 5 and abs(near_side.x) <= 6


def test_a_building_too_shallow_for_rooms_is_refused():
    with pytest.raises(ValueError, match="no room"):
        list(Building(12, 2, 3, interiors=True).walk())


def test_a_lit_room_shows_through_its_window(tmp_path):
    location = flat_set()
    location.add(Building(6, 10, 1, lit=1.0, seed=1, interiors=True))
    location.shot("close", (-0.5, 1.7, -8), (-0.5, 1.7, -5), lens=30)
    shot = stage(Styled(Look([Lit()], sky="#000000", name="p"), W, H, 1), location, "close", tmp_path)
    r, g, b = pixel(shot, W / 2, H / 2)
    assert r > 90 and r > b + 25


def test_a_front_keeps_no_lines_across_its_pieces():
    location = Location("t", Registry.default())
    location.add(Building(12, 10, 3, seed=4, interiors=True))
    location.shot("s", (0, 2, -20), (0, 2, 0))
    scene = Renderer().compile(location, "s", Styled(Look([Ink()], name="i"), W, H, 1))
    assert errors(scene) == []
    keys = {key for _, key in Ink().surfaces(SimpleNamespace(solids=location.solids()))
            if "stock.brick.red" in key and "[0.0, 0.0, -1.0]" in key and key.endswith("|5.000")}
    assert len(keys) == 1


def test_a_street_can_have_interiors():
    registry = Registry.default()
    plain = registry.archetypes.get("stock.street")().build(registry, seed=2, length=20)
    roomy = registry.archetypes.get("stock.street")().build(registry, seed=2, length=20, interiors=True)
    assert len(roomy.solids()) > len(plain.solids())
