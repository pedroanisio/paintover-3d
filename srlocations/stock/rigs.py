from dataclasses import dataclass
from typing import Iterable

from srlocations.location import LightRig
from srlocations.nodes import Ambient, Light, Sun


@dataclass
class Daylight(LightRig):
    """Sun from the side with a cool sky fill. `azimuth` and `elevation` place the sun, in degrees."""
    azimuth: float = 35.0
    elevation: float = 50.0
    strength: float = 3.2
    background = "#a8c8e6"

    def lights(self) -> Iterable[Light]:
        return [Ambient(0.75, color="#cfe0f5", name="sky"),
                Sun(self.strength, color="#fff1dc", yaw=self.azimuth + 180, pitch=-self.elevation, shadows=True,
                    softness=0.6, name="sun")]


@dataclass
class Night(LightRig):
    """A dim blue fill: the location's own lamps do the work."""
    fill: float = 0.12
    background = "#080b14"

    def lights(self) -> Iterable[Light]:
        return [Ambient(self.fill, color="#6a7cb0", name="night-fill")]


@dataclass
class Interior(LightRig):
    """Soft even room fill, for rooms with practical lamps."""
    fill: float = 0.45
    background = "#101215"

    def lights(self) -> Iterable[Light]:
        return [Ambient(self.fill, color="#ffe9cf", name="room-fill")]


RIGS = {"daylight": Daylight, "night": Night, "interior": Interior}
