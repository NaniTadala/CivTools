"""Connected PEB frame geometry and standalone STAAD geometry files."""
from dataclasses import dataclass
import math

from .geometry import RackPlan, MAX_NODES, MAX_BEAMS
from .staad_productivity import finite, positive_id, fmt, continued


@dataclass(frozen=True)
class PebConfig:
    variant: str = 'A'
    width: float = 20
    eave_height: float = 6
    ridge_height: float = 9
    frames: int = 4
    frame_spacing: float = 6
    tie_spacing: float = 3
    purlin_spacing: float = 1.5
    inner_left: float = 5
    inner_right: float = 5
    unit: str = 'METER'
    support: str = 'Pinned'


def build_peb_plan(config):
    c = config
    for name in ('width', 'eave_height', 'ridge_height', 'frame_spacing', 'tie_spacing', 'purlin_spacing'):
        finite(getattr(c, name), name.replace('_', ' '), True)
    frames = positive_id(c.frames)
    if c.variant not in 'ABCD' or len(c.variant) != 1 or frames < 2 or frames > 500:
        raise ValueError('Choose PEB A/B/C/D and between 2 and 500 frames.')
    if c.ridge_height <= c.eave_height:
        raise ValueError('Ridge / high-side height must exceed eave / low-side height.')
    if c.unit not in ('METER', 'INCHES') or c.support not in ('Pinned', 'Fixed'):
        raise ValueError('Choose METER/INCHES and Pinned/Fixed supports.')
    columns = [0., c.width]
    if c.variant == 'B':
        columns.insert(1, c.width / 2)
    elif c.variant == 'C':
        for v in (c.inner_left, c.inner_right):
            if not 0 < finite(v, 'Internal column spacing', True) < c.width / 2:
                raise ValueError('Internal column spacings must each be less than half the width.')
        columns = [0., c.inner_left, c.width - c.inner_right, c.width]

    def height(x):
        if c.variant == 'D':
            return c.eave_height + (c.ridge_height - c.eave_height) * x / c.width
        return c.ridge_height - (c.ridge_height - c.eave_height) * abs(x - c.width / 2) / (c.width / 2)

    corners = [0., c.width] if c.variant == 'D' else [0., c.width / 2, c.width]
    roof_xs = set(columns + corners)
    # Bound intervals before allocating. Very small spacings must fail cheaply.
    for a, b in zip(corners, corners[1:]):
        intervals = math.ceil(math.hypot(b - a, height(b) - height(a)) / c.purlin_spacing)
        if intervals * frames > MAX_NODES:
            raise ValueError('Purlin spacing creates too many nodes.')
        roof_xs.update(a + (b - a) * i / intervals for i in range(intervals + 1))
    roof_xs = sorted(roof_xs)
    levels = {}
    for x in columns:
        intervals = math.ceil(height(x) / c.tie_spacing)
        if intervals * frames > MAX_NODES:
            raise ValueError('Tie spacing creates too many nodes.')
        levels[x] = [height(x) * i / intervals for i in range(intervals + 1)]
    if frames * (len(roof_xs) + sum(len(ys) - 1 for ys in levels.values())) > MAX_NODES:
        raise ValueError('PEB exceeds the 10,000-node limit.')
    nodes, beams, supports, lookup, edges = [], [], [], {}, set()

    def node(x, y, z):
        key = tuple(round(v, 10) for v in (x, y, z))
        if key not in lookup:
            lookup[key] = len(nodes)
            nodes.append((x, y, z))
        return lookup[key]

    def beam(a, b, kind):
        key = tuple(sorted((a, b)))
        if a == b:
            raise ValueError('Spacing is too small to resolve separate nodes.')
        if key not in edges:
            edges.add(key)
            beams.append((a, b, kind))
            if len(beams) > MAX_BEAMS:
                raise ValueError('PEB exceeds the 30,000-member limit.')

    for frame in range(frames):
        z = frame * c.frame_spacing
        for x in columns:
            column = [node(x, y, z) for y in levels[x]]
            supports.append(column[0])
            for a, b in zip(column, column[1:]):
                beam(a, b, 'column')
        roof = [node(x, height(x), z) for x in roof_xs]
        for a, b in zip(roof, roof[1:]):
            beam(a, b, 'rafter')
        if frame:
            prev = (frame - 1) * c.frame_spacing
            for x in roof_xs:
                beam(node(x, height(x), prev), node(x, height(x), z), 'purlin')
            for x in columns:
                for y in levels[x][1:]:
                    beam(node(x, y, prev), node(x, y, z), 'tie')
    return RackPlan(nodes, beams, supports, c.support)


def geometry_commands(plan, unit='METER'):
    if unit not in ('METER', 'INCHES'):
        raise ValueError('Geometry unit must be METER or INCHES.')
    lines = ['STAAD SPACE', '* CivTools geometry only: assign materials, sections, bracing and loads.',
             '* Validate stability and connectivity before analysis.',
             'UNIT ' + unit + (' KN' if unit == 'METER' else ' KIP'), 'JOINT COORDINATES']
    for i, xyz in enumerate(plan.nodes, 1):
        lines.append(f'{i} ' + ' '.join(map(fmt, xyz)))
    lines.append('MEMBER INCIDENCES')
    groups = {}
    for i, (a, b, kind) in enumerate(plan.beams, 1):
        lines.append(f'{i} {a + 1} {b + 1}')
        groups.setdefault(kind, []).append(i)
    lines.extend(['START GROUP DEFINITION', 'MEMBER'])
    for kind, ids in groups.items():
        lines.extend(continued('_CIV_' + kind.upper(), ids))
    lines.extend(['END GROUP DEFINITION', 'SUPPORTS'])
    lines.extend(continued('', [n + 1 for n in plan.foundations], plan.support_type.upper()))
    return '\n'.join(lines + ['FINISH', ''])
