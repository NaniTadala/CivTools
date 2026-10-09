from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable, Optional
import openstaadpy

MAX_LINE_DEFAULT = 78
TOL_DEFAULT = 0.10
DJ_HORIZONTAL_TOL = 0.001
DJ_DIRECTION_TOL = 0.001
DJ_COLLINEAR_DOT_MIN = 0.999
DJ_ELEVATION_ROUND = 2
DJ_DOT_EQUAL_TOL = 1.0e-7

@dataclass(slots=True)
class Member:
    member_id: int
    start_node: int
    end_node: int
    length: float
    section: str
    material: str
    concrete: bool
    steel: bool
    column_y: bool
    beam_x: bool
    beam_z: bool


@dataclass(slots=True)
class Parameter:
    enabled: bool
    name: str
    value: Optional[float]
    scope: str
    description: str


@dataclass(slots=True)
class DJChain:
    start_node: int
    end_node: int
    direction: str
    elevation: float
    member_ids: list[int]
    release_dj1: bool = False
    release_dj2: bool = False
    ambiguous_dj1: bool = False
    ambiguous_dj2: bool = False


@dataclass(slots=True)
class DJStubChain:
    bottom_node: int
    top_node: int
    base_elevation: float
    top_elevation: float
    member_ids: list[int]
    release_dj1: bool = False
    release_dj2: bool = False
    ambiguous_dj1: bool = False
    ambiguous_dj2: bool = False


CONCRETE_PARAMETERS = [
    Parameter(True, "FC", 30.0, "All concrete", "Concrete compressive strength"),
    Parameter(True, "FYMAIN", 500.0, "All concrete", "Main reinforcement yield strength"),
    Parameter(True, "FYSEC", 500.0, "All concrete", "Secondary reinforcement yield strength"),
    Parameter(True, "MAXMAIN", 0.04, "All concrete", "Maximum main reinforcement ratio"),
    Parameter(True, "MAXSEC", 0.04, "All concrete", "Maximum secondary reinforcement ratio"),
    Parameter(True, "MINMAIN", 0.002, "All concrete", "Minimum main reinforcement ratio"),
    Parameter(True, "MINSEC", 0.002, "All concrete", "Minimum secondary reinforcement ratio"),
    Parameter(True, "TRACK", 2.0, "All concrete", "Design output detail level"),
    Parameter(True, "CLEAR (BEAMS)", 40.0, "Concrete beams", "Beam clear cover"),
    Parameter(False, "BRACE", 0.0, "Concrete beams", "Beam bracing parameter"),
    Parameter(False, "PLASTIC", 0.0, "Concrete beams", "Plastic design option"),
    Parameter(False, "TORSION", 0.0, "Concrete beams", "Torsion design option"),
    Parameter(True, "GLD", 0.0, "Concrete beams", "Beam design parameter"),
    Parameter(True, "DESIGN BEAM", None, "Concrete beams", "Design detected concrete beams"),
    Parameter(False, "CLEAR (COLUMNS)", 40.0, "Concrete columns", "Column clear cover"),
    Parameter(True, "RATIO", 4.0, "Concrete columns", "Column design ratio"),
    Parameter(False, "BRACE (COLUMNS)", 0.0, "Concrete columns", "Column bracing parameter"),
    Parameter(True, "RFACE", 4.0, "Concrete columns", "Reinforcement faces"),
    Parameter(True, "REINF", 0.0, "Concrete columns", "Column reinforcement option"),
    Parameter(True, "ELY", 1.2, "Concrete columns", "Effective length factor using global-X restraint beams"),
    Parameter(True, "ELZ", 1.2, "Concrete columns", "Effective length factor using global-Z restraint beams"),
    Parameter(True, "ULY", 1.0, "Concrete columns", "Unsupported length factor using global-X restraint beams"),
    Parameter(True, "ULZ", 1.0, "Concrete columns", "Unsupported length factor using global-Z restraint beams"),
    Parameter(False, "DESIGN COLUMN", None, "Concrete columns", "Design detected concrete columns"),
]

STEEL_PARAMETERS = [
    Parameter(True, "FYLD", 355000.0, "All steel", "Steel yield strength in active STAAD force/area units"),
    Parameter(True, "KY", 1.0, "All steel", "Effective length factor about local y-axis"),
    Parameter(True, "KZ", 1.0, "All steel", "Effective length factor about local z-axis"),
    Parameter(True, "LY", 0.0, "All steel", "Effective length about local y-axis"),
    Parameter(True, "LZ", 0.0, "All steel", "Effective length about local z-axis"),
    Parameter(False, "UNL", 0.0, "All steel", "Unsupported length for lateral-torsional buckling"),
    Parameter(False, "UNT", 0.0, "All steel", "Top-flange unbraced length"),
    Parameter(False, "UNB", 0.0, "All steel", "Bottom-flange unbraced length"),
    Parameter(True, "RATIO", 1.0, "All steel", "Allowable utilization ratio"),
    Parameter(True, "TRACK", 2.0, "All steel", "Design output detail level"),
    Parameter(False, "DJ", None, "Steel beams", "Generate DJ1 and DJ2 for continuous steel beam"),
    Parameter(False, "DJ STUB COLUMNS", None, "Steel stub columns", "Generate DJ1 and DJ2 for steel stub-column"),
    Parameter(True, "CHECK CODE", None, "All steel", "Check all detected steel members"),
]


