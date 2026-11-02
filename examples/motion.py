"""One set that moves: a figure walks across a room, the camera turns to keep it, and a table slides out of its way. Each
look makes the same film, and the frames written beside it are stills of the same moments.
Run: .venv/bin/python examples/motion.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from srlocations import Location, Renderer, Shaded, Styled, Wireframe
from srlocations.stock.looks import ink_toon, paper_cutout
from srlocations.stock.prefabs import Room, window

OUT = ROOT / "renders/motion"
LENGTH, FPS = 3.0, 24
STEPS = 6  # a pose every half a second: the figure swings between them, and its feet slide


def walk() -> Location:
    location = Location("walk")
    location.add(Room(8, 6, north=[window(-1.5), window(1.5)]))
    location.add("stock.sofa", at=(0, 0, 2.3), yaw=180)
    table = location.add("stock.table", at=(0.6, 0, -0.5), name="table")
    location.rig("stock.interior")
    location.mark("host", (-2.8, 0, -0.5), facing=90)
    figure = location.stand("host", pose="stand")[0]

    for step in range(1, STEPS + 1):
        location.move(figure, step * LENGTH / STEPS, ease="linear", pose="walk" if step % 2 else "stand")
    location.move("host", LENGTH, at=(2.8, 0, -0.5), ease="linear")
    location.move(table, 0.2)
    location.move(table, 1.2, at=(0.6, 0, 1.0), yaw=25)

    location.shot("follow", (0, 1.5, -2.8), (-2.8, 1.0, -0.5), lens=24)
    location.follow("follow", "host", (0, 1.0, 0))
    location.move("follow", LENGTH, eye=(0.8, 1.5, -2.8), lens=28)
    location.paint("path", depth=True).stroke([(-2.8, 0.02, -0.5), (2.8, 0.02, -0.5)], color="#d04030", width=0.04)
    return location


def main() -> None:
    location, renderer = walk(), Renderer()
    print(f"{location.duration('follow')} s, faults: {[issue.message for issue in location.validate()]}")
    for name, mode in (("shaded", Shaded(960, 540, 1, fps=FPS)), ("wireframe", Wireframe(960, 540, fps=FPS)),
                       ("toon", Styled(ink_toon(), 960, 540, 1, fps=FPS)), ("cutout", Styled(paper_cutout(), 960, 540, 1, fps=FPS))):
        print(renderer.clip(location, "follow", OUT / f"{name}.mp4", mode))
        for time in (0.0, 1.5, 3.0):
            renderer.frame(location, "follow", OUT / f"{name}-{time:g}.png", time, mode)


if __name__ == "__main__":
    main()
