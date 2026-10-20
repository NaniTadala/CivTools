"""Read Python 3.9 PyInstaller metadata without executing the target code.

Local investigation helper; outputs names, imports and scoped text constants.
It deliberately does not instantiate Python code objects or inspect stored login data.
"""
import argparse
import hashlib
import json
import struct
from pathlib import Path

from PyInstaller.archive.readers import CArchiveReader


class Marshal39:
    """Small, bounded reader for the marshal tags present in this supplied artifact."""

    def __init__(self, data):
        self.data, self.pos, self.refs = data, 0, []

    def take(self, size):
        if size < 0 or self.pos + size > len(self.data):
            raise ValueError("Invalid marshal length")
        value = self.data[self.pos:self.pos + size]
        self.pos += size
        return value

    def integer(self):
        return struct.unpack('<i', self.take(4))[0]

    def read(self):
        raw = self.take(1)[0]
        tag = chr(raw & 127)
        ref = len(self.refs) if raw & 128 else None
        if ref is not None:
            self.refs.append(None)
        if tag == 'r':
            value = self.refs[self.integer()]
        elif tag in 'NFT.':
            value = {'N': None, 'F': False, 'T': True, '.': Ellipsis}[tag]
        elif tag == 'i':
            value = self.integer()
        elif tag == 'l':
            count = self.integer()
            value = sum(struct.unpack('<H', self.take(2))[0] << (15 * i)
                        for i in range(abs(count))) * (-1 if count < 0 else 1)
        elif tag == 'g':
            value = struct.unpack('<d', self.take(8))[0]
        elif tag in 'stuazAZ':
            length = self.take(1)[0] if tag in 'zZ' else self.integer()
            raw_value = self.take(length)
            value = raw_value if tag == 's' else raw_value.decode('utf-8', errors='surrogatepass')
        elif tag in '([)<>':
            count = self.take(1)[0] if tag == ')' else self.integer()
            value = []
            if ref is not None:
                self.refs[ref] = value
            value.extend(self.read() for _ in range(count))
        elif tag == 'c':
            value = {'kind': 'code'}
            if ref is not None:
                self.refs[ref] = value
            for key in ('argcount', 'posonly', 'kwonly', 'nlocals', 'stacksize', 'flags'):
                value[key] = self.integer()
            for key in ('bytecode', 'consts', 'names', 'varnames', 'freevars', 'cellvars', 'filename', 'name'):
                value[key] = self.read()
            value['firstlineno'] = self.integer()
            value['lnotab'] = self.read()
        else:
            raise ValueError(f'Unsupported marshal tag {tag!r} at {self.pos - 1}')
        if ref is not None:
            self.refs[ref] = value
        return value


def walk(code, parent=''):
    name = parent + '.' + code['name'] if parent else code['name']
    # Retain engineering/UI observations; skip account/authentication implementation.
    sensitive = any(word in name.lower() for word in ('login', 'auth', 'cookie', 'password', 'licen'))
    strings = [v for v in code['consts'] if isinstance(v, str)]
    strings = [s for s in strings if len(s) <= 1200 and not any(
        token in s.lower() for token in ('http', 'password', 'cookie', 'token', 'secret', 'bearer'))]
    yield {'scope': name, 'source_line': code['firstlineno'],
           'names': code['names'], 'arguments': code['varnames'][:code['argcount']],
           'strings': [] if sensitive else strings,
           'bytecode_sha256': hashlib.sha256(code['bytecode']).hexdigest(),
           'bytecode_bytes': len(code['bytecode'])}
    for child in code['consts']:
        if isinstance(child, dict) and child.get('kind') == 'code':
            yield from walk(child, name)


def call_windows(code):
    """Record limited Python 3.9 instruction windows anchoring remote calls.

    Offsets are byte offsets; this is not a decompiler or control-flow analysis.
    Only the opcodes needed for these argument-loading sequences are decoded.
    """
    ops = {100: 'LOAD_CONST', 116: 'LOAD_GLOBAL', 124: 'LOAD_FAST',
           125: 'STORE_FAST', 106: 'LOAD_ATTR', 160: 'LOAD_METHOD',
           161: 'CALL_METHOD', 131: 'CALL_FUNCTION', 141: 'CALL_FUNCTION_KW',
           132: 'MAKE_FUNCTION', 144: 'EXTENDED_ARG'}
    results = []
    for child in code['consts']:
        if not isinstance(child, dict) or child.get('kind') != 'code':
            continue
        data = child['bytecode']
        instructions, extra = [], 0
        for offset in range(0, len(data), 2):
            op, arg = data[offset:offset + 2]
            arg |= extra
            extra = arg << 8 if op == 144 else 0
            value = arg
            if op == 100:
                value = child['consts'][arg]
                if isinstance(value, dict):
                    value = '<nested code>'
                if isinstance(value, str) and 'http' in value.lower():
                    value = '<vendor route template omitted>'
            elif op in (116, 106, 160):
                value = child['names'][arg]
            elif op in (124, 125):
                value = child['varnames'][arg]
            instructions.append({'offset': offset, 'opcode': ops.get(op, str(op)),
                                 'value': value})
        if child['name'] == 'serverCall':
            results.append({'scope': child['name'], 'instructions': instructions[:19]})
        for index, instruction in enumerate(instructions):
            if instruction['opcode'] == 'LOAD_GLOBAL' and instruction['value'] == 'serverCall':
                results.append({'scope': child['name'],
                                'instructions': instructions[index:index + 17]})
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('executable', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    archive = CArchiveReader(str(args.executable))
    entry = 'dEZignLink_v3.2_uc'
    data = archive.extract(entry)
    reader = Marshal39(data)
    code = reader.read()
    if reader.pos != len(data):
        raise ValueError('Trailing marshal data')
    report = {'artifact': str(args.executable),
              'sha256': hashlib.sha256(args.executable.read_bytes()).hexdigest(),
              'entry': entry, 'entry_sha256': hashlib.sha256(data).hexdigest(),
              'marshal_bytes_consumed': reader.pos,
              'method': 'Static PyInstaller CArchive + Python 3.9 marshal metadata; no execution',
              'scopes': list(walk(code)), 'remote_call_windows': call_windows(code)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=True), encoding='utf-8')
    print(json.dumps({'output': str(args.output), 'scopes': len(report['scopes']),
                      'sha256': report['sha256']}))


if __name__ == '__main__':
    main()
