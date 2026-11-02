"""Curved solids, the sky, path tracing and locations in a catalog."""
import importlib.util
import json
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from srlocations import (Blueprint, Box, CatalogError, Location, Material, Registry, Renderer, SceneCompiler, Shaded,
                         SharedCatalog, Sky, Solid, Surface, TemplateError, Traced, TracedCompiler, Transform, Vec3)
from srlocations.catalog import FrozenProp
from srlocations.compiler import Projection
from srlocations.geometry import aim
from srlocations.surfaces import MAX_SAMPLES
from srlocations.templates import engine_expression, evaluate


def ball(radius=0.5, **place) -> Surface:
    r = str(radius)
    return Surface(f"{r}*cos(v)*cos(u)", f"{r}*sin(v)", f"{r}*cos(v)*sin(u)", u=(0, 360), v=(-90, 90), closed=(True, False),
                   **{"material": "stock.default", **place})


def fresh(tmp_path, name="studio") -> SharedCatalog:
    return SharedCatalog.create(tmp_path / "shared", name)


def blueprint(**extra) -> dict:
    return {"name": "draft", "nodes": [{"use": "studio.pod"}], "rig": {"use": "stock.open-sky"},
            "shots": [{"name": "wide", "eye": [0, 1.5, -6], "look_at": [0, 0.5, 0]}], **extra}


def published_pod(tmp_path) -> SharedCatalog:
    catalog = fresh(tmp_path)
    catalog.publish_shader("skin", Material("#336699", 0.4))
    registry = Registry.default().use(catalog)
    catalog.publish_prop("pod", ball(material="studio.skin"), registry)
    return catalog


def test_a_surface_knows_its_own_bounds():
    low, high = ball(at=(1, 2, 3)).bounds(Transform.at((1, 2, 3)))
    assert (low.x, low.y, low.z) == pytest.approx((0.5, 1.5, 2.5))
    assert (high.x, high.y, high.z) == pytest.approx((1.5, 2.5, 3.5))


def test_a_lopsided_surface_is_not_taken_for_a_centred_one():
    sheet = Surface("u", "0", "v", u=(2, 3), v=(5, 6))
    low, high = sheet.bounds(Transform())
    assert (low.x, high.x, low.z, high.z) == pytest.approx((2, 3, 5, 6))


def test_a_camera_outside_a_surface_is_clear_of_it_and_one_inside_is_not():
    location = Location("x")
    location.add(ball(1.0))
    location.shot("out", (0, 0, -3), (0, 0, 0)).shot("in", (0, 0, 0.2), (0, 0, 1))
    assert [i.message for i in location.validate() if i.code == "shot-inside-solid"] == ["shot 'in' starts inside surface"]


def test_a_wireframe_follows_the_curve_and_not_its_box():
    points = [point for line in ball().edges() for point in line]
    assert points and all(sum(c * c for c in point) == pytest.approx(0.25) for point in points)


@pytest.mark.parametrize("axis", ["__import__('os')", "open('x')", "u.real", "[u][0]", "lambda: 1"])
def test_a_surface_cannot_reach_past_its_expressions(axis):
    with pytest.raises(TemplateError):
        Surface(axis).bounds(Transform())


def test_a_surface_that_cannot_be_drawn_is_found_at_build_time():
    with pytest.raises(TemplateError, match="not a finite number|cannot work out"):
        Surface("1/u", u=(0, 1)).bounds(Transform())


def test_a_surface_has_a_size_limit():
    with pytest.raises(TemplateError, match="samples"):
        Surface(samples=(MAX_SAMPLES + 1, 8))


