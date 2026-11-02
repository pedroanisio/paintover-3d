# StykAnimate-App: what the mannequin SDK can take

Reviewed 2026-11-01 from a read-only shallow clone of https://github.com/filippocalippo/StykAnimate-App (HEAD def9721,
19 Oct 2026). Nothing in it was built or run.

## Summary

StykAnimate is a 2D stick-figure animator in the style of Pivot and Stick Nodes, written in JavaScript with WebGPU and Electron.
Most of its roughly 2,100 files are interface, codecs and export. The rig and motion logic is about 1,500 lines. It has no
humanoid skeleton, no joint limits and no body proportions, and it reads and writes no 3D pose formats. What is worth taking
is a handful of textbook techniques. None of them is new, and each can be written from public sources.

**Licence: GPL-3.0-or-later** (`LICENSE`, `package.json`). Copying or translating its code would make srlocations a
derivative work, and distributing it would put the whole SDK under the GPL. srlocations has no licence yet, so taking their
code would decide ours. Take ideas only, written fresh. Their docs are in the same repository, so paraphrase them and do not
copy. One of their research notes (`docs/research/STICK-NODES-RIGGING-RESEARCH.md`) describes decompiling a commercial app with
JADX, which is one more reason to work from first principles.

## Worth taking

Ranked by value for this SDK. File references point at their repository, to say where the idea is, not what to copy.

| # | Technique | Lifts which limit of ours | Effort | Where theirs is |
|---|---|---|---|---|
| 1 | Analytic two-bone IK with a pole vector and swivel angle | `reach_to()` is coordinate descent: slow, and with no say over which way an elbow or knee points | about 1 day | `src/ik-spatial.mjs` 17-63 |
| 2 | Monotone cubic Hermite for the `smooth` ease | our `smooth` overshoots (see below) and does nothing for poses | small | `src/keyframe-easing.mjs` 85-105 |
| 3 | Keep a hand or foot's orientation through an IK solve, and plant both feet while the hips move | feet slide in a walk, and a foot turns with the shin after `reach_to()` | half a day after #1 | `src/ik.mjs` 97-110 |
| 4 | Of two equivalent angle triples, keep the one nearer the last pose | needed by #1, and keeps keyed poses continuous | small | `src/rig-spatial.mjs` 171-184 |
| 5 | Cubic-bezier eases, `ease=(x1, y1, x2, y2)` | our ease-in and ease-out are quadratics, not the CSS curves | small | `src/keyframe-easing.mjs` 57-69 |
| 6 | Follow with lag, dead zone and look-ahead | `location.follow()` pins `look_at` exactly to its target | medium | `src/camera-follow.mjs` 175-240 |
| 7 | Stateless camera shake, handheld, impact and zoom pulse | we have nothing like it | small to medium | `src/camera-motion.mjs` 48-69 |
| 8 | Onion skin and motion trails, as a review pass | no way to see a move in one still | medium | `src/onion-skin.mjs`, `src/motion-path.mjs` |
| 9 | Relax and push in-betweens | `Pose.blend` only interpolates | small | `src/editor-tweener.mjs` 95-135 |

Notes on fit:

- **#1** solves joint positions by the law of cosines. For us they must then be turned back into `upper_arm.front_back`,
  `down_up`, `twist_in_out` and `lower_arm.stretch` by inverting `_local`, and checked against the ranges, falling back to the
  current descent when a range is broken. Their IK ignores joint limits, so ours must clamp.
- **#3** is the one that reaches the motion limit "nothing keeps its feet on the floor". A `location.plant(figure)` would
  solve both legs again at each moment so the feet stay put while the hips move.
- **#6** depends only on time, through a forward pass with checkpoints, so it keeps the rule that a frame of a film is a
  still of that moment.
- **#8** would arrive as a `Pass` or `PaintItem`: one still holding `location.at(t)` for several t, or 2D trails through
  `Projection`. Their renderer caches do not port.

## A bug in our code that this review found

Checked in `srlocations/motion.py` and reported to the session that owns motion:

