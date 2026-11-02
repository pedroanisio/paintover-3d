"""Characters on marks. A cut-out's place and size only exist in the pixels, so these render."""
import json
import os
import shutil
import struct
import sys
import zlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]

from srlocations import (Actor, Blueprint, CatalogError, Cutout, Ensemble, Flat, Location, Look, PaintLayer, Performer,
                         Portrait, Projection, Registry, Renderer, SceneCompiler, Standee, Sticker, Styled, Vec3, alpha_box)
from srlocations.paint import png_size
from test_looks import GREY, H, RED, BLUE, W, deep, errors, flat_set, near, pixel, stage

FLAT = Styled(Look([Flat()], sky=GREY), W, H, supersample=1)
SRSTUDIO = os.environ.get("SRSTUDIO_PYTHON")
needs_srstudio = pytest.mark.skipif(not SRSTUDIO, reason="set SRSTUDIO_PYTHON to an interpreter with srstudio installed")


def figure(path: Path, color: bytes, size=(40, 80), box=(10, 20, 30, 70), half: bool = False) -> Path:
    """A transparent PNG with a solid block at `box`. With `half`, its left half is blue, to tell a flip by."""
    width, height = size
    left, top, right, bottom = box

    def texel(x: int, y: int) -> bytes:
        if not (left <= x < right and top <= y < bottom):
            return b"\0\0\0\0"
        return b"\0\0\xff\xff" if half and x < (left + right) // 2 else color

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))
    rows = b"".join(b"\0" + b"".join(texel(x, y) for x in range(width)) for y in range(height))
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))
    return path


def set_with_marks() -> Location:
    location = flat_set()
    location.mark("near", (-0.6, 0, 1)).mark("far", (0.6, 0, 3)).mark("same", (0.05, 0, 3))
    return location


def spot(location: Location, point) -> tuple[float, float]:
    return Projection(location.shots["front"], W, H).pixel(Vec3.of(point))


def test_alpha_box_finds_the_figure_through_every_png_filter(tmp_path):
    assert alpha_box(figure(tmp_path / "a.png", b"\xff\0\0\xff")) == (10, 20, 30, 70)
    raw = bytearray()
    width, height = 6, 6
    for number in range(height):
        row = bytearray((b"\0\0\0\0\0\0\0\0" + b"\xff\0\0\xff" * 2 + b"\0\0\0\0\0\0\0\0") if number in (2, 3) else bytes(24))
        kind = number % 5  # each row encoded with a different filter, the way an encoder mixes them
        previous = raw_rows[-1] if (raw_rows := getattr(test_alpha_box_finds_the_figure_through_every_png_filter, "rows", None)) else bytearray(24)
        encoded = bytearray(24)
        for i in range(24):
            a, b, c = (row[i - 4], previous[i], previous[i - 4]) if i >= 4 else (0, previous[i], 0)
            guess = {0: 0, 1: a, 2: b, 3: (a + b) // 2}.get(kind)
            if kind == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                guess = a if pa <= pb and pa <= pc else b if pb <= pc else c
            encoded[i] = (row[i] - guess) & 255
        raw += bytes([kind]) + encoded
        test_alpha_box_finds_the_figure_through_every_png_filter.rows = [row]
    del test_alpha_box_finds_the_figure_through_every_png_filter.rows

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))
    path = tmp_path / "mixed.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(bytes(raw))) + chunk(b"IEND", b""))
    assert alpha_box(path) == (2, 2, 4, 4)


def test_a_picture_redrawn_at_the_same_path_is_read_again(tmp_path):
    """Cut-outs are cached by path, so a character repainted between two renders must not keep its old outline."""
    path = figure(tmp_path / "a.png", b"\xff\0\0\xff", box=(10, 20, 30, 70))
    assert alpha_box(path) == (10, 20, 30, 70)
    figure(path, b"\xff\0\0\xff", box=(2, 4, 6, 8))
    os.utime(path, ns=(os.stat(path).st_atime_ns, os.stat(path).st_mtime_ns + 1))  # a repaint within the same tick still counts
    assert alpha_box(path) == (2, 4, 6, 8)


