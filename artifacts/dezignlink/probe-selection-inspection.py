"""Read only selected engineering function bytecode in the user's open client."""
import dis as _ct_dis
import json as _ct_json
import sys as _ct_sys

_ct_root = _ct_sys.modules['__main__'].__dict__
_ct_names = ('smProc', 'selMemWin', 'modelUnchanged', 'getModelData',
             'SelectMultipleBeams', 'SelectMultipleNodes', 'GetSelectedBeams')
_ct_functions = {}
for _ct_name in _ct_names:
    _ct_fn = _ct_root.get(_ct_name)
    if not hasattr(_ct_fn, '__code__'):
        continue
    _ct_rows = []
    for _ct_i in _ct_dis.get_instructions(_ct_fn):
        _ct_v = _ct_i.argrepr
        if any(_ct_s in _ct_v.lower() for _ct_s in ('http', 'password', 'token', 'cookie', 'secret')):
            _ct_v = '<omitted>'
        _ct_rows.append({'offset': _ct_i.offset, 'op': _ct_i.opname, 'arg': _ct_v})
    _ct_functions[_ct_name] = _ct_rows

_ct_windows = []
for _ct_frame in _ct_sys._current_frames().values():
    while _ct_frame:
        if _ct_frame.f_code.co_name == '<module>' and 'dEZignLink' in _ct_frame.f_code.co_filename:
            _ct_instructions = list(_ct_dis.get_instructions(_ct_frame.f_code))
            _ct_selected = set()
            for _ct_n, _ct_i in enumerate(_ct_instructions):
                if _ct_i.argval in ('SelectMultipleBeams', 'SelectMultipleNodes', 'ClearMemberSelection', 'ClearNodeSelection'):
                    _ct_selected.update(range(max(0, _ct_n - 18), min(len(_ct_instructions), _ct_n + 18)))
            for _ct_n in sorted(_ct_selected):
                _ct_i = _ct_instructions[_ct_n]
                _ct_v = _ct_i.argrepr
                if any(_ct_s in _ct_v.lower() for _ct_s in ('http', 'password', 'token', 'cookie', 'secret')):
                    _ct_v = '<omitted>'
                _ct_windows.append({'offset': _ct_i.offset, 'op': _ct_i.opname, 'arg': _ct_v})
        _ct_frame = _ct_frame.f_back

with open(r'C:\Users\asus\Documents\Python Project\CivTools\artifacts\dezignlink\selection-runtime-inspection.json', 'w', encoding='utf-8') as _ct_out:
    _ct_json.dump({'method': 'Python Frida runtime code introspection; no app actions or network requests',
                   'functions': _ct_functions, 'selection_call_windows': _ct_windows}, _ct_out, indent=2)
