"""Background jobs: serialized CAD access, transactional workbooks, bounded PDF rendering."""
import os
from pathlib import Path
import shutil
import tempfile
import threading
import time
from dataclasses import dataclass
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from multiprocessing import get_context

from PySide6.QtCore import QObject, QRunnable, Signal
from .core.results import OperationResult

_cad_lock = threading.Lock()


class JobSignals(QObject):
    event = Signal(str, object)
    succeeded = Signal(object)
    failed = Signal(str)
    finished = Signal()


class Job(QRunnable):
    def __init__(self, operation, *, cad=False):
        super().__init__()
        self.operation = operation
        self.cad = cad
        self.signals = JobSignals()

    def run(self):
        logs = []
        last_flush = time.monotonic()
        def flush():
            nonlocal last_flush
            if logs:
                self.signals.event.emit("log", "\n".join(logs))
                logs.clear()
            last_flush = time.monotonic()

        def report(kind, value):
            if kind == "log":
                logs.append(str(value))
                if len(logs) >= 100 or time.monotonic() - last_flush >= .1:
                    flush()
            else:
                self.signals.event.emit(kind, value)
        try:
            if self.cad:
                            # Use a more specific message for STAAD.Pro operations (serialized COM access)
                            self.signals.event.emit("stage", "Connecting to STAAD.Pro…")
                            with _cad_lock:
                    import pythoncom
                    pythoncom.CoInitialize()
                    try:
                        result = self.operation(report)
                    finally:
                        pythoncom.CoUninitialize()
            else:
                result = self.operation(report)
            flush()
            self.signals.succeeded.emit(result)
        except Exception as error:
            flush()
            self.signals.failed.emit(str(error))
        finally:
            self.signals.finished.emit()


def run_quantities(source, destination, files, consolidate, report):
    from .core.quantities import QuantityService
    source, destination = Path(source), Path(destination)
    if source.suffix.lower() != destination.suffix.lower():
        raise ValueError("Keep the same workbook extension to preserve its format and macros.")
    # Work in the destination directory so the final rename is atomic. A failed
    # extraction never damages either the original or a previous output workbook.
    handle, staging = tempfile.mkstemp(suffix=source.suffix, prefix=".civtools-", dir=destination.parent)
    os.close(handle)
    try:
        shutil.copy2(source, staging)
        service = QuantityService(report)
        if consolidate:
            service._run_consolidation_process(staging)
        else:
            service._run_extraction_process(files, staging)
        service.finish()
        report("stage", "Saving output workbook…")
        os.replace(staging, destination)
        counts = getattr(service, "counts", {})
        summary = f"{'Consolidation' if consolidate else 'Extraction'} completed."
        if counts:
            summary += f" {counts['successful']} drawings extracted; {counts['failed']} without usable tables."
        return OperationResult(summary + f"\nSaved to {destination}", str(destination), **counts)
    finally:
        if os.path.exists(staging):
            os.unlink(staging)


def run_mapper(path, height, offset, report, sheet_name=None):
    from .core.mapper import MapperService
    service = MapperService(report)
    try:
        service._plot_boxes_job(path, height, offset, sheet_name)
        return service.finish()
    finally:
        workbook = getattr(service, "_plot_workbook", None)
        if workbook:
            workbook.close()


def run_dj(config, report):
    from .core.dj import DJService
    service = DJService(report)
    service.assign_dj_parameters(config)
    return OperationResult(str(service.finish()), successful=getattr(service, "processed_count", 0))


@dataclass
class GeneratedParameterCommands:
    kind: str
    text: str
    model_path: str
    member_count: int
    warning_count: int

    def __str__(self):
        return (
            f"Generated {self.kind} commands from {self.model_path} · "
            f"{self.member_count:,} members scanned · "
            f"{self.warning_count:,} warnings"
        )


