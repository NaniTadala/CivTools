"""Pure geometry planning shared by the preview and CAD execution."""
from dataclasses import dataclass
import math

MAX_NODES = 10000
MAX_BEAMS = 30000


@dataclass
class RackPlan:
    nodes: list
    beams: list
    foundations: list
    support_type: str

    @property
    def com_calls(self):
        return len(self.nodes) + len(self.beams) + len(self.foundations) + 1


def rack_size(config):
    """Validate and estimate before allocating geometry or connecting to CAD."""
    series = []
    for key, minimum in (("transverse_spacing", 2), ("longitudinal_spacing", 2),
                         ("trans_beam_elevations", 1), ("long_beam_elevations", 1)):
        values = config[key]
        if len(values) < minimum or any(not math.isfinite(v) for v in values) or any(a >= b for a, b in zip(values, values[1:])):
            raise ValueError(f"{key.replace('_', ' ')}: use finite, increasing values.")
        series.append(values)
    xs, zs, transverse, longitudinal = series
    base, depth = config["base_elevation"], config["foundation_depth"]
    if not math.isfinite(base) or not math.isfinite(depth) or depth <= 0:
        raise ValueError("Use a finite base elevation and a positive foundation depth.")
    if min(transverse[0], longitudinal[0]) <= base:
        raise ValueError("Beam elevations must be above the base elevation.")
    if config["support_type"] not in ("Fixed", "Pinned"):
        raise ValueError("Choose Fixed or Pinned supports.")
    nx, nz = len(xs), len(zs)
    tiers = len(set(transverse + longitudinal))
    brace_nodes = 2 * len(brace_bays(nz)) * len(transverse) if config.get("bracing_enabled") else 0
    nodes = nx * nz * (tiers + 2) + brace_nodes
    beams = nx * nz * (tiers + 1) + (nx - 1) * nz * len(transverse) + nx * (nz - 1) * len(longitudinal) + 2 * brace_nodes
    if nodes > MAX_NODES or beams > MAX_BEAMS:
        raise ValueError(f"Model too large: {nodes:,} nodes / {beams:,} beams. Use at most {MAX_NODES:,} nodes and {MAX_BEAMS:,} beams.")
    return nodes, beams, nodes + beams + nx * nz + 1


def build_rack_plan(config):
    rack_size(config)
    xs, zs = config["transverse_spacing"], config["longitudinal_spacing"]
    transverse, longitudinal = config["trans_beam_elevations"], config["long_beam_elevations"]
    base, depth = config["base_elevation"], config["foundation_depth"]
    levels = sorted(set(transverse + longitudinal))
    nodes, beams, foundations, lookup = [], [], [], {}

    def node(x, y, z):
        key = (x, y, z)
        if key not in lookup:
            lookup[key] = len(nodes)
            nodes.append(key)
        return lookup[key]

    def beam(a, b, kind):
        beams.append((a, b, kind))

    for x in xs:
        for z in zs:
            column = [node(x, y, z) for y in [base - depth, base] + levels]
            foundations.append(column[0])
            for a, b in zip(column, column[1:]):
                beam(a, b, "column")
    for y in transverse:
        for z in zs:
            for x1, x2 in zip(xs, xs[1:]):
                beam(node(x1, y, z), node(x2, y, z), "transverse")
    for y in longitudinal:
        for x in xs:
            for z1, z2 in zip(zs, zs[1:]):
                beam(node(x, y, z1), node(x, y, z2), "longitudinal")
    if config.get("bracing_enabled"):
        for bottom, top in zip([base] + transverse, transverse):
            for j in brace_bays(len(zs)):
                for x in (xs[0], xs[-1]):
                    mid = node(x, top, (zs[j] + zs[j + 1]) / 2)
                    beam(node(x, bottom, zs[j]), mid, "brace")
                    beam(node(x, bottom, zs[j + 1]), mid, "brace")
    return RackPlan(nodes, beams, foundations, config["support_type"])
def brace_bays(grid_count):
    if grid_count <= 2:
        return []
    if grid_count in (3, 4):
        return [1]
    return list(range(1 if grid_count % 2 == 0 else 2, grid_count - 1, 2))
