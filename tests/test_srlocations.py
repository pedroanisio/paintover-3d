import json
import math
import subprocess
import sys
from pathlib import Path

import pytest
from sr_core.scene import check

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "examples")]

from srlocations import (Blueprint, Box, CatalogError, Cone, Cylinder, Group, Library, Location, Material, Plugin,
                         Registry, Renderer, SceneCompiler, Shaded, SharedCatalog, Sphere, Transform, Vec3, Wireframe,
                         WireframeCompiler, aim, rotation)
from srlocations.catalog import Entry, FrozenProp
from srlocations.templates import PropTemplate, TemplateError, evaluate
from srlocations.compiler import FLIP, engine_angles, engine_position
from srlocations.stock.prefabs import Building, Opening, Table, Wall

import use_cases


def registry() -> Registry:
    made = Registry.default()
    made.use(Library.from_file(ROOT / "examples/cafe-lib.json"))
    made.plugins.load_file(ROOT / "examples/plugins/scifi.py")
    return made


def rebuilt(angles: dict) -> list:
    """The engine's Rz*Ry*Rx from its own angles, per the schema's rotation attribute."""
    x, y, z = (math.radians(angles.get(k, 0)) for k in ("rotationX", "rotationY", "rotation"))
    rx = [[1, 0, 0], [0, math.cos(x), -math.sin(x)], [0, math.sin(x), math.cos(x)]]
    ry = [[math.cos(y), 0, math.sin(y)], [0, 1, 0], [-math.sin(y), 0, math.cos(y)]]
    rz = [[math.cos(z), -math.sin(z), 0], [math.sin(z), math.cos(z), 0], [0, 0, 1]]
    mul = lambda a, b: [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
    return mul(rz, mul(ry, rx))


@pytest.mark.parametrize("yaw,pitch,roll", [(0, 0, 0), (90, 0, 0), (33, -20, 71), (-140, 65, 10), (10, 90, 20)])
def test_engine_angles_rebuild_the_world_basis(yaw, pitch, roll):
    basis = rotation(yaw, pitch, roll)
    expected = [[basis[r][c] * FLIP[r] * FLIP[c] for c in range(3)] for r in range(3)]
    assert sum(rebuilt(engine_angles(basis)), []) == pytest.approx(sum(expected, []), abs=1e-5)


def test_world_metres_become_engine_centimetres_with_y_down():
    assert engine_position(Vec3(1, 2, 3)) == {"x": 100, "y": -200, "z": 300}


def test_aim_matches_the_engine_convention():
    assert aim((0, 0, 0), (1, 0, 1))[0] == pytest.approx(45)  # yaw turns toward +x
    assert aim((0, 0, 0), (0, 1, 1))[1] == pytest.approx(45)  # positive pitch looks up


def test_nested_transforms_compose():
    inner = Box(at=(1, 0, 0))
    outer = Group([Group([inner], at=(0, 2, 0))], at=(0, 0, 5), yaw=90)
    assert next(outer.walk()).world.position.x == pytest.approx(0)
    assert next(outer.walk()).world.position.y == pytest.approx(2)
    assert next(outer.walk()).world.position.z == pytest.approx(4)


def test_a_wall_keeps_its_area_minus_the_opening():
    wall = Wall(4, 2.5, [Opening(0, 1, 0, 2)])
    solid = [n for n in wall.build() if n.material != "stock.glass.window"]
    assert sum(Vec3.of(n.size).x * Vec3.of(n.size).y for n in solid) == pytest.approx(4 * 2.5 - 2)


def test_building_windows_are_on_the_minus_z_face():
    bulk = next(iter(Building(width=10, depth=9).build()))
    panes = [n for n in Building(width=10, depth=9).build() if n.material == "stock.glass.dark"]
    assert panes and all(Vec3.of(p.at).z < -Vec3.of(bulk.size).z / 2 for p in panes)


def test_street_windows_face_the_road():
    location = registry().archetypes.get("stock.street")().build(registry(), seed=1)
    for leaf in location.solids():
        if leaf.item.material == "stock.glass.dark" and "building" in leaf.path:
            normal = leaf.world.apply((0, 0, -1)) - leaf.world.position
            assert normal.x * leaf.world.position.x < 0


def test_catalog_refuses_a_taken_name_and_suggests_near_ones():
    made = registry()
    with pytest.raises(CatalogError, match="already registered"):
        made.materials.add("stock.soil", Material())
    made.materials.add("stock.soil", Material("#000000"), override=True)
    with pytest.raises(CatalogError, match="did you mean stock.table"):
        made.create("stock.tabel")


def test_plugin_requirements_are_enforced():
    class Needy(Plugin):
        name, requires = "needy", ("nowhere",)
        def register(self, registry):
            pass
    with pytest.raises(CatalogError, match="requires nowhere"):
        Registry().plugins.load(Needy())


def test_a_plugin_check_runs():
    made = registry()
    location = made.archetypes.get("scifi.corridor")().build(made)
    location.nodes = [n for n in location.nodes if type(n).__name__ == "Ambient"]
    assert "scifi-dark" in [issue.code for issue in location.validate()]


def test_a_camera_inside_a_solid_is_reported():
    location = Location("x", registry()).shot("bad", (0, 0, 0), (0, 0, 1))
    location.add(Box(size=(1, 1, 1)))
    assert [i.code for i in location.validate()] == ["shot-inside-solid"]


def test_the_same_seed_gives_the_same_document():
    def document(seed):
        made = registry()
        return SceneCompiler().compile(made.archetypes.get("stock.street")().build(made, seed=seed), "overlook").to_bytes()
    assert document(3) == document(3) != document(4)


def locations() -> dict:
    made = registry()
    street = made.archetypes.get("stock.street")()
    return {"office": use_cases.office(made), "street": street.build(made, seed=4),
            "night": street.build(made, seed=4, night=True),
            "cafe": Blueprint.load(ROOT / "examples/cafe.location.json").build(made),
            "scifi": made.archetypes.get("scifi.corridor")().build(made)}


@pytest.mark.parametrize("key", ["office", "street", "night", "cafe", "scifi"])
def test_every_use_case_is_clean_and_schema_valid(key):
    location = locations()[key]
    assert location.validate() == []
    for shot in location.shots:
        findings = check(SceneCompiler().compile(location, shot), schema=True)
        assert [f for f in findings if f.severity == "error"] == []


def pixels(path: Path, width: int, height: int) -> list[bytes]:
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(path), "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                         capture_output=True, check=True).stdout
    assert len(raw) == width * height
    return [raw[r * width:(r + 1) * width] for r in range(height)]


def frame_of(rows: list[bytes], threshold: int) -> tuple[int, int, int, int]:
    """Left, right, top and bottom of what is drawn."""
    lit = [(x, y) for y, row in enumerate(rows) for x, value in enumerate(row) if value > threshold]
    return min(p[0] for p in lit), max(p[0] for p in lit), min(p[1] for p in lit), max(p[1] for p in lit)


def study(*solids) -> Location:
    made = registry()
    made.materials.add("test.white", Material("#000000", glow="#ffffff", glow_strength=1.0))
    location = Location("study", made)
    for solid in solids:
        location.add(solid)
    location.shot("view", (0.7, 1.4, -4), (0, 0.8, 0), lens=35)
    return location


SOLIDS = {"box": lambda: Box(size=(1.2, 0.8, 0.6), at=(0.2, 0.9, 0.3), yaw=35, pitch=20, roll=-15, material="test.white"),
          "cylinder": lambda: Cylinder(0.4, 1.2, at=(-0.3, 1.0, 0.2), pitch=30, material="test.white"),
          "cone": lambda: Cone(0.5, 1.2, at=(0.1, 0.8, 0), material="test.white"),
          "sphere": lambda: Sphere(0.6, at=(0.3, 1.0, 0.1), material="test.white")}


@pytest.mark.parametrize("name", list(SOLIDS))
@pytest.mark.parametrize("width,height", [(480, 270), (270, 480)])
def test_the_wireframe_lands_on_the_engines_own_pixels(tmp_path, name, width, height):
    """The projection is the SDK's copy of the engine's camera, so it is held to the engine's frame, wide and narrow."""
    location = study(SOLIDS[name]())
    renderer = Renderer()
    shaded = renderer.render(location, "view", tmp_path / "s.png", Shaded(width, height, 1))
    wire = renderer.render(location, "view", tmp_path / "w.png", Wireframe(width, height, line="#ffffff"))
    drawn = frame_of(pixels(shaded, width, height), 90)
    traced = frame_of(pixels(wire, width, height), 40)
    assert all(abs(a - b) <= 2 for a, b in zip(drawn, traced)), (drawn, traced)


def test_the_cone_edges_point_the_way_the_engine_does(tmp_path):
    location = study(SOLIDS["cone"]())
    rows = pixels(Renderer().render(location, "view", tmp_path / "s.png", Shaded(480, 270, 1)), 480, 270)
    left, right, top, bottom = frame_of(rows, 90)
    span = lambda y: sum(value > 90 for value in rows[y])
    assert span(top + 3) < span(bottom - 3)


def test_wireframe_low_resolution_is_the_default(tmp_path):
    location = study(SOLIDS["box"]())
    assert isinstance(Renderer().default_mode, Wireframe)
    assert (Renderer().default_mode.width, Renderer().default_mode.height) == (480, 270)
    out = Renderer().render(location, "view", tmp_path / "default.png")
    named = Renderer().render(location, "view", tmp_path / "named.png", "stock.wireframe")
    assert out.read_bytes() == named.read_bytes()


def test_a_shot_behind_the_geometry_draws_nothing_and_stays_valid():
    location = study(Box(size=(1, 1, 1), at=(0, 0, -30), material="test.white"))
    compiled = WireframeCompiler().compile(location, "view")
    assert [f for f in check(compiled, schema=True) if f.severity == "error"] == []


def test_a_plugin_solid_gets_a_wireframe_without_writing_edges():
    class Crate(Box):
        primitive = "box"
    assert len(Crate(size=(1, 1, 1)).edges()) == 6


def test_a_plugin_can_add_a_render_mode():
    class Blueprinted(Wireframe):
        pass
    made = registry()
    made.modes.add("test.blueprint", Blueprinted)
    assert isinstance(made.modes.get("test.blueprint")(), Wireframe)


def test_an_empty_location_compiles_to_a_valid_scene():
    location = Location("bare", registry()).shot("view", (0, 1, 0), (0, 1, 5))
    for compiler in (SceneCompiler(), WireframeCompiler()):
        assert [f for f in check(compiler.compile(location, "view"), schema=True) if f.severity == "error"] == []


def fresh_catalog(tmp_path, name="studio") -> SharedCatalog:
    return SharedCatalog.create(tmp_path / "shared", name)


def oak(color="#8a5a33") -> Material:
    return Material(color, 0.5, extra={"clearcoat": 0.5})


def test_a_shader_round_trips_with_its_extended_attributes(tmp_path):
    catalog = fresh_catalog(tmp_path)
    catalog.publish_shader("oak", oak(), tags=["wood"])
    made = Registry.default().use(SharedCatalog.open(catalog.root))
    assert made.materials.get("studio.oak") == oak()
    assert made.materials.get("studio.oak@1.0.0") == oak()


def test_a_shader_the_engine_would_refuse_is_refused_at_publish(tmp_path):
    catalog = fresh_catalog(tmp_path)
    with pytest.raises(Exception, match="noSuchAttribute"):
        catalog.publish_shader("bad", Material(extra={"noSuchAttribute": 1}))
    with pytest.raises(Exception, match="maxInclusive"):
        catalog.publish_shader("bad", Material(extra={"clearcoat": 9}))
    assert catalog.entries() == []


def test_a_published_version_is_immutable_and_republishing_is_harmless(tmp_path):
    catalog = fresh_catalog(tmp_path)
    first = catalog.publish_shader("oak", oak())
    assert catalog.publish_shader("oak", oak()).digest == first.digest
    with pytest.raises(CatalogError, match="bump the version"):
        catalog.publish_shader("oak", oak("#000000"))
    assert catalog.get("shader", "oak").digest == first.digest


def test_creating_a_catalog_where_another_is_refuses_to_rename_it(tmp_path):
    """create() opens a catalog that is already there, but not one with another name: that would be a silent surprise."""
    catalog = fresh_catalog(tmp_path)
    assert SharedCatalog.create(catalog.root, catalog.name).root == catalog.root
    with pytest.raises(CatalogError, match="already holds"):
        SharedCatalog.create(catalog.root, "other")


def test_the_newest_version_wins_by_number_not_by_text(tmp_path):
    catalog = fresh_catalog(tmp_path)
    catalog.publish_shader("oak", oak("#111111"), "1.9.0")
    catalog.publish_shader("oak", oak("#222222"), "1.10.0")
    assert catalog.get("shader", "oak").version == "1.10.0"
    assert Registry.default().use(catalog).materials.get("studio.oak").color == "#222222"


def test_a_changed_file_is_refused(tmp_path):
    catalog = fresh_catalog(tmp_path)
    catalog.publish_shader("oak", oak())
    path = catalog.root / "shaders/oak/1.0.0.json"
    path.write_text(path.read_text().replace("#8a5a33", "#ff0000"))
    with pytest.raises(CatalogError, match="does not match its digest"):
        catalog.get("shader", "oak")
    assert [i.code for i in catalog.verify()] == ["catalog-digest"]


def test_a_changed_texture_is_reported(tmp_path):
    texture = tmp_path / "t.png"
    texture.write_bytes(b"one")
    catalog = fresh_catalog(tmp_path)
    catalog.publish_shader("tile", Material(maps={"baseColorMap": str(texture)}))
    stored = next((catalog.root / "files").iterdir())
    assert catalog.verify() == []
    stored.write_bytes(b"two")
    assert [i.code for i in catalog.verify()] == ["catalog-file"]


@pytest.mark.parametrize("name", ["../escape", "a/b", "Upper", "a..b", ""])
def test_names_cannot_leave_the_catalog(tmp_path, name):
    with pytest.raises(CatalogError, match="not an item name"):
        fresh_catalog(tmp_path).publish_shader(name, oak())


def test_a_stored_file_name_cannot_point_outside(tmp_path):
    catalog = fresh_catalog(tmp_path)
    entry = Entry("shader", "x", "1.0.0", "", {"maps": {"baseColorMap": "../../secret"}})
    with pytest.raises(CatalogError, match="not a stored file name"):
        catalog._material(entry)


def test_a_prop_works_without_the_plugin_that_made_it(tmp_path):
    maker = registry()
    catalog = fresh_catalog(tmp_path)
    catalog.publish_prop("bulkhead", maker.create("scifi.bulkhead"), maker)

    consumer = Registry.default().use(SharedCatalog.open(catalog.root))
    assert "scifi" not in consumer.plugins.loaded and "scifi.bulkhead" not in consumer.prefabs
    location = Location("elsewhere", consumer).shot("view", (0, 1.5, -5), (0, 1.5, 0))
    location.add("studio.bulkhead")
    assert location.validate() == []
    assert len(location.solids()) == 6 and len(location.lights()) == 1
    assert [f for f in check(SceneCompiler().compile(location, "view"), schema=True) if f.severity == "error"] == []


def test_a_frozen_prop_stands_exactly_where_the_original_stood(tmp_path):
    maker = registry()
    original = maker.create("stock.car", paint="stock.paint.red")
    catalog = fresh_catalog(tmp_path)
    catalog.publish_prop("car", original, maker)
    frozen = Registry.default().use(catalog).create("studio.car", at=(3, 0, 1), yaw=40)
    placed = Group([original], at=(3, 0, 1), yaw=40)
    for a, b in zip(placed.walk(), frozen.walk()):
        assert list(a.world.position) == pytest.approx(list(b.world.position), abs=1e-5)
        assert sum(map(list, a.world.basis), []) == pytest.approx(sum(map(list, b.world.basis), []), abs=1e-5)


def test_a_prop_keeps_the_shader_version_it_was_published_with(tmp_path):
    catalog = fresh_catalog(tmp_path)
    catalog.publish_shader("top", oak("#111111"), "1.0.0")
    maker = Registry.default().use(catalog)
    catalog.publish_prop("table", Table(top="studio.top"), maker)
    catalog.publish_shader("top", oak("#999999"), "2.0.0")

    later = Registry.default().use(SharedCatalog.open(catalog.root))
    assert later.materials.get("studio.top").color == "#999999"
    used = {leaf.item.material for leaf in later.create("studio.table").walk()}
    assert "studio.top@1.0.0" in used and later.materials.get("studio.top@1.0.0").color == "#111111"


def test_pins_bring_back_the_same_location(tmp_path):
    catalog = fresh_catalog(tmp_path)
    catalog.publish_shader("wall", oak("#111111"), "1.0.0")
    maker = Registry.default().use(catalog)
    catalog.publish_prop("table", Table(), maker, "1.0.0")

    def compose(made):
        location = Location("x", made).shot("view", (0, 1, -5), (0, 1, 0))
        location.add(Box(material="studio.wall"))
        location.add("studio.table")
        return location

    first = compose(maker)
    pins = catalog.pins(first)
    assert pins == {"props": {"table": "1.0.0"}, "shaders": {"wall": "1.0.0"}}
    catalog.publish_shader("wall", oak("#999999"), "2.0.0")
    catalog.publish_prop("table", Table(width=3), maker, "2.0.0")

    pinned, unpinned = Registry.default(), Registry.default()
    catalog.install(pinned, pins)
    catalog.install(unpinned)
    assert compose(pinned).solids()[0].item.material == "studio.wall"
    assert pinned.materials.get("studio.wall").color == "#111111"
    assert unpinned.materials.get("studio.wall").color == "#999999"
    document = lambda made: SceneCompiler().compile(compose(made), "view").to_bytes()
    assert document(pinned) == document(maker) != document(unpinned)


def test_a_missing_pin_is_refused(tmp_path):
    catalog = fresh_catalog(tmp_path)
    catalog.publish_shader("oak", oak())
    with pytest.raises(CatalogError, match="no pinned shader oak"):
        catalog.install(Registry.default(), {"shaders": {"oak": "9.9.9"}})


def test_search_finds_the_newest_by_text_kind_and_tags(tmp_path):
    catalog = fresh_catalog(tmp_path)
    catalog.publish_shader("oak", oak(), "1.0.0", tags=["wood"], description="Pale floorboards")
    catalog.publish_shader("oak", oak("#000000"), "2.0.0", tags=["wood"], description="Pale floorboards")
    catalog.publish_shader("steel", Material(), tags=["metal"])
    assert [e.ref for e in catalog.search("floorboards")] == ["oak@2.0.0"]
    assert [e.ref for e in catalog.search(tags=["metal"], kind="shader")] == ["steel@1.0.0"]
    assert catalog.search("nothing") == []


def test_catalogs_load_from_the_environment(tmp_path, monkeypatch):
    catalog = fresh_catalog(tmp_path)
    catalog.publish_shader("oak", oak())
    monkeypatch.setenv("SRLOCATIONS_CATALOGS", str(catalog.root))
    assert "studio.oak" in Registry.default().materials


def test_installing_twice_is_harmless_but_two_catalogs_cannot_share_a_name(tmp_path):
    first = SharedCatalog.create(tmp_path / "a", "studio")
    second = SharedCatalog.create(tmp_path / "b", "studio")
    made = Registry.default().use(first).use(first)
    with pytest.raises(CatalogError, match="two catalogs are named"):
        made.use(second)


def test_a_blueprint_names_its_catalog_and_pins(tmp_path):
    catalog = fresh_catalog(tmp_path)
    catalog.publish_shader("wall", oak("#111111"), "1.0.0")
    catalog.publish_shader("wall", oak("#999999"), "2.0.0")
    spec = {"name": "x", "catalogs": [{"path": "shared", "pins": {"shaders": {"wall": "1.0.0"}}}],
            "nodes": [{"use": "stock.box", "material": "studio.wall"}]}
    path = tmp_path / "x.location.json"
    path.write_text(json.dumps(spec))
    location = Blueprint.load(path).build()
    assert location.registry.materials.get("studio.wall").color == "#111111"


def test_two_publishers_cannot_both_win_a_version(tmp_path):
    catalog = fresh_catalog(tmp_path)
    (catalog.root / "shaders/oak").mkdir(parents=True)
    target = catalog.root / "shaders/oak/1.0.0.json"
    catalog._write_once(target, "first")
    with pytest.raises(CatalogError, match="published by someone else"):
        catalog._write_once(target, "second")
    assert target.read_text() == "first"
    assert [p.name for p in target.parent.iterdir()] == ["1.0.0.json"]


def test_a_new_item_is_usable_at_once_but_a_name_in_use_stays_on_its_version(tmp_path):
    catalog = fresh_catalog(tmp_path)
    made = Registry.default().use(catalog)
    catalog.publish_shader("oak", oak("#111111"), "1.0.0")
    assert made.materials.get("studio.oak").color == "#111111"
    catalog.publish_shader("oak", oak("#999999"), "2.0.0")
    assert made.materials.get("studio.oak").color == "#111111"
    assert made.materials.get("studio.oak@2.0.0").color == "#999999"
    catalog.publish_prop("table", Table(top="studio.oak"), made)
    assert isinstance(made.create("studio.table"), FrozenProp)


def desk_data(**changes) -> dict:
    data = {"name": "desk",
            "params": {"width": {"default": 1.4, "min": 0.6, "max": 3}, "legs": {"default": 4, "min": 0, "max": 8}},
            "slots": {"top": "studio.oak"},
            "variants": {"long": {"width": 2.5}},
            "parts": [{"solid": "box", "size": ["width", 0.04, 0.8], "at": [0, 0.73, 0], "shader": "top"},
                      {"repeat": "legs", "as": "i", "parts": [
                          {"solid": "box", "size": [0.05, 0.71, 0.05], "at": ["i * 0.1", 0.355, 0], "shader": "top"}]}]}
    return {**data, **changes}


def publishing(tmp_path):
    catalog = fresh_catalog(tmp_path)
    catalog.publish_shader("oak", oak())
    catalog.publish_shader("steel", Material("#888888", 0.3, 1.0))
    return catalog, Registry.default().use(catalog)


def desk(tmp_path, **changes):
    catalog, made = publishing(tmp_path)
    catalog.publish_template(PropTemplate.from_data(desk_data(**changes)), made)
    return catalog, made


@pytest.mark.parametrize("text,value", [("1 + 2 * 3", 7), ("(a - 1) / 2", 1.5), ("7 // 2", 3), ("7 % 2", 1), ("-a", -4),
                                        ("max(a, 9)", 9), ("floor(2.7)", 2), ("sqrt(16)", 4), ("cos(0)", 1),
                                        ("1 if a > 3 else 2", 1), ("a > 1 and a < 3", False), ("not a", False),
                                        ("1 < a < 5", True)])
def test_expressions_compute(text, value):
    assert evaluate(text, {"a": 4}) == pytest.approx(value)


@pytest.mark.parametrize("text", ["__import__('os').system('true')", "().__class__", "a.real", "open('x')", "'text'",
                                  "[1, 2][0]", "(lambda: 1)()", "a ** 2", "max(*[1])", "print(1)", "1 if", "x", "f'{a}'"])
def test_expressions_cannot_reach_python(text):
    with pytest.raises(TemplateError):
        evaluate(text, {"a": 4})


@pytest.mark.parametrize("text", ["1 / 0", "sqrt(-1)", "1e308 * 10", "max()", "1" * 300, "floor(1e308) * 10"])
def test_impossible_expressions_are_errors(text):
    with pytest.raises(TemplateError):
        evaluate(text, {})


def test_parameters_change_the_geometry_and_defaults_apply(tmp_path):
    catalog, made = desk(tmp_path)
    assert next(made.create("studio.desk").walk()).item.dimensions()["width"] == 1.4
    assert next(made.create("studio.desk", width=2.2).walk()).item.dimensions()["width"] == 2.2
    assert len(list(made.create("studio.desk", legs=2).walk())) == 3


def test_a_parameter_outside_its_range_or_unknown_is_refused(tmp_path):
    catalog, made = desk(tmp_path)
    with pytest.raises(TemplateError, match="outside 0.6 to 3"):
        made.create("studio.desk", width=9)
    with pytest.raises(CatalogError, match="did you mean width"):
        made.create("studio.desk", widht=2)


def test_a_variant_sets_values_and_a_parameter_can_still_override_it(tmp_path):
    catalog, made = desk(tmp_path)
    assert next(made.create("studio.desk", variant="long").walk()).item.dimensions()["width"] == 2.5
    assert next(made.create("studio.desk", variant="long", width=1).walk()).item.dimensions()["width"] == 1
    with pytest.raises(CatalogError, match="no variant 'lng'; did you mean long"):
        made.create("studio.desk", variant="lng")


def test_a_shader_slot_is_swapped_per_instance_and_defaults_stay(tmp_path):
    catalog, made = desk(tmp_path)
    assert next(made.create("studio.desk").walk()).item.material == "studio.oak@1.0.0"
    swapped = made.create("studio.desk", shaders={"top": "studio.steel"})
    assert next(swapped.walk()).item.material == "studio.steel"
    with pytest.raises(CatalogError, match="no shader slot 'side'"):
        made.create("studio.desk", shaders={"side": "studio.steel"})


def test_a_frozen_prop_has_slots_but_no_parameters(tmp_path):
    catalog, made = publishing(tmp_path)
    catalog.publish_prop("table", Table(top="studio.oak"), made, slots={"top": "studio.oak"})
    materials = {leaf.item.material for leaf in made.create("studio.table", shaders={"top": "studio.steel"}).walk()}
    assert "studio.steel" in materials and "studio.oak" not in {m.split("@")[0] for m in materials}
    with pytest.raises(CatalogError, match="no parameter 'width'"):
        made.create("studio.table", width=2)
    with pytest.raises(CatalogError, match="does not use"):
        catalog.publish_prop("other", Table(top="studio.oak"), made, slots={"top": "studio.steel"})


def test_a_prop_without_slots_keeps_its_published_content(tmp_path):
    """Slots must not change what older publishes digest to, or rerunning a publish would conflict."""
    catalog, made = publishing(tmp_path)
    first = catalog.publish_prop("table", Table(top="studio.oak"), made)
    assert "slots" not in first.payload
    assert catalog.publish_prop("table", Table(top="studio.oak"), made).digest == first.digest


@pytest.mark.parametrize("change,message", [
    ({"parts": [{"solid": "box", "size": [1, 1, 1], "shader": "nope"}]}, "unknown shader slot 'nope'"),
    ({"parts": [{"solid": "box", "size": [1, "wdith", 1], "shader": "top"}]}, "unknown name 'wdith'"),
    ({"parts": [{"solid": "box", "size": [1, 1, 1], "shader": "top", "when": "width > 9",
                 "at": [0, "typo", 0]}]}, "unknown name 'typo'"),
    ({"parts": [{"solid": "wedge", "shader": "top"}]}, "unknown solid"),
    ({"parts": [{"thing": 1}]}, "needs solid, light, prop or repeat"),
    ({"params": {"at": {"default": 1}}}, "cannot be a parameter name"),
    ({"params": {"width": {"default": 9, "max": 3}}}, "outside"),
    ({"variants": {"v": {"nope": 1}}}, "unknown parameter 'nope'"),
    ({"variants": {"v": {"shaders": {"nope": "studio.oak"}}}}, "unknown shader slot 'nope'"),
    ({"parts": [{"solid": "box", "size": ["width - 1", 1, 1], "shader": "top"}]}, "not positive"),
    ({"parts": [{"repeat": "width", "parts": [{"solid": "box", "size": [1, 1, 1], "shader": "top"}]}]}, "not a whole number"),
    ({"parts": [{"repeat": 100000, "parts": [{"solid": "box", "size": [1, 1, 1], "shader": "top"}]}]}, "more than"),
    ({"parts": [{"prop": "ghost"}]}, "no prop 'ghost'"),
    ({"parts": [{"prop": "../../outside@1.0.0"}]}, "not an item name"),
    ({"parts": [{"solid": "box", "size": [1, 1, 1], "shader": "top", "cast_shadow": False}]}, "cannot have 'cast_shadow'"),
    ({"parts": [{"repeat": 2, "at": [0, 0, 0], "parts": []}]}, "cannot have 'at'"),
    ({"parts": [{"repeat": 2, "as": "i", "when": "i > 0", "parts": []}]}, "unknown name 'i'"),
    ({"parts": [{"solid": "box", "size": [1, 1], "shader": "top"}]}, "three values"),
    ({"parts": [{"solid": "box", "size": [1, 1, 1], "segments": 8, "shader": "top"}]}, "segments"),
    ({"parts": [{"light": "sun"}]}, "point and spot"),
    ({"paramz": {}}, "unexpected keyword"),
])
def test_a_template_that_cannot_work_is_refused_at_publish(tmp_path, change, message):
    catalog, made = publishing(tmp_path)
    with pytest.raises(CatalogError, match=message):
        catalog.publish_template(PropTemplate.from_data(desk_data(**change)), made)
    assert catalog.search(kind="prop") == []


def test_repeats_and_conditions(tmp_path):
    parts = [{"repeat": "legs", "as": "i", "parts": [
        {"solid": "box", "size": [1, 1, 1], "shader": "top", "when": "i % 2 == 0"}]}]
    catalog, made = desk(tmp_path, parts=parts)
    assert len(list(made.create("studio.desk", legs=5).walk())) == 3
    assert list(made.create("studio.desk", legs=0).walk()) == []


def nested_catalog(tmp_path):
    catalog, made = publishing(tmp_path)
    leg = {"name": "leg", "params": {"height": {"default": 0.7, "min": 0.1, "max": 2}}, "slots": {"finish": "studio.oak"},
           "parts": [{"solid": "box", "size": [0.05, "height", 0.05], "shader": "finish"}]}
    catalog.publish_template(PropTemplate.from_data(leg), made, "1.0.0")
    table = {"name": "table", "params": {"height": {"default": 0.8, "min": 0.3, "max": 1.5}}, "slots": {"body": "studio.oak"},
             "parts": [{"solid": "box", "size": [1, 0.04, 1], "shader": "body"},
                       {"prop": "leg", "params": {"height": "height - 0.1"}, "at": [0.4, 0, 0], "yaw": 90,
                        "shaders": {"finish": "$body"}}]}
    catalog.publish_template(PropTemplate.from_data(table), made, "1.0.0")
    return catalog, made, leg


def test_a_nested_prop_takes_parameters_and_slots_from_its_parent(tmp_path):
    catalog, made, _ = nested_catalog(tmp_path)
    top, leg = list(made.create("studio.table", height=1.2, shaders={"body": "studio.steel"}, at=(0, 0, 2)).walk())
    assert leg.item.dimensions()["height"] == pytest.approx(1.1)
    assert leg.item.material == "studio.steel"
    assert leg.world.position.x == pytest.approx(0.4) and leg.world.position.z == pytest.approx(2)


def test_a_nested_prop_stays_on_the_version_it_was_published_with(tmp_path):
    catalog, made, leg = nested_catalog(tmp_path)
    catalog.publish_template(PropTemplate.from_data({**leg, "parts": [
        {"solid": "box", "size": [0.5, "height", 0.5], "shader": "finish"}]}), made, "2.0.0")
    later = Registry.default().use(SharedCatalog.open(catalog.root))
    assert next(later.create("studio.leg").walk()).item.dimensions()["width"] == 0.5
    assert list(later.create("studio.table").walk())[1].item.dimensions()["width"] == 0.05


def test_pins_record_what_a_location_chose_and_not_what_props_nest(tmp_path):
    catalog, made, _ = nested_catalog(tmp_path)
    location = Location("x", made).shot("view", (0, 1, -5), (0, 1, 0))
    location.add("studio.table", shaders={"body": "studio.steel"})
    assert catalog.pins(location) == {"props": {"table": "1.0.0"}, "shaders": {"steel": "1.0.0"}}


def test_pins_bring_back_a_template(tmp_path):
    catalog, made = desk(tmp_path)
    catalog.publish_template(PropTemplate.from_data(desk_data(parts=[
        {"solid": "box", "size": [1, 1, 1], "shader": "top"}])), made, "2.0.0")
    pinned = Registry.default()
    catalog.install(pinned, {"props": {"desk": "1.0.0"}})
    assert len(list(pinned.create("studio.desk").walk())) == 5
    assert len(list(Registry.default().use(SharedCatalog.open(catalog.root)).create("studio.desk").walk())) == 1


def test_nesting_cannot_multiply_past_the_limit(tmp_path):
    """Each level is small, together they are not: the budget is shared across the levels."""
    catalog, made = publishing(tmp_path)
    catalog.publish_template(PropTemplate.from_data({"name": "a", "slots": {"s": "studio.oak"}, "parts": [
        {"repeat": 40, "parts": [{"solid": "box", "size": [1, 1, 1], "shader": "s"}]}]}), made)
    catalog.publish_template(PropTemplate.from_data({"name": "b", "parts": [{"solid": "box", "size": [1, 1, 1], "shader": "s"},
        {"repeat": 100, "parts": [{"prop": "a"}]}], "slots": {"s": "studio.oak"}}), made)
    with pytest.raises(TemplateError, match="more than"):
        catalog.publish_template(PropTemplate.from_data({"name": "c", "parts": [
            {"solid": "box", "size": [1, 1, 1], "shader": "s"}, {"repeat": 100, "parts": [{"prop": "b"}]}],
            "slots": {"s": "studio.oak"}}), made)


def test_republishing_a_template_is_harmless_and_changing_it_needs_a_version(tmp_path):
    catalog, made = desk(tmp_path)
    catalog.publish_template(PropTemplate.from_data(desk_data()), made)
    with pytest.raises(CatalogError, match="bump the version"):
        catalog.publish_template(PropTemplate.from_data(desk_data(variants={})), made)


def test_verify_finds_a_template_whose_nested_prop_went_missing(tmp_path):
    catalog, made, _ = nested_catalog(tmp_path)
    assert catalog.verify() == []
    (catalog.root / "props/leg/1.0.0.json").unlink()
    assert [i.code for i in catalog.verify()] == ["catalog-reference"]


def test_a_foreign_shader_slot_is_copied_into_the_catalog(tmp_path):
    catalog, made = desk(tmp_path, slots={"top": "stock.wood.oak"})
    assert next(made.create("studio.desk").walk()).item.material == "studio.from.stock.wood.oak@1.0.0"
    assert catalog.verify() == []


def test_a_blueprint_sets_parameters_variants_and_slots(tmp_path):
    catalog, _ = desk(tmp_path)
    spec = {"name": "x", "catalogs": [{"path": "shared"}], "nodes": [
        {"use": "studio.desk", "width": 2.0, "at": [1, 0, 0], "shaders": {"top": "studio.steel"}},
        {"use": "studio.desk", "variant": "long", "at": [0, 0, 3]}]}
    path = tmp_path / "x.location.json"
    path.write_text(json.dumps(spec))
    first, second = Blueprint.load(path).build().nodes
    assert next(first.walk()).item.material == "studio.steel"
    assert next(second.walk()).item.dimensions()["width"] == 2.5


def test_a_template_compiles_to_a_valid_scene_in_both_modes(tmp_path):
    catalog, made, _ = nested_catalog(tmp_path)
    location = Location("x", made).shot("view", (0, 1, -5), (0, 1, 0))
    location.add("studio.table", height=1.0)
    for compiler in (SceneCompiler(), WireframeCompiler()):
        assert [f for f in check(compiler.compile(location, "view"), schema=True) if f.severity == "error"] == []


def test_the_example_meeting_table_seats_more_as_it_grows():
    made = Registry.default().use(SharedCatalog.open(ROOT / "catalog"))
    seats = lambda **p: sum(isinstance(n, FrozenProp) and n.entry == "chair" for n in made.create("studio.meeting-table", **p).descend())
    assert seats(length=1.8) < seats() < seats(length=6)
    assert seats(seated=0) == 0


def test_a_ref_cannot_leave_the_catalog_or_float_free_of_its_version(tmp_path):
    catalog, _ = desk(tmp_path)
    (tmp_path / "outside").mkdir()
    (tmp_path / "outside/1.0.0.json").write_text("{}")
    with pytest.raises(CatalogError, match="not an item name"):
        catalog.pinned("../../outside@1.0.0")
    with pytest.raises(CatalogError, match="not a version"):
        catalog.pinned("desk")
    assert catalog.pinned("desk@1.0.0").name == "desk"


@pytest.mark.parametrize("nested,message", [({"params": {"hieght": 1}}, "no parameter 'hieght'; did you mean height"),
                                            ({"shaders": {"nope": "studio.oak"}}, "no shader slot 'nope'")])
def test_a_nested_prop_is_checked_even_in_a_branch_the_trials_never_take(tmp_path, nested, message):
    catalog, made, _ = nested_catalog(tmp_path)
    parts = [{"solid": "box", "size": [1, 1, 1], "shader": "s"}, {"prop": "leg", "when": "0 > 1", **nested}]
    with pytest.raises(CatalogError, match=message):
        catalog.publish_template(PropTemplate.from_data({"name": "x", "slots": {"s": "studio.oak"}, "parts": parts}), made)


def test_a_template_carries_lights_that_follow_its_parameters(tmp_path):
    parts = [{"solid": "box", "size": [1, 1, 1], "shader": "top"},
             {"light": "point", "intensity": "width * 2", "reach": 4, "at": [0, 2, 0]},
             {"light": "spot", "intensity": 3, "cone": 40, "at": [0, 3, 0], "pitch": -90}]
    catalog, made = desk(tmp_path, parts=parts)
    _, point, spot = list(made.create("studio.desk", width=2).walk())
    assert point.item.intensity == 4 and point.item.reach == 4 and spot.item.cone == 40