class StaadService:
    def __init__(self) -> None:
        self.os: Any = None
        self.members: list[Member] = []
        self.by_node: dict[int, list[int]] = {}
        self.model_path = ""
        self._node_cache: dict[int, tuple[float, float, float]] = {}

    def connect(self) -> None:
        try:
            from openstaadpy import os_analytical
        except ImportError as exc:
            raise RuntimeError(
                "openstaadpy is not installed. Run: pip install openstaadpy"
            ) from exc

        self.os = os_analytical.connect()
        if self.os is None:
            raise RuntimeError(
                "Could not connect. Open STAAD.Pro with a valid analytical model first."
            )

        try:
            self.model_path = str(self.os.GetSTAADFile() or "Active STAAD model")
        except Exception:
            self.model_path = "Active STAAD model"

    @staticmethod
    def _coords(value: Any) -> tuple[float, float, float]:
        if isinstance(value, (tuple, list)) and len(value) >= 3:
            return float(value[0]), float(value[1]), float(value[2])
        raise RuntimeError(f"Unexpected node-coordinate result: {value!r}")

    @staticmethod
    def _incidence(value: Any) -> tuple[int, int]:
        if isinstance(value, (tuple, list)) and len(value) >= 2:
            return int(value[0]), int(value[1])
        raise RuntimeError(f"Unexpected member-incidence result: {value!r}")

    @staticmethod
    def _material_flags(
        material: str,
        section: str,
        fallback: bool,
    ) -> tuple[bool, bool]:
        material_upper = material.upper().strip()
        concrete = "CONCRETE" in material_upper
        steel = any(token in material_upper for token in ("STEEL", "STAINLESS"))

        if (
            not concrete
            and not steel
            and fallback
            and material_upper in {"", "NONE", "UNKNOWN", "N/A"}
        ):
            section_upper = section.upper().strip()
            concrete = section_upper.startswith(
                ("RECT", "CIRC", "TEE", "TRAP", "PRIS", "YD")
            )
            steel = not concrete and bool(section_upper)

        return concrete, steel

    def load_model(
        self,
        tolerance: float,
        fallback: bool = False,
    ) -> list[Member]:
        self.connect()
        self._node_cache.clear()

        ids = [int(value) for value in self.os.Geometry.GetBeamList()]
        if not ids:
            raise RuntimeError(
                "No analytical members were found in the active STAAD model."
            )

        members: list[Member] = []
        by_node: dict[int, list[int]] = {}

        for member_id in ids:
            n1, n2 = self._incidence(
                self.os.Geometry.GetMemberIncidence(member_id)
            )
            x1, y1, z1 = self.node_coords(n1)
            x2, y2, z2 = self.node_coords(n2)

            dx = abs(x2 - x1)
            dy = abs(y2 - y1)
            dz = abs(z2 - z1)
            length = math.sqrt(dx * dx + dy * dy + dz * dz)

            if length <= 1.0e-12:
                raise RuntimeError(f"Zero-length member detected: {member_id}")

            try:
                section = str(
                    self.os.Property.GetBeamSectionName(member_id) or ""
                )
            except Exception:
                section = ""

            try:
                material = str(
                    self.os.Property.GetBeamMaterialName(member_id) or ""
                )
            except Exception:
                material = ""

            concrete, steel = self._material_flags(
                material,
                section,
                fallback,
            )

            horizontal = dy / length <= tolerance
            column_y = math.hypot(dx, dz) / length <= tolerance
            beam_x = horizontal and dz / length <= tolerance and dx > dz
            beam_z = horizontal and dx / length <= tolerance and dz > dx

            index = len(members)
            members.append(
                Member(
                    member_id,
                    n1,
                    n2,
                    length,
                    section,
                    material,
                    concrete,
                    steel,
                    column_y,
                    beam_x,
                    beam_z,
                )
            )
            by_node.setdefault(n1, []).append(index)
            by_node.setdefault(n2, []).append(index)

        self.members = members
        self.by_node = by_node
        return members

    def support_nodes(self) -> list[int]:
        if self.os is None:
            return []
        return [int(value) for value in self.os.Support.GetSupportNodes()]

    def length_to_meters(self, value: float) -> float:
        """Convert OpenSTAAD base-unit coordinates to metres.

        GetNodeCoordinates returns coordinates in STAAD base units:
        metres for Metric models and inches for English models. It must not
        be converted using the current input-unit label.
        """
        if self.os is None:
            raise RuntimeError("STAAD.Pro is not connected.")

        try:
            base_unit = str(self.os.GetBaseUnit() or "").strip().casefold()
        except Exception as exc:
            raise RuntimeError(
                f"Could not determine the STAAD base unit: {exc}"
            ) from exc

        if base_unit == "metric":
            return float(value)
        if base_unit == "english":
            return float(value) * 0.0254

        raise RuntimeError(
            f"Unsupported STAAD base unit: {base_unit or 'blank'}"
        )

    def node_coords(self, node: int) -> tuple[float, float, float]:
        if self.os is None:
            raise RuntimeError("STAAD.Pro is not connected.")

        node = int(node)
        if node not in self._node_cache:
            self._node_cache[node] = self._coords(
                self.os.Geometry.GetNodeCoordinates(node)
            )
        return self._node_cache[node]

    def member_released_at_end(self, member_id: int, end: int) -> bool:
        """Return True when a release specification exists at an end.

        OpenSTAAD can raise ``[-1] General error`` when the requested member
        end has no release record. For DJ chain tracing, that condition means
        the end is unreleased and must not stop generation.
        """
        if self.os is None:
            raise RuntimeError("STAAD.Pro is not connected.")
        if end not in (0, 1):
            raise ValueError("Member end must be 0 for START or 1 for END.")

        try:
            result = self.os.Property.GetMemberReleaseSpec(
                int(member_id),
                int(end),
            )
        except Exception as exc:
            message = str(exc).casefold()
            if "general error" in message or "[-1]" in message:
                return False
            raise RuntimeError(
                f"Could not read release specification for member "
                f"{member_id}, end {end}: {exc}"
            ) from exc

        if not isinstance(result, (tuple, list)) or len(result) < 1:
            return False

        release_values = result[0]
        if not isinstance(release_values, (tuple, list)):
            return False

        for value in release_values:
            try:
                if int(value) != 0:
                    return True
            except (TypeError, ValueError):
                continue

        return False


