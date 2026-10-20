"""OpenSTAAD boundaries for local productivity jobs. Run on the serial CAD worker."""
from pathlib import Path
import hashlib
import shutil
from uuid import uuid4

from .geometry import MAX_NODES, MAX_BEAMS
from .results import OperationResult
from .staad_productivity import (ModelSnapshot, finite, positive_id, renumber_steps,
                                 write_result_workbook, group_commands, release_commands, DOFS)


def connect():
    from openstaadpy import os_analytical
    staad = os_analytical.connect()
    if staad is None:
        raise RuntimeError('Open STAAD.Pro with a saved analytical model first.')
    if staad.IsAnalyzing():
        raise RuntimeError('Wait for STAAD analysis to finish before accessing the model.')
    return staad


def capture(staad, report=lambda *args: None):
    if staad.IsAnalyzing():
        raise RuntimeError('Wait for STAAD analysis to finish before scanning.')
    path = str(staad.GetSTAADFile() or '')
    if not path or not Path(path).is_file():
        raise RuntimeError('Save the active STAAD model before scanning.')
    source_digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    geometry = staad.Geometry
    count_nodes, count_beams = int(geometry.GetNodeCount()), int(geometry.GetMemberCount())
    if not 0 < count_nodes <= MAX_NODES or not 0 < count_beams <= MAX_BEAMS:
        raise ValueError('Use a nonempty model within 10,000 nodes / 30,000 members.')
    report('target', path)
    report('stage', 'Reading geometry and load cases')
    node_ids, member_ids = list(geometry.GetNodeList()), list(geometry.GetBeamList())
    if len(node_ids) != count_nodes or len(member_ids) != count_beams:
        raise RuntimeError('STAAD geometry counts changed during scan. Scan again.')
    nodes, members = {}, {}
    for i, node in enumerate(node_ids):
        nodes[positive_id(node)] = tuple(geometry.GetNodeCoordinates(int(node)))
        if i % 100 == 0:
            report('progress', int(50 * i / count_nodes))
    for i, mid in enumerate(member_ids):
        members[positive_id(mid)] = tuple(geometry.GetMemberIncidence(int(mid)))
        if i % 100 == 0:
            report('progress', 50 + int(50 * i / count_beams))
    supports = list(staad.Support.GetSupportNodes()) if staad.Support.GetSupportCount() else []
    cases = []
    primary_cases = []
    if staad.Load.GetPrimaryLoadCaseCount():
        primary_cases = list(staad.Load.GetPrimaryLoadCaseNumbers())
        cases.extend(primary_cases)
    if staad.Load.GetLoadCombinationCaseCount():
        cases.extend(staad.Load.GetLoadCombinationCaseNumbers())
    snapshot = ModelSnapshot(path, str(staad.GetBaseUnit()), nodes, members, supports, cases, source_digest)
    snapshot.primary_cases = primary_cases
    if str(staad.GetSTAADFile() or '') != path:
        raise RuntimeError('Active model changed during scan. Scan again.')
    if source_digest != hashlib.sha256(Path(path).read_bytes()).hexdigest():
        raise RuntimeError('Saved model changed during scan. Scan again.')
    report('progress', 100)
    return snapshot


def scan(report):
    return capture(connect(), report)


def process_design_parameters(expected, mode, report):
    """Generate local candidates. Restraint/code-specific lengths need review."""
    from .staad_parameters import StaadService, SteelGenerator, Parameter, MAX_LINE_DEFAULT
    from .staad_productivity import fmt
    if mode not in ('columns', 'beams_dj', 'beams_lengths'):
        raise ValueError('Choose columns, beam design joints or beam lengths.')
    staad = connect()
    require_snapshot(staad, expected, report)
    service = StaadService()
    service.load_model(.001, fallback=False)
    if Path(service.model_path).resolve() != Path(expected.path).resolve():
        raise RuntimeError('The active STAAD model changed. Process Members again.')
    report('stage', 'Reading steel members and physical beam chains')
    if mode == 'beams_dj':
        result = SteelGenerator(service, MAX_LINE_DEFAULT).generate([
            Parameter(True, 'DESIGN JOINT', None, 'all', '')])
    else:
        members = [m for m in service.members if m.steel and (
            m.column_y if mode == 'columns' else (m.beam_x or m.beam_z))]
        if not members:
            raise ValueError('No steel members match this operation. Check STAAD materials.')
        result = '\n'.join([
            '* Geometric segment-length candidates; every end joint is assumed restrained.',
            '* Review actual lateral restraints and code requirements before assignment.',
            '* LX / UNL / LT is code-dependent and must be supplied separately.',
            'UNIT METER KN',
            *[f'{parameter} {fmt(service.length_to_meters(m.length))} MEMB {m.member_id}'
              for m in members for parameter in ('LY', 'LZ')],
            '* Restore previous input units after these parameters.', ''])
    require_snapshot(staad, expected, report)
    return result


