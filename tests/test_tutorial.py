"""The tutorial's Python runs, in order, as one script, and the tests it teaches pass."""
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="module")
def tutorial(tmp_path_factory, request):
    folder = tmp_path_factory.mktemp("tutorial")
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.chdir(folder)
    blocks = re.findall(r"```python\n(.*?)```", (ROOT / "docs" / "tutorial.md").read_text(), re.S)
    scope = {"__name__": "tutorial"}
    sys.modules["tutorial"] = type(sys)("tutorial")  # a dataclass looks its module up while it is being made
    exec(compile("\n".join(blocks), "docs/tutorial.md", "exec"), scope)
    del sys.modules["tutorial"]
    request.addfinalizer(monkeypatch.undo)
    return folder, scope


def test_the_tutorial_runs(tutorial):
    folder, scope = tutorial
    assert {"booth-empty.png", "booth-shaded.png", "booth-eyes.png", "booth-sketch.png", "booth-warm.png", "booth-paint.png",
            "booth-published.png"} <= {path.name for path in (folder / "renders").iterdir()}
    assert "booth.desk" in scope["registry"].prefabs
    assert "booth.stool" not in scope["published"].registry.prefabs  # the published booth has no need of the plugin
    assert "studio.desk" in scope["published"].registry.prefabs


@pytest.mark.parametrize("name", ["test_a_seed_repeats", "test_the_booth_is_sound", "test_the_check_speaks_up"])
def test_the_tests_it_teaches_pass(tutorial, name):
    tutorial[1][name]()


def test_a_frozen_stool_keeps_its_seat(tutorial):
    """A prop published now carries its seats, so a figure can sit on it from a catalog."""
    from srlocations import Location, Registry, SharedCatalog
    scope = tutorial[1]
    studio = SharedCatalog.open("shared")
    registry = scope["registry"]
    studio.publish_prop("stool", scope["Stool"](cushion="studio.felt"), registry)
    location = Location("set", Registry.default().use(SharedCatalog.open("shared")))
    location.add("studio.stool")
    wanted = list(scope["Stool"](cushion="studio.felt").seating())
    found = location.seats()
    assert len(found) == len(wanted) == 1 and (found[0].at - wanted[0].at).length < 1e-6
