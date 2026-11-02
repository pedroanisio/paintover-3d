# Mannequin and humanoid SDK: scorecard

First scored 2026-11-02 at commit 97c6566. Rescored the same day after the six improvements below, which are uncommitted
on `main`. The figures come from measurements on this machine and the test suite, not from memory.

## Bottom line

**7.5/10, up from 7.** It is a strong tool for blocking, previs and fit checks. Posing, reach, sitting, balance, walking
along a path and collision are accurate and well tested. It is still not a character animation rig. A skinned body now
exists for other packages, but renders of a location still draw rigid eggs.

## Scores

| Area | Before | Now | Evidence | What holds it back |
|---|---|---|---|---|
| Skeleton and controls | 9 | 9 | Unity Humanoid's 55 bones and 103 named controls. Mixamo names checked against three.js r160's `Xbot.glb`, eyes included. `JOINTS_VERSION` and a digest test guard the names srstudio reads | HumanIK, Unity and UE5 names not yet checked against real files |
| Body kinds | 8 | 8 | 11 kinds. Seven fitted to ANSUR II; teen, child and toddler stature and sitting height from NHANES | Children's heads, arms and widths are drawn, not measured |
| Joint ranges | 7 | 7 | Clinical ranges, cited; the rest marked as working ranges | No coupled limits |
| Poses | 7 | 8 | 17 poses. `hands-on-hips` fixed on wide bodies. Range, floor and tangle tests now run on all 11 kinds | Hand-tuned |
| Inverse kinematics | 6 | 7 | Exact limb solve with pole and orientation lock; fingers by geometry. `balanced=True` shifts the hips over the feet until the centre of mass is 2 cm inside the support. Works on all 11 kinds (from 1–7 cm outside to 2 cm inside) | No whole-body solve: the hips shift and lower but never turn. No two-handed grips, which wait on grip points |
| Walking and motion | 6 | 7 | `walk()` takes a list of points or marks, rounds each corner, faces along the curve and keeps planted feet within 5 mm | No stairs, slopes or running gait |
| Collision and placement | 7 | 7 | Convex hulls, seats, cushions, buried limbs, models by piece | Geometric and at placement only |
| Review tools | 8 | 8 | Point of view, framing, onion skins, `report()` (now with balance margin), `blocking()`, gaps, checks | No comfort verdicts (deliberate) |
| Interchange | 5 | 7 | BVH in and out, rigid and skinned GLB out, glTF in (`load_gltf`), all round-trip tested. A skinned GLB plays in the engine | No FBX. A `Mesh` of a skinned GLB is drawn and measured at the T-stance |
| Looks on screen | 4 | 4 | Clean jointed mannequin, reads well in every look | Location renders still draw rigid eggs with visible seams. The skinned GLB is for other tools; the SDK does not draw a posed one |
| Tests | 8 | 9 | 1508 passed, 2 skipped (they need srstudio). New tests for balance, walk paths, skinned GLB, glTF import, Mixamo names, joint-name digest and bit-exact geometry | — |
| Speed | 6 | 7 | Pose 6 ms, limb reach 18 ms (was 23), finger reach 56 ms (was 270), balanced pose 245 ms. Clash check of a walk with planted feet 8.5 s (was 18) | The target was 5x faster clash checks; it is 2.1x. Solving the figure at each instant is nearly all the time left |

## What changed

1. **`hands-on-hips` fixed, and every pose tested on all 11 kinds.**
2. **Balance.** `stand(..., balanced=True)` or `Mannequin(balanced=True)`. Segment masses come from Winter, Table 4.1
   (after Dempster). The support is the hull of the parts within 1 cm of the floor. A figure that is already steady keeps
   its frames unchanged. `centre_of_mass()`, `support()` and `balance()` are public.
3. **Skinned glTF** through `save_glb(skinned=True)`, and **glTF import** through `load_gltf()`.
4. **Faster checks.** `clashes()` reuses the frames `instants()` already solved and skips work with fewer than two
   bodies. Collision boxes are computed directly. Finger reach solves only the chain it moves. `geometry.py`'s
   products are unrolled and stay bit-identical, so published digests do not move.
5. **Walks along a path.** Corners are rounded by a parabola, the figure faces the curve's tangent, and a foot rising
   onto its toes pivots on its ball toward the hips. That last change stopped a planted foot from dragging on turns.
6. **Mixamo names checked** against `Xbot.glb`. The eye bones were wrong and are fixed.

## Open points

- **Centre of mass sits slightly high.** A standing man's centre of mass is at 0.584 of his height. Published values are
  0.55–0.57. The segment masses follow the published table, so the likely cause is where the eggs put each segment's
  centre. Height does not enter the support test, which works in the floor plane, so this matters mostly to a figure
  leaning far over.
- **Clash checks are 2.1x faster, not 5x.** Going further means caching solved figures between nearby instants, which
  is a larger change.
- **`save_bvh()` output changed** for walks (the new path and pivot move the feet), and with `names="mixamo"` the eye
  bones now carry Mixamo's names. The file layout is unchanged. srstudio reads these files.
- **HumanIK names stay unchecked** until a real HumanIK file is available.

## What would raise the score next

1. **Draw the skinned body in location renders**, posed, instead of rigid eggs. Raises Looks, the lowest score. This
   needs the SDK to set the engine's joint transforms per frame.
2. **Cache solved figures across instants** to reach the 5x clash-check target. Raises Speed.
3. **Two-handed grips and grip points on props**, once srstudio publishes socket names.
4. **Stairs and slopes in `walk()`.**
