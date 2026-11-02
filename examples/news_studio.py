"""The published news studio from every shot, then with two anchors behind the desk, then the floor camera's view path
traced. The portrait shots are 1080x1920, with the desk top just above where a banner goes. It needs only the catalog.
Run: .venv/bin/python examples/news_studio.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from srlocations import Registry, Renderer, Shaded, SharedCatalog, Traced

OUT = ROOT / "renders/news-studio"


def size(shot: str) -> Shaded:
    return Shaded(1080, 1920) if shot.startswith("portrait") else Shaded(1200, 675)


def main() -> None:
    renderer = Renderer()
    studio = SharedCatalog.open(ROOT / "catalog").location("news-studio", registry=Registry.default())
    print("issues:", studio.validate() or "none")
    for shot in studio.shots:
        print(renderer.render(studio, shot, OUT / f"{shot}.png", size(shot)).name)
    studio.stand("anchor-left", seed=2)
    studio.stand("anchor-right", kind="woman", seed=5)
    for shot in ("floor-camera", "two-shot", "portrait-two-shot", "portrait-push-in"):
        print(renderer.render(studio, shot, OUT / f"{shot}-anchors.png", size(shot)).name)
    print(renderer.render(studio, "floor-camera", OUT / "floor-camera-traced.png", Traced(1200, 675, samples=128)).name)


if __name__ == "__main__":
    main()
