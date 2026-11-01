"""Two stock looks, built only from the public passes."""
from __future__ import annotations

from typing import Optional, Union

from srlocations.looks import Cel, Flat, Ink, Look


def ink_toon(palette: Optional[dict[str, str]] = None, cut: Union[float, str] = 0.5, line: float = 2.4) -> Look:
    """Broadcast cartoon: bright flat colour, hard shadow shapes, and a black brush line that swells a little. `cut` is
    where shade begins, or "auto" to measure it from each shot."""
    return Look([Flat(palette or {}, saturation=1.5, value=1.2), Cel(cut=cut, shade="#a79fc4"),
                 Ink(width=line, vary=0.45, wobble=1.2)], sky="#79c6f0", name="stock.ink-toon")


def paper_cutout(palette: Optional[dict[str, str]] = None, line: float = 1.4) -> Look:
    """Construction paper: flat colour with grain, no light at all, and every edge lifted off the sheet behind it."""
    return Look([Flat(palette or {}, saturation=1.25, value=1.1, grain=0.05),
                 Ink(color="#2a2320", width=line, vary=0.3, wobble=0.8, shadow=0.42)], sky="#9fd3e8", warp=1.5,
                name="stock.paper-cutout")
