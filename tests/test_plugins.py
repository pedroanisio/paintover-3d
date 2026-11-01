"""Plugins reach a registry from a file, a module name or an installed package's entry point."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from srlocations import CatalogError, Location, Plugin, Registry, SceneCompiler
from srlocations.location import Shot

PLUGIN = '''
from dataclasses import dataclass
from srlocations import Box, Plugin, Prefab


@dataclass
class Crate(Prefab):
    width: float = 1.0

    def build(self):
        return [Box((self.width, self.width, self.width), at=(0, self.width / 2, 0), material="{name}.pine")]


class {cls}(Plugin):
    name = "{name}"
    version = "1.2.0"
    requires = {requires}

    def register(self, registry):
        from srlocations import Material
        registry.materials.add("{name}.pine", Material("#c8a165"))
        registry.prefabs.add("{name}.crate", Crate)
'''


def write_plugin(folder: Path, module: str, name: str, cls: str = "Acme", requires: tuple = ()) -> Path:
    path = folder.joinpath(*module.split(".")).with_suffix(".py")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(PLUGIN.format(name=name, cls=cls, requires=requires))
    return path


def install(folder: Path, package: str, entries: dict[str, str], version: str = "1.0") -> None:
    """What pip leaves behind for a package that declares entry points."""
    info = folder / f"{package}-{version}.dist-info"
    info.mkdir()
    (info / "METADATA").write_text(f"Metadata-Version: 2.1\nName: {package}\nVersion: {version}\n")
    lines = "\n".join(f"{name} = {target}" for name, target in entries.items())
    (info / "entry_points.txt").write_text(f"[srlocations.plugins]\n{lines}\n")


@pytest.fixture
def folder(tmp_path, monkeypatch):
    """A folder on the import path, and the modules imported from it forgotten afterwards."""
    monkeypatch.syspath_prepend(str(tmp_path))
    before = set(sys.modules)
    yield tmp_path
    for name in set(sys.modules) - before:
        if name.startswith("acme"):
            del sys.modules[name]


def compiles(registry: Registry, prefab: str) -> None:
    location = Location("yard", registry)
    location.add(prefab)
    location.shots["front"] = Shot("front", (0, 1, -4), (0, 1, 0), 30)
    assert SceneCompiler(64, 36).compile(location, "front") is not None


def test_a_module_name_loads_its_plugin(folder):
    write_plugin(folder, "acme_one", "acme")
    made = Registry.default()
    plugin = made.plugins.load_module("acme_one")
    assert plugin.name == "acme" and plugin.version == "1.2.0" and made.plugins.loaded["acme"] is plugin
    compiles(made, "acme.crate")


def test_a_dotted_module_name_loads_its_plugin(folder):
    write_plugin(folder, "acme_pack.sets.yard", "acme")
    assert Registry.default().plugins.load_module("acme_pack.sets.yard").name == "acme"


def test_a_module_loaded_twice_registers_once(folder):
    write_plugin(folder, "acme_twice", "acme")
    made = Registry.default()
    assert made.plugins.load_module("acme_twice") is made.plugins.load_module("acme_twice")


def test_a_missing_module_says_so():
    with pytest.raises(ImportError, match="acme_absent"):
        Registry().plugins.load_module("acme_absent")


def test_a_module_with_no_plugin_is_refused(folder):
    (folder / "acme_empty.py").write_text("VALUE = 1\n")
    with pytest.raises(CatalogError, match="acme_empty defines 0 Plugin"):
        Registry().plugins.load_module("acme_empty")


def test_a_module_with_two_plugins_is_refused(folder):
    (folder / "acme_two.py").write_text(
        "from srlocations import Plugin\n"
        "class One(Plugin):\n    name = 'one'\n    def register(self, registry): pass\n"
        "class Two(Plugin):\n    name = 'two'\n    def register(self, registry): pass\n")
    with pytest.raises(CatalogError, match="acme_two defines 2 Plugin"):
        Registry().plugins.load_module("acme_two")


def test_a_plugin_a_module_only_imports_does_not_count(folder):
    write_plugin(folder, "acme_base", "acme", "Base")
    (folder / "acme_more.py").write_text(
        "from acme_base import Base\nfrom srlocations import Plugin\n"
        "class More(Plugin):\n    name = 'more'\n    def register(self, registry): pass\n")
    assert Registry().plugins.load_module("acme_more").name == "more"


def test_a_module_cannot_load_ahead_of_what_it_requires(folder):
    write_plugin(folder, "acme_needy", "acme", requires=("base",))
    with pytest.raises(CatalogError, match="requires base"):
        Registry.default().plugins.load_module("acme_needy")


def test_a_plugin_file_can_use_postponed_annotations(tmp_path):
    """A dataclass looks up its module while it is being made, so a file must be a module by then."""
    path = tmp_path / "later.py"
    path.write_text("from __future__ import annotations\n" + PLUGIN.format(name="later", cls="Later", requires=()))
    made = Registry.default()
    assert made.plugins.load_file(path).name == "later"
    compiles(made, "later.crate")


def test_an_installed_package_is_found_by_its_entry_point(folder):
    write_plugin(folder, "acme_sets", "acme")
    install(folder, "acme_sets", {"acme": "acme_sets:Acme"})
    made = Registry.default()
    assert "acme" in made.plugins.loaded and "acme.crate" in made.prefabs
    compiles(made, "acme.crate")


def test_an_entry_point_is_not_loaded_in_another_group(folder):
    write_plugin(folder, "acme_sets", "acme")
    info = folder / "acme_sets-1.0.dist-info"
    info.mkdir()
    (info / "METADATA").write_text("Metadata-Version: 2.1\nName: acme_sets\nVersion: 1.0\n")
    (info / "entry_points.txt").write_text("[console_scripts]\nacme = acme_sets:Acme\n")
    assert "acme" not in Registry.default().plugins.loaded


def test_each_registry_gets_its_own_copy_of_a_plugins_work(folder):
    write_plugin(folder, "acme_sets", "acme")
    install(folder, "acme_sets", {"acme": "acme_sets:Acme"})
    assert "acme.crate" in Registry.default().prefabs and "acme.crate" in Registry.default().prefabs


@pytest.mark.parametrize("needy, needed", [("a", "z"), ("z", "a")])
def test_entry_points_load_in_the_order_they_require(folder, needy, needed):
    """Package order is no one's choice, so either one must be able to need the other."""
    write_plugin(folder, f"acme_{needy}", f"acme-{needy}", "Needy", requires=(f"acme-{needed}",))
    write_plugin(folder, f"acme_{needed}", f"acme-{needed}", "Needed")
    install(folder, f"acme_{needy}", {needy: f"acme_{needy}:Needy"})
    install(folder, f"acme_{needed}", {needed: f"acme_{needed}:Needed"})
    loaded = Registry().plugins.load_entry_points()
    assert [plugin.name for plugin in loaded] == [f"acme-{needed}", f"acme-{needy}"]


