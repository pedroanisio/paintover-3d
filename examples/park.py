"""The published park from every shot, then with someone on the bench and someone on the path, then the first shot path
traced. It needs only the catalog. Run: .venv/bin/python examples/park.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from srlocations import Registry, Renderer, Shaded, SharedCatalog, Traced

OUT = ROOT / "renders/park"


def main() -> None:
    renderer = Renderer()
    park = SharedCatalog.open(ROOT / "catalog").location("park", registry=Registry.default())
    print("issues:", park.validate() or "none")
    for shot in park.shots:
        print(renderer.render(park, shot, OUT / f"{shot}.png", Shaded(1200, 990)).name)
    print(renderer.render(park, "by-the-bench", OUT / "by-the-bench-traced.png", Traced(1200, 990, samples=128)).name)
    park.stand("bench", pose="sit")  # takes the bench's middle seat, which the published prop kept
    park.stand("walker", seed=4)
    print(renderer.render(park, "by-the-bench", OUT / "people.png", Shaded(1200, 990)).name)


if __name__ == "__main__":
    main()
