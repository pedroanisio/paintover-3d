# Location Book

Every location published in this repository's catalog, with its versions, what it is for, where its pictures come from and
what is known not to work. It is kept true by hand, in the same commit as the change it describes, and
`tests/test_location_book.py` fails when a published location or version is missing from it or it names a location or
file that does not exist.

Rebuilt on 2026-11-02 at commit 70033cb from `catalog/locations/`, the commits that published each version, `README.md`,
`docs/`, the example scripts and the tests. Nothing here comes from memory of an earlier edition.

## How to read a location

A published location is data: a JSON entry under `catalog/locations/<name>/<version>.json` naming frozen props, a light
rig, marks and shots. `SharedCatalog.open("catalog").location(name)` opens the newest version, and
`location(name, version)` an older one. None needs the plugin that made it, and a test under `tests/test_surfaces.py`
holds that for each. Published versions are never edited, so a fix is a new version. Solid, light and seat counts below
are from opening the newest version with the SDK.

## Pictures

No render of any location is committed. `docs/images/` holds only the tutorial's three pictures of its radio booth. Each
location's pictures are written by its example script into a folder under `renders/`, which is not in git, so to see a
location you run its example (each needs the engine; none needs a plugin). `examples/fit_check.py` also puts a mannequin
in every set and writes `renders/fit/<location>-<shot>.png`. The textures the locations use are committed, in
`examples/textures/` as drawn by the `*_pictures.py` scripts and under `catalog/files/` as frozen.

## Locations

### airliner

An empty narrow-body cabin in warm evening light, three seats either side of the aisle. Tags: vehicle, interior.

| Version | Published | Props | What changed |
|---|---|---|---|
| 1.0.0 | 2026-11-02, commit 59481e4 | airliner-cabin 1.0.0 | First edition. |
| 1.0.1 | 2026-11-02, commit 59481e4 | airliner-cabin 1.0.1 | The cabin prop at 1.0.1; marks and shots unchanged. |

- Shots: `down-the-aisle` (15 mm), `window-seat` (20 mm), `from-the-galley` (18 mm).
- Marks: `aisle`, `galley-door`. No seats are published, so a figure in the `sit` pose finds nothing to sit on.
- Size: 1,262 solids, 51 lights.
- Pictures: `examples/airliner.py` writes `renders/airliner/<shot>-shaded.png` and `<shot>-traced.png`. The plugin that
  made it is `examples/plugins/airliner.py`.
- Held by tests: it opens without its plugin, validates, has exactly those shots, pins airliner-cabin 1.0.1, and keeps
  under 63 lights, past which the engine drops the far end of the cabin's lights.

### flight-deck

An airliner's flight deck at dusk over a lit city, with lit screens and an overhead panel. Tags: vehicle, interior,
aircraft.

| Version | Published | Props | What changed |
|---|---|---|---|
| 1.0.0 | 2026-11-02, commit 59481e4 | flight-deck 1.0.0 | First edition. |

- Shots: `from-the-jump-seat` (24 mm), `captains-seat` (22 mm), `pedestal` (22 mm), `overhead` (20 mm).
- Marks: none are published, so the crew in the example is placed by the script, and `location.stand()` puts nobody in
  it. No seats are published.
- Size: 232 solids, 10 lights.
- Pictures: `examples/flight_deck.py` writes `renders/flight-deck/<shot>.png`, `crew.png` and
  `from-the-jump-seat-traced.png`. `examples/flight_deck_pictures.py` redraws its screens into
  `examples/textures/flight-deck/`.
- Held by tests: it opens without its plugin, validates, has exactly those shots and pins flight-deck 1.0.0.

### grand-tourer

A grand tourer in cognac hide parked at a mountain overlook, its right door open, above hazy ridges. Tags: vehicle,
interior, landscape. It is the catalog's first location and the one the README, `examples/use_catalog.py` and
`examples/mannequin.py` use.

