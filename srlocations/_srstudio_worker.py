"""Runs inside srstudio's interpreter, never in this SDK's: it imports srstudio and nothing of srlocations. It takes a job
as JSON on stdin and prints JSON. `cast` lists the characters. `draw` writes documents of one character alone, transparent
around it, at each of the given zooms: a document names what it draws, so the caller can tell when a drawing has changed.
"""
import json
import sys
from dataclasses import replace
from pathlib import Path

from sr_core.scene import Scene
from srstudio import cast_card, parts
from srstudio.canvas import Canvas, flat_counter
from srstudio.cast_card import CAST, FAMILIES, STYLES, HEIGHT, WIDTH, Pose

ROOM = 1.5  # a card's frame cuts a tall figure off at the waist, so the canvas runs on past it, below and to the sides


def cast() -> dict:
    return {card.slug: {"name": card.name, "drawing": card.drawing, "pose": vars_of(card.pose),
                        "style": parts.get(card.drawing).style, "words": words(card)} for card in CAST}


def words(card) -> dict:
    family = FAMILIES[parts.get(card.drawing).style]
    return {"eyes": list(family.eyes), "mouth": list(family.mouths), "arms": list(family.arms), "brows": list(family.brows)}


def vars_of(pose: Pose) -> dict:
    return {"eyes": pose.eyes, "mouth": pose.mouth, "arms": pose.arms, "brows": pose.brows}


def document(card, pose: Pose, zoom: float) -> Scene:
    part = parts.get(card.drawing)
    width, height = round(WIDTH * zoom * ROOM), round(HEIGHT * zoom * ROOM)
    scene = Scene(version="auto")
    scene.add_project(width=width, height=height, fps="24", duration=cast_card.SECONDS, background="#00000000")
    canvas = Canvas(scene, STYLES[part.style].palettes[0], font_asset=None, namer=flat_counter("n"), width=width, height=height)
    picture = canvas.group(canvas.comp, "picture", x=round(WIDTH * zoom * (ROOM - 1) / 2), y=0, scaleX=zoom, scaleY=zoom)
    FAMILIES[part.style].draw(canvas, picture, parts.drawing(card.drawing), pose)
    return scene


def draw(job: dict) -> dict:
    card = next((card for card in CAST if card.slug == job["character"]), None)
    if card is None:
        raise ValueError(f"no character {job['character']!r}; srstudio has {', '.join(c.slug for c in CAST)}")
    pose = replace(card.pose, **job["pose"])
    replace(card, pose=pose).validate()
    written = {}
    for name, zoom in job["zooms"].items():
        path = Path(job["folder"]) / f"{name}.scene.xml"
        path.write_bytes(document(card, pose, zoom).to_bytes(layout="pretty"))
        written[name] = str(path)
    return written


if __name__ == "__main__":
    request = json.load(sys.stdin)
    print(json.dumps({"cast": cast, "draw": draw}[request["do"]](*([request] if request["do"] == "draw" else []))))
