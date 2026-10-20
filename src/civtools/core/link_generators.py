"""Local generators with the input contracts observed in the dEZignLink client.

Server topology and numbering have not been recovered; these are independent
implementations. All operations here are pure and produce reviewable outputs.
"""
import math
from itertools import accumulate

from .geometry import RackPlan, MAX_NODES, MAX_BEAMS
from .staad_productivity import finite, positive_id, combination_commands


def spacings(text):
    values = [finite(v.strip(), 'Spacing', True) for v in text.split(',')]
    if len(values) > 500:
        raise ValueError('Use at most 500 spacings.')
    return values


def pipe_rack_plan(width, frames, spacing, tiers, longitudinal, support='Pinned'):
    width = finite(width, 'Width', True)
    spacing = finite(spacing, 'Frame spacing', True)
    frames = positive_id(frames)
    if not 2 <= frames <= 500:
        raise ValueError('Use between 2 and 500 frames.')
    if support not in ('Pinned', 'Fixed'):
        raise ValueError('Choose Pinned or Fixed supports.')
    ts = list(accumulate(spacings(tiers)))
    ls = list(accumulate(spacings(longitudinal)))
    if not math.isclose(ts[-1], ls[-1], rel_tol=1e-9, abs_tol=1e-8):
        raise ValueError('T and L spacings must reach the same total height.')
    # Merge floating point cumulative sums, retaining common connected joints.
    levels = sorted({round(y, 8) for y in [0., *ts, *ls]})
    ts, ls = [round(y, 8) for y in ts], [round(y, 8) for y in ls]
    if len(levels) != len(set(levels)) or min(levels[1:]) <= 0:
        raise ValueError('Spacings are too small to resolve.')
    count = 2 * frames * len(levels)
    beam_count = 2 * frames * (len(levels) - 1) + frames * len(ts) + 2 * (frames - 1) * len(ls)
    if count > MAX_NODES or beam_count > MAX_BEAMS:
        raise ValueError('Reduce the number of frames or tiers: model exceeds geometry limits.')
    nodes, beams, supports, lookup = [], [], [], {}
    for f in range(frames):
        for side, x in enumerate((0., width)):
            for y in levels:
                lookup[f, side, y] = len(nodes)
                nodes.append((x, y, f * spacing))
            supports.append(lookup[f, side, 0.])
            for a, b in zip(levels, levels[1:]):
                beams.append((lookup[f, side, a], lookup[f, side, b], 'column'))
        for y in ts:
            beams.append((lookup[f, 0, y], lookup[f, 1, y], 'transverse'))
        if f:
            for y in ls:
                for side in (0, 1):
                    beams.append((lookup[f - 1, side, y], lookup[f, side, y], 'longitudinal'))
    return RackPlan(nodes, beams, supports, support)


def matrix_contributions(rows):
    """Read the observed LOAD_COMB sheet contract (rows 2/3/4, factors row 5+)."""
    rows = [list(row) for row in rows]
    if len(rows) < 5 or len(rows) > 204 or max(map(len, rows), default=0) > 51:
        raise ValueError('Use the LOAD_COMB template: up to 50 cases and 200 combinations.')
    cases = []
    for col, value in enumerate(rows[1][1:], 1):
        if value is not None and str(value).strip():
            case = positive_id(value)
            symbol = str(rows[2][col] or case) if col < len(rows[2]) else str(case)
            cases.append((col, case, symbol))
    if not cases or len({c for _, c, _ in cases}) != len(cases):
        raise ValueError('Enter distinct primary load case numbers in row 2.')
    result = []
    for row in rows[4:]:
        if not any(v is not None and str(v).strip() for v in row):
            continue
        number = positive_id(row[0])
        contributions = []
        for col, case, symbol in cases:
            raw = row[col] if col < len(row) else None
            if raw is None or str(raw).strip() == '':
                continue
            value = finite(raw, 'Load factor')
            if value:
                contributions.append((case, value, symbol))
        if not contributions:
            raise ValueError(f'Combination {number} has no nonzero factors.')
        title = ' + '.join(f'{factor:g}{symbol}' for _, factor, symbol in contributions)
        result.extend((number, title, case, factor) for case, factor, _ in contributions)
    # Validate all IDs, duplicate rows and factors through the command generator.
    combination_commands(result)
    return result
