"""Prop templates: parametric props written as data, so a catalog can share them without sharing code.

A template declares its parameters and shader slots, then its parts. A parameter is a number, an on/off choice, or one of
some named `choices`, and its default says which. Any number in a part can be an expression over the parameters, where an
on/off parameter reads as a condition and a choice compares with text: "0.8 if finish == 'matte' else 0.2". Expressions are parsed and walked here against an allow-list, and never reach eval: arithmetic, comparisons,
and/or/not, `a if c else b`, pi, and min max abs floor ceil round sqrt pow sign sin cos tan, with angles in degrees.

    {"solid": "box", "size": ["width", 0.04, "depth"], "at": [0, "height - 0.02", 0], "shader": "top"}
    {"solid": "cylinder", "radius": 0.02, "height": "height", "shader": "legs"}
    {"solid": "sphere", "radius": 0.1, "shader": "top", "casts_shadow": false}
    {"light": "point", "intensity": "candela", "color": "#ffd29a", "reach": 6, "at": [0, 2, 0]}
    {"repeat": "shelves", "as": "i", "parts": [...]}
    {"prop": "chair", "at": [...], "yaw": 180, "params": {"width": 0.5}, "shaders": {"seat": "$seat"}}

Any part can also have "when": an expression that leaves the part out when false. In a nested prop's "shaders", "$seat"
passes on this template's own slot and any other value names a shader. A solid's "shader": "$finish" takes the slot that
the choice `finish` names, so each of its choices has to be a slot.
"""
from __future__ import annotations

import ast
import json
import math
import operator
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Iterator, Mapping, Optional, Sequence, Union

from srlocations.registry import CatalogError

Number = Union[int, float]
Value = Union[int, float, str]  # a bool is an int here, as it is to Python
MAX_EXPRESSION = 256
MAX_SURFACE_EXPRESSION = 2048  # one axis of a whole surface
PLACEMENT = ("at", "yaw", "pitch", "roll", "name", "basis", "role")
RESERVED = {*PLACEMENT, "shaders", "variant", "pi"}
SOLID_SIZES = {"box": ("size",), "cylinder": ("radius", "height"), "cone": ("radius", "height"), "sphere": ("radius",)}
LIGHT_KINDS = ("point", "spot")
PLACED = {"when", "at", "yaw", "pitch", "roll", "role"}
PART_KEYS = {"solid": PLACED | {"solid", "size", "radius", "height", "segments", "shader", "casts_shadow"},
             "light": PLACED | {"light", "intensity", "color", "reach", "cone"},
             "prop": PLACED | {"prop", "params", "shaders"},
             "repeat": {"when", "repeat", "as", "parts"}}
BINARY = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
          ast.Mod: operator.mod, ast.FloorDiv: operator.floordiv}
COMPARE = {ast.Lt: operator.lt, ast.LtE: operator.le, ast.Gt: operator.gt, ast.GtE: operator.ge, ast.Eq: operator.eq,
           ast.NotEq: operator.ne}
FUNCTIONS = {"min": min, "max": max, "abs": abs, "floor": math.floor, "ceil": math.ceil, "round": round,
             "sqrt": math.sqrt, "pow": pow, "sign": lambda a: (a > 0) - (a < 0),
             "sin": lambda a: math.sin(math.radians(a)), "cos": lambda a: math.cos(math.radians(a)),
             "tan": lambda a: math.tan(math.radians(a))}
ENGINE_BINARY = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/"}


class TemplateError(CatalogError):
    pass


@lru_cache(maxsize=4096)
def _parse(text: str, limit: int = MAX_EXPRESSION) -> ast.Expression:
    if len(text) > limit:
        raise TemplateError(f"expression longer than {limit} characters: {text[:40]}...")
    try:
        return ast.parse(text, mode="eval")
    except (SyntaxError, ValueError) as error:
        raise TemplateError(f"cannot read expression {text!r}: {error}") from error


