"""The published airliner cabin, from every shot. It needs only the catalog. Run: .venv/bin/python examples/airliner.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from srlocations import Registry, Renderer, SharedCatalog, Traced

OUT = ROOT / "renders/airliner"


def main() -> None:
    cabin = SharedCatalog.open(ROOT / "catalog").location("airliner", registry=Registry.default())
    print("issues:", cabin.validate() or "none")
    renderer = Renderer()
    for shot in cabin.shots:
        print(renderer.render(cabin, shot, OUT / f"{shot}-shaded.png", "stock.shaded").name)
        print(renderer.render(cabin, shot, OUT / f"{shot}-traced.png", Traced(1422, 812, samples=128)).name)


if __name__ == "__main__":
    main()