def test_a_fully_transparent_picture_is_refused(tmp_path):
    with pytest.raises(ValueError, match="fully transparent"):
        alpha_box(figure(tmp_path / "a.png", b"\xff\0\0\xff", box=(0, 0, 0, 0)))


def test_a_character_stands_on_its_mark_at_its_height(tmp_path):
    location = set_with_marks()
    location.cast(Portrait(figure(tmp_path / "a.png", b"\xff\0\0\xff")), "far", height=1.0, shadow=0)
    rows = stage(FLAT, location, "front", tmp_path)
    assert near(pixel(rows, *spot(location, (0.6, 0.5, 3))), RED)
    assert near(pixel(rows, *spot(location, (0.6, 0.05, 3))), RED)  # the feet are on the mark
    assert near(pixel(rows, *spot(location, (0.6, 0.95, 3))), RED)
    assert near(pixel(rows, *spot(location, (0.6, -0.1, 3))), GREY)
    assert near(pixel(rows, *spot(location, (0.6, 1.1, 3))), GREY)  # the margin of the picture did not count as height


def test_a_character_is_sized_by_distance(tmp_path):
    location = set_with_marks()
    picture = Portrait(figure(tmp_path / "a.png", b"\xff\0\0\xff"))
    location.cast(picture, "near", height=1.0, shadow=0)
    location.cast(picture, "far", height=1.0, shadow=0)
    layers = deep(FLAT.compiler().compile(location, "front"), "layer")
    assert len(layers) == 2 and layers[1].scaleY > layers[0].scaleY


def test_the_nearer_character_is_drawn_last_whatever_order_they_were_cast(tmp_path):
    location = set_with_marks()
    red = Portrait(figure(tmp_path / "r.png", b"\xff\0\0\xff", box=(0, 0, 40, 80)))
    blue = Portrait(figure(tmp_path / "b.png", b"\0\0\xff\xff", box=(0, 0, 40, 80)))
    location.mark("front", (0.05, 0, 1)).mark("back", (0.05, 0, 3))
    location.cast(blue, "front", height=1.0, shadow=0)
    location.cast(red, "back", height=1.0, shadow=0)
    rows = stage(FLAT, location, "front", tmp_path)
    assert near(pixel(rows, *spot(location, (0.05, 0.3, 1))), BLUE)
    location.shot("behind", (0.05, 1, 6), (0.05, 1, 0), lens=30)
    rows = stage(FLAT, location, "behind", tmp_path)
    assert near(pixel(rows, *Projection(location.shots["behind"], W, H).pixel(Vec3(0.05, 0.3, 3))), RED)


def test_flip_mirrors_a_character_about_its_feet(tmp_path):
    location = set_with_marks()
    picture = Portrait(figure(tmp_path / "a.png", b"\xff\0\0\xff", box=(0, 0, 40, 80), half=True))
    location.cast(picture, "same", height=1.0, shadow=0, flip=True)
    rows = stage(FLAT, location, "front", tmp_path)
    x, y = spot(location, (0.05, 0.5, 3))
    assert near(pixel(rows, x + 6, y), BLUE) and near(pixel(rows, x - 6, y), RED)


def test_a_character_casts_a_pool_of_shadow(tmp_path):
    location = set_with_marks()
    location.cast(Portrait(figure(tmp_path / "a.png", b"\xff\0\0\xff")), "far", shadow=0.5)
    shapes = deep(FLAT.compiler().compile(location, "front"), "shape")
    assert len(shapes) == 1 and shapes[0].fill.endswith("80")


def test_actors_with_the_same_limits_share_a_layer_and_others_do_not(tmp_path):
    location = set_with_marks()
    picture = Portrait(figure(tmp_path / "a.png", b"\xff\0\0\xff"))
    location.cast(picture, "near")
    location.cast(picture, "far")
    location.cast(picture, "same", looks=["house"])
    assert [len(layer.items[0].actors) for layer in location.paintings] == [2, 1]
    assert errors(SceneCompiler(W, H).compile(location, "front")) == []


