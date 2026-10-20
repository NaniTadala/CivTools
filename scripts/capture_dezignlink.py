"""Bounded, reversible engineering-only request capture in the supplied client.

Requires workspace-local Frida. No credentials, headers or authentication routes
are recorded. Restores Session.send before detaching. Does not invoke app actions.
"""
import argparse
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / '.rea-runtime'))
import frida


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('pid', type=int)
    parser.add_argument('output', type=Path)
    parser.add_argument('--seconds', type=int, default=300)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit('Choose a new capture file.')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    code = '''
import requests as _ct_requests, json as _ct_json, time as _ct_time, hashlib as _ct_hashlib
from urllib.parse import urlsplit as _ct_urlsplit
_ct_routes = {'sel_members', 'renum_members', 'grp_members', 'def_releases',
              'des_params', 'data_table', 'gen_loadComb', 'gen_pltgrdrs',
              'gen_pipeRack', 'gen_pebStr'}
_ct_original_send = _ct_requests.sessions.Session.send
_ct_original_call = globals().get('serverCall')
def _ct_clean(value):
    if isinstance(value, dict):
        return {str(k): ('[redacted]' if any(t in str(k).lower() for t in
                ('cookie', 'password', 'token', 'secret', 'authorization', 'email'))
                else _ct_clean(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [_ct_clean(v) for v in value]
    return value
def _ct_send(self, request, **kwargs):
    route = _ct_urlsplit(request.url).path.rstrip('/').rsplit('/', 1)[-1]
    response = _ct_original_send(self, request, **kwargs)
    if route in _ct_routes:
        try:
            body = request.body
            if body is None:
                payload = None
            else:
                payload = _ct_json.loads(body)
            try:
                result = response.json()
            except ValueError:
                result = {'non_json': True, 'bytes': len(response.content),
                          'sha256': _ct_hashlib.sha256(response.content).hexdigest(),
                          'known_error_markers': [s for s in ('Unauthorized', 'Forbidden', 'Application Error')
                                                if s.lower() in response.text.lower()]}
            record = {'timestamp': _ct_time.time(), 'route': route,
                      'method': request.method, 'status': response.status_code,
                      'content_type': response.headers.get('Content-Type'),
                      'request': _ct_clean(payload), 'response': _ct_clean(result)}
            text = _ct_json.dumps(record)
            if len(text) <= 4000000:
                with open(OUTPUT, 'a', encoding='utf-8') as stream:
                    stream.write(text + '\\n')
        except Exception:
            pass
    return response
def _ct_call(route, *args, **kwargs):
    if route not in _ct_routes:
        return _ct_original_call(route, *args, **kwargs)
    with open(OUTPUT, 'a', encoding='utf-8') as stream:
        stream.write(_ct_json.dumps({'event': 'request', 'route': route,
            'timestamp': _ct_time.time(), 'request': _ct_clean(list(args))}) + '\\n')
    result = _ct_original_call(route, *args, **kwargs)
    with open(OUTPUT, 'a', encoding='utf-8') as stream:
        stream.write(_ct_json.dumps({'event': 'response', 'route': route,
            'timestamp': _ct_time.time(), 'response': _ct_clean(result)}) + '\\n')
    return result
if callable(_ct_original_call):
    serverCall = _ct_call
_ct_requests.sessions.Session.send = _ct_send
'''.replace('OUTPUT', repr(str(args.output.resolve())))
    restore = '''
if '_ct_original_send' in globals():
    _ct_requests.sessions.Session.send = _ct_original_send
if callable(globals().get('_ct_original_call')):
    serverCall = _ct_original_call
'''
    session = frida.attach(args.pid)
    script = session.create_script('''
const py = Process.getModuleByName('python39.dll');
const ensure = new NativeFunction(py.getExportByName('PyGILState_Ensure'), 'int', []);
const release = new NativeFunction(py.getExportByName('PyGILState_Release'), 'void', ['int']);
const run = new NativeFunction(py.getExportByName('PyRun_SimpleString'), 'int', ['pointer']);
rpc.exports = { execute(code) {
    const text = Memory.allocUtf8String(code);
    const state = ensure();
    try { return run(text); } finally { release(state); }
}};
''')
    script.load()
    try:
        result = script.exports_sync.execute(code)
        if result != 0:
            raise RuntimeError('Client capture hook could not be installed.')
        print(json.dumps({'capture': 'attached', 'pid': args.pid,
                          'output': str(args.output), 'seconds': args.seconds}), flush=True)
        until = time.monotonic() + args.seconds
        while time.monotonic() < until:
            time.sleep(.5)
    finally:
        try:
            try:
                script.exports_sync.execute(restore)
            except frida.InvalidOperationError:
                print('Target exited; capture hook no longer exists.', flush=True)
        finally:
            session.detach()
        print('Capture detached; original request handler restored.', flush=True)


if __name__ == '__main__':
    main()
