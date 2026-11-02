"""The Location Book, docs/location-book.md, is kept true by hand in the same commit as the change it describes. These
tests fail when a published location or one of its versions is missing from it, when it has a section for a location
that is not published, or when it names a file, folder, link or picture that does not exist."""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
BOOK = ROOT / "docs" / "location-book.md"
LOCATIONS = ROOT / "catalog" / "locations"


def book() -> str:
    return BOOK.read_text()


def sections() -> dict[str, str]:
    """Each location's section, by the name in its `### name` heading."""
    found = {}
    names = re.findall(r"^### ([a-z][a-z0-9-]*)$", book(), re.M)
    for name in names:
        after = book().split(f"\n### {name}\n", 1)[1]
        found[name] = after.split("\n### ", 1)[0].split("\n## ", 1)[0]
    return found


def published() -> dict[str, list[str]]:
    return {folder.name: sorted(path.stem for path in folder.glob("*.json")) for folder in LOCATIONS.iterdir() if folder.is_dir()}


def test_every_published_location_has_a_section():
    assert set(published()) <= set(sections()), f"missing from the book: {set(published()) - set(sections())}"


def test_every_section_is_a_published_location():
    assert set(sections()) <= set(published()), f"in the book but not published: {set(sections()) - set(published())}"


@pytest.mark.parametrize("name", sorted(published()))
def test_every_published_version_is_in_its_section(name):
    section = sections()[name]
    listed = set(re.findall(r"^\| (\d+\.\d+\.\d+) \|", section, re.M))
    assert set(published()[name]) == listed, f"{name}: published {published()[name]}, book lists {sorted(listed)}"


def test_every_link_and_picture_in_the_book_exists():
    missing = []
    for target in re.findall(r"\]\(([^)]+)\)", book()):
        if target.startswith(("http://", "https://")):
            continue
        path = target.split("#", 1)[0]
        if path and not (BOOK.parent / path).exists():
            missing.append(target)
    assert not missing


def test_every_repository_path_the_book_names_exists():
    """A path in backticks under one of the repository's folders must exist, unless it is a pattern with <...> or *."""
    missing = []
    for name in re.findall(r"`((?:examples|tests|catalog|docs|srlocations)/[^`\s]+)`", book()):
        if "<" in name or "*" in name:
            continue
        if not (ROOT / name).exists():
            missing.append(name)
    assert not missing


def test_the_test_count_is_quoted_as_collected():
    assert re.search(r"^\d[\d,]* tests collected in [\d.]+s$", book(), re.M)
    assert "not a count passed" in book()