def _walk(node: ast.AST, scope: Mapping[str, Value]) -> Value:
    match node:
        case ast.Constant(value=value) if type(value) in (int, float, bool, str):
            return value
        case ast.Name(id=name):
            if name == "pi":
                return math.pi
            if name not in scope:
                raise TemplateError(f"unknown name {name!r}")
            return scope[name]
        case ast.BinOp(left=left, op=op, right=right) if type(op) in BINARY:
            operands = _walk(left, scope), _walk(right, scope)
            if any(isinstance(operand, str) for operand in operands):  # "a" * 10**9 is arithmetic Python would do
                raise TemplateError("text can be compared, and cannot be calculated with")
            return BINARY[type(op)](*operands)
        case ast.UnaryOp(op=ast.USub(), operand=operand):
            return -_walk(operand, scope)
        case ast.UnaryOp(op=ast.UAdd(), operand=operand):
            return _walk(operand, scope)
        case ast.UnaryOp(op=ast.Not(), operand=operand):
            return not _walk(operand, scope)
        case ast.BoolOp(op=op, values=values):
            results = (_walk(value, scope) for value in values)
            return all(results) if isinstance(op, ast.And) else any(results)
        case ast.Compare(left=left, ops=ops, comparators=comparators) if all(type(o) in COMPARE for o in ops):
            current = _walk(left, scope)
            for op, comparator in zip(ops, comparators):
                following = _walk(comparator, scope)
                if not COMPARE[type(op)](current, following):
                    return False
                current = following
            return True
        case ast.IfExp(test=test, body=body, orelse=orelse):
            return _walk(body if _walk(test, scope) else orelse, scope)
        case ast.Call(func=ast.Name(id=name), args=args, keywords=[]) if name in FUNCTIONS:
            return FUNCTIONS[name](*(_walk(arg, scope) for arg in args))
    raise TemplateError(f"expressions cannot use {type(node).__name__}")


def evaluate(expression: Value, scope: Mapping[str, Value], limit: int = MAX_EXPRESSION, text: bool = False) -> Value:
    """The value of a number or an expression; anything outside the allow-list is a TemplateError. It comes to a number
    unless `text` allows a choice as well."""
    if type(expression) not in (int, float, bool, str):
        raise TemplateError(f"{expression!r} is not a number or an expression")
    try:
        value = _walk(_parse(expression, limit).body, scope) if isinstance(expression, str) else expression
        if text and isinstance(value, str):
            return value
        finite = math.isfinite(value)
    except (ArithmeticError, ValueError, TypeError, RecursionError, MemoryError) as error:
        raise TemplateError(f"cannot work out {expression!r}: {error}") from error
    if not finite:
        raise TemplateError(f"{expression!r} is not a finite number")
    return value


def engine_expression(expression: str, names: Mapping[str, str]) -> str:
    """The same expression in the engine's language, ECMAScript in radians; `names` says what each variable becomes."""
    def text(node: ast.AST) -> str:
        match node:
            case ast.Constant(value=value) if type(value) in (int, float):
                return repr(value)
            case ast.Name(id="pi"):
                return "Math.PI"
            case ast.Name(id=name) if name in names:
                return names[name]
            case ast.BinOp(left=left, op=op, right=right) if type(op) in ENGINE_BINARY:
                return f"({text(left)}{ENGINE_BINARY[type(op)]}{text(right)})"
            case ast.UnaryOp(op=ast.USub(), operand=operand):
                return f"(-{text(operand)})"
            case ast.Call(func=ast.Name(id=name), args=args, keywords=[]) if name in FUNCTIONS and name != "round":
                inner = ",".join(text(arg) for arg in args)
                return f"Math.{name}(({inner})*Math.PI/180)" if name in ("sin", "cos", "tan") else f"Math.{name}({inner})"
        raise TemplateError(f"a surface expression cannot use {type(node).__name__}: {expression[:60]}")
    return text(_parse(expression, MAX_SURFACE_EXPRESSION).body)


def names_in(expression: Union[Number, str]) -> set[str]:
    if not isinstance(expression, str):
        return set()
    return {n.id for n in ast.walk(_parse(expression).body) if isinstance(n, ast.Name)} - {"pi", *FUNCTIONS}


def expressions_of(part: dict) -> Iterator[Union[Number, str]]:
    """The expressions of one part, leaving out what is under a repeat."""
    for key in ("when", "repeat", "yaw", "pitch", "roll", "radius", "height", "intensity", "reach", "cone"):
        if key in part:
            yield part[key]
    yield from part.get("at", ())
    yield from part.get("size", ())
    yield from part.get("params", {}).values()


@dataclass(frozen=True)
class Param:
    """A number, or on/off when `default` is True or False, or one of `choices`."""
    default: Value
    min: Optional[Number] = None
    max: Optional[Number] = None
    description: str = ""
    choices: Sequence[str] = ()

    def spec(self) -> dict:
        """As data. No choices are written when there are none, so a numeric template keeps its digest."""
        return {key: value for key, value in asdict(self).items() if key != "choices" or value}

    def trials(self) -> Sequence[Value]:
        """The values worth building at publish, besides the default."""
        return self.choices or ((True, False) if type(self.default) is bool else ())

    def check(self, name: str, value: object) -> Value:
        if self.choices:
            if value not in self.choices:
                raise TemplateError(f"parameter {name} is {value!r}; it takes {', '.join(self.choices)}")
            return value
        if type(self.default) is bool:
            if type(value) is not bool:
                raise TemplateError(f"parameter {name} must be true or false, not {value!r}")
            return value
        if type(value) not in (int, float) or not abs(value) < 1e30:
            raise TemplateError(f"parameter {name} must be a number, not {value!r}")
        if (self.min is not None and value < self.min) or (self.max is not None and value > self.max):
            raise TemplateError(f"parameter {name} is {value}, outside {self.min} to {self.max}")
        return value


