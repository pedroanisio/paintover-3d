from pathlib import Path

from srlocations.materials import Material

VIEWS = Path(__file__).resolve().parent / "views"  # drawn by examples/views.py


def view(name: str) -> Material:
    """A picture behind a window, which the set's lights do not touch."""
    return Material("#ffffff", 1.0, extra={"unlit": True}, maps={"baseColorMap": str(VIEWS / f"{name}.png")})


PALETTE = {
    "default": Material("#8a8a8a"),
    "plaster.sage": Material("#7f8f7a", 0.9),
    "plaster.cream": Material("#d8cdb8", 0.9),
    "plaster.white": Material("#e6e3dc", 0.9),
    "wood.oak": Material("#8a5a33", 0.55),
    "wood.walnut": Material("#4e2f1c", 0.45),
    "fabric.teal": Material("#1f5c63", 0.95),
    "fabric.rust": Material("#9c4a2a", 0.95),
    "metal.brass": Material("#b08d43", 0.3, 1.0),
    "metal.steel": Material("#8d9299", 0.35, 1.0),
    "metal.black": Material("#17181a", 0.5, 0.8),
    "glass.window": Material("#a9c8d8", 0.08, opacity=0.25),
    "glow.warm": Material("#fff0d0", 0.5, glow="#ffcf8a", glow_strength=3.0),
    "glow.window": Material("#3a3226", 0.3, glow="#ffc873", glow_strength=1.6),
    "glass.dark": Material("#1d2a33", 0.12, 0.4),
    "leaf.green": Material("#3f7a3a", 0.85),
    "bark.brown": Material("#4a3424", 0.95),
    "soil": Material("#3b2a1e", 1.0),
    "concrete": Material("#8f8e8a", 0.9),
    "asphalt": Material("#2c2d30", 0.95),
    "brick.red": Material("#8c4433", 0.9),
    "brick.tan": Material("#b08e68", 0.9),
    "paint.blue": Material("#2a4a7a", 0.4),
    "paint.red": Material("#a32a2a", 0.35),
    "paint.yellow": Material("#d0a62c", 0.4),
    "rubber": Material("#111214", 0.9),
    "view.day": view("day"),
    "view.dusk": view("dusk"),
    "view.night": view("night"),
    "interior.lit": Material("#4a3d2e", 0.8, glow="#ffcf8a", glow_strength=1.0),
    "interior.lit.side": Material("#3a3026", 0.8, glow="#ffb870", glow_strength=0.55),
    "interior.dark": Material("#181b20", 0.9),
    "curtain": Material("#b8a88c", 0.9),
    "mannequin.body": Material("#c9c2b4", 0.7),
    "mannequin.joint": Material("#3a3d42", 0.5),
    "mannequin.left": Material("#2f6db5", 0.5),
    "mannequin.right": Material("#c23b32", 0.5),
}
