"""A page of what a catalog holds."""
import re
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]

from srlocations import Flat, Ink, Look, Material, Registry, Renderer, SharedCatalog
from srlocations import browse
from srlocations.exchange import allowed
from srlocations.stock.prefabs import Table


@pytest.fixture
def shelf(tmp_path) -> SharedCatalog:
    catalog = SharedCatalog.create(tmp_path / "shelf", "shelf")
    registry = Registry.default()
    catalog.publish_shader("oak", Material("#8a5a33", 0.5), tags=["wood"], description="Warm oak")
    catalog.publish_prop("desk", Table(), registry, tags=["furniture"])
    catalog.publish_look("sketch", Look([Flat(), Ink()]), registry)
    return catalog


def pictures(folder: Path) -> list:
    return sorted(path.name for path in folder.glob("*.png"))


def test_a_page_shows_every_kind_with_a_picture(shelf):
    page = shelf.browse()
    text = page.read_text()
    assert page == shelf.root / "browse/index.html"
    for word in ("Props", "Shaders", "Looks", "shelf.oak@1.0.0", "shelf.desk@1.0.0", "Warm oak", "wood"):
        assert word in text
    assert len(pictures(page.parent)) == len(shelf.search())
    assert all((page.parent / name).stat().st_size > 1000 for name in pictures(page.parent))


def test_every_picture_on_the_page_is_there(shelf):
    page = shelf.browse()
    assert sorted(re.findall(r'src="([^"]+)"', page.read_text())) == pictures(page.parent)


def test_what_a_catalog_says_cannot_run_on_the_page(tmp_path):
    catalog = SharedCatalog.create(tmp_path / "shelf", "shelf")
    catalog.publish_shader("oak", Material("#8a5a33"), tags=['"><img src=x onerror=alert(1)>'],
                           description="<script>alert('hi')</script>")
    text = catalog.browse(thumbnails=False).read_text()
    assert "<script>alert" not in text and "<img src=x" not in text and "&lt;script&gt;" in text


def test_the_page_stands_alone():
    assert not re.search(r"""(src|href)=["']?https?:""", browse.PAGE) and "@import" not in browse.PAGE


def test_a_picture_is_drawn_once(shelf, monkeypatch):
    shelf.browse()
    drawn = []
    monkeypatch.setattr(browse, "thumbnail", lambda *args: drawn.append(args))
    shelf.browse()
    assert drawn == []


def test_a_new_version_gets_its_own_picture(shelf):
    shelf.browse()
    shelf.publish_shader("oak", Material("#8a5a44", 0.5), version="1.1.0")
    assert len(pictures(shelf.browse().parent)) == len(shelf.search()) + 1


def test_only_the_newest_version_is_listed(shelf):
    shelf.publish_shader("oak", Material("#8a5a44", 0.5), version="1.1.0")
    text = shelf.browse(thumbnails=False).read_text()
    assert "shelf.oak@1.1.0" in text and "shelf.oak@1.0.0" not in text


def test_without_an_engine_the_page_still_comes(shelf, monkeypatch):
    monkeypatch.setattr(browse, "Renderer", lambda: Renderer("/no/such/engine"))
    with pytest.warns(UserWarning, match="no thumbnail"):
        page = shelf.browse()
    assert "shelf.desk@1.0.0" in page.read_text() and pictures(page.parent) == []


def test_it_can_go_elsewhere(shelf, tmp_path):
    page = shelf.browse(tmp_path / "site", thumbnails=False)
    assert page == tmp_path / "site/index.html" and not (shelf.root / "browse").exists()


def test_a_page_counts_as_catalog_data_and_harms_nothing(shelf):
    page = shelf.browse()
    assert allowed(page.relative_to(shelf.root).as_posix())
    assert all(allowed(f"browse/{name}") for name in pictures(page.parent))
    assert shelf.verify() == []


def test_the_example_catalog_lists_every_item(tmp_path):
    copy = tmp_path / "copy"
    shutil.copytree(ROOT / "catalog", copy)
    catalog = SharedCatalog.open(copy)
    text = catalog.browse(thumbnails=False).read_text()
    assert all(f"{catalog.name}.{entry.name}@{entry.version}" in text for entry in catalog.search())