class BaseGenerator:
    def __init__(self, service: StaadService, max_line: int) -> None:
        self.s = service
        self.max_line = max_line

    @staticmethod
    def fmt(value: float) -> str:
        if abs(value - round(value)) < 1.0e-7:
            return str(int(round(value)))
        return f"{value:.4f}".rstrip("0").rstrip(".")

    @staticmethod
    def tokens(ids: Iterable[int]) -> list[str]:
        values = sorted(set(map(int, ids)))
        output: list[str] = []
        index = 0

        while index < len(values):
            end = index
            while (
                end + 1 < len(values)
                and values[end + 1] == values[end] + 1
            ):
                end += 1

            if end - index >= 2:
                output.append(f"{values[index]} TO {values[end]}")
            elif end - index == 1:
                output.extend((str(values[index]), str(values[end])))
            else:
                output.append(str(values[index]))

            index = end + 1

        return output

    def wrap(self, prefix: str, ids: Iterable[int]) -> list[str]:
        member_tokens = self.tokens(ids)
        if not member_tokens:
            return [f"* WARNING: No members for {prefix}"]

        lines: list[str] = []
        current = prefix

        for token in member_tokens:
            candidate = f"{current} {token}"
            if len(candidate) + 2 > self.max_line and current != prefix:
                lines.append(current + " -")
                current = token
            else:
                current = candidate

        lines.append(current)
        return lines

    @staticmethod
    def require_value(parameter: Parameter) -> float:
        if (
            parameter.value is None
            or not math.isfinite(float(parameter.value))
        ):
            raise ValueError(f"{parameter.name} requires a numeric value.")
        return float(parameter.value)