@pytest.mark.parametrize("text", ["cos(u)*2", "pow(abs(sin(u)),0.5)*sign(cos(v))", "-sqrt(u+1)/max(v,1)", "pi*u", "min(u,v)+floor(v)"])
def test_the_engine_accepts_every_translated_expression(text, tmp_path):
    written = engine_expression(text, {"u": "u", "v": "v"})
    assert "Math." in written and "__" not in written
    surface = Surface(text, "v", "u", u=(10, 40), v=(1, 3), material="stock.default", samples=(4, 4))
    location = Location("x")
    location.add(surface)
    location.rig("stock.open-sky")
    location.shot("wide", (0, 2, -80), (0, 2, 25))
    assert Renderer().render(location, "wide", tmp_path / "e.png", Shaded(64, 36, supersample=1)).exists()
    assert surface.half_extents().z == pytest.approx(40)


def test_angles_stay_in_degrees_on_the_way_to_the_engine():
    assert engine_expression("sin(u)", {"u": "u"}) == "Math.sin((u)*Math.PI/180)"
    assert engine_expression("sin(u)+v", {"u": "u", "v": "(0-v)"}) == "(Math.sin((u)*Math.PI/180)+(0-v))"


def test_rendering_a_surface_passes_the_engines_own_checks(tmp_path):
    location = Location("x")
    location.add(Box((6, 0.1, 6), at=(0, -0.05, 0), material="stock.concrete"))
    location.add(ball(at=(0, 0.6, 0)))
    location.rig("stock.open-sky")
    location.shot("wide", (0, 1.2, -3), (0, 0.5, 0), lens=30)
    assert Renderer().render(location, "wide", tmp_path / "s.png", Shaded(160, 90, supersample=1)).stat().st_size > 1000
    assert Renderer().render(location, "wide", tmp_path / "w.png").stat().st_size > 1000


def test_traced_mode_asks_the_camera_for_the_path_tracer():
    location = Location("x")
    location.add(ball(at=(0, 1, 0)))
    location.shot("wide", (0, 1, -3), (0, 1, 0))
    assert isinstance(Traced().compiler(), TracedCompiler)
    camera = next(n for n in Traced(samples=9, bounces=3).compiler().compile(location, "wide").iter() if n.xml_name == "camera")
    assert (camera.renderer, str(camera.pathSamples), str(camera.maxBounces)) == ("pathtrace", "9", "3")
    plain = next(n for n in SceneCompiler().compile(location, "wide").iter() if n.xml_name == "camera")
    assert plain.renderer != "pathtrace"


def test_shaded_mode_can_set_the_cameras_lens_effects():
    location = Location("x")
    location.add(ball(at=(0, 1, 0)))
    location.shot("wide", (0, 1, -3), (0, 1, 0))
    mode = Shaded(camera={"depthOfField": True, "fStop": 0.6, "focusDistance": 300, "screenSpaceReflections": True, "near": 20})
    camera = next(n for n in mode.compiler().compile(location, "wide").iter() if n.xml_name == "camera")
    assert (str(camera.depthOfField), float(camera.fStop), float(camera.focusDistance), float(camera.near)) == ("True", 0.6, 300, 20)
    assert str(camera.screenSpaceReflections) == "True" and float(camera.far) == 500000
    plain = next(n for n in Shaded().compiler().compile(location, "wide").iter() if n.xml_name == "camera")
    assert (float(plain.near), plain.depthOfField) == (5, None)


@pytest.mark.parametrize("taken", ["yaw", "focalLength", "x", "renderer"])
def test_shaded_mode_leaves_the_camera_where_the_shot_puts_it(taken):
    with pytest.raises(ValueError, match=taken):
        Shaded(camera={taken: 1}).compiler()


def test_a_traced_shot_comes_out(tmp_path):
    location = Location("x", Registry.default())
    location.add(ball(at=(0, 0.6, 0)))
    location.rig("stock.open-sky")
    location.shot("wide", (0, 1, -3), (0, 0.6, 0))
    assert Renderer().render(location, "wide", tmp_path / "t.png", "stock.traced", width=96, height=54, samples=2).exists()


