from dataclasses import dataclass
from typing import Iterable

from srlocations.location import LightRig
from srlocations.nodes import Ambient, Light, Sky, Sun


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


@dataclass
class OpenSky(LightRig):
    """A real sky and a low sun, for anywhere open to the air. Best path traced, which lets the sky reflect."""
    azimuth: float = 35.0
    elevation: float = 30.0
    strength: float = 2.5
    brightness: float = 1.0
    zenith: str = "#6f9fb0"
    horizon: str = "#e4e6d8"
    ground: str = "#3d3a33"
    sun: str = "#ffe8c8"
    falloff: float = 0.5

    def lights(self) -> Iterable[Light]:
        return [Sky(self.brightness, zenith=self.zenith, horizon=self.horizon, ground=self.ground, falloff=self.falloff,
                    name="sky"),
                Sun(self.strength, color=self.sun, yaw=self.azimuth + 180, pitch=-self.elevation, shadows=True,
                    softness=0.6, name="sun")]


RIGS = {"daylight": Daylight, "night": Night, "interior": Interior, "open-sky": OpenSky}
