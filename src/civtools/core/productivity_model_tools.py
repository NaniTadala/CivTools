"""Local counterparts of the guide's Renum, Groups and Releases tools.

The guide describes behavior, not its remote classification algorithm. Plans
here use the same support-connected classifications as the local Select tool.
No function contacts Dezign Link or changes a model without an apply call.
"""
from collections import defaultdict
from bisect import bisect_left
from dataclasses import dataclass
import math
from pathlib import Path
import re

from . import staad_productivity_com as live
from .results import OperationResult
from .staad_productivity import (CATEGORIES, DOFS, classify_members, continued,
                                 finite, positive_id, release_commands)


def _categories(model, categories=None):
    result = dict(categories if categories is not None else
                  classify_members(model, overrides=model.classifications))
    if set(result) != set(model.members) or set(result.values()) - set(CATEGORIES):
        raise ValueError('Process the complete model before continuing.')
    return result


def _levels(values, tolerance):
    result = []
    for value in sorted(values):
        if not result or value - result[-1] > tolerance:
            result.append(value)
    return result


def _level_index(levels, value):
    insertion = bisect_left(levels, value)
    candidates = {max(0, insertion - 1), min(insertion, len(levels) - 1)}
    return min(candidates, key=lambda i: abs(levels[i] - value))


def _floor(model, mid):
    return max(model.nodes[n][1] for n in model.members[mid])