def test_a_look_limit_keeps_a_character_out_of_other_looks(tmp_path):
    location = set_with_marks()
    location.cast(Portrait(figure(tmp_path / "a.png", b"\xff\0\0\xff")), "far", looks=["house"])
    assert deep(FLAT.compiler().compile(location, "front"), "layer") == []


def test_one_mark_can_hold_a_mannequin_for_blocking_and_a_character_for_the_finished_look(tmp_path):
    location = set_with_marks()
    location.stand("near", looks=("stock.shaded",))
    location.cast(Portrait(figure(tmp_path / "a.png", b"\xff\0\0\xff")), "near", looks=("example.finished",))
    finished = Look([Flat()], name="example.finished", sky=GREY)
    finished.register(location.registry)
    assert location.validate() == []

    def figures(scene) -> list:
        return [node for node in deep(scene, "object3D") if "left_hand" in (node.id or "").replace("-", "_")]

    blocking = SceneCompiler().compile(location, "front")
    final = Styled(finished, W, H, supersample=1).compiler().compile(location, "front")
    assert figures(blocking) and not deep(blocking, "layer")
    assert deep(final, "layer") and not figures(final)


def test_a_picture_covers_the_frame_once(tmp_path):
    location = flat_set()
    location.paint("final").picture(figure(tmp_path / "half.png", b"\xff\0\0\xff", size=(32, 18), box=(0, 0, 16, 18)))
    rows = stage(FLAT, location, "front", tmp_path)
    assert near(pixel(rows, W * 0.25, H / 2), RED) and near(pixel(rows, W * 0.75, H / 2), GREY)


def test_a_cast_document_carries_its_pictures_with_it(tmp_path):
    location = set_with_marks()
    location.cast(Portrait(figure(tmp_path / "a.png", b"\xff\0\0\xff")), "far")
    document = Renderer().package(location, "front", tmp_path / "out", FLAT)
    (tmp_path / "a.png").unlink()
    assert Renderer().draw(document, tmp_path / "shot.png").exists()


def test_casting_on_a_mark_that_is_not_there_names_the_marks(tmp_path):
    location = set_with_marks()
    with pytest.raises(CatalogError, match="far, near, same"):
        location.cast(Portrait(figure(tmp_path / "a.png", b"\xff\0\0\xff")), "stage")


def test_casting_a_character_that_is_not_registered_suggests_one(tmp_path):
    location = set_with_marks()
    location.registry.cast.add("t.hero", Portrait(figure(tmp_path / "a.png", b"\xff\0\0\xff")), override=True)
    with pytest.raises(CatalogError, match="did you mean t.hero"):
        location.cast("t.hera", "far")
    assert location.cast("t.hero", "far").performer is location.registry.cast.get("t.hero")


def test_a_portrait_has_no_poses(tmp_path):
    with pytest.raises(ValueError, match="no pose"):
        Portrait(figure(tmp_path / "a.png", b"\xff\0\0\xff")).cutout({"mouth": "smile"})


def test_a_plugin_can_bring_a_performer(tmp_path):
    class Twin(Performer):
        def cutout(self, pose):
            return Cutout(figure(tmp_path / f"{pose.get('mood', 'calm')}.png", b"\xff\0\0\xff"), (10, 20, 30, 70))

    location = set_with_marks()
    actor = location.cast(Twin(), "far", pose={"mood": "angry"})
    assert actor.sticker().path.name == "angry.png"


def blueprint_with_cast(tmp_path: Path) -> dict:
    figure(tmp_path / "hero.png", b"\xff\0\0\xff")
    return {"name": "stage", "marks": [{"name": "spot", "at": [0, 0, 3]}],
            "shots": [{"name": "front", "eye": [0, 1, -5], "look_at": [0, 1, 3], "lens": 30}],
            "cast": [{"character": {"image": "hero.png"}, "mark": "spot", "height": 1.2, "shadow": 0}]}