def test_the_sky_is_light_and_background_together():
    sky = Sky(1.2, zenith="#112233")
    assert sky.kind == "dome"
    assert sky.attributes()["environmentVisible"] is True and sky.attributes()["skyZenith"] == "#112233"


def test_a_frozen_surface_comes_back_the_same(tmp_path):
    catalog = fresh(tmp_path)
    catalog.publish_shader("skin", Material("#336699", 0.4))
    registry = Registry.default().use(catalog)
    made = ball(material="studio.skin", at=(1, 0, 0))
    entry = catalog.publish_prop("pod", made, registry)
    assert entry.size == pytest.approx((1, 1, 1))
    thawed = next(leaf for leaf in Registry.default().use(catalog).create("studio.pod").walk())
    assert isinstance(thawed.item, Surface) and thawed.item.spec() == made.spec() and thawed.world.position.x == 1


def test_a_frozen_surface_takes_a_slot(tmp_path):
    catalog = fresh(tmp_path)
    catalog.publish_shader("skin", Material("#336699", 0.4))
    registry = Registry.default().use(catalog)
    catalog.publish_prop("pod", ball(material="studio.skin"), registry, slots={"skin": "studio.skin"})
    reskinned = registry.create("studio.pod", shaders={"skin": "stock.fabric.teal"})
    assert isinstance(reskinned, FrozenProp) and next(reskinned.walk()).item.material == "stock.fabric.teal"


def test_a_location_is_published_with_its_names_pinned(tmp_path):
    catalog = published_pod(tmp_path)
    entry = catalog.publish_location("garage", blueprint(), tags=["test"], description="A pod")
    assert entry.payload["nodes"][0]["use"] == "studio.pod@1.0.0" and entry.payload["name"] == "garage"
    assert (catalog.root / "locations/garage/1.0.0.json").exists()
    assert catalog.search("pod", kind="location")[0].name == "garage"


def test_a_location_builds_with_nothing_but_the_catalog(tmp_path):
    catalog = published_pod(tmp_path)
    catalog.publish_location("garage", blueprint())
    location = SharedCatalog.open(catalog.root).location("garage")
    assert list(location.registry.plugins.loaded) == ["stock"] and location.name == "garage"
    assert len(location.solids()) == 1 and "wide" in location.shots and location.validate() == []


def test_a_location_keeps_the_versions_it_was_published_against(tmp_path):
    catalog = published_pod(tmp_path)
    catalog.publish_location("garage", blueprint())
    registry = Registry.default().use(catalog)
    catalog.publish_prop("pod", ball(0.9, material="studio.skin"), registry, "2.0.0")
    location = SharedCatalog.open(catalog.root).location("garage")
    assert location.solids()[0].item.half_extents().x == pytest.approx(0.5)


def test_a_published_location_is_a_fresh_location_each_time(tmp_path):
    catalog = published_pod(tmp_path)
    catalog.publish_location("garage", blueprint())
    first = catalog.location("garage")
    count = len(first.nodes)
    first.add(Box())
    assert len(catalog.location("garage").nodes) == count


def test_a_location_cannot_lean_on_a_plugin(tmp_path):
    catalog = published_pod(tmp_path)
    with pytest.raises(CatalogError, match="no prefab"):
        catalog.publish_location("garage", {**blueprint(), "nodes": [{"use": "someone.elses-prefab"}]})
    assert catalog.entries("location") == []


def test_a_location_with_a_broken_shot_is_refused(tmp_path):
    catalog = published_pod(tmp_path)
    inside = {"name": "wide", "eye": [0, 0, 0], "look_at": [0, 0, 1]}
    with pytest.raises(CatalogError, match="cannot be published"):
        catalog.publish_location("garage", {**blueprint(), "shots": [inside]})


def test_a_location_cannot_carry_files_it_does_not_own(tmp_path):
    with pytest.raises(CatalogError, match="paint"):
        published_pod(tmp_path).publish_location("garage", blueprint(paint=[{"name": "layer"}]))


