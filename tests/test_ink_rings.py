"""Lines across curved solids."""
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]

from test_looks import H, W, deep, errors, flat_set, near, pixel, solid_png, stage

from srlocations import Box, Cone, Cylinder, Flat, Ink, Location, Look, Mesh, Registry, Renderer, Sphere, Styled
from srlocations.geometry import Transform
from srlocations.stock.mannequin import Mannequin
from srlocations.surfaces import Surface

INK = "#000000"
PLAIN = "#c8c8c8"


def inked(**params) -> Styled:
    return Styled(Look([Flat({"": PLAIN}), Ink(width=2, **params)], sky="#ffffff", name="inked"), W, H, 1)


def lines_down(rows, x) -> int:
    """How many dark lines a column crosses."""
    dark = [sum(pixel(rows, x, y)) < 200 for y in range(H)]
    return sum(b and not a for a, b in zip(dark, dark[1:]))


@pytest.mark.parametrize("solid", [Cylinder(1, 3, at=(0, 1, 3)), Cone(1.2, 3, at=(0, 1, 3)), Sphere(1.5, at=(0, 1, 3))])
def test_rings_cross_a_curved_solid(tmp_path, solid):
    def shot(**params):
        location = flat_set()
        location.add(solid)
        return lines_down(stage(inked(**params), location, "front", tmp_path), W / 2)
    assert shot() == 2  # the outline, in and out
    assert shot(rings=0.5) >= 6


def test_lines_stay_as_far_apart_on_a_small_solid_as_on_a_big_one():
    assert len(Cylinder(1, 4).bands(0.5)) == 8 and len(Sphere(1).bands(0.5)) == 6
    assert len(Cone(1, 3).bands(0.5)) == round(math.hypot(1, 3) / 0.5)


@pytest.mark.parametrize("solid", [Cylinder(0.1, 0.2), Sphere(0.05), Cone(0.1, 0.2)])
def test_a_solid_too_small_for_a_line_stays_whole(solid):
    assert solid.bands(0.5) == []


@pytest.mark.parametrize("solid", [Cylinder(1, 4), Cone(1, 3), Sphere(1.5)])
def test_bands_fill_the_solid_and_stop_at_it(solid):
    low, high = solid.bounds(Transform())
    bands = solid.bands(0.5)
    tops = [band.bounds(Transform()) for band in bands]
    assert min(b[0].y for b in tops) == pytest.approx(low.y, abs=1e-6)
    assert max(b[1].y for b in tops) == pytest.approx(high.y, abs=1e-6)
    assert all(a[1].y == pytest.approx(b[0].y, abs=1e-6) for a, b in zip(tops, tops[1:]))
    assert all(b[1].x <= high.x + 0.01 for b in tops)


def test_a_surface_divides_along_v_by_its_length():
    tube = Surface("cos(u)", "v", "sin(u)", u=(0, 360), v=(0, 3), closed=(True, False))
    bands = tube.bands(0.5)
    assert len(bands) == 6 and bands[0].v == (0, 0.5) and bands[-1].v == (2.5, 3) and bands[0].u == (0, 360)
    assert tube.v == (0, 3)


def test_a_closed_surface_opens_when_it_is_divided():
    torus = Surface("(2 + cos(v)) * cos(u)", "sin(v)", "(2 + cos(v)) * sin(u)", u=(0, 360), v=(0, 360), closed=(True, True))
    assert torus.bands(1)[0].closed == (True, False)


def test_a_box_gains_nothing(tmp_path):
    def nodes(**params):
        location = flat_set()
        location.add(Box((2, 2, 2), at=(0, 1, 3)))
        return len(deep(Renderer().compile(location, "front", inked(**params)), "object3D"))
    assert nodes() == nodes(rings=0.1)


def test_a_model_keeps_its_outline(tmp_path):
    model = tmp_path / "tri.obj"
    model.write_text("v -1 0 0\nv 1 0 0\nv 0 2 0\nf 1 2 3\n")
    assert Mesh(model).bands(0.1) == []


def test_rings_need_creases():
    location = flat_set()
    location.add(Cylinder(1, 3, at=(0, 1, 3)))
    scene = Renderer().compile(location, "front", inked(rings=0.5, creases=False))
    assert not deep(scene, "parametricSurface")


def test_rings_are_valid_and_survive_a_look_as_data():
    registry = Registry.default()
    location = flat_set()
    location.add(Sphere(1, at=(0, 1, 3)))
    look = Look([Ink(rings=0.25)], name="inked")
    assert errors(Renderer().compile(location, "front", Styled(look, W, H, 1))) == []
    assert Look.from_spec(look.spec(registry), registry).passes[0].rings == 0.25


def test_a_figure_keeps_its_shape_under_rings(tmp_path):
    location = flat_set()
    location.add(Mannequin(at=(0, 0, 2), solid=False))
    assert errors(Renderer().compile(location, "front", inked(rings=0.2))) == []


def test_a_look_without_rings_keeps_the_digest_it_was_published_with():
    assert Ink().spec() == {"color": "#000000", "width": 2.0, "vary": 0.0, "wobble": 0.0, "creases": True,
                            "shadow": 0.0, "shadow_offset": (5.0, -6.0)}
    assert Ink(rings=0.3).spec()["rings"] == 0.3


def test_rings_survive_a_look_being_written_out_and_read_back():
    registry = Registry.default()
    look = Look([Ink(rings=0.3)], name="engraved")
    assert Look.from_spec(look.spec(registry), registry).passes[0].rings == 0.3