def test_an_entry_point_can_require_the_stock_plugin(folder):
    write_plugin(folder, "acme_sets", "acme", requires=("stock",))
    install(folder, "acme_sets", {"acme": "acme_sets:Acme"})
    assert "acme" in Registry.default().plugins.loaded


def test_an_entry_point_missing_what_it_requires_is_refused(folder):
    write_plugin(folder, "acme_sets", "acme", requires=("absent",))
    install(folder, "acme_sets", {"acme": "acme_sets:Acme"})
    with pytest.raises(CatalogError, match="requires absent"):
        Registry.default()


def test_a_circle_of_entry_points_is_refused(folder):
    write_plugin(folder, "acme_a", "acme-a", "A", requires=("acme-b",))
    write_plugin(folder, "acme_b", "acme-b", "B", requires=("acme-a",))
    install(folder, "acme_a", {"a": "acme_a:A"})
    install(folder, "acme_b", {"b": "acme_b:B"})
    with pytest.raises(CatalogError, match="requires"):
        Registry().plugins.load_entry_points()


def test_a_broken_entry_point_is_named(folder):
    install(folder, "acme_sets", {"acme": "acme_absent:Acme"})
    with pytest.raises(CatalogError, match="entry point 'acme'.*acme_absent"):
        Registry().plugins.load_entry_points()


def test_an_entry_point_that_is_not_a_plugin_is_named(folder):
    (folder / "acme_thing.py").write_text("class Thing:\n    pass\n")
    install(folder, "acme_sets", {"acme": "acme_thing:Thing"})
    with pytest.raises(CatalogError, match="entry point 'acme'.*Thing is not a Plugin"):
        Registry().plugins.load_entry_points()


def test_the_stock_plugin_is_a_plugin():
    assert isinstance(Registry.default().plugins.loaded["stock"], Plugin)
