"""Project A: publishes to the shared catalog. Safe to rerun. Run: .venv/bin/python examples/publish_catalog.py"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import json

from srlocations import Group, Material, PropTemplate, Registry, SharedCatalog
from srlocations.stock.prefabs import Chair, FloorLamp, Table

TEXTURE = ROOT / "examples" / "textures" / "checker.png"


def main() -> None:
    TEXTURE.parent.mkdir(exist_ok=True)
    if not TEXTURE.exists():
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                        "color=c=white:s=256x256,geq=lum='if(eq(mod(floor(X/128)+floor(Y/128),2),0),205,60)':cb=128:cr=128",
                        "-frames:v", "1", str(TEXTURE)], check=True)
    catalog = SharedCatalog.create(ROOT / "catalog", "studio")
    catalog.publish_shader("car-paint.midnight", Material("#10234f", 0.35, 0.6, extra={"clearcoat": 1, "clearcoatRoughness": 0.05}),
                           tags=["paint", "glossy"], description="Deep blue paint under a hard clear coat")
    catalog.publish_shader("velvet.plum", Material("#4a1740", 0.8, extra={"sheenColor": "#e58fd0", "sheenRoughness": 0.3}),
                           tags=["fabric"], description="Soft fabric with a bright rim")
    catalog.publish_shader("copper.brushed", Material("#b5673a", 0.32, 1.0, extra={"anisotropy": 0.8}),
                           tags=["metal"], description="Brushed copper with stretched highlights")
    catalog.publish_shader("soap-film", Material("#d0d4dc", 0.2, 0.9, extra={"iridescence": 1, "iridescenceIor": 1.6}),
                           tags=["metal", "glossy"], description="Metal with thin-film colours")
    catalog.publish_shader("floor.checker", Material("#ffffff", 0.35, maps={"baseColorMap": str(TEXTURE)}, extra={"uvScaleX": 4, "uvScaleY": 4}),
                           tags=["floor", "textured"], description="Black and white tiles")

    registry = Registry.default()
    registry.use(catalog)
    registry.plugins.load_file(ROOT / "examples/plugins/scifi.py")
    catalog.publish_prop("dining-set", Group([
        Table(1.2, 0.8, top="studio.car-paint.midnight"),
        Chair(seat="studio.velvet.plum", at=(0, 0, 0.62)),
        Chair(seat="studio.velvet.plum", at=(0, 0, -0.62), yaw=180)]), registry, "1.0.1",
        tags=["furniture"], description="Table for two with velvet chairs")  # 1.0.0 was published before props kept their seats
    catalog.publish_prop("floor-lamp.warm", FloorLamp(), registry, tags=["lighting"], description="Brass lamp with its own light")
    catalog.publish_prop("bulkhead", registry.create("scifi.bulkhead"), registry, tags=["scifi", "structure"],
                         description="Corridor ring, made by the sci-fi plugin")
    # A new version: the same set, now with slots a project can reskin.
    catalog.publish_prop("dining-set", Group([
        Table(1.2, 0.8, top="studio.car-paint.midnight"),
        Chair(seat="studio.velvet.plum", at=(0, 0, 0.62)),
        Chair(seat="studio.velvet.plum", at=(0, 0, -0.62), yaw=180)]), registry, "1.1.1",
        tags=["furniture"], description="Table for two with velvet chairs",
        slots={"top": "studio.car-paint.midnight", "seat": "studio.velvet.plum"})
    for name in ("chair", "meeting-table", "bookcase"):  # in order: the table nests the chair
        catalog.publish_template(PropTemplate.from_file(ROOT / f"examples/props/{name}.prop.json"), registry)
    grand_tourer = registry.plugins.load_file(ROOT / "examples/plugins/grand_tourer.py")
    for name, (material, tags, description) in grand_tourer.shaders.items():
        catalog.publish_shader(name, material, tags=tags, description=description)
    catalog.publish_prop("gt-cabin", registry.create("gt.cabin"), registry, "1.5.0", tags=["vehicle", "interior"],
                         description="Grand tourer interior in cognac hide, its right door open", slots=grand_tourer.slots)
    catalog.publish_prop("mountain-overlook", registry.create("gt.overlook"), registry, "1.5.0", tags=["landscape", "backdrop"],
                         description="Pull-off on a mountain road above hazy ridges")
    catalog.publish_location("grand-tourer", json.loads((ROOT / "examples/grand-tourer.location.json").read_text()), "1.5.0",
                             tags=["vehicle", "interior", "landscape"],
                             description="Grand tourer parked at a mountain overlook, door open")
    airliner = registry.plugins.load_file(ROOT / "examples/plugins/airliner.py")
    for name, (material, tags, description) in airliner.shaders.items():
        catalog.publish_shader(name, material, tags=tags, description=description)
    catalog.publish_prop("airliner-cabin", registry.create("air.cabin"), registry, "1.0.1", tags=["vehicle", "interior"],
                         description="A narrow-body cabin, three seats either side of the aisle", slots=airliner.slots)
    catalog.publish_location("airliner", json.loads((ROOT / "examples/airliner.location.json").read_text()), "1.0.1",
                             tags=["vehicle", "interior"], description="An empty airliner cabin in warm evening light")
    flight_deck = registry.plugins.load_file(ROOT / "examples/plugins/flight_deck.py")
    for name, (material, tags, description) in flight_deck.shaders.items():
        catalog.publish_shader(name, material, tags=tags, description=description)
    catalog.publish_prop("flight-deck", registry.create("air.flight-deck"), registry, "1.0.0", tags=["vehicle", "interior", "aircraft"],
                         description="An airliner's flight deck with lit screens, overhead and a city at dusk outside", slots=flight_deck.slots)
    catalog.publish_location("flight-deck", json.loads((ROOT / "examples/flight-deck.location.json").read_text()), "1.0.0",
                             tags=["vehicle", "interior", "aircraft"], description="A flight deck at dusk over a lit city")
    park = registry.plugins.load_file(ROOT / "examples/plugins/park.py")
    for name, (material, tags, description) in park.shaders.items():
        catalog.publish_shader(name, material, tags=tags, description=description)
    catalog.publish_prop("park", registry.create("park.park"), registry, "1.0.0", tags=["exterior", "landscape", "city"],
                         description="A city park: a brick path, a bench before a hedge, broadleaf trees and towers beyond", slots=park.slots)
    catalog.publish_location("park", json.loads((ROOT / "examples/park.location.json").read_text()), "1.0.0",
                             tags=["exterior", "landscape", "city"], description="A city park on a summer afternoon")
    catalog.publish_prop("park-night", registry.create("park.park", night=True), registry, "1.0.0",
                         tags=["exterior", "landscape", "city", "night"],
                         description="The city park after rain at night: the path and kerbs wet, the leaves and lawn dark, no clouds",
                         slots={**park.slots, "paving": "studio.paving.wet", "lawn": "studio.grass.night"})
    for name, prefab, params, description in (
            ("park-lamp", "park.lamp", {}, "A generic post-top park lantern, lit, with its own light"),
            ("park-lamp.off", "park.lamp", {"lit": False}, "The park lantern switched off: the same lamp with no light"),
            ("park-bollard", "park.bollard", {}, "A low path light, lit, with its own light"),
            ("park-bollard.off", "park.bollard", {"lit": False}, "The low path light switched off"),
            ("park-mist", "park.mist", {}, "A bank of thin blue night mist: see-through cards with no body, facing back"),
            ("park-haze", "park.haze", {}, "A street lamp's warm light caught in the mist: see-through cards with no body")):
        catalog.publish_prop(name, registry.create(prefab, **params), registry, "1.0.0", tags=["exterior", "night"],
                             description=description)
    catalog.publish_location("park-night", json.loads((ROOT / "examples/park-night.location.json").read_text()), "1.0.0",
                             tags=["exterior", "landscape", "city", "night"],
                             description="The park at night after rain: one street lamp, low path lights in rows, a cool "
                                         "moon behind and mist, with a hip-height shot for a dancer on the path")
    newsroom = registry.plugins.load_file(ROOT / "examples/plugins/newsroom.py")
    for name, (material, tags, description) in newsroom.shaders.items():
        catalog.publish_shader(name, material, tags=tags, description=description)
    catalog.publish_prop("news-studio", registry.create("news.studio"), registry, "2.0.0", tags=["interior", "broadcast"],
                         description="A news studio in plum, tangerine and mint: a curved desk on a lit riser, a curved video wall "
                                     "with nothing written on it, a lighting grid and cameras", slots=newsroom.slots)
    catalog.publish_location("news-studio", json.loads((ROOT / "examples/news-studio.location.json").read_text()), "2.0.0",
                             tags=["interior", "broadcast"], description="A television news studio on air, with portrait shots for two anchors")
    bridge = registry.plugins.load_file(ROOT / "examples/plugins/bridge.py")
    for name, (material, tags, description) in bridge.shaders.items():
        catalog.publish_shader(name, material, tags=tags, description=description)
    catalog.publish_prop("starship-bridge", registry.create("ship.bridge"), registry, "2.1.0", tags=["interior", "scifi", "vehicle"],
                         description="A starship's bridge laid out as a control room: consoles under a band of windows, a mimic "
                                     "board and a chart table", slots=bridge.slots)
    catalog.publish_location("starship-bridge", json.loads((ROOT / "examples/starship-bridge.location.json").read_text()), "2.1.0",
                             tags=["interior", "scifi", "vehicle"], description="A starship's bridge with a capital ship off to port")
    for entry in catalog.entries():
        print(f"{entry.kind:<9}{entry.ref:<34}{entry.description}")
    print("verify:", catalog.verify() or "clean")


if __name__ == "__main__":
    main()