def test_a_location_drops_the_paths_of_the_machine_it_came_from(tmp_path):
    catalog = published_pod(tmp_path)
    entry = catalog.publish_location("garage", blueprint(catalogs=[{"path": "../somewhere"}]))
    assert "catalogs" not in entry.payload


def test_a_location_version_cannot_change(tmp_path):
    catalog = published_pod(tmp_path)
    first = catalog.publish_location("garage", blueprint())
    assert catalog.publish_location("garage", blueprint()).digest == first.digest
    with pytest.raises(CatalogError, match="bump the version"):
        catalog.publish_location("garage", blueprint(marks=[{"name": "here", "at": [3, 0, 0]}]))


def test_verify_finds_a_location_that_no_longer_builds(tmp_path):
    catalog = published_pod(tmp_path)
    catalog.publish_location("garage", blueprint())
    assert catalog.verify() == []
    (catalog.root / "props/pod/1.0.0.json").unlink()
    assert "catalog-location" in [issue.code for issue in catalog.verify()]


def test_verify_finds_a_changed_location(tmp_path):
    catalog = published_pod(tmp_path)
    catalog.publish_location("garage", blueprint())
    path = catalog.root / "locations/garage/1.0.0.json"
    data = json.loads(path.read_text())
    data["payload"]["name"] = "elsewhere"
    path.write_text(json.dumps(data))
    assert [issue.code for issue in catalog.verify()] == ["catalog-digest"]


def test_the_published_grand_tourer_needs_no_plugin():
    catalog = SharedCatalog.open(ROOT / "catalog")
    location = catalog.location("grand-tourer")
    assert "grand-tourer" not in location.registry.plugins.loaded
    assert location.validate() == [] and set(location.shots) == {"from-the-door", "drivers-seat", "console"}
    assert catalog.pins(location)["props"] == {"gt-cabin": "1.5.0", "mountain-overlook": "1.5.0"}
    assert catalog.pins(catalog.location("grand-tourer", "1.0.0"))["props"] == {"gt-cabin": "1.0.0", "mountain-overlook": "1.0.0"}


def test_the_published_airliner_needs_no_plugin():
    catalog = SharedCatalog.open(ROOT / "catalog")
    location = catalog.location("airliner")
    assert "airliner" not in location.registry.plugins.loaded
    assert location.validate() == [] and set(location.shots) == {"down-the-aisle", "window-seat", "from-the-galley"}
    assert catalog.pins(location)["props"] == {"airliner-cabin": "1.0.1"}
    assert len(location.lights()) < 63  # past that the engine drops the far end of the cabin's lights


def test_the_published_flight_deck_needs_no_plugin():
    catalog = SharedCatalog.open(ROOT / "catalog")
    location = catalog.location("flight-deck")
    assert "flight-deck" not in location.registry.plugins.loaded
    assert location.validate() == [] and set(location.shots) == {"from-the-jump-seat", "captains-seat", "pedestal", "overhead"}
    assert catalog.pins(location)["props"] == {"flight-deck": "1.0.0"}


def test_the_published_park_needs_no_plugin():
    catalog = SharedCatalog.open(ROOT / "catalog")
    location = catalog.location("park")
    assert "park" not in location.registry.plugins.loaded
    assert location.validate() == [] and set(location.shots) == {"by-the-bench", "along-the-path", "from-the-bench", "over-the-lawn"}
    assert catalog.pins(location)["props"] == {"park": "1.0.0"}
    assert len(location.seats()) == 6  # three on each bench, kept when the prop was frozen


def test_the_published_park_night_needs_no_plugin():
    catalog = SharedCatalog.open(ROOT / "catalog")
    location = catalog.location("park-night")
    assert "park" not in location.registry.plugins.loaded
    assert location.validate() == [] and set(location.shots) == {"dance", "along-the-path"} and set(location.marks) == {"dancer"}
    assert catalog.pins(location)["props"] == {"park-night": "1.0.0", "park-lamp": "1.0.0", "park-bollard": "1.0.0",
                                                "park-mist": "1.0.0", "park-haze": "1.0.0"}
    assert len(location.lights()) < 63


