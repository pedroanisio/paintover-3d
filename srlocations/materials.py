"""Materials by value; the compiler turns the ones a location uses into engine materials.

A Material is a surface shader. The engine's 3D surfaces take no custom shader code, so a shader is a set of values for
its glTF metallic-roughness model and extensions: `extra` carries any attribute of <material> (clearcoat, sheen,
transmission, anisotropy...) and `maps` any texture attribute (baseColorMap, normalMap...) as a file path.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sr_core.scene import Scene


@dataclass(frozen=True)
class Material:
    color: str = "#808080"
    roughness: float = 0.7
    metallic: float = 0.0
    glow: str = ""
    glow_strength: float = 1.0
    opacity: float = 1.0
    extra: dict[str, object] = field(default_factory=dict, hash=False)
    maps: dict[str, str] = field(default_factory=dict, hash=False)

    def attributes(self) -> dict[str, object]:
        out: dict[str, object] = {"baseColor": self.color, "roughness": self.roughness, "metallic": self.metallic}
        if self.glow:
            out |= {"emissive": self.glow, "emissiveStrength": self.glow_strength}
        if self.opacity < 1:
            out |= {"opacity": self.opacity, "alphaMode": "blend"}
        return {**out, **self.extra, **self.maps}

    def validate(self) -> None:
        """Raises sr_core's schema error for an attribute the engine does not have or a value it would refuse."""
        Scene(version="auto").add_materials().add_material(id="probe", **self.attributes())
