"""Documents that leave this machine. The tests that move a package render it, because only the engine can say what it reads."""
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from sr_core.vpkg import archive as vpkg

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]

from srlocations import Box, Flat, Ink, Lit, Location, Look, Material, PaintLayer, Picture, Registry, Renderer, SceneCompiler
from srlocations import Styled, StyledCompiler, Texture
from srlocations import compiler as compilers
from srlocations.portable import archive, package
from srlocations.stock.looks import ink_toon, paper_cutout
from test_looks import half_png, materials, solid_png

W, H = 320, 180
ABSOLUTE = re.compile(r'(?:src|\w+Map)="(/[^"]*)"')


def textured_set(folder: Path) -> tuple[Location, Look]:
    """Every kind of file a document can name here: a map, a look's texture, the look's shaders and a finished paintover."""
    made = Registry.default()
    made.materials.add("t.grey", Material("#808080"), override=True)
    made.materials.add("t.map", Material("#ffffff", maps={"baseColorMap": str(half_png(folder / "map.png"))}), override=True)
    location = Location("test set", made)
    location.add(Box((3, 3, 0.2), at=(-1.6, 1, 3), material="t.map"))
    location.add(Box((3, 3, 0.2), at=(1.6, 1, 3), material="t.grey"))
    location.shot("front", (0, 1, -5), (0, 1, 3), lens=30)
    location.paint("final").picture(solid_png(folder / "over.png", b"\0\xff\0\x40"))
    return location, Look([Flat(), Ink()], textures={"t.grey": Texture(half_png(folder / "tex.png"), tile=0.5)})


def test_a_compiled_scene_names_local_files_and_a_package_does_not(tmp_path):
    location, look = textured_set(tmp_path)
    scene = StyledCompiler(look, W, H).compile(location, "front")
    assert ABSOLUTE.findall(scene.to_bytes().decode())
    document = package(scene, tmp_path / "out" / "shot.scene.xml")
    text = document.read_text()
    assert not ABSOLUTE.findall(text) and str(tmp_path) not in text and "/home" not in text
    assert 'src="assets/' in text and 'baseColorMap="assets/' in text


def test_packaging_leaves_the_scene_alone(tmp_path):
    location, look = textured_set(tmp_path)
    scene = StyledCompiler(look, W, H).compile(location, "front")
    before = scene.to_bytes()
    package(scene, tmp_path / "out" / "shot.scene.xml")
    assert scene.to_bytes() == before


@pytest.mark.parametrize("look", [ink_toon(), paper_cutout()], ids=["ink-toon", "paper"])
def test_a_moved_package_renders_the_same_with_its_sources_gone(tmp_path, look):
    source = tmp_path / "source"
    source.mkdir()
    location, _ = textured_set(source)
    look.textures["t.grey"] = Texture(half_png(source / "tex.png"), tile=0.5)
    renderer = Renderer()
    direct = renderer.render(location, "front", tmp_path / "direct.png", Styled(look, W, H, 1))
    document = renderer.package(location, "front", tmp_path / "made-here", Styled(look, W, H, 1))
    shutil.move(tmp_path / "made-here", tmp_path / "elsewhere")
    shutil.rmtree(source)
    moved = renderer.draw(tmp_path / "elsewhere" / document.name, tmp_path / "moved.png")
    assert moved.read_bytes() == direct.read_bytes()


def test_an_archive_verifies_unpacks_and_renders(tmp_path):
    location, look = textured_set(tmp_path)
    renderer = Renderer()
    direct = renderer.render(location, "front", tmp_path / "direct.png", Styled(look, W, H, 1))
    pack = renderer.archive(location, "front", tmp_path / "shot.vpkg.zip", Styled(look, W, H, 1))
    assert pack.is_file() and not vpkg.verify(str(pack)).errors
    vpkg.unpack(str(pack), str(tmp_path / "opened"))
    moved = renderer.draw(tmp_path / "opened" / "project" / "test-set-front.scene.xml", tmp_path / "moved.png")
    assert moved.read_bytes() == direct.read_bytes()


def test_a_package_is_the_same_every_time(tmp_path):
    location, look = textured_set(tmp_path)
    compile_ = lambda: StyledCompiler(look, W, H).compile(location, "front")
    assert package(compile_(), tmp_path / "a" / "s.xml").read_bytes() == package(compile_(), tmp_path / "b" / "s.xml").read_bytes()
    assert sorted(path.name for path in (tmp_path / "a/assets").iterdir()) == sorted(path.name for path in (tmp_path / "b/assets").iterdir())