@dataclass
class PropTemplate:
    name: str
    parts: Sequence[dict]
    params: dict[str, Param] = field(default_factory=dict)
    slots: dict[str, str] = field(default_factory=dict)  # slot to default shader
    variants: dict[str, dict] = field(default_factory=dict)  # name to parameter values, and "shaders"
    description: str = ""
    tags: Sequence[str] = ()

    @classmethod
    def from_data(cls, data: dict) -> "PropTemplate":
        values = dict(data)
        try:
            values["params"] = {name: Param(**param) for name, param in data.get("params", {}).items()}
            return cls(**values)
        except TypeError as error:
            raise TemplateError(f"template {data.get('name')!r}: {error}") from error

    @classmethod
    def from_file(cls, path: Union[str, Path]) -> "PropTemplate":
        return cls.from_data(json.loads(Path(path).read_text()))

    def check(self) -> None:
        """Everything that can be found without evaluating: bad names, slots and part shapes, in every branch."""
        for name, param in self.params.items():
            if name in RESERVED or name in FUNCTIONS or not name.isidentifier():
                raise TemplateError(f"{self.name}: {name!r} cannot be a parameter name")
            if (param.choices or type(param.default) is bool) and (param.min is not None or param.max is not None):
                raise TemplateError(f"{self.name}: parameter {name} is not a number, so it has no min or max")
            if not all(type(choice) is str and choice for choice in param.choices):
                raise TemplateError(f"{self.name}: parameter {name} has choices that are not names: {param.choices}")
            param.check(name, param.default)
        for variant, values in self.variants.items():
            for name, value in values.items():
                if name == "shaders":
                    self._check_slots(value, f"variant {variant}")
                elif name not in self.params:
                    raise TemplateError(f"{self.name}: variant {variant} sets unknown parameter {name!r}")
                else:
                    self.params[name].check(name, value)
        self._check_parts(self.parts, set(self.params))

    def _check_slots(self, used: Iterable[str], where: str) -> None:
        for slot in used:
            if slot not in self.slots:
                raise TemplateError(f"{self.name}: {where} uses unknown shader slot {slot!r}")

    def _check_parts(self, parts: Sequence[dict], names: set[str]) -> None:
        for part in parts:
            kind = next((key for key in PART_KEYS if key in part), None)
            if kind is None:
                raise TemplateError(f"{self.name}: a part needs solid, light, prop or repeat: {part}")
            stray = set(part) - PART_KEYS[kind]
            if stray:
                raise TemplateError(f"{self.name}: a {kind} part cannot have {sorted(stray)[0]!r}")
            for expression in expressions_of(part):  # a repeat's own "when" and count come before its "as" exists
                unknown = names_in(expression) - names
                if unknown:
                    raise TemplateError(f"{self.name}: unknown name {sorted(unknown)[0]!r} in {expression!r}")
            if kind == "repeat":
                self._check_parts(part.get("parts", ()), {*names, part["as"]} if "as" in part else names)
            elif kind == "solid":
                self._check_solid(part)
            elif kind == "light" and part["light"] not in LIGHT_KINDS:
                raise TemplateError(f"{self.name}: a prop can carry point and spot lights, not {part['light']!r}")
            elif kind == "prop":
                passed = [value[1:] for value in part.get("shaders", {}).values() if value.startswith("$")]
                self._check_slots(passed, f"prop {part['prop']}")

    def _check_solid(self, part: dict) -> None:
        kind = part["solid"]
        if kind not in SOLID_SIZES:
            raise TemplateError(f"{self.name}: unknown solid {kind!r}")
        for key in SOLID_SIZES[kind]:
            if key not in part:
                raise TemplateError(f"{self.name}: a {kind} needs {key}")
        if kind == "box" and len(part["size"]) != 3:
            raise TemplateError(f"{self.name}: a box size has three values, not {part['size']}")
        if "segments" in part and (kind == "box" or type(part["segments"]) is not int):
            raise TemplateError(f"{self.name}: segments is a whole number on a round solid")
        shader = part.get("shader") or ""
        if shader.startswith("$"):
            choices = self.params[shader[1:]].choices if shader[1:] in self.params else ()
            if not choices:
                raise TemplateError(f"{self.name}: {shader} does not name a parameter with choices")
            self._check_slots(choices, f"parameter {shader[1:]}")
        else:
            self._check_slots([part.get("shader")], f"a {kind}")
