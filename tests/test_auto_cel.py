"""Cel's cut, measured from the shot."""
import sys
import warnings
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]

from test_looks import H, W, deep, flat_set, pixel, stage

import srlocations.looks
from srlocations import Box, Cel, Flat, Look, Registry, Renderer, Styled
from srlocations.looks import cut_for
from srlocations.nodes import Ambient, Sun
from srlocations.stock.looks import ink_toon


def yard(sun: float, ambient: float = 0.4):
    """A wall half in shadow, under a sun of this strength."""
    location = flat_set()
    location.add(Box((12, 6, 0.2), at=(0, 3, 4), material="t.grey"))
    location.add(Box((1.5, 4, 0.6), at=(-1.5, 2, 1.5), material="t.grey"))
    location.add(Ambient(ambient))
    location.add(Sun(sun, yaw=25, pitch=-30))
    return location


def cut_in(scene) -> float:
    return float(next(p.value for p in deep(scene, "param") if p.name == "cut"))


def tints(rows) -> set:
    return {pixel(rows, x, y) for x in range(0, W, 6) for y in range(0, H, 6)}


def toon(cut):
    return Styled(Look([Flat(), Cel(cut=cut, shade="#404040")], name="toon"), W, H, 1)


def test_a_number_is_left_alone():
    assert cut_in(Renderer().compile(yard(1.0), "front", toon(0.37))) == 0.37


def test_auto_follows_the_light_of_the_shot():
    assert cut_in(Renderer().compile(yard(0.25, 0.1), "front", toon("auto"))) \
        < cut_in(Renderer().compile(yard(1.5, 0.3), "front", toon("auto")))


@pytest.mark.parametrize("sun,ambient", [(0.25, 0.1), (1.5, 0.3)])
def test_auto_keeps_both_tones_in_a_dim_set_and_a_bright_one(tmp_path, sun, ambient):
    shot = stage(toon("auto"), yard(sun, ambient), "front", tmp_path)
    assert len({tint for tint in tints(shot) if sum(tint) > 0}) >= 2


def test_a_fixed_cut_loses_the_dim_set_that_auto_keeps(tmp_path):
    fixed = stage(toon(0.9), yard(0.25, 0.1), "front", tmp_path)
    assert len({tint for tint in tints(fixed) if sum(tint) > 0}) == 1


def test_one_tone_is_not_all_shade():
    assert cut_for([0.07] * 100) < 0.07


def test_the_brightest_surfaces_set_the_line():
    assert cut_for([0.2] * 80 + [0.8] * 20) == pytest.approx(0.48)


def test_a_shot_of_only_sky_uses_the_ordinary_cut():
    assert cut_for([]) == 0.5


def test_auto_without_an_engine_warns_and_still_compiles(monkeypatch):
    monkeypatch.setattr(srlocations.looks, "Renderer", lambda: Renderer("/no/such/engine"))
    with pytest.warns(UserWarning, match="cannot measure"):
        scene = Renderer().compile(yard(1.0), "front", toon("auto"))
    assert cut_in(scene) == 0.5


def test_a_word_other_than_auto_is_refused():
    with pytest.raises(ValueError, match="auto"):
        Cel(cut="soft")


def test_auto_survives_a_look_as_data():
    registry = Registry.default()
    spec = ink_toon(cut="auto").spec(registry)
    assert Look.from_spec(spec, registry).passes[1].cut == "auto"


def test_paint_is_not_measured(tmp_path):
    bare, painted = yard(1.0), yard(1.0)
    painted.paint("over").disc((0.5, 0.5), 0.6, color="#ffffff", frame=True)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        assert cut_in(Renderer().compile(bare, "front", toon("auto"))) \
            == cut_in(Renderer().compile(painted, "front", toon("auto")))
