"""The published starship bridge from every shot, then with a captain in the command chair and an officer at the holo
table, then the view from the pit traced. It needs only the catalog. Run: .venv/bin/python examples/starship_bridge.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from srlocations import Registry, Renderer, Shaded, SharedCatalog, Traced

OUT = ROOT / "renders/starship-bridge"


def main() -> None:
    renderer = Renderer()
    bridge = SharedCatalog.open(ROOT / "catalog").location("starship-bridge", registry=Registry.default())
    print("issues:", bridge.validate() or "none")
    for shot in bridge.shots:
        print(renderer.render(bridge, shot, OUT / f"{shot}.png", Shaded(1200, 990)).name)
    bridge.stand("captain", pose="sit")
    bridge.stand("officer", seed=3)
    print("with the crew:", bridge.validate() or "no issues")
    for shot in ("from-the-pit", "holo-table"):
        print(renderer.render(bridge, shot, OUT / f"{shot}-crew.png", Shaded(1200, 990)).name)
    print(renderer.render(bridge, "from-the-pit", OUT / "from-the-pit-traced.png", Traced(1200, 990, samples=128)).name)


if __name__ == "__main__":
    main()