def _backup_model(staad, expected, report):
    staad.SaveModel(True)
    source = Path(expected.path)
    backup = source.with_name(source.stem + '.civtools-' + uuid4().hex + '.std')
    shutil.copy2(source, backup)
    report('log', 'Backup: ' + str(backup))
    return backup


def apply_groups(expected, categories, prefix, report):
    """Apply precisely the preview's groups, refusing name collisions."""
    text = group_commands(expected, categories, prefix)
    types, kind, pending, groups = {'JOINT': 1, 'MEMBER': 2, 'FLOOR': 6}, None, '', []
    for line in text.splitlines():
        if line in types:
            kind = types[line]
        elif line.startswith('*') or line in ('START GROUP DEFINITION', 'END GROUP DEFINITION'):
            continue
        else:
            pending += ' ' + line.rstrip('-').strip()
            if not line.endswith('-'):
                name, *ids = pending.split()
                groups.append((kind, name, list(map(int, ids))))
                pending = ''
    staad = connect()
    require_snapshot(staad, expected, report)
    names = {name.casefold() for kind in range(1, 7)
             for name in (staad.Geometry.GetGroupNames(kind) if staad.Geometry.GetGroupCount(kind) else [])}
    if any(name.casefold() in names for _, name, _ in groups):
        raise ValueError('One or more group names already exist. Choose a different prefix.')
    backup = _backup_model(staad, expected, report)
    try:
        for kind, name, ids in groups:
            if str(staad.GetSTAADFile()) != expected.path:
                raise RuntimeError('Active model changed.')
            staad.Geometry.CreateGroupEx(kind, name, ids)
            if set(staad.Geometry.GetGroupEntities(name)) != set(ids):
                raise RuntimeError(f'Group {name} did not match the requested members.')
        staad.SaveModel(True)
    except Exception as exc:
        raise RuntimeError(f'Group creation may be partial. Backup: {backup}. {exc}') from exc
    return OperationResult(f'Created {len(groups)} groups. Backup: {backup}', str(backup))


def apply_releases(expected, ids, end, dofs, report):
    release_commands(ids, end, dofs)  # Validate the same input used by the preview.
    ids = sorted({positive_id(mid) for mid in ids})
    if set(ids) - expected.members.keys():
        raise ValueError('Choose members from the scanned model.')
    staad = connect()
    require_snapshot(staad, expected, report)
    backup = _backup_model(staad, expected, report)
    flags = [int(dof in dofs) for dof in DOFS]
    ends = (0, 1) if end == 'BOTH' else (0,) if end == 'START' else (1,)
    try:
        for location in ends:
            if str(staad.GetSTAADFile()) != expected.path:
                raise RuntimeError('Active model changed.')
            spec = staad.Property.CreateMemberReleaseSpec(location, flags, [0.] * 6)
            if not isinstance(spec, int) or spec <= 0:
                raise RuntimeError('STAAD did not create the release specification.')
            staad.Property.AssignMemberSpecToBeam(ids, spec)
            for mid in ids:
                actual, springs = staad.Property.GetMemberReleaseSpec(mid, location)
                if list(actual) != flags or any(springs):
                    raise RuntimeError(f'STAAD release verification failed for member {mid}.')
        staad.SaveModel(True)
    except Exception as exc:
        raise RuntimeError(f'Release assignment may be partial. Backup: {backup}. {exc}') from exc
    return OperationResult(f'Assigned releases to {len(ids)} members. Re-run analysis. Backup: {backup}', str(backup))


def require_snapshot(staad, expected, report):
    current = capture(staad, report)
    if current.fingerprint != expected.fingerprint:
        raise RuntimeError('Active model, units, supports or geometry changed. Scan again before continuing.')
    return current


def select_members(expected, ids, report, nodes=False):
    staad = connect()
    current = require_snapshot(staad, expected, report)
    allowed = current.nodes if nodes else current.members
    ids = sorted({positive_id(i) for i in ids})
    if not ids or set(ids) - allowed.keys():
        raise ValueError('Select valid nodes or members from the scanned model.')
    if nodes:
        staad.Geometry.ClearNodeSelection()
        staad.Geometry.SelectMultipleNodes(ids)
    else:
        staad.Geometry.ClearMemberSelection()
        staad.Geometry.SelectMultipleBeams(ids)
    return OperationResult(f'Selected {len(ids):,} ' + ('nodes.' if nodes else 'members.'))


