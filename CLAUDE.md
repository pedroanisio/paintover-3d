# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

`srlocations` is a Python SDK that builds 3D locations as objects and compiles them to `sr_core.scene` documents, which the scene-render engine (Rust, GPU) draws. `README.md` is for people using the SDK, and every Python block in it runs as a test. The [Location Book](https://claude.ai/artifact/UpPQTUcQih1vkCypRatjab) (private artifact) shows the use cases, renders and known limits. Keep its test count and limits true when they change: read it with the Artifact tool, then republish to that URL.

## Commands

```sh
./doctor.py                  # install or update sr-core and scene-render into .venv/ and .tools/
./doctor.py --check          # change nothing; exit 1 unless both are current and working
./doctor.py --no-build       # newest published binary only, never compile
.venv/bin/python -m pip install pytest      # doctor does not install it

.venv/bin/python -m pytest -q tests -p no:cacheprovider                 # all tests, about 4 minutes, needs the GPU
.venv/bin/python -m pytest -q tests/test_looks.py -k decal -p no:cacheprovider    # a single test
SRSTUDIO_PYTHON=<srstudio's venv>/bin/python .venv/bin/python -m pytest -q tests/test_cast.py -p no:cacheprovider    # the two tests that need srstudio; they skip without it

.venv/bin/python examples/use_cases.py        # the first examples; each writes into renders/
.venv/bin/python examples/paintover.py        # cartoon looks and paint
.venv/bin/python examples/texture_looks.py    # looks that differ by texture, material and paint
.venv/bin/python examples/casting.py          # a model, a cast and a published look; mannequins alone without SRSTUDIO_PYTHON
.venv/bin/python examples/mannequin.py        # every pose, and figures in the office and the car
.venv/bin/python examples/polish.py           # window views, interiors, ink rings, and a catalog sealed, served and fetched
.venv/bin/python examples/motion.py           # one film in four looks, with stills of the same moments
.venv/bin/python examples/views.py            # redraws the pictures in srlocations/stock/views, which are checked in
.venv/bin/python -m srlocations.exchange --help    # seal, browse, serve, token, revoke, fetch
```

There is no linter or build step. This machine has engine 0.9.0; v0.9.0 has no published binary, so a new machine gets 0.8.0 with `--no-build` unless it can compile. The test suite passes on both.

CI is `.github/workflows/tests.yml`: Ubuntu, Mesa's software Vulkan, `./doctor.py --no-build`, then the tests. The remote is `origin` on GitHub. Its one run so far never started, because the account was locked over billing, so the suite has not yet passed there; check `gh run list` before saying otherwise.

## Architecture

The pipeline is `Location` -> `RenderMode` -> `Compiler` -> `sr_core` `Scene` -> package -> engine.

- **Graph** (`nodes.py`, `location.py`): a `Location` holds a tree of `Node`s, plus lights, marks, shots and `paintings`. `Node.walk()` flattens it into `Placed` leaves with world transforms. `location.solids()` and `location.lights()` are what compilers consume. A node's `role` says what it is in the set, and a leaf's `Placed.roles` holds its own and those above it.
- **Registry** (`registry.py`): named catalogs of materials, prefabs, rigs, archetypes, modes and checks. `Registry.default()` installs `stock/`. Names are refused twice unless `override=True`. Plugins and libraries fill it; `location.add("stock.sofa", ...)` resolves through it. Entry points load in the order their `requires` needs.
- **Compilers** (`compiler.py`): `SceneCompiler` is the real render, `WireframeCompiler` projects edges to 2D. `SceneCompiler.draw()` is the one place a solid becomes an `object3D`, and passes call it too. Each compiler has a `mode` name that paint and decals are matched against.
- **Looks** (`looks.py`): the engine has no custom surface shaders, but a group's 2D effects and blend modes apply to the 3D inside it. So `StyledCompiler` draws the whole set several times in one document, one `Pass` per group (`Lit`, `Flat`, `Cel`, `Ink`). `Stage` is what passes share. A `Look` also carries `textures` and `materials`, which change surfaces without touching the location. Those tables and a `Flat` palette take material names or their beginnings, `"role:wall"` or `"path:room/north/*"`, and a path beats a role beats a material (`lookup`). A key aimed at solids changes the material's id through `Stage.aimed`, or two solids of one material would share the first one's result. `Look.spec`, `from_spec`, `load` and `save` are its JSON form, and a blueprint can hold them under `"looks"`. `Cel(cut="auto")` renders a small probe of the shot while compiling (`measured_cut`), so a compile with it needs an engine. `Ink(rings=)` splits a curved solid through `Solid.bands()`, one key per band, and the ink shader does the rest. Shaders are in `srlocations/shaders/*.fs`.
- **Motion** (`motion.py`): the rule is that a frame of a moving shot is byte-identical to a still of `location.at(t)`, and `tests/test_motion.py` compares them. Keys live in `location.motion`, not on `Shot`, so published digests cannot shift. `Clip` turns a shot into one key per frame, linear, at exactly `frame / fps`: rounding those times to 6 places moved about 1,300 ink pixels. Solids, lights and the camera carry keys, so every pass follows without knowing. `Placed.track` holds a moving leaf's world per frame and `Placed.within()` derives its parts'. Paint and the wireframe are 2D, so each frame's marks are drawn by the still's own code in a group or shape that lives for that frame, and a plugin's `PaintItem` needs no change; `Frames` then lets a frame's leading nodes that repeat the frame before live on instead, and only leading ones, so later nodes stay on top. `Node.posed()` makes a node at a moment and `Node.keyed()` normalises key values; the mannequin overrides both, blending joint by joint. A node whose parts change (`motion.shape()`) is drawn as runs, one set of objects per shape, each living for its frames through `Placed.span`, and a node's lights may not change in number. An actor's keys are applied in `Location._item_at()`. A moment keeps its source as `origin`, and its `placed()` gives each moved leaf the world it began at as `Placed.start`, or marks it `reshaped` when its node's parts changed, as `Clip` does; `Ink.surfaces` keys by those, because paths are not unique and a key must not change as a solid moves. `smooth` is monotone cubic Hermite per number, per axis and per pose control. `instants()` bisects between keys until nothing moving goes `STRIDE` (3 cm), and after the first instant `clashes()` tests only pairs with something moving in them. A `Check` with `over_time` is run once on the moving location and looks between keys itself; the others run at each key. Motion blur is the project's shutter, and ink and paint groups set `motionBlur="off"`, because blurred ink stripes.
- **Sheets** (`sheets.py`): a tiled texture on a box goes to the engine as a small OBJ with world-space UVs, written by content to the cache (`portable.cache_folder("sheets")`), because the engine has no UV offset. `Solid.faces()` gives the corners, and `Stage.lay` takes this route when there are any. Round solids still use `spans()`. A model is turned on import, so writing z negated reverses winding, and the engine culls back faces: a wrong winding shows the far side of a wall.
- **Paint** (`paint.py`): `paint_over()` adds 2D layers after everything else, positioned through `Projection`, so it ignores depth unless its layer has `depth=True`, which `location.cast()` sets by default. Then `Holdout` gives each mark a track matte: the solids in the way in black over a white `Card` at the mark's distance. `PaintItem.cards()` says where those stand, so `frame` paint and `Picture`s have none and stay on top. A wireframe gets no `Holdout`, and glass holds nothing out. `Decal` is a real solid, hidden by the depth buffer.
- **Models** (`mesh.py`): `Mesh` is a `Solid` over a model file. glTF, GLB and OBJ are read here for bounds, material names and wireframe lines; the engine's other formats need a `size`. A solid reports its materials as `skins()`, one per slot, and a mesh keeps the file's materials unless `material` or `materials` replaces them. A file's `doubleSided` arrives in the skin's `own.extra`, and every material a pass or `Holdout` draws in a solid's place must keep it (`Stage.sided`, `Solid.two_sided`), or that face goes from that pass only. `Solid.declare()` adds its asset, and `portable.bundle()` follows the files a model reads.
- **Cast** (`cast.py`, `srstudio.py`, `_srstudio_worker.py`): `location.cast()` puts a `Performer` on a mark as paint, so a character stands the picture's lowest opaque edge on the mark, and furniture hides it through `Holdout`. `SrstudioCast` is a plugin that reaches srstudio through a subprocess in that project's interpreter (`SRSTUDIO_PYTHON`, Python 3.11 or later) because the two pin different sr-core versions. It never imports srstudio and writes nothing into that repository. Pictures are cached under `SRLOCATIONS_CACHE`. The worker runs with `-P` so `srlocations/srstudio.py` cannot shadow the real package. A mark can hold both a mannequin and a character: `looks=` on each gives solid blocking in the reviews and the paint in the finished looks, as `examples/casting.py` does.
- **Catalog** (`catalog.py`, `templates.py`): a shared folder of frozen props, parametric `PropTemplate`s, shaders, locations and looks, versioned and digest-checked. A frozen mesh copies its files into `models/<digest>/`. A published look may only use `stock.` passes, because a catalog holds data and not code. `catalog/` in this repo is a published example, and published versions are not edited. A digest covers an entry's payload and not its tags or description, which is one reason seals exist.
- **Exchange** (`exchange.py`, `browse.py`): `seal()` signs a manifest of every file with `ssh-keygen -Y`, and there is no cryptography here to maintain. `fetch()` stages, checks and swaps, and `allowed()` is the one list of paths a catalog can hold, used by inventory, fetch and server alike, so a new folder in a catalog must be added there. `CatalogServer` is read-only and binds to loopback, and tokens grant whole catalogs because a seal covers a whole catalog. Every defence has a test in `tests/test_exchange.py` that fails without it. `browse.py` writes a static page, escaping everything from the catalog.
- **Windows** (`stock/prefabs.py`): `Opening.view` hangs a `Backdrop` outside a `Wall`, one card to a picture. `Wall.outside` says which side of local z that is, since a `Room`'s south and west walls have it on -z. `Building(interiors=True)` replaces its block with a front cut around the windows, a body behind and a shallow `room()` per window.
- **Mannequin** (`stock/mannequin.py`): `stock.mannequin` is a `Prefab` for reviewing a set with a body in it, and `location.stand()` puts one on each mark. `kind` picks a body from `KINDS`, as multiples of the man in `JOINTS`, and `seed` varies it, or picks a kind too. `location.pov()` records a shot from a figure's eyes. It has Unity Humanoid's 55 bones and 95 muscles plus six root channels, 101 parameters written `"joint.control"`, with zero at the T-stance. Its ranges are this SDK's own, because Unity publishes none. Limbs are `Surface`s so a frozen figure keeps its shape, and they are `hollow`, so `MarksClear` and `ShotsClear` see through them. A figure faces +z at yaw 0 and a stock chair faces -z, so sit it at the chair's yaw plus 180.
- **Collision** (`collision.py`): `Solid.hulls()` gives each solid's body as convex shapes, and the rules for when an overlap is a fault are all in that module's docstring: one object's parts never clash, a node with `moves` may touch but not enter anything, set pieces may share `DRESSED`, and a node with `yields` gives way to set pieces. `location.settle()` moves a body clear or refuses it, onto a `Seat` if it sits, and `Renderer.compile()` refuses a body still inside something. `solid=False` on a mannequin opts out.
- **Portability** (`portable.py`): a compiled `Scene` names local absolute paths. `package()` copies each file a document reads into `assets/`, named by content, and rewrites a copy of the scene. `Renderer.still()` always goes through this, so every render tests it. `Renderer.package()` gives a folder and `Renderer.archive()` a `.vpkg.zip`.

Extension points are `Prefab`, `LightRig`, `Archetype`, `Check`, `Library`, `PropTemplate`, `Plugin`, `Compiler`, `RenderMode`, `Pass`, `PaintItem` and `Performer`. New behaviour should arrive through one of these rather than through a branch in a compiler.

## Coordinates

- SDK world: metres, x right, y up, z away.
- Engine: x right, y down, z away, 100 units to a metre. `engine_position` and `engine_angles` convert, and nothing else should.
- Yaw turns +z toward +x, pitch turns +z toward +y.
- A model is turned 180° about x on import (`Y_UP_METRES` in the engine), so model (x, y, z) lands at SDK (x, y, -z). It is a turn, not a mirror.

## Engine facts that shape the code

- A document's order is materials, composition, lights, effects, and sr-core sorts it. `<lights>`, `<materials>` and `<effects>` may not be empty, which is why they are created lazily.
- `object3D` takes no effects. Effects and blend go on the group around it.
- Lights are document-wide and one camera is shared, so a pass changes light through `Pass.relight`, for the whole document.
- Effect `<param>` values must be strings.
- Relative paths resolve against the document's folder.
- A layer's `scaleX`/`scaleY` are ratios with a default of 1, not percentages. `object3D` honours `scaleX/Y/Z`.
- `materialOverride` is `slot:name` pairs, split on whitespace and `:`, so a slot with either in its name cannot be addressed, and a pair naming no material only warns. `node=` draws the first node of that name and drops its own transform.
- Every face of a primitive maps a picture 0 to 1, and a box runs its UVs a different way along each axis (`prim.rs`, `cuboid`). There is no UV rotation, offset or world-space mapping on a primitive, and `uvScaleX`/`uvScaleY` are per material. A model's own UVs are honoured past 0 to 1, which is what `sheets.py` relies on. A round solid still gets `Solid.spans()`, one upright panel per face, each with its own material.
- Any node takes `matte` and `matteMode`, and the matte node is not drawn itself. A group of `object3D` works as a matte, with the shared camera and its own depth, which is what `Holdout` uses on both engines.
- A shader that fails to compile is passed through, with a note and exit 0. `Renderer.draw` therefore passes `--strict`. `encode --strict` also fails on warnings such as a solid off camera for a whole film, so `Renderer.clip` looks for "not rendered yet" in the output instead.
- `Solid.facets()` is for ink: thin surfaces in the solid's local frame. A facet that `is` the solid must not apply its transform again. A box's slabs stop `SEAM` short of the planes beside them: sharing a plane with a neighbour's face, they fought it for pixels and ink drew specks.
- The engine source is the scene-render repository, cloned here as `../scene-render`. Its `schema/scene-render-1.1.xsd` is the reference for attributes.

## Testing

Occlusion, registration and tiling only exist in the pixels, so those tests render small frames and sample them. `tests/test_looks.py` has the helpers (`stage`, `pixel`, `near`, `flat_set`). PIL is not installed; pixels come from ffmpeg as raw video. Reading `Scene` nodes: `deep()` for a recursive search, since `find_all` covers direct children only, and attributes are Python properties (`node.baseColor`), while `node.attributes()` is a method.

A render can pass every test and still look wrong. After changing a look, a pass or paint, run its example and view the PNGs.

## Scope

The mannequin is forward kinematics only, with rigid segments and no skinning. Collision is geometric and happens at placement: the engine's `rigidBody` and `physics` are unused, and a settled figure does not change its pose to fit. P0 to P3 and motion are done, so the backlog is empty.