def test_the_night_park_leaves_the_summer_park_as_published(tmp_path):
    """Park(night=False) still freezes to the digest park 1.0.0 was published with, so the summer park renders as before."""
    registry = Registry.default()
    catalog = SharedCatalog.create(tmp_path / "catalog", "studio")
    registry.use(catalog)
    park = registry.plugins.load_file(ROOT / "examples/plugins/park.py")
    for name, (material, tags, description) in park.shaders.items():
        catalog.publish_shader(name, material, tags=tags, description=description)
    frozen = catalog.publish_prop("park", registry.create("park.park"), registry, "1.0.0", slots=park.slots)
    assert frozen.digest == SharedCatalog.open(ROOT / "catalog").get("prop", "park", "1.0.0").digest


def test_the_night_park_is_wet_and_has_no_clouds():
    location = SharedCatalog.open(ROOT / "catalog").location("park-night")
    resolved = location.registry.resolved
    names = {resolved.get(leaf.item.material, leaf.item.material).split("@")[0] for leaf in location.solids()}
    assert {"studio.paving.wet", "studio.kerb.wet", "studio.grass.night"} <= names
    assert not names & {"studio.paving.brick", "studio.kerb.stone", "studio.grass.lawn", "studio.leaf.sun", "studio.cloud"}


def test_the_night_mist_stands_on_the_ground():
    """Each mist card's bottom edge is on the lawn, where its picture is clear, so no card draws a line across the
    ground where it meets it: a card reaching below the ground showed a hard step in the plate behind the dancer."""
    location = SharedCatalog.open(ROOT / "catalog").location("park-night")
    cards = [leaf for leaf in location.solids() if leaf.path.startswith("mist/")]
    assert len(cards) == 12
    assert all(abs(leaf.world.position.y - leaf.item.height / 2) < 1e-6 for leaf in cards)


def test_the_lamp_haze_stands_on_the_ground_facing_the_dance_shot():
    """The lamp's light in the mist is drawn on upright cards turned to the dance shot's heading, meeting the ground where
    they are clear, behind the dancer and in front of the lamp."""
    location = SharedCatalog.open(ROOT / "catalog").location("park-night")
    shot = location.shots["dance"]
    view = Projection(shot, 1080, 1920)
    heading, _ = aim(shot.eye, shot.look_at)
    cards = [leaf for leaf in location.solids() if leaf.path.startswith("lamp-haze/")]
    lamp = next(leaf.world.position for leaf in location.lights() if leaf.path.startswith("lamp/") and leaf.item.kind == "spot")
    dancer = view.to_camera(location.marks["dancer"].at).z
    assert len(cards) == 2
    for card in cards:
        assert abs(card.world.position.y - card.item.height / 2) < 1e-6
        facing = card.world.apply((0, 0, 1)) - card.world.position  # a card faces -z, so its +z points away from the camera
        assert abs(facing.y) < 1e-9 and abs(math.degrees(math.atan2(facing.x, facing.z)) - heading) < 0.01
        assert dancer < view.to_camera(card.world.position).z < view.to_camera(lamp).z