- `smooth` overshoots. With keys 0 at 0 s, 1 at 1 s and 1 at 2 s, all `smooth`, the value peaks at 1.074 between the last two
  keys. The Catmull-Rom tangent at the middle key carries a body past a key where it should hold, possibly into a wall. A
  monotone Hermite (#2) fixes this: its tangents are zero at flat spans and reversals, and it stays between its keys.
- A pose keyed `smooth` is not smoothed. `value_at()` sends only numbers and `Vec3` to `through()`, and `EASES["smooth"]` is
  the identity, so a pose blends linearly and stops dead at every key.

## Not worth taking

- **Rig and naming.** Free names on 10 segments. We use Unity Humanoid's 55 bones with aliases to other packages' names.
- **Joint parameters.** Absolute 2D angles in radians, in screen space with y down, plus a derived depth layer that turns
  bend, turn, pitch in its own order. Formulas would have to be derived again, not transcribed.
- **Stretch, Smart Stretch, connectors, weighted joints and dual-quaternion skinning.** These break our rule of rigid limbs.
- **Mirroring.** Theirs flips a whole figure. `Pose.mirror()` swaps left for right.
- **Proportions.** Their sliders are per bone. We have body kinds, seeded variation, and figures fitted to ANSUR II.
- **Formats.** `.piv`, `.stk`, Stick Nodes `.nodes` and their own `.styk` and `.stkz` are all 2D, with no BVH, FBX, glTF
  animation or humanoid pose JSON. None maps to our controls.
- **Pose library.** There is none in the repository. Their "pose choices" are named partial sets of controls, such as hand
  shapes, which `both()` and `curled()` already give us. Fixtures for an auto-pose bank exist but no code uses them.
- **Things we have and they lack.** Joint ranges, collision with the set and with itself, settling onto seats, gaze and
  point-of-view shots, collision checked over time.

## What was built (2026-11-01)

All nine ideas were written from scratch, from the textbook methods named above. No StykAnimate code was copied, translated or
run. Tests are in `tests/test_kinematics.py` (35).

| # | Where | What it does |
|---|---|---|
| 1 | `srlocations/kinematics.py`, `Mannequin._aimed` | `reach_to()` takes `pole=`. Bend from the law of cosines, a hinge folding the way most of its range lies, the elbow or knee toward the pole, by default the way it bends now (or down and back for an arm, forward for a leg, when near straight). Root angles come from the rotation, with both sets tried. If that breaks a range, swivels 15° apart are tried, nearest the pole first, and only then the old search. On the test points none needed the search, and a reach lands within the 0.001° rounding of the controls. |
| 3 | `Mannequin._kept`, `holds`, `location.plant()` | `reach_to(keep=True)` turns the forearm or shin twist and the hand or foot back to their old orientation: exact without ranges, limited by the hand's ±40° side to side with them. `Mannequin(holds=...)` keeps a hand or foot at a world point, solved in `frames()`. `plant(figure, joint, start, end)` keys those holds as a step value, so each moment is solved from its own keys and a frame is still the still of `at(t)`. |
| 4 | `kinematics.nearest`, `Mannequin._chosen` | Of the two angle sets, the one within range and nearest the old values wins, each angle moved by whole turns. |
| 2 | studio-73's `fix-all` | Monotone `smooth` and smoothing of poses, done there. |
| 5 | `motion.cubic_bezier`, `Eases` | `move(ease=(x1, y1, x2, y2))` or `"cubic-bezier(...)"`. CSS `ease` at 0.5 gives 0.8024. |
| 6 | `srlocations/camera.py`, `location.follow()` | `lag`, `dead`, `ahead`, worked out in fixed steps from time 0 along the target's keys. |
| 7 | `camera.Shake`, `location.shake()` | Handheld, or a blow with `decay`, from seeded waves. A still location lasts as long as its shake. |
| 8 | `location.onion()`, `Figure.ghosted()` | One still with see-through, non-solid ghosts at other times. No 2D motion trails. |
| 9 | `Pose.push()`, `Pose.relax()` | An in-between moved away from or toward the plain blend of its keys, held at the ranges. |

`examples/mannequin.py` now draws `reach-poles.png` (one spot, elbow low and elbow out) and `squat-onion.png` (both feet
planted, ghosts on the way down). Making the squat showed that past about 25 cm the ankles run out of range, the held feet tip,
and the toes go into the floor. The collision check refuses it rather than drawing it.

Still not done: nothing solves a whole body (hips lowering to keep both feet in reach), a foot cannot roll, a plant lets go at
once, and fingers are still searched for.

## Recommendation

Do #1 to #4 together, as one piece of work on the mannequin: an analytic limb solve with a pole, orientation holds, nearest
angle choice and planted feet. It improves `reach_to()` now and gives motion a way to stop feet sliding. Fix #2 in motion
alongside it, because a planted walk keyed `smooth` would otherwise overshoot its keys. Leave #5 to #9 until a shot needs them.
Write all of it from public descriptions (Fritsch-Carlson for the monotone curve, the law of cosines and a pole vector for
two-bone IK), not from StykAnimate's source.