def apply_renumber(expected, mapping, report):
    staad = connect()
    require_snapshot(staad, expected, report)
    if set(mapping) != set(expected.members):
        raise ValueError('The renumber plan must cover the complete scanned member list.')
    for method in ('GetLastPlateNo', 'GetLastSolidNo', 'GetLastPhysicalMemberNo'):
        if getattr(staad.Geometry, method)():
            raise ValueError('Renumbering supports analytical beam-only models; plates, solids and physical members are excluded.')
    steps = renumber_steps(mapping)
    if not steps:
        return OperationResult('Member numbering already matches the plan.')
    # Save the current model before taking the backup, including previously unsaved edits.
    report('stage', 'Saving and backing up the model')
    staad.SaveModel(True)
    source = Path(expected.path)
    backup = source.with_name(source.stem + '.civtools-' + uuid4().hex + '.std')
    shutil.copy2(source, backup)
    journal = backup.with_suffix('.renumber.json')
    import json
    journal.write_text(json.dumps({'model': expected.path, 'mapping': mapping,
                                   'steps': steps}, indent=2), encoding='utf-8')
    report('log', f'Backup: {backup}\nRenumber plan: {journal}')
    completed = 0
    try:
        if str(staad.GetSTAADFile()) != expected.path:
            raise RuntimeError('Active model changed before renumbering.')
        for old, new in steps:
            if str(staad.GetSTAADFile()) != expected.path:
                raise RuntimeError('Active model changed during renumbering.')
            if not staad.Geometry.RenumberBeam(old, new):
                raise RuntimeError(f'STAAD rejected renumbering {old} to {new}.')
            completed += 1
            if completed % 25 == 0:
                report('progress', int(100 * completed / len(steps)))
        actual = {int(i) for i in staad.Geometry.GetBeamList()}
        if actual != set(mapping.values()):
            raise RuntimeError('STAAD member IDs do not match the requested plan.')
        for old, new in mapping.items():
            if tuple(staad.Geometry.GetMemberIncidence(new)) != expected.members[old]:
                raise RuntimeError(f'Member connectivity changed for renumbered member {new}.')
        staad.SaveModel(True)
    except Exception as exc:
        raise RuntimeError(f'Renumbering stopped after {completed}/{len(steps)} steps. '
                           f'The active model may contain partial changes. Restore the backup {backup} '
                           f'and inspect the journal {journal}. {exc}') from exc
    return OperationResult(f'Renumbered {len(mapping):,} members. Re-run analysis. Backup: {backup}', str(backup))


def export_results(expected, kind, nodes, cases, path, report, pedestal=None):
    staad = connect()
    current = require_snapshot(staad, expected, report)
    if kind not in ('Reactions', 'Displacements', 'Pedestal'):
        raise ValueError('Choose a supported result type.')
    nodes, cases = sorted({positive_id(n) for n in nodes}), sorted({positive_id(c) for c in cases})
    if not nodes or not cases or set(nodes) - current.nodes.keys() or set(cases) - set(current.load_cases):
        raise ValueError('Choose valid nodes and load cases from a fresh scan.')
    if kind != 'Displacements' and set(nodes) - set(current.supports):
        raise ValueError('Reaction/pedestal exports require support nodes.')
    if len(nodes) * len(cases) > 100_000:
        raise ValueError('Limit an export to 100,000 node/load-case pairs.')
    if not staad.Output.AreResultsAvailable():
        raise RuntimeError('Run analysis in STAAD.Pro before exporting results.')
    report('stage', 'Reading analysis results')
    getter = staad.Output.GetNodeDisplacements if kind == 'Displacements' else staad.Output.GetSupportReactions
    records = []
    for node in nodes:
        for case in cases:
            values = tuple(finite(v, 'STAAD result') for v in getter(node, case))
            if len(values) != 6:
                raise RuntimeError(f'STAAD returned incomplete results for node {node}, case {case}.')
            records.append((node, case, values))
            if len(records) % 50 == 0:
                report('progress', int(100 * len(records) / (len(nodes) * len(cases))))
    # Do not publish a workbook after a target switch during a long result read.
    require_snapshot(staad, current, report)
    if not staad.Output.AreResultsAvailable():
        raise RuntimeError('Analysis results became unavailable during export.')
    report('stage', 'Writing workbook and envelopes')
    write_result_workbook(path, current, kind, records, pedestal)
    return OperationResult(f'Exported {len(records):,} result rows and component envelopes to {path}.', str(path))