def test_a_blueprint_can_cast_a_picture_named_relative_to_it(tmp_path):
    path = tmp_path / "stage.location.json"
    path.write_text(json.dumps(blueprint_with_cast(tmp_path)))
    location = Blueprint.load(path).build()
    actors = location.paintings[0].items[0].actors
    assert actors[0].height == 1.2 and actors[0].performer.path == tmp_path / "hero.png"


def test_a_blueprint_holds_standees_and_stickers_on_mark_names(tmp_path):
    data = blueprint_with_cast(tmp_path)
    del data["cast"]
    data["paint"] = [{"name": "cast", "items": [
        {"kind": "sticker", "at": "spot", "path": "hero.png", "height": 1.0},
        {"kind": "standee", "at": "spot", "marks": [{"kind": "disc", "center": [0, 1, 0], "radius": 0.2, "color": RED},
                                                    {"kind": "fill", "points": [[0, 0], [1, 0], [0, 1]]}]}]}]
    path = tmp_path / "stage.location.json"
    path.write_text(json.dumps(data))
    location = Blueprint.load(path).build()
    sticker, standee = location.paintings[0].items
    assert isinstance(sticker, Sticker) and sticker.at == Vec3(0, 0, 3) and sticker.path == tmp_path / "hero.png"
    assert isinstance(standee, Standee) and standee.at == Vec3(0, 0, 3) and len(standee.marks) == 2
    assert errors(SceneCompiler(W, H).compile(location, "front")) == []


def test_a_mark_with_a_name_that_is_not_a_mark_is_refused(tmp_path):
    data = blueprint_with_cast(tmp_path)
    del data["cast"]
    data["paint"] = [{"name": "cast", "items": [{"kind": "sticker", "at": "nowhere", "path": "hero.png"}]}]
    with pytest.raises(ValueError, match="layer 'cast'.*no such mark"):
        Blueprint(data, tmp_path).build()


@needs_srstudio
def test_an_srstudio_character_is_cast_and_cached(tmp_path, monkeypatch):
    from srlocations.srstudio import SrstudioCast, _cutout
    monkeypatch.setenv("SRLOCATIONS_CACHE", str(tmp_path / "cache"))
    _cutout.cache_clear()
    registry = Registry()
    registry.plugins.load(SrstudioCast())
    cut = registry.cast.get("srstudio.pip").cutout({})
    left, top, right, bottom = cut.box
    width, height = png_size(cut.path)
    assert 0 < left < right < width and 0 < top < bottom < height  # nothing is cut off by the edge of the canvas
    assert cut.path.parent == tmp_path / "cache" / "cast"
    stamp = cut.path.stat().st_mtime_ns
    _cutout.cache_clear()
    assert registry.cast.get("srstudio.pip").cutout({}).path.stat().st_mtime_ns == stamp


@needs_srstudio
def test_a_pose_changes_the_drawing_and_a_bad_one_names_the_choices(tmp_path, monkeypatch):
    from srlocations.srstudio import SrstudioCast
    monkeypatch.setenv("SRLOCATIONS_CACHE", str(tmp_path / "cache"))
    registry = Registry()
    registry.plugins.load(SrstudioCast())
    pip = registry.cast.get("srstudio.pip")
    assert pip.cutout({}).path != pip.cutout({"arms": "wave-a"}).path
    with pytest.raises(CatalogError, match="not in its style"):
        pip.cutout({"arms": "moonwalk"})


def test_srstudio_needs_to_be_named(monkeypatch):
    from srlocations.srstudio import SrstudioCast
    monkeypatch.delenv("SRSTUDIO_PYTHON", raising=False)
    with pytest.raises(CatalogError, match="SRSTUDIO_PYTHON"):
        Registry().plugins.load(SrstudioCast())
