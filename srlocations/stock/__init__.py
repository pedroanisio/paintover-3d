"""The stock library, itself an ordinary plugin: nothing in the core depends on it."""
from __future__ import annotations

from srlocations.compiler import Shaded, Traced, Wireframe
from srlocations.looks import Cel, Flat, Ink, Lit, Styled
from srlocations.materials import Material
from srlocations.mesh import MODEL, Mesh
from srlocations.paint import Decal
from srlocations.stock.looks import ink_toon, paper_cutout
from srlocations.stock.mannequin import Mannequin
from srlocations.registry import Plugin, Registry
from srlocations.stock import archetypes, checks, materials, prefabs, rigs


class StockPlugin(Plugin):
    name = "stock"
    version = "0.1.0"

    def register(self, registry: Registry) -> None:
        for name, material in materials.PALETTE.items():
            registry.materials.add(f"stock.{name}", material)
        for name, prefab in prefabs.PREFABS.items():
            registry.prefabs.add(f"stock.{name}", prefab)
        for name, rig in rigs.RIGS.items():
            registry.rigs.add(f"stock.{name}", rig)
        registry.archetypes.add("stock.street", archetypes.Street)
        registry.modes.add("stock.wireframe", Wireframe)
        registry.modes.add("stock.shaded", Shaded)
        registry.modes.add("stock.traced", Traced)
        registry.prefabs.add("stock.decal", Decal)
        registry.prefabs.add("stock.mesh", Mesh)
        registry.prefabs.add("stock.mannequin", Mannequin)
        for step in (Flat, Lit, Cel, Ink):
            registry.passes.add(f"stock.{step.__name__.lower()}", step)
        registry.materials.add(MODEL, Material("#c8c8c8"))
        registry.modes.add("stock.ink-toon", lambda **params: Styled(ink_toon(), **params))
        registry.modes.add("stock.paper-cutout", lambda **params: Styled(paper_cutout(), **params))
        registry.checks.extend([checks.MaterialsExist(), checks.ModelSlots(), checks.LooksKnown(), checks.ShotsClear(), checks.MarksClear(),
                                checks.SolidsClear()])
