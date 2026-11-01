"""Template parameters that are not numbers: on/off, and one of some named choices."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from srlocations import Registry, SharedCatalog
from srlocations.templates import Param, PropTemplate, TemplateError, evaluate


def table(**extra) -> dict:
    return {"name": "desk", "slots": {"oak": "stock.wood.oak", "walnut": "stock.wood.walnut"},
            "params": {"drawers": {"default": False}, "finish": {"default": "oak", "choices": ["oak", "walnut"]},
                       "style": {"default": "plain", "choices": ["plain", "tall"]}, "width": {"default": 1.2}},
            "parts": [{"solid": "box", "size": ["width", 0.04, 0.6], "at": [0, "1.1 if style == 'tall' else 0.72", 0],
                       "shader": "$finish"},
                      {"solid": "box", "when": "drawers", "size": [0.4, 0.5, 0.5], "at": [0.3, 0.4, 0], "shader": "oak"}],
            **extra}


@pytest.fixture
def made(tmp_path):
    registry = Registry.default()
    shared = SharedCatalog.create(tmp_path / "shared", "shared")
    shared.publish_template(PropTemplate.from_data(table()), registry)
    registry.use(shared)
    return registry


def solids(registry, **params) -> list:
    return list(registry.create("shared.desk", **params).walk())


def test_an_on_off_parameter_switches_a_part(made):
    assert len(solids(made)) == 1 and len(solids(made, drawers=True)) == 2


def test_a_choice_steers_an_expression(made):
    assert solids(made)[0].world.position.y == pytest.approx(0.72)
    assert solids(made, style="tall")[0].world.position.y == pytest.approx(1.1)


def test_a_choice_picks_a_shader_slot(made):
    assert solids(made)[0].item.material != solids(made, finish="walnut")[0].item.material
    assert "walnut" in solids(made, finish="walnut")[0].item.material


def test_a_choice_outside_its_list_is_refused(made):
    with pytest.raises(TemplateError, match="finish is 'pine'; it takes oak, walnut"):
        solids(made, finish="pine")


@pytest.mark.parametrize("value", [1, 0, "yes", None])
def test_an_on_off_parameter_takes_only_true_or_false(made, value):
    with pytest.raises(TemplateError, match="must be true or false"):
        solids(made, drawers=value)


def test_a_number_parameter_still_refuses_true_and_text(made):
    for value in (True, "wide"):
        with pytest.raises(TemplateError, match="must be a number"):
            solids(made, width=value)


def test_a_variant_can_set_choices(tmp_path):
    registry = Registry.default()
    shared = SharedCatalog.create(tmp_path / "shared", "shared")
    data = table(variants={"study": {"finish": "walnut", "drawers": True}})
    shared.publish_template(PropTemplate.from_data(data), registry)
    registry.use(shared)
    parts = solids(registry, variant="study")
    assert len(parts) == 2 and "walnut" in parts[0].item.material


def test_a_bad_choice_in_a_variant_is_refused():
    with pytest.raises(TemplateError, match="it takes"):
        PropTemplate.from_data(table(variants={"bad": {"finish": "pine"}})).check()


def test_a_nested_prop_takes_a_choice_from_its_parent(tmp_path):
    registry = Registry.default()
    shared = SharedCatalog.create(tmp_path / "shared", "shared")
    shared.publish_template(PropTemplate.from_data(table()), registry)
    outer = {"name": "office", "params": {"tone": {"default": "walnut", "choices": ["oak", "walnut"]}, "full": {"default": True}},
             "parts": [{"prop": "desk", "params": {"finish": "tone", "drawers": "full"}},
                       {"prop": "desk", "at": [3, 0, 0], "params": {"finish": "'oak'"}}]}
    shared.publish_template(PropTemplate.from_data(outer), registry)
    registry.use(shared)
    materials = [leaf.item.material for leaf in registry.create("shared.office").walk()]
    assert "walnut" in materials[0] and len(materials) == 3 and "oak" in materials[2]


def test_every_choice_is_built_at_publish(tmp_path):
    """Only one choice breaks, and its failure belongs to the publisher."""
    registry = Registry.default()
    shared = SharedCatalog.create(tmp_path / "shared", "shared")
    data = table()
    data["parts"][0]["size"] = ["width if style == 'plain' else 0", 0.04, 0.6]
    with pytest.raises(TemplateError):
        shared.publish_template(PropTemplate.from_data(data), registry)


def test_every_on_off_value_is_built_at_publish(tmp_path):
    registry = Registry.default()
    shared = SharedCatalog.create(tmp_path / "shared", "shared")
    data = table()
    data["parts"][1]["size"] = [0.4, "0 if drawers else 0.5", 0.5]
    with pytest.raises(TemplateError):
        shared.publish_template(PropTemplate.from_data(data), registry)


@pytest.mark.parametrize("change, message", [
    (lambda d: d["params"].update(finish={"default": "oak", "choices": ["oak"], "min": 1}), "no min or max"),
    (lambda d: d["params"].update(drawers={"default": True, "max": 1}), "no min or max"),
    (lambda d: d["params"].update(finish={"default": "pine", "choices": ["oak", "walnut"]}), "it takes"),
    (lambda d: d["params"].update(finish={"default": "oak", "choices": ["oak", 2]}), "not names"),
    (lambda d: d["params"].update(finish={"default": "oak", "choices": ["oak", "ash"]}), "unknown shader slot"),
    (lambda d: d["params"].update(finish={"default": 1.0}), "does not name a parameter with choices"),
    (lambda d: d["parts"][0].update(shader="$absent"), "does not name a parameter with choices"),
])
def test_a_bad_declaration_is_refused(change, message):
    data = table()
    change(data)
    with pytest.raises(TemplateError, match=message):
        PropTemplate.from_data(data).check()


def test_text_can_be_compared_and_not_calculated():
    assert evaluate("1 if a == 'x' else 2", {"a": "x"}) == 1
    assert evaluate("1 if a != 'x' else 2", {"a": "x"}) == 2
    for expression in ("a * 1000000000", "a + a", "'x' * 1000000000"):
        with pytest.raises(TemplateError, match="cannot be calculated"):
            evaluate(expression, {"a": "x"})


def test_a_size_cannot_come_to_text():
    with pytest.raises(TemplateError):
        evaluate("a", {"a": "x"})
    assert evaluate("a", {"a": "x"}, text=True) == "x"


def test_a_numeric_template_keeps_its_stored_form():
    assert Param(1.0).spec() == {"default": 1.0, "min": None, "max": None, "description": ""}
    assert Param("a", choices=["a"]).spec()["choices"] == ["a"]
