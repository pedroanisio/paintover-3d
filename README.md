# srlocations

Build 3D locations in Python, as objects, and render them with the
[scene-render](https://github.com/pedroanisio/scene-render) engine. A location is a tree of rooms, props, lights, marks and
shots, measured in metres. The SDK compiles it to an `sr_core.scene` document and the engine draws it on the GPU.

The same location can be drawn as a low-resolution wireframe, a shaded review, a cartoon or a paper cut-out, without
changing the location. Plugins and shared catalogs add props, materials and looks.

## Install

You need Python 3.10 or later, and a Vulkan driver. Software Vulkan (Mesa's lavapipe) works but is slower.

```sh
./doctor.py                  # installs sr-core and scene-render into .venv/ and .tools/
./doctor.py --no-build       # the newest published engine binary, never compile
./doctor.py --check          # change nothing; exit 1 unless both are current and working
```

Nothing is installed outside this folder. The doctor does not install this package, so run scripts from here or add the
folder to your path. To install it into another project, use `pip install .`, and put a `scene-render` on `PATH`.

## A first location

```python
from srlocations import Location, Registry, Renderer, Styled
from srlocations.stock.looks import ink_toon
from srlocations.stock.prefabs import Room, window

location = Location("flat", Registry.default())
location.add(Room(6, 5, 2.8, walls="stock.plaster.cream", north=[window(1.2)]))
location.add("stock.sofa", at=(-0.8, 0, 1.8))
location.add("stock.table", at=(1.6, 0, 1.2))
location.rig("stock.interior")
location.mark("host", (1.6, 0, 2.0), facing=180)
location.shot("wide", (0.4, 1.5, -2.2), (0, 1, 2), lens=24)
print(location.validate() or "no issues")

renderer = Renderer()
renderer.render(location, "wide", "renders/flat-wireframe.png")  # wireframe is the default
renderer.render(location, "wide", "renders/flat-shaded.png", "stock.shaded")
renderer.render(location, "wide", "renders/flat-toon.png", Styled(ink_toon()))
```

The world is in metres, with x right, y up and z away from the camera's usual place. `location.add()` takes a node, or the
name of a registered prefab and its parameters. `Registry.default().prefabs.names()` lists the prefabs, and `materials`,
`rigs` and `modes` work the same way.

## Looks

A `Look` is a list of passes, drawn in one document: `Lit`, `Flat`, `Cel` and `Ink`. It can also change what surfaces are
made of, and the location stays as it was.

A key in `textures`, `materials` or a `Flat` palette picks surfaces one of three ways. A path beats a role, and a role beats
a material name.

| Key | Picks |
| --- | --- |
| `"stock.plaster"` | every material whose name starts with this, including a plant pot in plaster |
| `"role:wall"` | every solid with this role |
| `"path:room/north/*"` | every solid whose path matches, where `*` and `?` are wildcards |

`Room` and `Wall` tag their parts `wall`, `floor`, `ceiling` and `window`. Any node takes `role=`, and its parts inherit it.
A role or path key that finds nothing warns and carries on, because one look serves many locations.

```python
from srlocations import Lit, Look

loft = Look([Lit()], name="loft", materials={"role:wall": "stock.brick.red", "path:room/ceiling": "stock.concrete"})
renderer.render(location, "wide", "renders/flat-loft.png", Styled(loft))
```

A tiled `Texture` is measured in the world, so a pattern carries on past a window and around a room's corners.

`Cel(cut="auto")` measures where shade begins from each shot, so one look suits a dim room and a bright street, at the cost
of a small render while compiling. A number gives the same result on every machine. `Ink(rings=0.3)` draws lines 0.3 m
apart across curved solids, the way an engraving shows a form turning.

```python
from srlocations import Cel, Flat, Ink

engraved = Look([Flat(), Cel(cut="auto"), Ink(width=2, rings=0.3)], name="engraved")
renderer.render(location, "wide", "renders/flat-engraved.png", Styled(engraved))
```

`Look.save()` and `Look.load()` keep a look as a `.look.json`.

## Windows

A window is real glass, so anything built outside it shows through. For a room, a picture is enough:
`window(0, view="stock.view.day")`, or `stock.view.dusk` and `stock.view.night`. Any material with a picture works as a view.
A shot from outside the room can see the picture hanging there, so build the outside for a shot that needs both.

`Building(interiors=True)`, or `interiors=True` on the `stock.street` archetype, puts a shallow room behind each window, with
curtains and shapes against the light. It costs about seven solids a window, so it suits a close shot.

## Paint

`location.paint()` adds 2D layers over the render, and they are placed through the shot's camera. Paint ignores depth
unless a layer asks for it. With `depth=True`, what stands in front of a world position hides it.

```python
layer = location.paint("notes", depth=True)
layer.disc((1.6, 0.6, 2.0), 0.25, color="#e8432e")  # behind the table, so the table hides part of it
renderer.render(location, "wide", "renders/flat-notes.png", Styled(ink_toon()))
```

Frame-relative paint stays on top. A wireframe has nothing solid to hide paint, so paint stays on top there as well. Glass
hides nothing.

## Bodies on marks

`stock.mannequin` is a posable figure for reviewing a set with a body in it. `location.stand()` puts one on a mark and moves
it clear of the furniture, or raises `CollisionError` if there is no room. `location.pov()` records a shot from its eyes.

```python
location.stand("host", looks=("stock.wireframe", "stock.shaded"))
renderer.render(location, "wide", "renders/flat-blocking.png", "stock.shaded")
```

A figure comes as a `kind` (`man`, `woman`, `teen`, `child` or `toddler`) and a `pose` (`t`, `a`, `stand`, `sit`, `walk`,
`point` or `drive`). `adjust` turns single controls on top of the pose, in degrees, and `height` overrides the kind. A figure
in the `sit` pose takes the nearest free seat within 0.8 m of its mark.

```python
location.mark("guest", (-0.4, 0, 1.2), facing=180)
location.stand("guest", pose="sit", kind="woman", adjust={"head.turn_left_right": 30})
print(location.clashes(bodies_only=True) or "nobody passes through anything")
```

`location.clashes()` lists what passes through what, and a render refuses a figure that still does. `solid=False` on a
figure lets it through on purpose. These checks find overlap only, so a figure floating 15 cm off a seat back reports nothing.
`examples/fit_check.py` goes further for the car: each limb against hard parts and cushions separately, how far the back,
hips and thighs are from the seat, wrist to steering wheel, and joint angles.

`location.cast()` puts a 2D character on a mark, and furniture hides it by default. Characters come from a `Performer`. The
optional `SrstudioCast` plugin gets them from srstudio, through that project's interpreter in `SRSTUDIO_PYTHON`.
`examples/casting.py` holds a mannequin and a character on each mark, and picks by look.

## Curved solids

A `Surface` draws any shape you can write as `x(u, v)`, `y(u, v)` and `z(u, v)`. The expressions are in metres, and angles
are in degrees. The grand tourer's seats and dashboard are built this way.

```python
from srlocations import Surface

location.add(Surface("0.12 * cos(u) * cos(v)", "0.12 * sin(v)", "0.12 * sin(u) * cos(v)", u=(0, 360), v=(-90, 90),
                     closed=(True, False), at=(1.6, 0.9, 1.2), material="stock.plaster.cream"))
```

## Models

`Mesh` places a glTF, GLB or OBJ file as a solid, and keeps the file's materials unless `material` or `materials` replaces
them. The engine's other formats need a `size`.

## Sharing work

A `SharedCatalog` is a folder of versioned, digest-checked props, parametric templates, shaders, locations and looks. A
frozen prop needs no code to use, so it works without the plugin that made it.

```python
from srlocations import SharedCatalog

studio = SharedCatalog.create("shared", "studio")
studio.publish_prop("sofa", location.registry.create("stock.sofa"), location.registry)

other = Location("set", Registry.default().use(SharedCatalog.open("shared")))
other.add("studio.sofa")
```

Published versions never change, so a fix is a new version, and old ones stay readable. `catalog/` in this repository is a
published example: `SharedCatalog.open("catalog").location("grand-tourer")` opens the newest version of a car at a mountain
overlook.

`SRLOCATIONS_CATALOGS` lists catalogs that `Registry.default()` opens by itself. `studio.browse()` writes a page of what is
in a catalog, with a thumbnail of each item, into its `browse/` folder.

To share a catalog past one folder, seal it, serve it, and fetch it. A seal is a signature over every file in it, made with an
SSH key by `ssh-keygen`. The reader lists who they trust in an allowed-signers file, one `name key` line, kept outside the
catalog:

```sh
.venv/bin/python -m srlocations.exchange seal shared ~/.ssh/catalog_key
.venv/bin/python -m srlocations.exchange token tokens.json alex studio        # prints a token, once
.venv/bin/python -m srlocations.exchange serve shared --tokens tokens.json    # on this machine, read-only

SRLOCATIONS_TOKEN=... .venv/bin/python -m srlocations.exchange fetch http://127.0.0.1:8740/studio vendor/studio --signers trusted
```

`SharedCatalog.open(path, signers=...)` then refuses the catalog if anything in it changed. A sealed catalog can also be
fetched from any plain web server, or a folder. The server speaks plain HTTP, so anything past this machine belongs behind a
TLS proxy.

To send a render to another machine, `renderer.package()` writes a folder and `renderer.archive()` writes a `.vpkg.zip`.
Both copy every file the document reads.

## Extending it

A plugin is a class with a `register()` method. New behaviour arrives through `Prefab`, `LightRig`, `Archetype`, `Check`,
`Library`, `PropTemplate`, `Compiler`, `RenderMode`, `Pass`, `PaintItem` and `Performer`.

```python
from dataclasses import dataclass

from srlocations import Box, Material, Plugin, Prefab


@dataclass
class Crate(Prefab):
    width: float = 0.6

    def build(self):
        return [Box((self.width,) * 3, at=(0, self.width / 2, 0), material="acme.pine")]


class Acme(Plugin):
    name = "acme"
    version = "1.0.0"

    def register(self, registry):
        registry.materials.add("acme.pine", Material("#c8a165"))
        registry.prefabs.add("acme.crate", Crate)


registry = Registry.default()
registry.plugins.load(Acme())
```

There are three other ways to load one: `registry.plugins.load_module("acme.plugin")`, `registry.plugins.load_file(path)`,
and an entry point, which `Registry.default()` finds by itself. A plugin that names others in `requires` loads after them.

```toml
[project.entry-points."srlocations.plugins"]
acme = "acme.plugin:Acme"
```

## Tests and examples

```sh
.venv/bin/python -m pip install pytest
.venv/bin/python -m pytest -q tests -p no:cacheprovider
```

The tests need ffmpeg, because many render small frames and read their pixels, and ssh-keygen for seals. Two tests need
srstudio and skip without it.
GitHub Actions runs the suite on every push and pull request, on Mesa's software Vulkan and the newest published engine.

`examples/` holds runnable scripts, and each writes into `renders/`. A good order is `use_cases.py`, `paintover.py`,
`texture_looks.py`, `mannequin.py`, `casting.py` and `polish.py`. `publish_catalog.py` and `use_catalog.py` publish and read
the catalog, `grand_tourer_paper.py` renders the car as a paper paint-over, and `fit_check.py` puts mannequins in every set.

## Limits

- Shots are stills. Motion is not implemented.
- A mannequin is forward kinematics with rigid segments, and a settled figure does not change its pose to fit.
- `location.clashes()` reports the deepest overlap for each pair of nodes, so a smaller one can hide behind it, and it cannot
  see a limb wholly inside a `Surface`. Contact is measured only by `examples/fit_check.py`, and only for the car.
- The comfort ranges in `examples/fit_check.py` are working values, not taken from a published standard.
- Depth for paint treats a mark as one distance, to within 15 cm, and paint casts no shadow onto the set.
- A tiled texture runs backwards on two of a room's four walls, which only lettering would show, and still restarts on each
  round solid. Only walls along x and z meet exactly at a corner. An imported model keeps its own UVs.
- A window's view is a flat picture. It shifts a little as the camera moves, and a shot from outside can see it.
- `Building` puts windows and interiors on its front only, and those rooms are shallow.
- `Ink(rings=...)` draws across cylinders, cones, spheres and `Surface`s. An imported model keeps its outline.
- Ink can leave a few tiny specks on a wall built in sections around windows. The cause has not been found.
- `Cel(cut="auto")` needs an engine while compiling, and falls back to 0.5 with a warning without one.
- A token reads whole catalogs, so keep what one audience may not see in a catalog of its own. Publishing stays with whoever
  holds the folder.
- A seal stops a mirror winding back a reader who has fetched before. It cannot show a first-time reader that a seal is old,
  or show anyone that a mirror stopped updating.
- A character's picture stands on its mark, while a seated mannequin settles onto the seat, so the two can differ.
