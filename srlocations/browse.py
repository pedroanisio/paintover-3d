"""A page to see what is in a shared catalog: a static folder that opens from disk or from a CatalogServer. Thumbnails are
named by the entry's digest, so a version that has not changed is not drawn again."""
from __future__ import annotations

import html
import warnings
from pathlib import Path
from typing import Any, Optional, Union

from srlocations.compiler import Renderer
from srlocations.geometry import Vec3
from srlocations.location import Location
from srlocations.looks import Lit, Look, Styled
from srlocations.nodes import Box, Sphere
from srlocations.registry import CatalogError, Registry

SIZE = (320, 200)
MAX_REACH = 300.0  # a prop as big as a landscape is seen from inside it, within what the camera reaches
FOLDER = "browse"
PLAIN = Look([Lit()], sky="#d9dde0", name="catalog.thumbnail")
KIND_TITLES = {"prop": "Props", "shader": "Shaders", "look": "Looks", "location": "Locations"}

PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title><style>
:root{{--page:#f6f5f2;--card:#fff;--ink:#23262a;--soft:#666d75;--line:#dcdbd6}}
@media (prefers-color-scheme:dark){{:root{{--page:#191b1e;--card:#23262a;--ink:#e8e6e1;--soft:#a0a6ad;--line:#383c42}}}}
body{{margin:0 auto;max-width:1120px;padding:24px 16px;background:var(--page);color:var(--ink);font:15px/1.45 system-ui,sans-serif}}
h1{{font-size:24px;margin:0 0 4px}}h2{{font-size:17px;margin:28px 0 10px}}
input{{width:100%;box-sizing:border-box;margin:14px 0 4px;padding:9px 11px;border:1px solid var(--line);border-radius:6px;
background:var(--card);color:var(--ink);font:inherit}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:14px}}
article{{background:var(--card);border:1px solid var(--line);border-radius:8px;overflow:hidden}}
img,.none{{display:block;width:100%;aspect-ratio:8/5;object-fit:cover;background:var(--line)}}
.text{{padding:9px 11px 11px}}b{{display:block;overflow-wrap:anywhere}}small{{color:var(--soft)}}p{{margin:5px 0 0}}
code{{display:block;margin-top:6px;font-size:12px;color:var(--soft);overflow-wrap:anywhere}}
</style></head><body><h1>{title}</h1><small>{count} items, the newest version of each</small>
<input type="search" placeholder="Filter by name, tag or description" aria-label="Filter">
{sections}
<script>
const box=document.querySelector("input"),cards=[...document.querySelectorAll("article")];
box.addEventListener("input",()=>{{const q=box.value.toLowerCase();
for(const c of cards)c.hidden=!c.textContent.toLowerCase().includes(q);
for(const s of document.querySelectorAll("section"))s.hidden=![...s.querySelectorAll("article")].some(c=>!c.hidden)}});
</script></body></html>
"""


def framed(location: Location, centre: Vec3, reach: float) -> None:
    location.shot("thumbnail", centre + Vec3(reach * 1.0, reach * 0.65, -reach * 1.7), centre, lens=35)


def table(location: Location, y: float, reach: float) -> None:
    location.add(Box((reach * 12, 0.02, reach * 12), at=(0, y - 0.01, 0), material="stock.plaster.white"))
    location.rig("stock.daylight")


def of_shader(catalog: Any, entry: Any, registry: Registry) -> tuple[Location, Any]:
    location = Location("thumbnail", registry)
    location.add(Sphere(0.5, at=(0, 0.5, 0), material=f"{catalog.name}.{entry.name}@{entry.version}"))
    table(location, 0.0, 1.0)
    framed(location, Vec3(0, 0.5, 0), 1.0)
    return location, Styled(PLAIN, *SIZE, supersample=1)


def of_prop(catalog: Any, entry: Any, registry: Registry) -> tuple[Location, Any]:
    location = Location("thumbnail", registry)
    prop = location.add(f"{catalog.name}.{entry.name}@{entry.version}")
    bounds = [leaf.item.bounds(leaf.world) for leaf in prop.walk() if hasattr(leaf.item, "bounds")]
    low = Vec3(*(min(getattr(b[0], a) for b in bounds) for a in "xyz"))
    high = Vec3(*(max(getattr(b[1], a) for b in bounds) for a in "xyz"))
    reach = min(max(max(high - low), 0.2), MAX_REACH)
    table(location, low.y, reach)
    framed(location, Vec3(*((a + b) / 2 for a, b in zip(low, high))), reach)
    return location, Styled(PLAIN, *SIZE, supersample=1)


def of_look(catalog: Any, entry: Any, registry: Registry) -> tuple[Location, Any]:
    from srlocations.stock.prefabs import Room, window
    location = Location("thumbnail", registry)
    location.add(Room(5, 4, north=[window(1.0, view="stock.view.day")]))
    location.add("stock.sofa", at=(-0.6, 0, 1.3), yaw=180)
    location.add("stock.table", at=(-0.6, 0, 0.1))
    location.rig("stock.interior")
    location.shot("thumbnail", (1.6, 1.4, -1.8), (-0.4, 0.9, 1.0), lens=22)
    return location, Styled(catalog.look(entry.name, entry.version, registry), *SIZE, supersample=1)


def of_location(catalog: Any, entry: Any, registry: Registry) -> tuple[Location, Any]:
    location = catalog.location(entry.name, entry.version, registry)
    if not location.shots:
        raise CatalogError(f"{entry.ref} has no shot")
    location.shots["thumbnail"] = next(iter(location.shots.values()))
    return location, Styled(PLAIN, *SIZE, supersample=1)


DRAWN = {"shader": of_shader, "prop": of_prop, "look": of_look, "location": of_location}


def thumbnail(catalog: Any, entry: Any, output: Path, renderer: Renderer) -> Optional[Path]:
    registry = Registry.default()
    catalog.install(registry)
    location, mode = DRAWN[entry.kind](catalog, entry, registry)
    return renderer.render(location, "thumbnail", output, mode)


def card(catalog: Any, entry: Any, picture: Optional[str]) -> str:
    """Everything here came from the catalog, so all of it is escaped."""
    words = {key: html.escape(value) for key, value in (("name", entry.name), ("version", entry.version),
                                                        ("description", entry.description), ("catalog", catalog.name))}
    tags = html.escape(", ".join(entry.tags))
    size = " x ".join(f"{value:g}" for value in entry.size) + " m" if entry.size else ""
    image = (f'<img loading="lazy" src="{html.escape(picture)}" alt="{words["name"]}">' if picture
             else '<div class="none" role="img" aria-label="No picture"></div>')
    lines = [f'<b>{words["name"]}</b><small>{words["version"]}{" · " + size if size else ""}</small>']
    lines += [f"<p>{words['description']}</p>"] if entry.description else []
    lines += [f"<p><small>{tags}</small></p>"] if tags else []
    lines += [f"<code>{words['catalog']}.{words['name']}@{words['version']}</code>"]
    return f'<article>{image}<div class="text">{"".join(lines)}</div></article>'


def page(catalog: Any, output: Union[str, Path, None] = None, thumbnails: bool = True,
         renderer: Optional[Renderer] = None) -> Path:
    """Writes index.html and its thumbnails. A thumbnail that cannot be drawn warns, and the page goes without it."""
    folder = Path(output) if output else catalog.root / FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    renderer = renderer or Renderer()
    sections = []
    entries = catalog.search()
    for kind, title in KIND_TITLES.items():
        cards = []
        for entry in (found for found in entries if found.kind == kind):
            picture = folder / f"{entry.digest}.png"
            if thumbnails and not picture.exists():
                try:
                    thumbnail(catalog, entry, picture, renderer)
                except (CatalogError, RuntimeError, OSError, ValueError, KeyError) as error:
                    warnings.warn(f"no thumbnail for {entry.ref}: {error}", stacklevel=2)
            cards.append(card(catalog, entry, picture.name if picture.exists() else None))
        if cards:
            sections.append(f'<section><h2>{title}</h2><div class="grid">{"".join(cards)}</div></section>')
    target = folder / "index.html"
    target.write_text(PAGE.format(title=html.escape(catalog.name), count=len(entries), sections="\n".join(sections)))
    return target