| Version | Published | Props | What changed |
|---|---|---|---|
| 1.0.0 | 2026-11-01, commit 8dfe7a1 | gt-cabin 1.0.0, mountain-overlook 1.0.0 | First edition. |
| 1.1.0 | 2026-11-01, commit 8dfe7a1 | both 1.1.0 | All three shots reframed. |
| 1.2.0 | 2026-11-01, commit 8dfe7a1 | both 1.2.0 | Both marks lowered 12 cm, to the ground as built; shots moved. |
| 1.3.0 | 2026-11-01, commit 8dfe7a1 | both 1.3.0 | `from-the-door` and `drivers-seat` moved. |
| 1.4.0 | 2026-11-01, commit 8dfe7a1 | both 1.4.0 | `from-the-door` moved. |
| 1.5.0 | 2026-11-01, commit 8dfe7a1 | both 1.5.0 | Props only; marks and shots as 1.4.0. |

All six were published in one commit, so the catalog shows the car being framed rather than a history of releases.

- Shots: `from-the-door` (19 mm), `drivers-seat` (20 mm), `console` (24 mm).
- Marks: `open-door`, `front-wing`. No seats: the cabin was frozen before props kept their seats, and a frozen prop keeps
  seats only from the version that was published with them.
- Size: 366 solids, 2 lights.
- Pictures: `examples/grand_tourer_paper.py` writes `renders/looks/grand-tourer-<shot>-paper.png`, the car as paper
  cut-outs with paint over a copy. `examples/use_catalog.py` writes `renders/traced/7-grand-tourer-<shot>.png` and
  `renders/wireframe/7-grand-tourer.png`. `examples/fit_check.py` writes `renders/fit/grand-tourer-<shot>.png` and
  prints the driver's joint angles.
- Held by tests: it opens without its plugin, validates, has exactly those shots, pins both props at 1.5.0 while
  1.0.0 pins both at 1.0.0, every part of the frozen cabin has its own path, and the cabin can be reskinned by slot.

### news-studio

A television news studio on air, in the approved plum, tangerine and mint: a curved desk on a lit riser, a curved video
wall with nothing written on it, a lighting grid and cameras. Tags: interior, broadcast.

| Version | Published | Props | What changed |
|---|---|---|---|
| 1.0.0 | 2026-11-02, commit 4ae2278 | news-studio 1.0.0 | First edition, four landscape shots. |
| 1.1.0 | 2026-11-02, commit be0aabc | news-studio 1.1.0 | Lit in the approved palette with a neutral fill; no lettering, ticker or map on the screens; two portrait shots at 1080x1920 added. |
| 2.0.0 | 2026-11-02, commit a212e2c | news-studio 2.0.0 | Desk ends lacquered plum in place of walnut, which was outside the palette. Drops `from-the-desk`, which faced an empty black studio; dropping a shot is why it is a major version. |

- Shots: `floor-camera` (20 mm), `two-shot` (35 mm), `wide` (20 mm), `portrait-two-shot` (35 mm), `portrait-push-in`
  (35 mm). The portrait shots are meant for 1080x1920, where the back of the desk top is at row 1082 and its front at
  1134, so a banner from row 1146 clears it.
- Marks: `anchor-left`, `anchor-right`. No seats are published.
- Size: 228 solids, 13 lights.
- Pictures: `examples/news_studio.py` writes `renders/news-studio/<shot>.png`, `<shot>-anchors.png` and
  `floor-camera-traced.png`. `examples/news_pictures.py` redraws the video wall and concrete into
  `examples/textures/news/`.
- Held by tests: it opens without its plugin, validates, has exactly those shots and marks, pins news-studio 2.0.0, keeps
  under 63 lights, every lit colour is in the palette or a grey or a lamp white, and the portrait rows are where the
  banner needs them.

### park

A city park on a summer afternoon: a brick path, a bench before a hedge, broadleaf trees and towers beyond. Tags:
exterior, landscape, city.

