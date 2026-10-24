"""Supervise bounded Excel jobs and publish reviewed PDF artifacts."""
from multiprocessing import get_context
from pathlib import Path
import json
import os
import shutil
import tempfile
import time
import uuid

from .report_models import ENGINE_VERSION, fingerprint, safe_name, versioned_path


def commit_file(staging, target):
    if os.name == 'nt':
        # Windows rename is atomic on the same volume and refuses an existing target.
        os.rename(staging, target)
    else:
        os.link(staging, target)


class ExcelSession:
    """Reuse one privately owned Excel process for a serial, bounded batch.

    A failed/timed-out request discards the process; the next call starts fresh.
    The per-file watchdog and exact process handle also apply to reused Excel.
    """
    def __init__(self, report, stop_now=None, timeout=180, max_requests=32):
        self.report = report
        self.stop_now = stop_now
        self.timeout = timeout
        self.max_requests = max_requests
        self.process = self.parent = self.handle = None
        self.requests = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close(graceful=exc_type is None)

    def _start(self):
        from .report_excel_worker import excel_process
        context = get_context('spawn')
        self.parent, child = context.Pipe(duplex=True)
        self.process = context.Process(target=excel_process, args=(child,))
        try:
            self.process.start()
        except BaseException:
            self.parent.close()
            self.parent = self.process = None
            raise
        finally:
            child.close()
        self.requests = 0

    def call(self, request):
        if self.stop_now is not None and self.stop_now.is_set():
            self.close(graceful=False)
            raise InterruptedError('Stopped. Completed reports are retained.')
        try:
            if self.requests >= self.max_requests:
                self.close()
            if self.process is None:
                self._start()
            deadline = time.monotonic() + self.timeout
            self.parent.send(request)
            while True:
                if self.stop_now is not None and self.stop_now.is_set():
                    raise InterruptedError('Stopped. Completed reports are retained.')
                if time.monotonic() > deadline:
                    raise TimeoutError('Excel timed out. This file can be retried.')
                if self.parent.poll(.1):
                    try:
                        kind, value = self.parent.recv()
                    except EOFError:
                        break
                    if kind == 'pid':
                        import win32api
                        self.handle = win32api.OpenProcess(0x0001 | 0x00100000, False, value)
                    elif kind == 'stage':
                        self.report('stage', value)
                    elif kind == 'error':
                        raise RuntimeError(value)
                    elif kind == 'result':
                        self.requests += 1
                        return value
                elif not self.process.is_alive():
                    break
            raise RuntimeError('Excel worker exited without a result.')
        except BaseException:
            self.close(graceful=False)
            raise

    def close(self, graceful=True):
        process, parent, handle = self.process, self.parent, self.handle
        self.process = self.parent = self.handle = None
        if process is None:
            return
        try:
            if graceful and process.is_alive():
                try:
                    parent.send(None)
                    process.join(2)
                except (OSError, EOFError):
                    pass
            if process.is_alive():
                process.terminate()
            process.join(2)
        finally:
            try:
                if handle is not None:
                    import win32api
                    import win32event
                    if win32event.WaitForSingleObject(handle, 0) == 258:
                        win32api.TerminateProcess(handle, 1)
                    handle.Close()
            finally:
                parent.close()
                process.close()


def excel_call(request, report, stop_now=None, timeout=180):
    """Single-request compatibility entry point; batches use ExcelSession."""
    with ExcelSession(report, stop_now, timeout) as session:
        return session.call(request)


def cached_sheet_results(prepared, settings, source_fingerprint):
    """Return validated sheets from the same saved workbook and layout settings."""
    stored_settings = {**(prepared or {}).get('available_settings',{}),**(prepared or {}).get('settings',{})}
    if (not prepared or prepared.get('engine_version') != ENGINE_VERSION
            or prepared.get('fingerprint') != source_fingerprint
            or any(s.get('recalculate') for s in settings.values())
            or any(s and s.get('recalculate') for s in stored_settings.values())):
        return {}
    available = {s['name']:s for s in prepared.get('available_rendered',[])}
    available.update({s['name']:s for s in prepared.get('rendered',[])})
    return {name:available[name] for name,layout in settings.items()
            if name in available and stored_settings.get(name)==layout and Path(available[name]['path']).is_file()}


def can_reuse_prepared(record, prepared, settings, source_fingerprint=None):
    """Reuse only current source bytes, selected order, settings and artifacts."""
    if (not prepared or prepared.get('engine_version') != ENGINE_VERSION
            or prepared.get('settings') != settings
            or any(s['recalculate'] for s in settings.values())
            or [s['name'] for s in prepared.get('rendered',[])] != list(settings)):
        return False
    try:
        source_fingerprint = source_fingerprint or fingerprint(record['source'])
        return (Path(prepared['artifact']).is_file()
                and len(cached_sheet_results(prepared,settings,source_fingerprint))==len(settings))
    except (OSError, KeyError):
        return False


