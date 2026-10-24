"""Report discovery, settings precedence and deterministic layout decisions."""
from dataclasses import asdict, dataclass
from pathlib import Path
import hashlib
import os
import re

FORMATS = {'.xlsx', '.xlsm', '.xlsb', '.xls'}
ENGINE_VERSION = 2


@dataclass
class ReportSettings:
    orientation: str = 'Auto'
    paper: str = 'A4'
    allow_a3: bool = False
    minimum_font: float = 9.0
    margin_mm: float = 12.0
    area_mode: str = 'Existing or detect'
    print_area: str = ''
    title_rows: str = ''
    repair_tables: bool = False
    recalculate: bool = False
    section_breaks: str = ''
    keep_sections: bool = True
    repeat_headings: bool = True


def resolve_settings(batch=None, workbook=None, sheet=None):
    values = asdict(ReportSettings())
    for layer in (batch, workbook, sheet):
        values.update(layer or {})
    settings = ReportSettings(**values)
    if settings.orientation not in ('Auto', 'Portrait', 'Landscape') or settings.paper not in ('A4', 'A3'):
        raise ValueError('Choose A4/A3 and Auto/Portrait/Landscape.')
    if not 5 <= settings.minimum_font <= 20 or not 5 <= settings.margin_mm <= 40:
        raise ValueError('Text target must be 5–20 pt and margins 5–40 mm.')
    if settings.title_rows and not re.fullmatch(r'\$?\d+:\$?\d+', settings.title_rows):
        raise ValueError('Repeated rows must look like 1:4.')
    if settings.section_breaks and not re.fullmatch(r'\d+(\s*,\s*\d+)*', settings.section_breaks):
        raise ValueError('Section breaks must be comma-separated row numbers.')
    return asdict(settings)


def fingerprint(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def discover(inputs, recursive=True, excluded=()):
    excluded = [Path(p).resolve() for p in excluded if p]
    found, ignored, seen, directories = [], [], set(), set()
    def accept(path, root):
        absolute = path.resolve()
        if any(absolute == p or p in absolute.parents for p in excluded):
            return
        key = os.path.normcase(str(absolute))
        if key in seen or path.name.startswith(('~$', '.civtools-')):
            return
        seen.add(key)
        if path.suffix.lower() in FORMATS:
            found.append({'source': str(absolute), 'relative': str(path.relative_to(root))})
        else:
            ignored.append(str(path))
    for entry in inputs:
        path = Path(entry)
        if path.is_file():
            accept(path, path.parent)
        elif path.is_dir():
            for base, dirs, files in os.walk(path, followlinks=False):
                resolved = Path(base).resolve()
                identity = os.path.normcase(str(resolved))
                if identity in directories or any(resolved == p or p in resolved.parents for p in excluded):
                    dirs[:] = []
                    continue
                directories.add(identity)
                dirs[:] = [d for d in dirs if not Path(base, d).is_symlink() and not d.startswith('.civtools-')]
                for name in files:
                    accept(Path(base, name), path)
                if not recursive:
                    break
    return sorted(found, key=lambda x: x['source'].casefold()), ignored


def choose_layout(width, body_font, existing, settings):
    """Return candidate and explanation; physical point widths, never column counts."""
    margin = settings['margin_mm'] * 72 / 25.4
    papers = [settings['paper']]
    if settings['allow_a3'] and 'A3' not in papers:
        papers.append('A3')
    orientations = [settings['orientation']] if settings['orientation'] != 'Auto' else ['Portrait', 'Landscape']
    candidates = []
    for paper in papers:
        for orientation in orientations:
            w, h = (595.276, 841.89) if paper == 'A4' else (841.89, 1190.551)
            if orientation == 'Landscape':
                w, h = h, w
            scale = min(1., max(.01, (w - 2 * margin) / max(width, 1)))
            candidates.append(dict(paper=paper, orientation=orientation, scale=scale,
                                   effective_font=body_font * scale, page_width=w, page_height=h))
    passing = [c for c in candidates if c['effective_font'] >= settings['minimum_font']]
    if passing:
        # Paper preference precedes orientation; preserve author intent if readable.
        chosen = min(passing, key=lambda c: (papers.index(c['paper']), c['orientation'] != existing, c['orientation'] != 'Portrait'))
    else:
        chosen = max(candidates, key=lambda c: c['effective_font'])
    chosen['needs_review'] = not bool(passing)
    chosen['reason'] = (f"{chosen['paper']} {chosen['orientation'].lower()}: estimated body text "
                        f"{chosen['effective_font']:.1f} pt; all columns fit the width.")
    return chosen


def safe_name(name):
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name).strip(' .') or 'Report'
    if name.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL', *('COM'+str(i) for i in range(1,10)), *('LPT'+str(i) for i in range(1,10))}:
        name = '_' + name
    return name[:160]


def versioned_path(path):
    path = Path(path)
    index, candidate = 2, path
    while candidate.exists():
        candidate = path.with_name(f'{path.stem} ({index}){path.suffix}')
        index += 1
    return candidate