| Version | Published | Props | What changed |
|---|---|---|---|
| 1.0.0 | 2026-11-02, commit 4ae2278 | park 1.0.0 | First edition. |

- Shots: `by-the-bench` (24 mm), `along-the-path` (28 mm), `from-the-bench` (24 mm), `over-the-lawn` (20 mm).
- Marks: `bench`, `walker`. Six seats, three on each bench, kept when the prop was frozen.
- Size: 1,412 solids, 2 lights.
- Pictures: `examples/park.py` writes `renders/park/<shot>.png`, `people.png` (someone on the bench and someone on the
  path) and `by-the-bench-traced.png`. `examples/park_pictures.py` redraws its pavers, grass, leaves and tower glass
  into `examples/textures/park/`.
- Held by tests: it opens without its plugin, validates, has exactly those shots, pins park 1.0.0 and has six seats. The
  night park's plugin still freezes `Park(night=False)` to this version's digest, so publishing the night did not change
  the summer park.

### park-night

The same park after rain at night: wet path and kerbs under a clear coat, dark lawn and leaves, no clouds, one post-top
street lamp, four rows of low path lights, a bank of mist cards and a low cool moon behind as the rim. It is a plate for a
2D dancer to be composited over. Tags: exterior, landscape, city, night.

| Version | Published | Props | What changed |
|---|---|---|---|
| 1.0.0 | 2026-11-02, commit 36f5ca8 | park-night, park-lamp, park-haze, park-bollard, park-mist, all 1.0.0 | First edition. |

- Shots: `dance` (30 mm, eye at 0.8 m, the hips of a 1.6 m figure, looking along the path), `along-the-path` (28 mm).
  At 1080x1920 the floor at the dancer's mark is at row 1440 in the middle of the frame and a 1.6 m figure is 800 px tall.
- Marks: `dancer`. The lamp's spot is centred on it. Six seats, from the benches.
- Size: 1,450 solids, 12 lights.
- Pictures: `examples/park_night.py [folder] [width]` writes into `renders/park-night/` a wide plate with every light on,
  `base.png` with every lamp off (moon, sky and mist only), `lamp.png` and one light-only layer per row of path lights,
  which added to the base give the plate back, and `set.json` with the plate's camera numbers projected from the shot
  and the luminance behind the figure. It needs ffmpeg. The plates are 3200 px tall at 18 mm, for a camera pull-back:
  the same 2400 px focal length as the published 30 mm on 1920 px, so the published frame is their middle 1920 rows,
  the crop at (0, 640), which `set.json` (schema 2) records, with the f-stop scaled to 0.36 to keep the blur in px.
- Held by tests: it opens without its plugin, validates, has exactly those shots and the one mark, pins all five props at
  1.0.0, keeps under 63 lights, every lamp's `.off` twin differs only by its light, the mist cards stand on the lawn, the
  lamp haze faces the dance shot, and the dance shot's rows are as above.

### starship-bridge

A starship's bridge with a capital ship off to port, laid out as a control room: a straight band of raked windows with a
line of consoles under it, chairs only at two consoles off the centre line, a mimic board with no words to port and a
chart table against the starboard wall. Tags: interior, scifi, vehicle.

| Version | Published | Props | What changed |
|---|---|---|---|
| 1.0.0 | 2026-11-02, commit 4ae2278 | starship-bridge 1.0.0 | First edition: a pit with a command chair and a holo table; marks `captain` and `officer`; shots `from-the-pit`, `command-chair`, `holo-table`, `the-view`. |
| 2.0.0 | 2026-11-02, commit be0aabc | starship-bridge 2.0.0 | Reworked to the channel's ruling: one floor, no centre seat facing the windows, no holo table; four station marks and five shots. |
| 2.1.0 | 2026-11-02, commit a212e2c | starship-bridge 2.1.0 | Each console chair's seat and back named after its station, so a seat or clash report can tell the two apart. |

- Shots (2.x): `bridge-wide` (18 mm), `console-line` (22 mm), `mimic-board` (22 mm), `chart-table` (28 mm), `the-view`
  (26 mm).
