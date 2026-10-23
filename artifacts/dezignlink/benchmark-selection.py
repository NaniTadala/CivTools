"""Measure selection on the open model; restore its original selection."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
from time import perf_counter
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
from civtools.core import staad_productivity_com as live
from civtools.core.staad_productivity import classify_members

staad = live.connect()
original_members = live._selected_ids(staad.Geometry)
original_nodes = live._selected_ids(staad.Geometry, nodes=True)
start = perf_counter()
snapshot = live.capture(staad)
scan_ms = (perf_counter() - start) * 1000
start = perf_counter()
categories = classify_members(snapshot)
classify_ms = (perf_counter() - start) * 1000
measurements = []
trace = []
class TimedSTAAD:
    def __init__(self, target, name='STAAD'):
        self.target, self.name = target, name

    def __getattr__(self, name):
        value = getattr(self.target, name)
        if name in ('Geometry', 'View', '_geometry', '_view'):
            return TimedSTAAD(value, self.name + '.' + name)
        def call(*args, **kwargs):
            start = perf_counter()
            try:
                return value(*args, **kwargs)
            finally:
                trace.append({'call': self.name + '.' + name, 'ms': round((perf_counter() - start) * 1000, 3)})
        return call

original_connect = live.connect
def timed_connect():
    start = perf_counter()
    value = original_connect()
    trace.append({'call': 'connect', 'ms': round((perf_counter() - start) * 1000, 3)})
    return TimedSTAAD(value)
try:
    for name, roles in [('Columns', {'Columns'}),
                        ('Primary beams', {'Primary beams X', 'Primary beams Z'}),
                        ('Vertical bracing', {'Vertical bracing'})]:
        ids = sorted(mid for mid, role in categories.items() if role in roles)
        for selecting in (True, False):
            trace.clear()
            start = perf_counter()
            with patch.object(live, 'connect', side_effect=timed_connect):
                live.set_selection(snapshot, ids if selecting else [], [], lambda *args: None)
            measurements.append({'group': name, 'select': selecting, 'members': len(ids) if selecting else 0,
                                 'elapsed_ms': round((perf_counter() - start) * 1000, 3), 'calls': list(trace)})
finally:
    if str(staad.GetSTAADFile()) != snapshot.path:
        raise RuntimeError('Active model changed; original selection was not applied to another model.')
    live._replace_selection(staad, sorted(original_members))
    live._replace_selection(staad, sorted(original_nodes), nodes=True)
    staad.View.RefreshView()

restored = (live._selected_ids(staad.Geometry) == original_members and
            live._selected_ids(staad.Geometry, nodes=True) == original_nodes)
unchanged = hashlib.sha256(Path(snapshot.path).read_bytes()).hexdigest() == snapshot.source_digest
result = {'model': Path(snapshot.path).name, 'nodes': len(snapshot.nodes), 'members': len(snapshot.members),
          'scan_ms': round(scan_ms, 3), 'classify_ms': round(classify_ms, 3),
          'categories': dict(Counter(categories.values())), 'toggles': measurements,
          'original_selection_restored': restored, 'saved_model_unchanged': unchanged}
Path(__file__).with_name('selection-benchmark.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps({**result, 'toggles': [{k: v for k, v in entry.items() if k != 'calls'}
                                      for entry in measurements]}, indent=2))
if not restored or not unchanged:
    raise RuntimeError('Selection restoration or saved-model identity check failed.')
