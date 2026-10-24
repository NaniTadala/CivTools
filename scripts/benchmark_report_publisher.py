"""Measure Excel preparation separately from PDF assembly and preview.

Uses the synthetic publisher workbooks, leaving their originals unchanged.
Run with --count 30 to repeat the sample workload at batch size.
"""
import argparse
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--count', type=int, default=3)
    parser.add_argument('--label', default='baseline')
    args = parser.parse_args()
    from civtools.core.report_models import fingerprint, resolve_settings
    from civtools.core.report_service import ExcelSession, pdf_task
    samples = sorted((ROOT/'artifacts'/'publisher-polish'/'samples').glob('*.xlsx'))
    if not samples:
        raise SystemExit('Create the synthetic reports with preview_report_publisher.py first.')
    output = ROOT/'artifacts'/'publisher-performance'/args.label
    output.mkdir(parents=True,exist_ok=True)
    results = dict(count=args.count, workload='Repeated synthetic two-sheet workbooks', reports=[])
    started = time.perf_counter()
    inventories = []
    with ExcelSession(lambda *args:None) as excel:
        for index in range(args.count):
            source = samples[index % len(samples)]
            before = time.perf_counter()
            inventory = excel.call(dict(operation='inspect',source=str(source)))
            inventories.append(inventory)
            results['reports'].append(dict(name=source.name,inspect_seconds=round(time.perf_counter()-before,3)))
            print(f'Inspected {index+1}/{args.count}',flush=True)
    results['intake_seconds'] = round(time.perf_counter()-started,3)
    entries = []
    started = time.perf_counter()
    with ExcelSession(lambda *args:None) as excel:
        for index,inventory in enumerate(inventories):
            stage = output/str(index)
            stage.mkdir(exist_ok=True)
            before = time.perf_counter()
            selected = {s['name']:resolve_settings() for s in inventory['sheets'] if s['visible'] and not s['empty']}
            rendered = excel.call(dict(operation='prepare',source=inventory['source'],selected=selected,staging=str(stage)))
            results['reports'][index]['prepare_seconds'] = round(time.perf_counter()-before,3)
            results['reports'][index]['sheet_timings'] = [s['plan'].get('timings',{}) for s in rendered['rendered']]
            print(f'Prepared {index+1}/{args.count}',flush=True)
            before = time.perf_counter()
            for sheet in rendered['rendered']:
                pdf_task('validate',dict(path=sheet['path'],minimum_font=9,text_samples=sheet['plan'].get('text_samples',[])))
            artifact = stage/'workbook.pdf'
            pdf_task('assemble',dict(entries=rendered['rendered'],output=str(artifact)))
            results['reports'][index]['validate_assemble_seconds'] = round(time.perf_counter()-before,3)
            assert fingerprint(inventory['source']) == inventory['fingerprint']
            entries.append(dict(name=f'Report {index+1}',path=str(artifact)))
    results['prepare_seconds'] = round(time.perf_counter()-started,3)
    combined = output/'combined.pdf'
    before = time.perf_counter()
    pdf_task('assemble',dict(entries=entries,output=str(combined)))
    results['combined_assembly_seconds'] = round(time.perf_counter()-before,3)
    before = time.perf_counter()
    sizes = pdf_task('page_sizes',dict(path=str(combined)))
    pdf_task('preview',dict(path=str(combined),page=0,fit_width=800))
    results['page_count'] = len(sizes)
    results['first_page_seconds'] = round(time.perf_counter()-before,3)
    (output/'timings.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
    print(json.dumps(results,indent=2),flush=True)


if __name__ == '__main__':
    main()
