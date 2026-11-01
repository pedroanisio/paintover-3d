"""Windows with something behind them, lines that follow a form, a cut measured from the light, textures that carry on past
a window, and a catalog taken to another folder over HTTP with a seal on it.
Run: .venv/bin/python examples/polish.py"""
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from srlocations import Box, Cel, Cone, Cylinder, Flat, Ink, Lit, Location, Look, Registry, Renderer, SharedCatalog, Sphere, Styled
from srlocations.exchange import CatalogServer, Tokens
from srlocations.nodes import Ambient, Sun
from srlocations.stock.looks import ink_toon
from srlocations.stock.prefabs import Room, window

OUT = ROOT / "renders/polish"
PLAIN = Look([Lit()], name="example.plain")
ENGRAVED = Look([Flat(saturation=1.3), Cel(cut="auto"), Ink(width=2.2, rings=0.3)], sky="#dfe9ee", name="example.engraved")


def lounge(registry: Registry) -> Location:
    location = Location("lounge", registry)
    location.add(Room(6, 5, north=[window(-1.3, view="stock.view.day"), window(1.3, view="stock.view.day")],
                      east=[window(0, 1.8, view="stock.view.dusk")]))
    location.add("stock.sofa", at=(0, 0, 1.6), yaw=180)
    location.add("stock.table", at=(0, 0, 0.3))
    location.rig("stock.interior", fill=0.6)
    location.shot("wide", (-1.6, 1.5, -2.0), (0.8, 1.3, 2.5), lens=20)
    return location


def forms(registry: Registry) -> Location:
    location = Location("forms", registry)
    location.add(Box((12, 0.1, 8), at=(0, -0.05, 3), material="stock.concrete"))
    location.add(Box((12, 5, 0.2), at=(0, 2.5, 6), material="stock.plaster.cream"))
    location.add(Sphere(0.9, at=(-2.4, 0.9, 2), material="stock.paint.red"))
    location.add(Cylinder(0.7, 2, at=(-0.4, 1, 2), material="stock.paint.blue"))
    location.add(Cone(0.9, 2, at=(1.6, 1, 2), material="stock.paint.yellow"))
    location.add("stock.mannequin", at=(3.4, 0, 2), solid=False)
    location.add(Ambient(0.6))
    location.add(Sun(3, yaw=25, pitch=-35))
    location.shot("front", (0, 1.6, -4), (0, 1, 2), lens=26)
    return location


def street(registry: Registry) -> Location:
    location = registry.archetypes.get("stock.street")().build(registry, seed=4, length=30, night=True, interiors=True)
    location.shot("up", (0.5, 1.6, 3), (9, 5.5, 14), lens=30)
    return location


def carried(folder: Path) -> None:
    """The stored example goes from a server into another folder, and only a catalog its signer sealed gets through."""
    key = folder / "key"
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "publisher", "-f", str(key)], check=True)
    signers = folder / "signers"
    signers.write_text(f"publisher {(folder / 'key.pub').read_text()}")
    shelf = SharedCatalog.fetch(ROOT / "catalog", folder / "shelf")
    shelf.browse(thumbnails=False)
    shelf.seal(key)
    tokens = Tokens()
    token = tokens.issue("a colleague", [shelf.name])
    with CatalogServer([shelf.root], tokens) as server:
        copy = SharedCatalog.fetch(f"{server.url}/{shelf.name}", folder / "copy", token=token, signers=signers)
    print(f"{len(copy.search())} items fetched, sealed and checked:", copy.verify(signers=signers) == [])


def main() -> None:
    renderer, registry = Renderer(), Registry.default()
    room, shapes, town = lounge(registry), forms(registry), street(registry)
    jobs = [(room, "wide", "lounge-lit", Styled(PLAIN)), (room, "wide", "lounge-toon", Styled(ink_toon(cut="auto"))),
            (shapes, "front", "forms-engraved", Styled(ENGRAVED)), (town, "up", "street-interiors", Styled(PLAIN))]
    for location, shot, name, mode in jobs:
        print(renderer.render(location, shot, OUT / f"{name}.png", mode).name)
    with tempfile.TemporaryDirectory() as folder:
        carried(Path(folder))


if __name__ == "__main__":
    main()
