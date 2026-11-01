# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

`srlocations` is a Python SDK that builds 3D locations as objects and compiles them to `sr_core.scene` documents, which the scene-render engine (Rust, GPU) draws. There is no README; the [Location Book](https://claude.ai/artifact/UpPQTUcQih1vkCypRatjab) (private artifact) shows the use cases, renders and known limits. Keep its test count and limits true when they change: read it with the Artifact tool, then republish to that URL.

## Commands

```sh
./doctor.py                  # install or update sr-core and scene-render into .venv/ and .tools/
./doctor.py --check          # change nothing; exit 1 unless both are current and working
./doctor.py --no-build       # newest published binary only, never compile
.venv/bin/python -m pip install pytest      # doctor does not install it

.venv/bin/python -m pytest -q tests -p no:cacheprovider                 # all tests, about 40 s, needs the GPU
.venv/bin/python -m pytest -q tests/test_looks.py -k decal -p no:cacheprovider    # a single test

.venv/bin/python examples/use_cases.py        # the first examples; each writes into renders/
.venv/bin/python examples/paintover.py        # cartoon looks and paint
.venv/bin/python examples/texture_looks.py    # looks that differ by texture, material and paint
```

There is no linter or build step. This machine has engine 0.9.0 and no Rust toolchain; v0.9.0 has no published binary, so a new machine gets 0.8.0 with `--no-build` unless it can compile. The test suite passes on both.

## Architecture

The pipeline is `Location` -> `RenderMode` -> `Compiler` -> `sr_core` `Scene` -> package -> engine.

- **Graph** (`nodes.py`, `location.py`): a `Location` holds a tree of `Node`s, plus lights, marks, shots and `paintings`. `Node.walk()` flattens it into `Placed` leaves with world transforms. `location.solids()` and `location.lights()` are what compilers consume.
- **Registry** (`registry.py`): named catalogs of materials, prefabs, rigs, archetypes, modes and checks. `Registry.default()` installs `stock/`. Names are refused twice unless `override=True`. Plugins and libraries fill it; `location.add("stock.sofa", ...)` resolves through it.
- **Compilers** (`compiler.py`): `SceneCompiler` is the real render, `WireframeCompiler` projects edges to 2D. `SceneCompiler.draw()` is the one place a solid becomes an `object3D`, and passes call it too. Each compiler has a `mode` name that paint and decals are matched against.
- **Looks** (`looks.py`): the engine has no custom surface shaders, but a group's 2D effects and blend modes apply to the 3D inside it. So `StyledCompiler` draws the whole set several times in one document, one `Pass` per group (`Lit`, `Flat`, `Cel`, `Ink`). `Stage` is what passes share. A `Look` also carries `textures` and `materials`, which change surfaces without touching the location. Shaders are in `srlocations/shaders/*.fs`.
- **Paint** (`paint.py`): `paint_over()` adds 2D layers after everything else, positioned through `Projection`, so it ignores depth. `Decal` is the exception: a real solid, hidden correctly by what stands in front.
- **Catalog** (`catalog.py`, `templates.py`): a shared folder of frozen props, parametric `PropTemplate`s and shaders, versioned and digest-checked. `catalog/` in this repo is a published example, and published versions are not edited.
- **Portability** (`portable.py`): a compiled `Scene` names local absolute paths. `package()` copies each file a document reads into `assets/`, named by content, and rewrites a copy of the scene. `Renderer.still()` always goes through this, so every render tests it. `Renderer.package()` gives a folder and `Renderer.archive()` a `.vpkg.zip`.

Extension points are `Prefab`, `LightRig`, `Archetype`, `Check`, `Library`, `PropTemplate`, `Plugin`, `Compiler`, `RenderMode`, `Pass` and `PaintItem`. New behaviour should arrive through one of these rather than through a branch in a compiler.

## Coordinates

- SDK world: metres, x right, y up, z away.
- Engine: x right, y down, z away, 100 units to a metre. `engine_position` and `engine_angles` convert, and nothing else should.
- Yaw turns +z toward +x, pitch turns +z toward +y.

## Engine facts that shape the code

- A document's order is materials, composition, lights, effects, and sr-core sorts it. `<lights>`, `<materials>` and `<effects>` may not be empty, which is why they are created lazily.
- `object3D` takes no effects. Effects and blend go on the group around it.
- Lights are document-wide and one camera is shared, so a pass changes light through `Pass.relight`, for the whole document.
- Effect `<param>` values must be strings.
- Relative paths resolve against the document's folder.
- Every face of a primitive maps a picture 0 to 1, and a box runs its UVs a different way along each axis (`prim.rs`, `cuboid`). There is no UV rotation, offset or world-space mapping, and `uvScaleX`/`uvScaleY` are per material. So `Solid.spans()` gives a tiled texture one upright panel per face, each with its own material.
- `Solid.facets()` is for ink: thin surfaces in the solid's local frame. A facet that `is` the solid must not apply its transform again.
- The engine source is the scene-render repository, cloned here as `../scene-render`. Its `schema/scene-render-1.1.xsd` is the reference for attributes.

## Testing

Occlusion, registration and tiling only exist in the pixels, so those tests render small frames and sample them. `tests/test_looks.py` has the helpers (`stage`, `pixel`, `near`, `flat_set`). PIL is not installed; pixels come from ffmpeg as raw video. Reading `Scene` nodes: `deep()` for a recursive search, since `find_all` covers direct children only, and attributes are Python properties (`node.baseColor`), while `node.attributes()` is a method.

A render can pass every test and still look wrong. After changing a look, a pass or paint, run its example and view the PNGs.

## Scope

Motion is deliberately deferred: shots are stills, and the wireframe and paint are positioned once per shot. The agreed backlog after P0 is, in order: the srstudio cast on marks, mesh import, publishing looks to the catalog, JSON for looks and textures, then paint depth and role-based targeting.