def run_staad_parameter_generation(kind, parameters, report):
    from .core.staad_parameters import (
        ConcreteGenerator,
        MAX_LINE_DEFAULT,
        StaadService,
        SteelGenerator,
        TOL_DEFAULT,
    )

    service = StaadService()
    report("stage", "Scanning the active STAAD.Pro model…")
    members = service.load_model(TOL_DEFAULT, False)
    generator_type = ConcreteGenerator if kind == "concrete" else SteelGenerator
    text = generator_type(service, MAX_LINE_DEFAULT).generate(parameters, True)
    warning_count = sum(
        line.startswith("* WARNING") for line in text.splitlines()
    )
    return GeneratedParameterCommands(
        kind=kind,
        text=text,
        model_path=service.model_path,
        member_count=len(members),
        warning_count=warning_count,
    )


def run_piperack(config, report):
    from .core.piperack import PipeRackGenerator
    report("log", "Connecting to STAAD.Pro and generating the structure…")
    generator = PipeRackGenerator(report)
    if not generator.create_comprehensive_pipe_rack(config) or not generator.nodes:
        raise RuntimeError("Model generation failed. Ensure a blank STAAD model is open.")
    return OperationResult(f"Generated {len(generator.nodes):,} nodes and {len(generator.beams):,} beams in STAAD.Pro.", successful=len(generator.beams))


def pdf_process_request(operation, args):
    """Executed serially inside the PDF process; no Qt objects cross the boundary."""
    events = []
    def report(kind, message):
        if len(events) < 1000:
            events.append((kind, message))
    if operation == "selftest":
        import pymupdf as fitz
        with fitz.open() as document:
            page = document.new_page(width=100, height=100)
            page.insert_text((10, 30), "CivTools")
            return page.get_pixmap(alpha=False).tobytes("png"), []
    function = {"scan": scan_pdfs, "render": render_pdf}[operation]
    if operation == "scan":
        result = function(args[0], report, args[1])
    else:
        result = function(args[0], report)
    return result, events


class PdfProcess:
    """One lazily started process owns all PyMuPDF work for this workspace."""
    def __init__(self):
        self.executor = None
        self.lock = threading.Lock()

    def call(self, operation, report, *args):
        if operation == "scan" and not Path(args[0]).is_dir():
            return []
        with self.lock:
            if self.executor is None:
                self.executor = ProcessPoolExecutor(max_workers=1, mp_context=get_context("spawn"))
            future = self.executor.submit(pdf_process_request, operation, args)
        try:
            result, events = future.result()
        except BrokenProcessPool as error:
            self.close()
            raise RuntimeError("The PDF worker stopped unexpectedly. Refresh the library to restart it.") from error
        for kind, message in events:
            report(kind, message)
        return result

    def close(self):
        with self.lock:
            if self.executor:
                self.executor.shutdown(wait=False, cancel_futures=True)
                self.executor = None


def scan_pdfs(folder, report, cache_path=None):
    import pymupdf as fitz
    import json
    documents = []
    cached = {}
    if cache_path:
        try:
            cached = json.loads(Path(cache_path).read_text(encoding="utf-8"))
            if not isinstance(cached, dict):
                cached = {}
        except (OSError, ValueError):
            pass
    updated = {}
    if not Path(folder).is_dir():
        return documents
    for path in sorted(Path(folder).glob("*")):
        if path.suffix.lower() != ".pdf":
            continue
        try:
            stat = path.stat()
            entry = cached.get(str(path))
            if isinstance(entry, dict) and entry.get("size") == stat.st_size and entry.get("mtime") == stat.st_mtime_ns:
                pages = int(entry["pages"])
            else:
                with fitz.open(path) as pdf:
                    pages = len(pdf)
            updated[str(path)] = {"size": stat.st_size, "mtime": stat.st_mtime_ns, "pages": pages}
            documents.append((path.name, str(path), stat.st_size, pages, stat.st_mtime_ns))
        except Exception as error:
            report("log", f"Could not read {path.name}: {error}")
    if cache_path:
        try:
            cache_path = Path(cache_path)
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            staging = cache_path.with_suffix(".tmp")
            staging.write_text(json.dumps(updated), encoding="utf-8")
            staging.replace(cache_path)
        except OSError:
            pass  # A read-only cache must not stop the library from loading.
    return documents


def render_pdf(path, report):
    import pymupdf as fitz
    with fitz.open(path) as pdf:
        page = pdf.load_page(0)
        scale = min(700 / max(page.rect.width, 1), 850 / max(page.rect.height, 1))
        return page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False).tobytes("png")