def _park_night_script():
    spec = importlib.util.spec_from_file_location("park_night", ROOT / "examples/park_night.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("lit, lights, haze", [(set(), 0, False), ({"lamp"}, 2, True), ({"row-1-left", "row-1-right"}, 2, False)])
def test_switching_lights_off_takes_their_light_and_the_lamp_its_haze(lit, lights, haze):
    """The plate script's states: every lamp not lit is its switched-off prop, and the lamp's haze goes with the lamp."""
    catalog = SharedCatalog.open(ROOT / "catalog")
    payload = _park_night_script().switched(catalog.get("location", "park-night").payload, lit)
    location = Blueprint(payload).build(Registry.default().use(catalog))
    assert len([leaf for leaf in location.lights() if leaf.path.startswith(("lamp/", "row-"))]) == lights
    assert any(leaf.path.startswith("lamp-haze/") for leaf in location.solids()) is haze
    assert location.validate() == []


def test_the_dance_shot_frames_a_dancer_for_a_portrait_plate():
    """The dance video's plate: at 1080x1920 the floor at the dancer's mark is at row 1440 in the middle of the frame, a
    1.6 m figure there is 800 px tall, and the lamp is in the frame above the dancer's head."""
    location = SharedCatalog.open(ROOT / "catalog").location("park-night")
    view = Projection(location.shots["dance"], 1080, 1920)
    mark = location.marks["dancer"].at
    floor, head = view.pixel(mark), view.pixel(mark + Vec3(0, 1.6, 0))
    assert abs(floor[0] - 540) < 1 and abs(floor[1] - 1440) < 1 and abs(floor[1] - head[1] - 800) < 2
    assert location.shots["dance"].eye.y == 0.8  # at the hips of a 1.6 m figure
    lamp = view.pixel(next(leaf.world.position for leaf in location.lights() if leaf.path.startswith("lamp/") and leaf.item.kind == "spot"))
    assert 0 < lamp[0] < 1080 and 0 < lamp[1] < head[1]


def test_the_lamp_centres_its_pool_on_the_dancer():
    location = SharedCatalog.open(ROOT / "catalog").location("park-night")
    beam = next(leaf for leaf in location.lights() if leaf.path.startswith("lamp/") and leaf.item.kind == "spot")
    assert beam.item.kind == "spot"
    origin = beam.world.position
    direction = beam.world.apply((0, 0, 1)) - origin
    reach = -origin.y / direction.y
    ground = Vec3(origin.x + direction.x * reach, 0, origin.z + direction.z * reach)
    assert (ground - location.marks["dancer"].at).length < 0.1


@pytest.mark.parametrize("prop", ["park-lamp", "park-bollard"])
def test_a_switched_off_light_differs_only_by_its_light(prop):
    """So the picture of it on less the picture of it off is its light alone, glow and reflections included."""
    registry = Registry.default().use(SharedCatalog.open(ROOT / "catalog"))
    on, off = (list(registry.create(f"studio.{name}").walk()) for name in (prop, f"{prop}.off"))
    assert [leaf.item.kind for leaf in on if not isinstance(leaf.item, Solid)] and all(isinstance(leaf.item, Solid) for leaf in off)
    lit = [leaf for leaf in on if isinstance(leaf.item, Solid)]
    assert [(leaf.world, leaf.item.dimensions()) for leaf in lit] == [(leaf.world, leaf.item.dimensions()) for leaf in off]
    changed = {(a.item.material.split("@")[0], b.item.material.split("@")[0]) for a, b in zip(lit, off) if a.item.material != b.item.material}
    assert len(changed) == 1 and next(iter(changed))[1] == "studio.glass.unlit"


def test_the_published_news_studio_needs_no_plugin():
    catalog = SharedCatalog.open(ROOT / "catalog")
    location = catalog.location("news-studio")
    assert "newsroom" not in location.registry.plugins.loaded
    assert location.validate() == [] and set(location.shots) == {"floor-camera", "two-shot", "wide", "portrait-two-shot",
                                                                  "portrait-push-in"}
    assert catalog.pins(location)["props"] == {"news-studio": "2.0.0"}
    assert set(location.marks) == {"anchor-left", "anchor-right"} and len(location.lights()) < 63


def test_the_news_studio_keeps_to_its_palette():
    """News Compiler's approved look: every lit colour is plum, tangerine or mint, or white for lamps and screens, whose
    pictures carry the palette; every other colour is the palette's or a grey; and no light is blue."""
    location = SharedCatalog.open(ROOT / "catalog").location("news-studio")
    palette = {"#2a1458", "#160a30", "#ff8a1f", "#d9620a", "#3fe0b5", "#1fa98a"}
    resolved = location.registry.resolved
    materials = [location.registry.materials.get(resolved.get(leaf.item.material, leaf.item.material)) for leaf in location.solids()]
    assert {material.glow for material in materials} - {None, ""} <= palette | {"#ffffff", "#fff6e8"}

    def grey(color: str) -> bool:
        channels = [int(color[i:i + 2], 16) for i in (1, 3, 5)]
        return max(channels) - min(channels) < 24
    assert not {material.color for material in materials if material.color not in palette and not grey(material.color)}
    assert {light.item.color for light in location.lights()} <= palette | {"#fff3e4", "#ffe9cf"}


def test_the_portrait_shots_put_the_desk_above_the_banner():
    """At 1080x1920 the back of the desk top is at row 1082 and its front at 1134, so a banner from 1146 clears it, in the
    two-shot and at the end of the push-in alike. The points are the middle of the desk top, from newsroom.py."""
    location = SharedCatalog.open(ROOT / "catalog").location("news-studio")
    for name in ("portrait-two-shot", "portrait-push-in"):
        view = Projection(location.shots[name], 1080, 1920)
        back, front = (view.pixel(Vec3(0, 0.98, z))[1] for z in (0.33, -0.52))
        assert abs(back - 1082) < 1 and abs(front - 1134) < 1, name


def test_the_published_starship_bridge_needs_no_plugin():
    catalog = SharedCatalog.open(ROOT / "catalog")
    location = catalog.location("starship-bridge")
    assert "bridge" not in location.registry.plugins.loaded
    assert location.validate() == [] and set(location.shots) == {"bridge-wide", "console-line", "mimic-board", "chart-table", "the-view"}
    assert catalog.pins(location)["props"] == {"starship-bridge": "2.1.0"}
    assert len(location.lights()) < 63


def test_the_bridge_has_no_centre_seat():
    """Saga's ruling: no seat in the middle facing the windows. Each seat is at a console, off the centre line."""
    location = SharedCatalog.open(ROOT / "catalog").location("starship-bridge")
    seats = location.seats()
    assert len(seats) == 2 and all(abs(seat.at.x) > 1.0 for seat in seats)
    assert not any("holo" in leaf.path or "command-chair" in leaf.path for leaf in location.solids())


def test_each_bridge_chair_has_its_own_paths():
    """So a seat or clash report can say which chair it means."""
    paths = [leaf.path for leaf in SharedCatalog.open(ROOT / "catalog").location("starship-bridge").solids()]
    assert {"starship-bridge/seat-helm", "starship-bridge/seat-navigator", "starship-bridge/back-helm",
            "starship-bridge/back-navigator"} <= set(paths)
    assert len([path for path in paths if "/seat" in path or "/back" in path]) == 4


def test_every_part_of_a_published_prop_has_its_own_path():
    leaves = SharedCatalog.open(ROOT / "catalog").location("grand-tourer").solids()
    cabin = [leaf.path for leaf in leaves if isinstance(leaf.item, Surface) and leaf.path.startswith("gt-cabin")]
    ridges = [leaf.path for leaf in leaves if "/ridge-3" in leaf.path]
    assert len(set(cabin)) == len(cabin)
    assert len(ridges) == 12 and len(set(ridges)) == 1  # the sectors of one hill, with no ink between them


def test_the_cabin_can_be_reskinned_by_slot():
    registry = Registry.default().use(SharedCatalog.open(ROOT / "catalog"))
    cabin = registry.create("studio.gt-cabin", shaders={"hide": "stock.fabric.teal"})
    used = {leaf.item.material for leaf in cabin.walk() if isinstance(leaf.item, Surface)}
    assert "stock.fabric.teal" in used and not any("cognac" in name for name in used)
