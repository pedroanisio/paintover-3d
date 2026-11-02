# SDK review, November 2026

A read of every module on `main` after the motion and fix-all work landed, looking for defects, dead code and API
inconsistencies. What was changed is listed first, then what was found and left, with the reason.

## Changed

| Where | What | Why |
|---|---|---|
| `cast.py` | The PNG reader's cache is keyed by path and modification time. `alpha_box()` is one function. | `_png` was cached by path alone, so a cut-out repainted at the same path kept its old pixels and outline for the rest of the process; the mtime that `alpha_box` passed went to an uncached function and did nothing. `tests/test_cast.py::test_a_picture_redrawn_at_the_same_path_is_read_again` fails without this. |
| `catalog.py` | `SharedCatalog.create(root, name)` refuses a root that already holds a catalog of another name. | It opened and returned the other catalog, so a typo in the name went unnoticed. `tests/test_srlocations.py::test_creating_a_catalog_where_another_is_refuses_to_rename_it`. |
| `motion.py` | Removed the unreachable lines after `return curve[""]` in `through()`. | An older `tangents()` and a second `curve` were left behind when the monotone cubic replaced them. |
| `catalog.py`, `motion.py`, `registry.py`, `sheets.py`, `surfaces.py` | Unused imports removed. | Found by a scan of names that appear once in a module. |

## Found and left

- **Styled compile time.** Compiling the street archetype with interiors (2,927 solids) through `ink_toon` takes 7.3 s. Half
  of it is sr_core validating attributes in `add_object3D`, which is not ours. Of the rest, `Ink.surfaces()` takes 1.6 s
  and `Node.transform` is recomputed 23,000 times (0.8 s, a `rotation()` each). Caching a node's transform would need the
  node to be immutable, and `settle()` moves nodes, so it was not done.
- **Figure contract.** `review._within_reach()` and `framing.blocking()` read `frames()`, `height` and `yaw`, which only
  `Mannequin` has, so a `Figure` with another rig would break the report and the blocking data. Nothing else needs them;
  the fix is to add what they need to `Figure` when a second rig arrives.
- **`Location.mark()`** checks `framing not in self.registry.framings` and then calls `framings.get()` only to raise. A
  plain `get()` does the same. Left for the session editing `location.py`.
- **`Backdrop` and `Decal`** set `casts_shadow=False` in `__post_init__`, so `casts_shadow=True` on either is silently
  ignored. Both are meant never to cast, so this is documented here rather than changed.
- **Catalog reads.** `get()` without a version and `_adopt()` read and digest every entry file. Installing the repository's
  catalog (97 entries) reads 176 files in 0.1 s, so a cache is not worth its complexity yet. Published versions never
  change, so one keyed by path and mtime would be safe if a catalog grows large.
- **Tests on engine 0.8.0.** The lavapipe environment used for the earlier 0.8.0 runs is gone, so this review's suite ran on
  0.9.0 only. CI (`.github/workflows/tests.yml`) covers 0.8.0 once the GitHub account is unlocked.