class ConcreteGenerator(BaseGenerator):
    VALUELESS = {"DESIGN BEAM", "DESIGN COLUMN"}
    ALL = {
        "FC",
        "FYMAIN",
        "FYSEC",
        "MAXMAIN",
        "MAXSEC",
        "MINMAIN",
        "MINSEC",
        "TRACK",
    }
    BEAM = {
        "CLEAR (BEAMS)",
        "BRACE",
        "PLASTIC",
        "TORSION",
        "GLD",
        "DESIGN BEAM",
    }
    COLUMN = {
        "CLEAR (COLUMNS)",
        "RATIO",
        "BRACE (COLUMNS)",
        "RFACE",
        "REINF",
        "DESIGN COLUMN",
    }
    EL = {"ELY", "ELZ", "ULY", "ULZ"}

    def ids(self, scope: str) -> list[int]:
        return [
            member.member_id
            for member in self.s.members
            if member.concrete
            and (
                scope == "ALL"
                or scope == "BEAM" and (member.beam_x or member.beam_z)
                or scope == "COLUMN" and member.column_y
            )
        ]

    def generate(
        self,
        parameters: list[Parameter],
        comments: bool,
    ) -> str:
        blocks: list[str] = []

        for parameter in parameters:
            if not parameter.enabled:
                continue

            name = parameter.name.upper().strip()

            if name in self.ALL:
                value = self.require_value(parameter)
                if name in {"FC", "FYMAIN", "FYSEC"}:
                    value *= 1000.0

                blocks.append(
                    "\n".join(
                        self.wrap(
                            f"{name} {self.fmt(value)} MEMB",
                            self.ids("ALL"),
                        )
                    )
                )

            elif name in self.BEAM or name in self.COLUMN:
                scope = "BEAM" if name in self.BEAM else "COLUMN"
                command = (
                    "CLEAR"
                    if name.startswith("CLEAR")
                    else "BRACE"
                    if name.startswith("BRACE")
                    else name
                )

                if name in self.VALUELESS:
                    prefix = command
                else:
                    prefix = (
                        f"{command} "
                        f"{self.fmt(self.require_value(parameter))} MEMB"
                    )

                blocks.append(
                    "\n".join(self.wrap(prefix, self.ids(scope)))
                )

            elif name in self.EL:
                blocks.append(
                    "\n".join(
                        self._generate_el(
                            name,
                            self.require_value(parameter),
                            comments,
                        )
                    )
                )

            else:
                blocks.append(
                    f"* WARNING: No concrete generator defined for {name}"
                )

        return "\n\n".join(blocks).rstrip() + "\n"

    def _trace_column(
        self,
        base_node: int,
    ) -> tuple[list[int], list[int]]:
        chain: list[int] = []
        nodes = [base_node]
        used: set[int] = set()
        current = base_node

        while True:
            _, y0, _ = self.s.node_coords(current)
            candidates: list[tuple[float, int, int]] = []

            for index in self.s.by_node.get(current, []):
                if index in used:
                    continue

                member = self.s.members[index]
                if not (member.concrete and member.column_y):
                    continue

                other = (
                    member.end_node
                    if member.start_node == current
                    else member.start_node
                )
                _, y1, _ = self.s.node_coords(other)

                if y1 - y0 > 1.0e-7:
                    candidates.append((y1 - y0, index, other))

            if not candidates:
                break

            _, index, current = max(
                candidates,
                key=lambda value: (
                    value[0],
                    -self.s.members[value[1]].member_id,
                ),
            )
            used.add(index)
            chain.append(index)
            nodes.append(current)

        return chain, nodes

    def _has_restraint(
        self,
        node: int,
        use_x: bool,
        chain: set[int],
    ) -> bool:
        return any(
            index not in chain
            and self.s.members[index].concrete
            and (
                use_x and self.s.members[index].beam_x
                or not use_x and self.s.members[index].beam_z
            )
            for index in self.s.by_node.get(node, [])
        )

    def _has_upward_steel(
        self,
        node: int,
        chain: set[int],
    ) -> bool:
        _, y0, _ = self.s.node_coords(node)

        for index in self.s.by_node.get(node, []):
            if index in chain:
                continue

            member = self.s.members[index]
            if not (member.steel and member.column_y):
                continue

            other = (
                member.end_node
                if member.start_node == node
                else member.start_node
            )
            if self.s.node_coords(other)[1] - y0 > 1.0e-7:
                return True

        return False

    def _generate_el(
        self,
        name: str,
        multiplier: float,
        comments: bool,
    ) -> list[str]:
        if multiplier <= 0:
            raise ValueError(
                f"{name} multiplication factor must be greater than zero."
            )

        use_x = name in {"ELY", "ULY"}
        lines: list[str] = []
        seen: set[int] = set()
        supports = self.s.support_nodes()

        if not supports:
            raise RuntimeError(
                "No supports were found in the active STAAD model."
            )

        for support in supports:
            chain, nodes = self._trace_column(support)
            if not chain:
                continue

            chain_set = set(chain)
            restraints = [True] + [
                self._has_restraint(nodes[position], use_x, chain_set)
                for position in range(1, len(chain) + 1)
            ]

            if self._has_upward_steel(nodes[-1], chain_set):
                restraints[-1] = True

            start = 0
            while start < len(chain):
                end = next(
                    (
                        position
                        for position in range(start + 1, len(chain) + 1)
                        if restraints[position]
                    ),
                    None,
                )

                if end is None:
                    break

                restraint_length = sum(
                    self.s.members[chain[position - 1]].length
                    for position in range(start + 1, end + 1)
                )

                for position in range(start + 1, end + 1):
                    member = self.s.members[chain[position - 1]]
                    result = (
                        math.ceil(
                            (
                                multiplier
                                * restraint_length
                                / member.length
                                - 1.0e-12
                            )
                            * 100
                        )
                        / 100
                    )

                    if member.member_id in seen:
                        continue

                    seen.add(member.member_id)

                    if comments:
                        lines.append(
                            f"*{name} = {self.fmt(multiplier)} * "
                            f"{self.fmt(restraint_length)} / "
                            f"{self.fmt(member.length)} = "
                            f"{self.fmt(result)}"
                        )

                    lines.append(
                        f"{name} {self.fmt(result)} MEMB {member.member_id}"
                    )

                start = end

        return lines or [
            f"* WARNING: No eligible concrete columns for {name}"
        ]