- Marks (2.x): `helm`, `navigator`, `engineer`, `officer`. Two seats, at the helm and navigator consoles.
- Size: 159 solids, 13 lights.
- Pictures: `examples/starship_bridge.py` writes `renders/starship-bridge/<shot>.png`, `<shot>-crew.png` (two seated at
  the consoles, one at the mimic board, one at the chart table) and `bridge-wide-traced.png`.
  `examples/bridge_pictures.py` redraws its screens, mimic board, chart, deck plates and stars into
  `examples/textures/bridge/`.
- Held by tests: it opens without its plugin, validates, has exactly those shots, pins starship-bridge 2.1.0, keeps under
  63 lights, has no seat within 1 m of the centre line and nothing named holo or command-chair, and each chair's seat
  and back has its own path.

## Known limits

The SDK's limits are listed under "Limits" in `README.md`, and that list is the one kept current. The ones that show in
these locations:

- **Lights.** The engine holds 63 lights to a screen tile, and past that some drop out. The airliner (51), the news
  studio, the bridge and the night park each have a test that keeps them under it, so a set with many lamps needs short
  `reach`.
- **Seats.** A frozen prop keeps its seats only from the version published with them. The grand tourer, airliner, flight
  deck and news studio publish none, so a figure in the `sit` pose finds nothing on them until a new version is
  published. Props carry no grip points yet, and new seats wait on socket names from srstudio.
- **Characters.** A character on a mark is one picture: it goes where the figure on its mark settled, but it stands where
  the figure sits. Depth for paint treats a mark as one distance, to within 15 cm, and paint casts no shadow onto the set.
- **Views and windows.** A window's view is a flat picture: it shifts a little as the camera moves, and a shot from
  outside can see it. The flight deck's city, the overlook's ridges and the bridge's capital ship are such pictures.
- **Textures.** A tiled texture runs backwards on two of a room's four walls, which only lettering would show, and
  restarts on each round solid. An imported model keeps its own UVs.
- **Published locations take their rig from stock.** A catalog prop can carry point and spot lights but not a sun or
  ambient light.
- **Shots.** A shot has no lens shift, so a reference photo with corrected verticals is matched by eye height only. The
  portrait shots of the news studio and the night park are framed by row numbers at 1080x1920 for that reason.
- **Marks.** A mark warns `mark-blocked` without about 2 m of clear space above it, which a seat or a low cockpit roof
  does not have. The flight deck publishes no marks.
- **Mannequins in the sets.** A mannequin has rigid segments, a settled figure does not change its pose to fit, and
  `repose()` stops where something is in the way. `location.clashes()` reports the deepest overlap per pair of nodes and
  `location.faults()` every limb. The comfort ranges in `examples/fit_check.py` are working values, not from a standard.
- **Motion in them.** A planted foot holds while the leg can reach it, nothing moving goes more than 3 cm unchecked
  between keys, and a figure walking 10 m across a big set with its feet planted takes about 18 s to check. Ink stays
  sharp under motion blur, so fast ink sits on a smear, and ink line widths waver by about 0.4 px frame to frame.

Open points on the mannequin that these sets exercise are under "Open points" in `docs/mannequin-score.md`: the centre
of mass sits slightly high, clash checks are 2.1x faster rather than the 5x aimed for, and the HumanIK bone names are
unchecked. What a review of the SDK found and left is under "Found and left" in `docs/sdk-review.md`.

## Tests

```
$ .venv/bin/python -m pytest --collect-only -q tests -p no:cacheprovider
...
1567 tests collected in 3.73s
```

That is the count collected on 2026-11-02 at commit 70033cb, with engine 0.9.0 on this machine, not a count passed: the
suite was not run for this edition, because the machine was reserved. The full suite takes about four minutes and needs
the GPU; two tests need srstudio and skip without it. The count changes with every test added, so when it changes, so
does this line.