def test_an_archive_is_the_same_every_time(tmp_path):
    location, look = textured_set(tmp_path)
    scene = StyledCompiler(look, W, H).compile(location, "front")
    assert archive(scene, tmp_path / "a.zip", "shot").read_bytes() == archive(scene, tmp_path / "b.zip", "shot").read_bytes()


def test_shots_in_one_folder_share_their_files(tmp_path):
    location, look = textured_set(tmp_path)
    location.shot("other", (0, 1, -4), (0, 1, 3), lens=30)
    renderer = Renderer()
    documents = {renderer.package(location, shot, tmp_path / "out", Styled(look, W, H, 1)) for shot in ("front", "other")}
    assets = list((tmp_path / "out/assets").iterdir())
    assert len(documents) == 2
    assert all(renderer.draw(document, tmp_path / f"{document.stem}.png").is_file() for document in documents)
    assert len(assets) == len({path.read_bytes() for path in assets})


def test_two_paths_to_one_picture_become_one_file(tmp_path):
    location = Location("t", Registry.default())
    first, second = half_png(tmp_path / "a.png"), tmp_path / "b.PNG"
    shutil.copyfile(first, second)
    location.registry.materials.add("t.a", Material("#ffffff", maps={"baseColorMap": str(first)}))
    location.registry.materials.add("t.b", Material("#ffffff", maps={"baseColorMap": str(second)}))
    location.add(Box((1, 1, 1), material="t.a"))
    location.add(Box((1, 1, 1), at=(2, 0, 0), material="t.b"))
    location.shot("s", (0, 1, -5), (0, 1, 3))
    package(SceneCompiler(W, H).compile(location, "s"), tmp_path / "out/s.xml")
    assert len(list((tmp_path / "out/assets").iterdir())) == 1


def test_a_relative_map_is_found_from_where_python_runs(tmp_path, monkeypatch):
    half_png(tmp_path / "map.png")
    monkeypatch.chdir(tmp_path)
    location = Location("t", Registry.default())
    location.registry.materials.add("t.map", Material("#ffffff", maps={"baseColorMap": "map.png"}))
    location.add(Box((1, 1, 1), at=(0, 1, 3), material="t.map"))
    location.shot("s", (0, 1, -5), (0, 1, 3))
    assert Renderer().render(location, "s", tmp_path / "s.png", "stock.shaded", width=W, height=H, supersample=1).is_file()


def test_a_missing_file_is_named(tmp_path):
    location = Location("t", Registry.default())
    location.registry.materials.add("t.map", Material("#ffffff", maps={"baseColorMap": "/no/such/map.png"}))
    location.add(Box((1, 1, 1), material="t.map"))
    location.shot("s", (0, 1, -5), (0, 1, 3))
    with pytest.raises(FileNotFoundError, match="/no/such/map.png"):
        package(SceneCompiler(W, H).compile(location, "s"), tmp_path / "s.xml")


def test_a_remote_url_stays_a_url(tmp_path):
    location = Location("t", Registry.default())
    location.registry.materials.add("t.map", Material("#ffffff", maps={"baseColorMap": "https://example.com/map.png"}))
    location.add(Box((1, 1, 1), material="t.map"))
    location.shot("s", (0, 1, -5), (0, 1, 3))
    assert "https://example.com/map.png" in package(SceneCompiler(W, H).compile(location, "s"), tmp_path / "s.xml").read_text()


def test_the_engine_is_found_beside_python_then_on_the_path(tmp_path, monkeypatch):
    beside = tmp_path / "venv" / "scene-render"
    beside.parent.mkdir()
    beside.touch()
    monkeypatch.setattr(compilers.sys, "executable", str(tmp_path / "venv" / "python"))
    assert compilers.find_engine() == beside
    beside.unlink()
    monkeypatch.setattr(compilers.shutil, "which", lambda name: f"/opt/bin/{name}")
    assert compilers.find_engine() == Path("/opt/bin/scene-render")
    assert Renderer("/custom/engine").engine == Path("/custom/engine")


@pytest.mark.skipif(not (ROOT / ".git").exists(), reason="needs a checkout")
def test_the_repository_holds_no_path_from_this_machine():
    tracked = subprocess.run(["git", "ls-files", "-co", "--exclude-standard"], cwd=ROOT, capture_output=True, text=True, check=True)
    home = str(Path.home())
    needle = re.compile(re.escape(home).encode())
    found = [name for name in tracked.stdout.splitlines() if name != "tests/test_portable.py"
             and (ROOT / name).is_file() and needle.search((ROOT / name).read_bytes())]
    assert found == []