class SteelGenerator(BaseGenerator):
    VALUELESS = {
        "CHECK CODE",
        "SELECT MEMBER",
        "DESIGN JOINT",
        "DJ",
        "DJ STUB COLUMNS",
    }
    DJ_NAMES = {"DESIGN JOINT", "DJ"}
    STUB_DJ_NAMES = {"DJ STUB COLUMNS"}

    def generate(
        self,
        parameters: list[Parameter],
        comments: bool = True,
    ) -> str:
        steel_ids = [
            member.member_id
            for member in self.s.members
            if member.steel
        ]
        blocks: list[str] = []

        for parameter in parameters:
            if not parameter.enabled:
                continue

            name = parameter.name.upper().strip()

            if name in self.DJ_NAMES:
                blocks.append(self._generate_design_joints(comments))
            elif name in self.STUB_DJ_NAMES:
                blocks.append(self._generate_stub_column_joints(comments))
            elif name == "CHECK CODE":
                blocks.append(
                    "\n".join(
                        self.wrap("CHECK CODE MEMB", steel_ids)
                    )
                )
            elif name == "SELECT MEMBER":
                blocks.append(
                    "\n".join(
                        self.wrap("SELECT MEMBER", steel_ids)
                    )
                )
            else:
                value = self.require_value(parameter)
                blocks.append(
                    "\n".join(
                        self.wrap(
                            f"{name} {self.fmt(value)} MEMB",
                            steel_ids,
                        )
                    )
                )

        return "\n\n".join(blocks).rstrip() + "\n"

    def _generate_stub_column_joints(self, comments: bool) -> str:
        all_vertical = {
            index: member
            for index, member in enumerate(self.s.members)
            if self._is_vertical_member(member)
        }
        eligible = {
            index: member
            for index, member in all_vertical.items()
            if member.steel
        }

        if not eligible:
            return (
                "* WARNING: No eligible vertical steel members were found "
                "for DJ STUB COLUMNS"
            )

        main_nodes = self._main_column_nodes(all_vertical)
        adjacency: dict[int, list[int]] = {}
        for index, member in eligible.items():
            adjacency.setdefault(member.start_node, []).append(index)
            adjacency.setdefault(member.end_node, []).append(index)

        for connected in adjacency.values():
            connected.sort(key=lambda index: eligible[index].member_id)

        release_start: dict[int, bool] = {}
        release_end: dict[int, bool] = {}
        for index, member in eligible.items():
            release_start[index] = self.s.member_released_at_end(
                member.member_id, 0
            )
            release_end[index] = self.s.member_released_at_end(
                member.member_id, 1
            )

        seen: set[int] = set()
        chains: list[DJStubChain] = []

        for seed_index in sorted(
            eligible,
            key=lambda index: eligible[index].member_id,
        ):
            if seed_index in seen:
                continue

            seed = eligible[seed_index]
            seen.add(seed_index)
            chain_indices = [seed_index]

            forward = self._extend_stub_chain(
                adjacency=adjacency,
                member_by_index=eligible,
                release_start=release_start,
                release_end=release_end,
                seen=seen,
                chain_indices=chain_indices,
                previous_node=seed.start_node,
                current_node=seed.end_node,
            )
            backward = self._extend_stub_chain(
                adjacency=adjacency,
                member_by_index=eligible,
                release_start=release_start,
                release_end=release_end,
                seen=seen,
                chain_indices=chain_indices,
                previous_node=seed.end_node,
                current_node=seed.start_node,
            )

            if len(chain_indices) <= 1:
                continue

            terminal_forward, release_forward, ambiguous_forward = forward
            terminal_backward, release_backward, ambiguous_backward = backward
            y_forward = self.s.node_coords(terminal_forward)[1]
            y_backward = self.s.node_coords(terminal_backward)[1]

            if y_backward <= y_forward:
                bottom_node = terminal_backward
                top_node = terminal_forward
                release_bottom = release_backward
                release_top = release_forward
                ambiguous_bottom = ambiguous_backward
                ambiguous_top = ambiguous_forward
                y_bottom = y_backward
                y_top = y_forward
            else:
                bottom_node = terminal_forward
                top_node = terminal_backward
                release_bottom = release_forward
                release_top = release_backward
                ambiguous_bottom = ambiguous_forward
                ambiguous_top = ambiguous_backward
                y_bottom = y_forward
                y_top = y_backward

            # A chain touching the support-traced vertical system is a main
            # column, not a stub column.
            if bottom_node in main_nodes or top_node in main_nodes:
                continue

            chains.append(
                DJStubChain(
                    bottom_node=bottom_node,
                    top_node=top_node,
                    base_elevation=round(
                        self.s.length_to_meters(y_bottom),
                        DJ_ELEVATION_ROUND,
                    ),
                    top_elevation=round(
                        self.s.length_to_meters(y_top),
                        DJ_ELEVATION_ROUND,
                    ),
                    member_ids=sorted(
                        eligible[index].member_id
                        for index in chain_indices
                    ),
                    release_dj1=release_bottom,
                    release_dj2=release_top,
                    ambiguous_dj1=ambiguous_bottom,
                    ambiguous_dj2=ambiguous_top,
                )
            )

        if not chains:
            return (
                "* WARNING: No multi-member steel stub-column chains "
                "were found for DJ"
            )

        chains.sort(
            key=lambda chain: (
                chain.base_elevation,
                chain.top_elevation,
                chain.bottom_node,
                chain.top_node,
            )
        )
        return self._format_stub_dj_output(chains, comments)

    @staticmethod
    def _is_vertical_member(member: Member) -> bool:
        return member.column_y

    def _main_column_nodes(
        self,
        vertical_members: dict[int, Member],
    ) -> set[int]:
        adjacency: dict[int, list[int]] = {}
        for index, member in vertical_members.items():
            adjacency.setdefault(member.start_node, []).append(index)
            adjacency.setdefault(member.end_node, []).append(index)

        main_nodes = set(self.s.support_nodes())
        queue = list(main_nodes)
        head = 0

        while head < len(queue):
            node = queue[head]
            head += 1
            node_y = self.s.node_coords(node)[1]

            for index in adjacency.get(node, []):
                member = vertical_members[index]
                other = self._other_node(member, node)
                if other is None or other in main_nodes:
                    continue
                if self.s.node_coords(other)[1] <= node_y + 1.0e-9:
                    continue
                main_nodes.add(other)
                queue.append(other)

        return main_nodes

    def _extend_stub_chain(
        self,
        *,
        adjacency: dict[int, list[int]],
        member_by_index: dict[int, Member],
        release_start: dict[int, bool],
        release_end: dict[int, bool],
        seen: set[int],
        chain_indices: list[int],
        previous_node: int,
        current_node: int,
    ) -> tuple[int, bool, bool]:
        release_boundary = False
        ambiguous_boundary = False

        while True:
            current_member = self._find_chain_member_at_end(
                chain_indices,
                member_by_index,
                previous_node,
                current_node,
            )
            if (
                current_member is not None
                and self._released_at_node(
                    current_member,
                    current_node,
                    member_by_index,
                    release_start,
                    release_end,
                )
            ):
                release_boundary = True
                break

            candidates: list[tuple[float, int, int]] = []
            release_candidate_found = False

            for candidate_index in adjacency.get(current_node, []):
                if candidate_index in seen:
                    continue

                candidate = member_by_index[candidate_index]
                other_node = self._other_node(candidate, current_node)
                if other_node is None:
                    continue

                if self._released_at_node(
                    candidate_index,
                    current_node,
                    member_by_index,
                    release_start,
                    release_end,
                ):
                    release_candidate_found = True
                    continue

                dot = self._continuation_dot_product(
                    previous_node,
                    current_node,
                    other_node,
                )
                if dot >= DJ_COLLINEAR_DOT_MIN:
                    candidates.append(
                        (dot, candidate.member_id, candidate_index)
                    )

            if len(candidates) > 1:
                ambiguous_boundary = True

            if not candidates:
                if release_candidate_found:
                    release_boundary = True
                break

            # Straightest continuation first, then lowest actual member ID.
            candidates.sort(key=lambda item: (-item[0], item[1]))
            _, _, selected_index = candidates[0]
            selected = member_by_index[selected_index]
            selected_other = self._other_node(selected, current_node)
            if selected_other is None:
                break

            seen.add(selected_index)
            chain_indices.append(selected_index)
            previous_node = current_node
            current_node = selected_other

        return current_node, release_boundary, ambiguous_boundary

    def _format_stub_dj_output(
        self,
        chains: list[DJStubChain],
        comments: bool,
    ) -> str:
        lines: list[str] = []
        previous_group: Optional[tuple[float, float]] = None

        for chain in chains:
            group = (chain.base_elevation, chain.top_elevation)
            if comments and group != previous_group:
                if lines:
                    lines.append("")
                lines.append(
                    "*------------------ "
                    f"EL. {self._format_elevation(chain.base_elevation)} to "
                    f"{self._format_elevation(chain.top_elevation)} "
                    "METER - Stub Columns ------------------"
                )
                previous_group = group

            lines.extend(
                self.wrap(
                    f"DJ1 {chain.bottom_node} MEMB",
                    chain.member_ids,
                )
            )
            lines.extend(
                self.wrap(
                    f"DJ2 {chain.top_node} MEMB",
                    chain.member_ids,
                )
            )

        diagnostics = self._format_stub_diagnostics(chains)
        if diagnostics:
            lines.extend(["", ""])
            lines.extend(diagnostics)
        return "\n".join(lines)

    def _format_stub_diagnostics(
        self,
        chains: list[DJStubChain],
    ) -> list[str]:
        one_sided = [
            chain
            for chain in chains
            if chain.release_dj1 != chain.release_dj2
        ]
        ambiguous = [
            chain
            for chain in chains
            if chain.ambiguous_dj1 or chain.ambiguous_dj2
        ]
        if not one_sided and not ambiguous:
            return []

        lines = [
            "*=======================================================================",
            "* DJ STUB-COLUMN DIAGNOSTIC REVIEW",
            "*=======================================================================",
        ]

        if one_sided:
            lines.extend([
                "",
                f"* {len(one_sided)} chain(s) have a release at only one end",
            ])
            for chain in one_sided:
                location = "DJ1" if chain.release_dj1 else "DJ2"
                lines.append(
                    f"* RELEASE ONLY AT {location}: "
                    f"DJ1 {chain.bottom_node}, DJ2 {chain.top_node}"
                )
                lines.extend(self._wrap_comment_members(chain.member_ids))

        if ambiguous:
            lines.extend([
                "",
                f"* {len(ambiguous)} chain(s) passed an ambiguous intersection",
            ])
            for chain in ambiguous:
                lines.append(
                    f"* AMBIGUOUS: DJ1 {chain.bottom_node}, "
                    f"DJ2 {chain.top_node}"
                )
                lines.extend(self._wrap_comment_members(chain.member_ids))

        return lines

    def _generate_design_joints(self, comments: bool) -> str:
        eligible = self._eligible_dj_members()

        if not eligible:
            return (
                "* WARNING: No eligible horizontal steel members "
                "were found for DJ"
            )

        adjacency: dict[int, list[int]] = {}
        for index, member in eligible.items():
            adjacency.setdefault(member.start_node, []).append(index)
            adjacency.setdefault(member.end_node, []).append(index)

        release_start: dict[int, bool] = {}
        release_end: dict[int, bool] = {}
        for index, member in eligible.items():
            release_start[index] = self.s.member_released_at_end(
                member.member_id,
                0,
            )
            release_end[index] = self.s.member_released_at_end(
                member.member_id,
                1,
            )

        seen: set[int] = set()
        chains: list[DJChain] = []

        for seed_index in sorted(
            eligible,
            key=lambda index: eligible[index].member_id,
        ):
            if seed_index in seen:
                continue

            seed = eligible[seed_index]
            direction = self._dj_direction(seed)
            if direction is None:
                continue

            seen.add(seed_index)
            chain_indices = [seed_index]

            (
                terminal_forward,
                release_forward,
                ambiguous_forward,
            ) = self._extend_dj_chain(
                adjacency=adjacency,
                member_by_index=eligible,
                release_start=release_start,
                release_end=release_end,
                seen=seen,
                chain_indices=chain_indices,
                previous_node=seed.start_node,
                current_node=seed.end_node,
                chain_direction=direction,
            )

            (
                terminal_backward,
                release_backward,
                ambiguous_backward,
            ) = self._extend_dj_chain(
                adjacency=adjacency,
                member_by_index=eligible,
                release_start=release_start,
                release_end=release_end,
                seen=seen,
                chain_indices=chain_indices,
                previous_node=seed.end_node,
                current_node=seed.start_node,
                chain_direction=direction,
            )

            if len(chain_indices) <= 1:
                continue

            member_ids = sorted(
                eligible[index].member_id
                for index in chain_indices
            )
            raw_elevation = self.s.node_coords(terminal_backward)[1]
            elevation = round(
                self.s.length_to_meters(raw_elevation),
                DJ_ELEVATION_ROUND,
            )

            chains.append(
                DJChain(
                    start_node=terminal_backward,
                    end_node=terminal_forward,
                    direction=direction,
                    elevation=elevation,
                    member_ids=member_ids,
                    release_dj1=release_backward,
                    release_dj2=release_forward,
                    ambiguous_dj1=ambiguous_backward,
                    ambiguous_dj2=ambiguous_forward,
                )
            )

        if not chains:
            return (
                "* WARNING: No multi-span eligible steel beam "
                "chains were found for DJ"
            )

        chains.sort(
            key=lambda chain: (
                chain.elevation,
                0 if chain.direction == "X" else 1,
                chain.start_node,
                chain.end_node,
            )
        )

        return self._format_dj_output(chains, comments)

    def _eligible_dj_members(self) -> dict[int, Member]:
        return {
            index: member
            for index, member in enumerate(self.s.members)
            if member.steel and self._dj_direction(member) is not None
        }

    def _dj_direction(self, member: Member) -> Optional[str]:
        x1, y1, z1 = self.s.node_coords(member.start_node)
        x2, y2, z2 = self.s.node_coords(member.end_node)

        dx = x2 - x1
        dy = y2 - y1
        dz = z2 - z1
        length = math.sqrt(dx * dx + dy * dy + dz * dz)

        if length <= 1.0e-12:
            return None
        if abs(dy) / length > DJ_HORIZONTAL_TOL:
            return None
        if abs(dx) > 1.0e-12 and abs(dz) / length <= DJ_DIRECTION_TOL:
            return "X"
        if abs(dz) > 1.0e-12 and abs(dx) / length <= DJ_DIRECTION_TOL:
            return "Z"
        return None

    def _extend_dj_chain(
        self,
        *,
        adjacency: dict[int, list[int]],
        member_by_index: dict[int, Member],
        release_start: dict[int, bool],
        release_end: dict[int, bool],
        seen: set[int],
        chain_indices: list[int],
        previous_node: int,
        current_node: int,
        chain_direction: str,
    ) -> tuple[int, bool, bool]:
        release_boundary = False
        ambiguous_boundary = False
        terminal_node = current_node

        while True:
            terminal_node = current_node
            current_member_index = self._find_chain_member_at_end(
                chain_indices,
                member_by_index,
                previous_node,
                current_node,
            )

            if (
                current_member_index is not None
                and self._released_at_node(
                    current_member_index,
                    current_node,
                    member_by_index,
                    release_start,
                    release_end,
                )
            ):
                release_boundary = True
                break

            selected_index: Optional[int] = None
            selected_other_node: Optional[int] = None
            best_dot = -2.0
            valid_candidate_count = 0
            release_candidate_found = False

            for candidate_index in adjacency.get(current_node, []):
                if candidate_index in seen:
                    continue

                candidate = member_by_index[candidate_index]
                if self._dj_direction(candidate) != chain_direction:
                    continue

                other_node = self._other_node(candidate, current_node)
                if other_node is None:
                    continue

                if self._released_at_node(
                    candidate_index,
                    current_node,
                    member_by_index,
                    release_start,
                    release_end,
                ):
                    release_candidate_found = True
                    continue

                candidate_dot = self._continuation_dot_product(
                    previous_node,
                    current_node,
                    other_node,
                )
                if candidate_dot < DJ_COLLINEAR_DOT_MIN:
                    continue

                valid_candidate_count += 1

                if selected_index is None:
                    selected_index = candidate_index
                    selected_other_node = other_node
                    best_dot = candidate_dot
                elif candidate_dot > best_dot + DJ_DOT_EQUAL_TOL:
                    selected_index = candidate_index
                    selected_other_node = other_node
                    best_dot = candidate_dot
                elif (
                    abs(candidate_dot - best_dot) <= DJ_DOT_EQUAL_TOL
                    and candidate.member_id
                    < member_by_index[selected_index].member_id
                ):
                    selected_index = candidate_index
                    selected_other_node = other_node
                    best_dot = candidate_dot

            if valid_candidate_count > 1:
                ambiguous_boundary = True

            if selected_index is None or selected_other_node is None:
                if release_candidate_found:
                    release_boundary = True
                break

            seen.add(selected_index)
            chain_indices.append(selected_index)
            previous_node = current_node
            current_node = selected_other_node

        return terminal_node, release_boundary, ambiguous_boundary

    @staticmethod
    def _find_chain_member_at_end(
        chain_indices: list[int],
        member_by_index: dict[int, Member],
        previous_node: int,
        current_node: int,
    ) -> Optional[int]:
        for index in chain_indices:
            member = member_by_index[index]
            if (
                member.start_node == previous_node
                and member.end_node == current_node
            ) or (
                member.start_node == current_node
                and member.end_node == previous_node
            ):
                return index
        return None

    @staticmethod
    def _other_node(
        member: Member,
        common_node: int,
    ) -> Optional[int]:
        if member.start_node == common_node:
            return member.end_node
        if member.end_node == common_node:
            return member.start_node
        return None

    @staticmethod
    def _released_at_node(
        member_index: int,
        node: int,
        member_by_index: dict[int, Member],
        release_start: dict[int, bool],
        release_end: dict[int, bool],
    ) -> bool:
        member = member_by_index[member_index]
        if member.start_node == node:
            return release_start.get(member_index, False)
        if member.end_node == node:
            return release_end.get(member_index, False)
        return False

    def _continuation_dot_product(
        self,
        previous_node: int,
        current_node: int,
        next_node: int,
    ) -> float:
        px, py, pz = self.s.node_coords(previous_node)
        cx, cy, cz = self.s.node_coords(current_node)
        nx, ny, nz = self.s.node_coords(next_node)

        ax, ay, az = cx - px, cy - py, cz - pz
        bx, by, bz = nx - cx, ny - cy, nz - cz

        length_a = math.sqrt(ax * ax + ay * ay + az * az)
        length_b = math.sqrt(bx * bx + by * by + bz * bz)

        if length_a <= 1.0e-12 or length_b <= 1.0e-12:
            return -2.0

        dot = (
            ax * bx + ay * by + az * bz
        ) / (length_a * length_b)
        return max(-1.0, min(1.0, dot))

    def _format_dj_output(
        self,
        chains: list[DJChain],
        comments: bool,
    ) -> str:
        lines: list[str] = []
        previous_group: Optional[tuple[float, str]] = None

        for chain in chains:
            group = (chain.elevation, chain.direction)

            if comments and group != previous_group:
                if lines:
                    lines.append("")
                direction_label = (
                    "X-Direction"
                    if chain.direction == "X"
                    else "Z-Direction"
                )
                lines.append(
                    "*------------------ "
                    f"EL. {self._format_elevation(chain.elevation)} "
                    f"METER {direction_label} "
                    "------------------"
                )
                previous_group = group

            lines.extend(
                self.wrap(
                    f"DJ1 {chain.start_node} MEMB",
                    chain.member_ids,
                )
            )
            lines.extend(
                self.wrap(
                    f"DJ2 {chain.end_node} MEMB",
                    chain.member_ids,
                )
            )

        diagnostic_lines = self._format_dj_diagnostics(chains)
        if diagnostic_lines:
            lines.extend(["", ""])
            lines.extend(diagnostic_lines)

        return "\n".join(lines)

    def _format_dj_diagnostics(
        self,
        chains: list[DJChain],
    ) -> list[str]:
        one_sided = [
            chain
            for chain in chains
            if chain.release_dj1 != chain.release_dj2
        ]
        ambiguous = [
            chain
            for chain in chains
            if chain.ambiguous_dj1 or chain.ambiguous_dj2
        ]

        if not one_sided and not ambiguous:
            return []

        lines = [
            "*=======================================================================",
            "* DJ CHAIN DIAGNOSTIC REVIEW",
            "*=======================================================================",
        ]

        if one_sided:
            lines.extend(
                [
                    "",
                    f"* {len(one_sided)} chain(s) have a release at only one end",
                ]
            )
            for chain in one_sided:
                location = "DJ1" if chain.release_dj1 else "DJ2"
                lines.append(
                    f"* RELEASE ONLY AT {location}: "
                    f"DJ1 {chain.start_node}, DJ2 {chain.end_node}"
                )
                lines.extend(
                    self._wrap_comment_members(chain.member_ids)
                )

        if ambiguous:
            lines.extend(
                [
                    "",
                    f"* {len(ambiguous)} chain(s) passed an ambiguous intersection",
                ]
            )
            for chain in ambiguous:
                lines.append(
                    f"* AMBIGUOUS: DJ1 {chain.start_node}, "
                    f"DJ2 {chain.end_node}"
                )
                lines.extend(
                    self._wrap_comment_members(chain.member_ids)
                )

        return lines

    def _wrap_comment_members(self, member_ids: Iterable[int]) -> list[str]:
        tokens = self.tokens(member_ids)
        prefix = "* MEMBERS:"
        lines: list[str] = []
        current = prefix

        for token in tokens:
            candidate = f"{current} {token}"
            if len(candidate) > self.max_line and current != prefix:
                lines.append(current)
                current = f"*   {token}"
            else:
                current = candidate

        lines.append(current)
        return lines

    @staticmethod
    def _format_elevation(elevation: float) -> str:
        text = f"{elevation:.{DJ_ELEVATION_ROUND}f}".rstrip("0")
        if text.endswith("."):
            text += "0"
        elif "." not in text:
            text += ".0"
        return text


