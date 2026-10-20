"""Execute a caller-reviewed Python observation probe in the selected client."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / '.rea-runtime'))
import frida

parser = argparse.ArgumentParser()
parser.add_argument('pid', type=int)
parser.add_argument('probe', type=Path)
args = parser.parse_args()
session = frida.attach(args.pid)
script = session.create_script('''
const py = Process.getModuleByName('python39.dll');
const ensure = new NativeFunction(py.getExportByName('PyGILState_Ensure'), 'int', []);
const release = new NativeFunction(py.getExportByName('PyGILState_Release'), 'void', ['int']);
const run = new NativeFunction(py.getExportByName('PyRun_SimpleString'), 'int', ['pointer']);
rpc.exports = { execute(code) {
    const ptr = Memory.allocUtf8String(code), state = ensure();
    try { return run(ptr); } finally { release(state); }
}};
''')
try:
    script.load()
    result = script.exports_sync.execute(args.probe.read_text(encoding='utf-8'))
    print('Probe exit:', result)
    if result:
        raise SystemExit(result)
finally:
    session.detach()
