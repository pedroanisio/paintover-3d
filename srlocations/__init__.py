"""Build 3D locations in metres, as objects, and compile them to sr_core.scene documents."""
from srlocations.blueprint import Blueprint
from srlocations.cast import Actor, Cutout, Ensemble, Performer, Portrait, alpha_box
from srlocations.catalog import Entry, FrozenProp, SharedCatalog, TemplateProp
from srlocations.collision import Clash, CollisionError
from srlocations.compiler import (Compiler, Projection, RenderMode, Renderer, SceneCompiler, Shaded, Traced,
                                  TracedCompiler, Wireframe, WireframeCompiler)
from srlocations.geometry import Transform, Vec3, aim, rotation
from srlocations.location import Archetype, Check, Issue, LightRig, Location, Mark, Shot
from srlocations.materials import Material
from srlocations.mesh import Mesh, MeshError, read_model
from srlocations.nodes import (Ambient, Backdrop, Box, Cone, Cylinder, Group, Light, Node, Placed, Point, Prefab, Seat, Sky,
                               Solid, Sphere, Spot, Sun)
from srlocations.looks import Cel, Flat, Ink, Lit, Look, Pass, Stage, Styled, StyledCompiler, Texture
from srlocations.paint import Decal, Disc, Fill, PaintItem, PaintLayer, Picture, Standee, Sticker, Stroke
from srlocations.surfaces import Surface
from srlocations.templates import Param, PropTemplate, TemplateError
from srlocations.registry import Assembly, Catalog, CatalogError, Library, Plugin, PluginManager, Registry

__version__ = "0.1.0"