def floor_renumber_plan(model, floor_block=1000, categories=None, tolerance=.001):
    """Map every member into ascending floor/category bands.

    At the default block size, first-floor beams start at 1001, columns at
    1501, braces at 1751 and roof/other slopes at 1901. Following floors start
    at 2001/2501/etc. A block of 100 uses 101/151/176/191. Reject crowded
    bands rather than overflowing into another category or floor.
    """
    floor_block = positive_id(floor_block)
    if floor_block not in (100, 1000, 10000):
        raise ValueError('Choose floor blocks of 100, 1000 or 10000.')
    tolerance = finite(tolerance, 'Level tolerance', True)
    categories = _categories(model, categories)
    levels = _levels((_floor(model, mid) for mid in model.members), tolerance)
    bands = defaultdict(list)
    for mid, category in categories.items():
        floor = _level_index(levels, _floor(model, mid)) + 1
        band = (1 if category == 'Columns' else
                2 if category in ('Plan diagonals', 'Vertical bracing', 'Rafter bracing') else
                3 if category in ('Sloping members', 'Rafters') else 0)
        bands[floor, band].append(mid)
    offsets = (0, floor_block // 2, floor_block * 3 // 4, floor_block * 9 // 10, floor_block)
    ranks = {category: i for i, category in enumerate(CATEGORIES)}
    def order(mid):
        points = [model.nodes[n] for n in model.members[mid]]
        center = tuple(sum(p[i] for p in points) / 2 for i in range(3))
        return ranks[categories[mid]], center[2], center[0], center[1], mid
    mapping = {}
    for (floor, band), ids in sorted(bands.items()):
        if len(ids) > offsets[band + 1] - offsets[band]:
            raise ValueError(f'Floor {floor} has too many members in one numbering band. Choose a larger floor block.')
        for index, mid in enumerate(sorted(ids, key=order), 1):
            mapping[mid] = positive_id(floor * floor_block + offsets[band] + index)
    if len(set(mapping.values())) != len(mapping):
        raise ValueError('Floor numbering contains duplicate IDs.')
    return mapping


def apply_floor_renumber(expected, report, floor_block=1000, categories=None):
    return live.apply_renumber(expected, floor_renumber_plan(expected, floor_block, categories), report)


@dataclass(frozen=True)
class GroupDefinition:
    kind: int
    name: str
    ids: tuple


_GROUP_CODES = ('CND', 'MEM', 'FLR', 'COL', 'PLN_BRC', 'PRI_BM', 'SEC_TER_BM', 'VER_BRC', 'RAFTER', 'RAF_BRC')


def _group_prefix(prefix):
    if not re.fullmatch(r'_[A-Za-z][A-Za-z0-9_]{0,11}', prefix):
        raise ValueError('Use an underscore followed by 1–12 letters, digits or underscores for the group prefix.')
    return prefix


def is_generated_group(name, prefix='_RB'):
    """Only our exact documented names belong to the replaceable namespace."""
    prefix = _group_prefix(prefix)
    suffix = str(name).upper().removeprefix(prefix.upper() + '_')
    return str(name).upper().startswith(prefix.upper() + '_') and bool(
        re.fullmatch(r'(?:' + '|'.join(_GROUP_CODES) + r')(?:_LVL[1-9][0-9]*)?', suffix))


def predefined_group_plan(model, categories=None, prefix='_RB', tolerance=.001):
    """Return typed group definitions using the guide's CND/MEM/FLR legend."""
    prefix = _group_prefix(prefix)
    categories = _categories(model, categories)
    tolerance = finite(tolerance, 'Level tolerance', True)
    groups = []
    def add(kind, code, ids):
        ids = tuple(sorted(set(ids)))
        if ids:
            groups.append(GroupDefinition(kind, prefix + '_' + code, ids))
    columns = {mid for mid, category in categories.items() if category == 'Columns'}
    column_nodes = {n for mid in columns for n in model.members[mid]}
    horizontal = {mid for mid, (a, b) in model.members.items()
                  if abs(model.nodes[a][1] - model.nodes[b][1]) <= tolerance}
    add(1, 'CND', column_nodes)
    add(2, 'MEM', model.members)
    add(2, 'COL', columns)
    add(6, 'FLR', horizontal)
    codes = {'PLN_BRC': ('Plan diagonals',), 'PRI_BM': ('Primary beams X', 'Primary beams Z'),
             'SEC_TER_BM': ('Secondary beams X', 'Secondary beams Z', 'Other horizontal'),
             'VER_BRC': ('Vertical bracing',), 'RAFTER': ('Rafters',), 'RAF_BRC': ('Rafter bracing',)}
    for code, names in codes.items():
        add(2, code, (mid for mid, category in categories.items() if category in names))
    levels = _levels((xyz[1] for xyz in model.nodes.values()), tolerance)
    nodes_by_level, members_by_level = defaultdict(list), defaultdict(list)
    for node in column_nodes:
        nodes_by_level[_level_index(levels, model.nodes[node][1])].append(node)
    for mid in horizontal:
        members_by_level[_level_index(levels, _floor(model, mid))].append(mid)
    for index, elevation in enumerate(levels, 1):
        add(1, f'CND_LVL{index}', nodes_by_level[index - 1])
        floor_members = members_by_level[index - 1]
        add(2, f'MEM_LVL{index}', floor_members)
        add(6, f'FLR_LVL{index}', floor_members)
    return tuple(groups)


def group_plan_commands(groups):
    lines = ['START GROUP DEFINITION']
    for kind, title in ((1, 'JOINT'), (2, 'MEMBER'), (6, 'FLOOR')):
        selected = [group for group in groups if group.kind == kind]
        if selected:
            lines.append(title)
            for group in selected:
                lines.extend(continued(group.name, group.ids))
    return '\n'.join(lines + ['END GROUP DEFINITION', ''])


def _void_comparison_error(exc):
    return "'<' not supported between instances of 'NoneType' and 'int'" in str(exc)


def _void_group_call(method, *args):
    # openstaadpy 0.2 compares documented void returns with zero. The
    # mutation already happened when that comparison raises; verify once
    # afterward, without repeating the write.
    try:
        status = method(*args)
    except TypeError as exc:
        if not _void_comparison_error(exc):
            raise
        return
    if status is False or isinstance(status, (int, float)) and status < 0:
        raise RuntimeError('STAAD rejected a group operation.')


def _group_array(geometry, method, arg):
    try:
        return getattr(geometry, method)(arg)
    except TypeError as exc:
        if not _void_comparison_error(exc):
            raise
    # Recover output arrays discarded by the same wrapper bug on reads.
    from comtypes import automation
    from openstaadpy.os_analytical.openstaadhelper import (
        make_safe_array_long, make_safe_array_string, make_variant_vt_ref)
    raw = geometry._geometry
    if method == 'GetGroupNames':
        count = int(raw.GetGroupCount(arg))
        values = make_variant_vt_ref(make_safe_array_string(count), automation.VT_ARRAY | automation.VT_BSTR)
    else:
        count = int(raw.GetGroupEntityCount(arg))
        values = make_variant_vt_ref(make_safe_array_long(count), automation.VT_ARRAY | automation.VT_I4)
    status = getattr(raw, method)(arg, values)
    if isinstance(status, (int, float)) and status < 0:
        raise RuntimeError('STAAD could not read groups.')
    result = list(values[0])
    if len(result) != count:
        raise RuntimeError('STAAD returned an incomplete group list.')
    return result


def _read_groups(geometry):
    result = {}
    for kind in range(1, 7):
        names = _group_array(geometry, 'GetGroupNames', kind) if geometry.GetGroupCount(kind) else []
        for name in names:
            key = str(name).casefold()
            if key in result:
                raise RuntimeError('STAAD returned duplicate group names.')
            result[key] = GroupDefinition(kind, str(name), tuple(sorted(_group_array(geometry, 'GetGroupEntities', name))))
    return result


def _same_geometry(current, expected):
    if (Path(current.path).resolve() != Path(expected.path).resolve() or
            current.base_unit != expected.base_unit or current.nodes != expected.nodes or
            current.members != expected.members or current.supports != expected.supports or
            current.load_cases != expected.load_cases):
        raise RuntimeError('Active model, geometry, supports or load cases changed during the operation.')


def _active_path(staad, expected):
    if Path(str(staad.GetSTAADFile() or '')).resolve() != Path(expected.path).resolve():
        raise RuntimeError('The active STAAD model changed before assignment.')


def apply_predefined_groups(expected, report, categories=None, prefix='_RB'):
    groups = predefined_group_plan(expected, categories, prefix)
    staad = live.connect()
    live.require_snapshot(staad, expected, report)
    existing = _read_groups(staad.Geometry)
    preserved = {key: group for key, group in existing.items() if not is_generated_group(group.name, prefix)}
    backup = live._backup_model(staad, expected, report)
    try:
        _active_path(staad, expected)
        for group in existing.values():
            if is_generated_group(group.name, prefix):
                _void_group_call(staad.Geometry.DeleteGroup, group.name)
        for group in groups:
            _void_group_call(staad.Geometry.CreateGroupEx, group.kind, group.name, list(group.ids))
        actual = _read_groups(staad.Geometry)
        requested = {group.name.casefold(): group for group in groups}
        if set(actual) != set(preserved) | set(requested):
            raise RuntimeError('STAAD group names did not match the plan.')
        for key, group in {**preserved, **requested}.items():
            if actual[key].kind != group.kind or actual[key].ids != group.ids:
                raise RuntimeError(f'STAAD group verification failed for {group.name}.')
        _same_geometry(live.capture(staad, report), expected)
        if staad.SaveModel(True) is False:
            raise RuntimeError('STAAD could not save the generated groups.')
    except Exception as exc:
        raise RuntimeError(f'Group assignment may be partial. Backup: {backup}. {exc}') from exc
    return OperationResult(f'Created {len(groups)} groups. Backup: {backup}', str(backup), len(groups))


@dataclass(frozen=True)
class BeamChain:
    members: tuple
    nodes: tuple
    category: str


@dataclass
class ReleasePlan:
    selected: tuple
    assignments: dict  # (member ID, local end 0/1) -> ordered DOF tuple
    chains: tuple
    skipped: dict  # selected member ID -> reason

    @property
    def member_ids(self):
        return tuple(sorted({mid for mid, _ in self.assignments}))

    @property
    def summary(self):
        return (f'{len(self.chains)} complete beam chains; {len(self.assignments)} exterior ends; '
                f'{len(self.skipped)} members ignored.')


def _beam_chains(model, categories, tolerance):
    """Split straight runs at their actual supporting frame nodes."""
    columns = {n for mid, category in categories.items() if category == 'Columns' for n in model.members[mid]}
    primary_nodes = {n for mid, category in categories.items() if category.startswith('Primary beams') for n in model.members[mid]}
    chains = []
    for category in ('Primary beams X', 'Primary beams Z', 'Secondary beams X', 'Secondary beams Z'):
        remaining = {mid for mid, name in categories.items() if name == category}
        adjacency = defaultdict(set)
        for mid in remaining:
            for node in model.members[mid]:
                adjacency[node].add(mid)
        anchors = columns if category.startswith('Primary') else columns | primary_nodes
        # Do not merge adjacent spans through a column or a primary beam.
        for seed in sorted(remaining):
            if seed not in remaining:
                continue
            remaining.remove(seed)
            component, nodes = {seed}, set(model.members[seed])
            pending = list(nodes)
            for node in pending:
                if node in anchors:
                    continue
                for mid in sorted(adjacency[node] & remaining):
                    remaining.remove(mid)
                    component.add(mid)
                    for end in model.members[mid]:
                        if end not in nodes:
                            nodes.add(end)
                            pending.append(end)
            local = {node: adjacency[node] & component for node in nodes}
            ends = [node for node in nodes if len(local[node]) == 1]
            reason = ''
            if len(ends) != 2 or any(len(mids) > 2 for mids in local.values()):
                reason = 'Ambiguous or branching beam chain'
            elif not set(ends) <= anchors:
                reason = 'Tertiary or unsupported beam chain'
            ordered, ordered_nodes = [], []
            if not reason:
                axis = 0 if category.endswith('X') else 2
                ends.sort(key=lambda node: (model.nodes[node][axis], node))
                start, finish = ends
                line = [v - u for u, v in zip(model.nodes[start], model.nodes[finish])]
                length = math.sqrt(sum(v * v for v in line))
                for node in nodes:
                    vec = [v - u for u, v in zip(model.nodes[start], model.nodes[node])]
                    cross = (vec[1]*line[2]-vec[2]*line[1], vec[2]*line[0]-vec[0]*line[2], vec[0]*line[1]-vec[1]*line[0])
                    if length <= tolerance or math.sqrt(sum(v*v for v in cross)) / length > tolerance:
                        reason = 'Beam chain is not straight'
                        break
                node, visited = start, set()
                ordered_nodes = [node]
                while not reason and node != finish:
                    onward = local[node] - visited
                    if len(onward) != 1:
                        reason = 'Ambiguous beam chain'
                        break
                    mid = next(iter(onward))
                    ordered.append(mid)
                    visited.add(mid)
                    a, b = model.members[mid]
                    node = b if a == node else a
                    ordered_nodes.append(node)
            chains.append((BeamChain(tuple(ordered or sorted(component)), tuple(ordered_nodes), category), reason))
    return chains


def selected_release_plan(model, selected, end='BOTH', dofs=('MY', 'MZ'), categories=None, tolerance=.001):
    """Release only physical exterior ends of fully selected supported chains.

    START/END refer to the corresponding analytical member's local incidence,
    so a reversed last segment correctly receives START at its exterior end.
    Intermediate segment ends and excluded members are never assigned.
    """
    selected = tuple(sorted({positive_id(mid) for mid in selected}))
    release_commands(selected, end, dofs)
    if set(selected) - set(model.members):
        raise ValueError('Selected members are missing from the processed model.')
    tolerance = finite(tolerance, 'Chain tolerance', True)
    categories = _categories(model, categories)
    dofs = tuple(dof for dof in DOFS if dof in dofs)
    assignments, skipped, accepted = {}, {}, []
    selected_set = set(selected)
    considered = set()
    allowed_ends = (0, 1) if end == 'BOTH' else (0,) if end == 'START' else (1,)
    for chain, reason in _beam_chains(model, categories, tolerance):
        intersection = set(chain.members) & selected_set
        if not intersection:
            continue
        considered.update(intersection)
        if not reason and not set(chain.members) <= selected_set:
            reason = 'Incomplete beam chain: select all its segments'
        if reason:
            skipped.update({mid: reason for mid in intersection})
            continue
        accepted.append(chain)
        for mid, node in ((chain.members[0], chain.nodes[0]), (chain.members[-1], chain.nodes[-1])):
            location = model.members[mid].index(node)
            if location in allowed_ends:
                assignments[mid, location] = dofs
    for mid in selected_set - considered:
        skipped[mid] = 'Columns, braces, rafters and other non-beam members are excluded'
    return ReleasePlan(selected, assignments, tuple(accepted), dict(sorted(skipped.items())))


def read_selected_release_plan(expected, report, end='BOTH', dofs=('MY', 'MZ'), categories=None):
    staad = live.connect()
    live.require_snapshot(staad, expected, report)
    selected = live._selected_ids(staad.Geometry)
    if not selected:
        raise ValueError('Select beams in STAAD.Pro before defining releases.')
    return selected_release_plan(expected, selected, end, dofs, categories)


def release_plan_commands(plan):
    lines = ['* LOCAL member axes; physical chain exterior ends only.', 'MEMBER RELEASE']
    buckets = defaultdict(list)
    for (mid, location), dofs in sorted(plan.assignments.items()):
        buckets[location, dofs].append(mid)
    for (location, dofs), ids in sorted(buckets.items()):
        lines.extend(continued('', ids, ('START' if location == 0 else 'END') + ' ' + ' '.join(dofs)))
    return '\n'.join(lines) + '\n'


def apply_selected_releases(expected, report, end='BOTH', dofs=('MY', 'MZ'), categories=None,
                            proceed_skipped=False, plan=None):
    staad = live.connect()
    live.require_snapshot(staad, expected, report)
    selected = live._selected_ids(staad.Geometry)
    if not selected:
        raise ValueError('Select beams in STAAD.Pro before defining releases.')
    regenerated = selected_release_plan(expected, selected, end, dofs, categories)
    if plan is not None and (not isinstance(plan, ReleasePlan) or regenerated != plan):
        raise ValueError('STAAD selection or release options changed. Define Releases again before assigning.')
    plan = regenerated
    if plan.skipped and not proceed_skipped:
        raise ValueError(plan.summary + ' Review ignored members and choose Proceed to assign valid chains.')
    if not plan.assignments:
        raise ValueError('No valid exterior beam ends match this selection. ' + plan.summary)
    backup = live._backup_model(staad, expected, report)
    buckets = defaultdict(list)
    for (mid, location), flags in plan.assignments.items():
        buckets[location, flags].append(mid)
    try:
        _active_path(staad, expected)
        for (location, dofs), ids in sorted(buckets.items()):
            flags = [int(dof in dofs) for dof in DOFS]
            spec = staad.Property.CreateMemberReleaseSpec(location, flags, [0.] * 6)
            if isinstance(spec, bool) or not isinstance(spec, int) or spec < 0:
                raise RuntimeError('STAAD did not create the release specification.')
            if staad.Property.AssignMemberSpecToBeam(sorted(ids), spec) is False:
                raise RuntimeError('STAAD rejected the release assignment.')
            for mid in ids:
                actual, springs = staad.Property.GetMemberReleaseSpec(mid, location)
                if list(actual) != flags or any(springs):
                    raise RuntimeError(f'Release verification failed for member {mid}.')
        _same_geometry(live.capture(staad, report), expected)
        if staad.SaveModel(True) is False:
            raise RuntimeError('STAAD could not save the assigned releases.')
    except Exception as exc:
        raise RuntimeError(f'Release assignment may be partial. Backup: {backup}. {exc}') from exc
    summary = plan.summary + f' Releases assigned. Re-run analysis. Backup: {backup}'
    return OperationResult(summary, str(backup), len(plan.member_ids), len(plan.skipped))