def prepare_report(record, settings, workbook_settings, staging, excel, pdf, report,
                   cached=None, password='', force=False):
    """Render changed sheets, validate them, then assemble selected cached pages."""
    source = record['source']
    source_hash = fingerprint(source)
    if not force and can_reuse_prepared(record,cached,settings,source_hash):
        report('stage',f"Reusing prepared report: {Path(source).name}")
        return cached
    stored_settings = {name:layout for name,layout in
        {**(cached or {}).get('available_settings',{}),**(cached or {}).get('settings',{})}.items() if layout}
    available_settings = {**stored_settings,**settings}
    available = {} if force else cached_sheet_results(cached,available_settings,source_hash)
    pending = {name:layout for name,layout in settings.items() if name not in available}
    stage = Path(staging)
    stage.mkdir(parents=True,exist_ok=True)
    if pending:
        fresh = excel.call(dict(operation='prepare',source=source,password=password,selected=pending,
            settings=workbook_settings,staging=str(stage),expected_fingerprint=source_hash))
        if fresh['fingerprint'] != source_hash:
            raise ValueError('Source changed during preparation. Prepare again.')
        workbook_issues = list(fresh['issues'])
        for sheet in fresh['rendered']:
            name = sheet['name']
            layout = settings[name]
            validation = pdf.call('report',report,'validate',dict(path=sheet['path'],minimum_font=layout['minimum_font'],text_samples=sheet['plan'].get('text_samples',[])))
            if (validation['median_font'] is not None and validation['median_font'] < layout['minimum_font']-.3
                    and layout['orientation']=='Auto' and sheet['plan'].get('orientation')=='Portrait'):
                retry_stage = stage/('alternative-'+uuid.uuid4().hex)
                retry_stage.mkdir()
                alternative = dict(layout,orientation='Landscape')
                retry = excel.call(dict(operation='prepare',source=source,password=password,selected={name:alternative},
                    staging=str(retry_stage),expected_fingerprint=source_hash))
                if retry['fingerprint'] != source_hash:
                    raise ValueError('Source changed during preparation. Prepare again.')
                candidate = retry['rendered'][0]
                second = pdf.call('report',report,'validate',dict(path=candidate['path'],minimum_font=alternative['minimum_font'],text_samples=candidate['plan'].get('text_samples',[])))
                if (second['median_font'] or 0) > validation['median_font'] and len(second['issues']) <= len(validation['issues']):
                    sheet = candidate
                    sheet['plan']['reason'] += ' Landscape selected after checking actual rendered text.'
                    validation = second
            sheet['issues'].extend(validation['issues'])
            available[name] = sheet
        if not set(settings)<=set(available):
            raise ValueError('Some selected sheets were not rendered. Prepare again.')
    else:
        fresh = cached
        workbook_issues = list(cached.get('workbook_issues',[]))
    rendered = [available[name] for name in settings]
    issues = workbook_issues+[f"{s['name']}: {issue}" for s in rendered for issue in s['issues']]
    artifact = stage/'prepared.pdf'
    page_map = pdf.call('report',report,'assemble',dict(entries=[dict(name=s['name'],path=s['path']) for s in rendered],output=str(artifact)))
    if fingerprint(source) != source_hash:
        raise ValueError('Source changed during preparation. Prepare again.')
    return dict(fresh,source=source,fingerprint=source_hash,relative=record['relative'],artifact=str(artifact),
        rendered=rendered,available_rendered=list(available.values()),settings=settings,
        available_settings={name:available_settings[name] for name in available},issues=issues,
        page_map=page_map,workbook_issues=workbook_issues,engine_version=ENGINE_VERSION)


def pdf_task(operation, payload):
    """Called only in the shared isolated PDF worker."""
    import pymupdf as fitz
    if operation == 'page_sizes':
        with fitz.open(payload['path']) as pdf:
            return [(page.rect.width,page.rect.height) for page in pdf]
    if operation == 'preview':
        with fitz.open(payload['path']) as pdf:
            page = pdf[max(0, min(payload.get('page', 0), len(pdf) - 1))]
            zoom = payload.get('zoom', 1.)
            if payload.get('fit_width'):
                zoom = max(.15,min(2.5,payload['fit_width']/page.rect.width))
            return dict(pages=len(pdf), image=page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False).tobytes('png'))
    if operation == 'assemble':
        document = fitz.open()
        toc = []
        page_map = []
        front = bool(payload.get('cover') or payload.get('contents'))
        entries = payload['entries']
        contents_pages = (len(entries) + 34) // 35 if payload.get('contents') else 0
        front_count = int(bool(payload.get('cover'))) + contents_pages
        if payload.get('cover'):
            page = document.new_page()
            page.insert_textbox(fitz.Rect(50, 180, 545, 400), payload['cover'], fontsize=22)
        for _ in range(contents_pages):
            document.new_page()
        for entry in entries:
            start = len(document) + 1
            with fitz.open(entry['path']) as part:
                child_toc = part.get_toc()
                document.insert_pdf(part)
            toc.append([1, entry['name'], start])
            toc.extend([level+1,title,page+start-1] for level,title,page in child_toc if page>0)
            page_map.append(dict(name=entry['name'], first=start, last=len(document)))
        if not entries:
            document.close()
            raise ValueError('Select at least one report to publish.')
        document.set_toc(toc)
        if contents_pages:
            for index, entry in enumerate(page_map):
                page = document[int(bool(payload.get('cover'))) + index // 35]
                if index % 35 == 0:
                    page.insert_text((45, 55), 'Contents', fontsize=20)
                y = 90 + (index % 35) * 19
                label = f"{entry['name'][:72]}    {entry['first']}"
                page.insert_text((45, y), label, fontsize=10)
                page.insert_link({'kind':fitz.LINK_GOTO, 'from':fitz.Rect(45,y-12,550,y+3), 'page':entry['first']-1})
        if payload.get('numbering'):
            for index in range(front_count, len(document)):
                page = document[index]
                page.insert_text((page.rect.width / 2 - 30, page.rect.height - 10),
                                 f'{index + 1} / {len(document)}', fontsize=8)
        document.save(payload['output'], garbage=3, deflate=True)
        document.close()
        return page_map
    if operation == 'validate':
        issues, count = [], 0
        with fitz.open(payload['path']) as pdf:
            count = len(pdf)
            fonts = []
            for index, page in enumerate(pdf):
                data = page.get_text('dict')
                spans = [span for block in data['blocks'] if 'lines' in block for line in block['lines'] for span in line['spans'] if span['text'].strip()]
                fonts.extend(span['size'] for span in spans if len(span['text'].strip()) > 4)
                if not spans and not page.get_images() and not page.get_drawings():
                    issues.append(f'Page {index+1} appears empty; retained for review.')
            median = sorted(fonts)[len(fonts)//2] if fonts else None
            if median is not None and median < payload['minimum_font'] - .3:
                issues.append('Rendered body text is below the readability target.')
            text = ''.join(page.get_text() for page in pdf)
            normalise = lambda value: ''.join(value.split()).casefold()
            for sample in payload.get('text_samples',[]):
                if normalise(sample) not in normalise(text):
                    issues.append(f'Expected edge text was not found in the PDF: {sample[:60]}. Review clipping or font rendering.')
        if not count:
            raise ValueError('Excel produced an empty PDF.')
        return dict(pages=count, issues=issues, median_font=median)
    raise ValueError('Unknown PDF operation.')


def publish(prepared, destination, pdf, report, *, combined=False, cover='', contents=False, numbering=False, per_sheet=False, combined_artifact=None):
    """Commit exact prepared bytes. Recheck source hashes before each publication."""
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    published, entries = [], []
    for item in prepared:
        if fingerprint(item['source']) != item['fingerprint']:
            raise ValueError(f"{Path(item['source']).name} changed. Prepare it again before exporting.")
        relative = Path(item['relative'])
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('Invalid output relative path.')
        target = destination.joinpath(*[safe_name(p) for p in relative.parent.parts], safe_name(relative.stem) + '.pdf')
        target.parent.mkdir(parents=True, exist_ok=True)
        target = versioned_path(target)
        fd, stage = tempfile.mkstemp(prefix='.civtools-', suffix='.pdf', dir=target.parent)
        os.close(fd)
        try:
            shutil.copyfile(item['artifact'], stage)
            # Same-volume link creates the complete file atomically and refuses overwrite.
            commit_file(stage, target)
        finally:
            Path(stage).unlink(missing_ok=True)
        published.append(str(target))
        entries.append(dict(name=relative.stem, path=str(target)))
        if per_sheet:
            for sheet in item.get('rendered',[]):
                folder = target.parent / safe_name(relative.stem)
                folder.mkdir(exist_ok=True)
                sheet_target = versioned_path(folder / (safe_name(sheet['name'])+'.pdf'))
                fd, sheet_stage = tempfile.mkstemp(prefix='.civtools-',suffix='.pdf',dir=folder)
                os.close(fd)
                try:
                    shutil.copyfile(sheet['path'],sheet_stage)
                    commit_file(sheet_stage,sheet_target)
                    published.append(str(sheet_target))
                finally:
                    Path(sheet_stage).unlink(missing_ok=True)
    if combined and entries:
        final = versioned_path(destination / 'Combined report.pdf')
        fd, stage = tempfile.mkstemp(prefix='.civtools-', suffix='.pdf', dir=destination)
        os.close(fd)
        Path(stage).unlink()
        try:
            if combined_artifact:
                shutil.copyfile(combined_artifact,stage)
            else:
                pdf.call('report', report, 'assemble', dict(entries=entries, output=stage, cover=cover, contents=contents, numbering=numbering))
            commit_file(stage, final)
            published.append(str(final))
        finally:
            Path(stage).unlink(missing_ok=True)
    manifest = versioned_path(destination / 'Export summary.json')
    manifest.write_text(json.dumps({'outputs': published, 'reports': prepared}, indent=2), encoding='utf-8')
    return published
