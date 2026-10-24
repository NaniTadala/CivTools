"""Isolated Excel automation. Only this child process owns its Excel instance."""
from collections import Counter
from pathlib import Path
import gc
import shutil
import tempfile
import time
import zipfile
import xml.etree.ElementTree as ET

from .report_models import choose_layout, fingerprint


def preflight(path):
    issues = []
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            if any('macrosheets/' in n.lower() for n in names):
                raise ValueError('Legacy Excel macro sheets require manual publishing.')
            if 'xl/connections.xml' in names:
                raise ValueError('Workbook has data connections. Disable/remove refresh connections in a publishing copy first.')
            if any(n.startswith('xl/externalLinks/') for n in names):
                issues.append('External links: published without updating linked data.')
            missing = errors = 0
            for name in names:
                if name.startswith('xl/worksheets/sheet') and name.endswith('.xml'):
                    for _, cell in ET.iterparse(archive.open(name)):
                        if cell.tag.endswith('}c'):
                            formula = cell.find('{*}f')
                            value = cell.find('{*}v')
                            if formula is not None and (value is None or value.text is None):
                                missing += 1
                            if cell.attrib.get('t') == 'e':
                                errors += 1
                            cell.clear()
            if missing:
                issues.append(f'{missing} formulas have no saved value; calculate and save in Excel before issuing.')
            if errors:
                issues.append(f'{errors} saved formula errors found.')
    else:
        issues.append('Legacy/binary workbook: saved-value and refresh preflight is limited; review before issuing.')
    return issues


def sheet_bounds(sheet):
    # Find actual formulas/content, ignoring inflated formatting-only UsedRange.
    # Positional COM arguments work with late-bound Excel as well as makepy wrappers.
    first_row = sheet.Cells.Find('*', sheet.Cells(sheet.Rows.Count, sheet.Columns.Count), -4123, 2, 1, 1, False, False, False)
    if first_row is None:
        bounds = None
    else:
        last_row = sheet.Cells.Find('*', sheet.Cells(1,1), -4123, 2, 1, 2, False, False, False)
        first_col = sheet.Cells.Find('*', sheet.Cells(sheet.Rows.Count, sheet.Columns.Count), -4123, 2, 2, 1, False, False, False)
        last_col = sheet.Cells.Find('*', sheet.Cells(1,1), -4123, 2, 2, 2, False, False, False)
        bounds = [first_row.Row, first_col.Column, last_row.Row, last_col.Column]
    for i in range(1, sheet.Shapes.Count + 1):
        shape = sheet.Shapes(i)
        try:
            printable = bool(shape.DrawingObject.PrintObject)
        except Exception:
            printable = True
        if shape.Visible and printable:
            a, b = shape.TopLeftCell, shape.BottomRightCell
            if bounds is None:
                bounds = [a.Row, a.Column, b.Row, b.Column]
            else:
                bounds = [min(bounds[0], a.Row), min(bounds[1], a.Column), max(bounds[2], b.Row), max(bounds[3], b.Column)]
    if bounds is None:
        return None
    area = sheet.Range(sheet.Cells(bounds[0], bounds[1]), sheet.Cells(bounds[2], bounds[3]))
    # Expand edge merges; never unmerge or delete report content.
    for cell in (area.Cells(1, 1), area.Cells(area.Rows.Count, area.Columns.Count)):
        merge = cell.MergeArea
        bounds[2] = max(bounds[2], merge.Row + merge.Rows.Count - 1)
        bounds[3] = max(bounds[3], merge.Column + merge.Columns.Count - 1)
    return sheet.Range(sheet.Cells(bounds[0], bounds[1]), sheet.Cells(bounds[2], bounds[3]))


def sample_body_font(sheet, bounds):
    """Count the same populated sample cells with bulk value/font reads.

    Excel returns a size for a uniform range and None for mixed sizes. Only
    mixed rows need individual font queries, and blank cells need none.
    """
    rows, columns = min(bounds.Rows.Count,35), min(bounds.Columns.Count,25)
    sample = sheet.Range(bounds.Cells(1,1),bounds.Cells(rows,columns))
    values = sample.Value2
    if not isinstance(values,tuple):
        values = ((values,),)
    populated = sum(value is not None for row in values for value in row)
    uniform = sample.Font.Size
    if uniform and populated:
        return float(uniform)
    fonts = Counter()
    for r,row in enumerate(values,1):
        occupied = [c for c,value in enumerate(row,1) if value is not None]
        if not occupied:
            continue
        size = sample.Rows(r).Font.Size
        if size:
            fonts[float(size)] += len(occupied)
        else:
            for c in occupied:
                size = sample.Cells(r,c).Font.Size
                if size:
                    fonts[float(size)] += 1
    return fonts.most_common(1)[0][0] if fonts else 11.


def inspect_sheet(sheet):
    chart = sheet.Type == -4109
    record = dict(name=sheet.Name, visible=sheet.Visible == -1, chart=chart, empty=False,
                  area='', existing_area='', title_rows='', width=0., body_font=11., issues=[])
    if chart:
        return record
    bounds = sheet_bounds(sheet)
    record['empty'] = bounds is None
    if bounds is None:
        return record
    record['area'] = bounds.Address
    record['width'] = float(bounds.Width)
    record['existing_area'] = str(sheet.PageSetup.PrintArea or '')
    record['title_rows'] = str(sheet.PageSetup.PrintTitleRows or '')
    record['existing_orientation'] = 'Landscape' if sheet.PageSetup.Orientation == 2 else 'Portrait'
    record['protected'] = bool(sheet.ProtectContents)
    record['objects'] = int(sheet.Shapes.Count)
    record['signature'] = [int(bounds.Columns.Count), round(float(bounds.Width)), int(sheet.Shapes.Count), bool(bounds.MergeCells)]
    record['body_font'] = sample_body_font(sheet,bounds)
    if record['existing_area']:
        existing = sheet.Range(record['existing_area'])
        overlap = sheet.Application.Intersect(existing, bounds)
        if overlap is None or overlap.CountLarge < bounds.CountLarge:
            record['issues'].append('Content exists outside the configured print area. Choose existing area or detected content explicitly.')
    if record['protected']:
        record['issues'].append('Protected worksheet: formatting may require an unlocked publishing copy.')
    return record


def apply_page_setup(sheet, **properties):
    """Commit layout settings together instead of contacting the printer per field."""
    application = sheet.Application
    application.PrintCommunication = False
    try:
        setup = sheet.PageSetup
        for name,value in properties.items():
            setattr(setup,name,value)
    finally:
        application.PrintCommunication = True


def render_sheet(sheet, record, settings, output):
    started = time.perf_counter()
    issues = list(record['issues'])
    if record['chart']:
        sheet.ExportAsFixedFormat(0, str(output))
        return {'reason': 'Printable chart sheet; preserved Excel layout.'}, issues
    setup = sheet.PageSetup
    if settings['print_area']:
        area = sheet.Range(settings['print_area'])
    elif settings['area_mode'] == 'Detected content' or not record['existing_area']:
        area = sheet.Range(record['area'])
    else:
        area = sheet.Range(record['existing_area'])
    try:
        errors = area.SpecialCells(-4123,16)
        if errors is not None:
            issues.append(f'{errors.CountLarge} formula error cells detected in Excel; inspect calculation results.')
    except Exception:
        pass  # Excel raises when there are no matching cells.
    if settings['area_mode'] != 'Existing or detect' or settings['print_area']:
        issues = [x for x in issues if not x.startswith('Content exists outside')]
    if settings['repair_tables']:
        # Opt-in repair retains column widths, merges, numeric formats and object anchors.
        if record['objects']:
            issues.append('Row-height repair skipped: sheet contains anchored objects.')
        elif area.MergeCells is not False and area.MergeCells != 0:
            issues.append('Row-height repair skipped: merged cells require visual review.')
        else:
            area.Rows.AutoFit()
    plan = choose_layout(float(area.Width), record['body_font'], record.get('existing_orientation', 'Portrait'), settings)
    margin = settings['margin_mm'] * 72 / 25.4
    # Leave a clear strip for optional assembly page numbers without covering authors' footers.
    apply_page_setup(sheet,PrintArea=area.Address,PaperSize=9 if plan['paper']=='A4' else 8,
        Orientation=1 if plan['orientation']=='Portrait' else 2,LeftMargin=margin,RightMargin=margin,
        TopMargin=max(margin,float(setup.HeaderMargin)+12),BottomMargin=max(margin,float(setup.FooterMargin)+12,32))
    samples = []
    for row in (1, area.Rows.Count):
        for col in range(1, min(area.Columns.Count,25)+1):
            value = area.Cells(row,col).Value
            if isinstance(value,str) and len(value.strip())>6:
                samples.append(value.strip())
    plan['text_samples'] = samples
    if settings['title_rows']:
        setup.PrintTitleRows = settings['title_rows']
    elif settings['repeat_headings'] and not record['title_rows'] and not record['objects'] and area.MergeCells == 0 and area.Columns.Count >= 3:
        cells = [area.Cells(1,col) for col in range(1,min(area.Columns.Count,30)+1)]
        if all(c.Value is not None and bool(c.Font.Bold) for c in cells):
            setup.PrintTitleRows = f'${area.Row}:${area.Row}'
            plan['reason'] += f' Repeated table heading: row {area.Row}.'
    break_rows = [int(row) for row in settings['section_breaks'].split(',')] if settings['section_breaks'] else []
    if not break_rows and settings['keep_sections'] and area.Rows.Count < 3000:
        # A section heading is a bold merged label with no other row content.
        headings = []
        for offset in range(1,area.Rows.Count+1):
            cell = area.Cells(offset,1)
            if isinstance(cell.Value,str) and cell.Value.strip() and cell.Font.Bold and cell.MergeCells:
                merged = cell.MergeArea
                if merged.Rows.Count == 1:
                    headings.append(cell.Row)
        if len(headings)>=2:
            page_height = plan['page_height'] - setup.TopMargin - setup.BottomMargin
            scale = max(.1, int(plan['scale'] * 98)/100)
            used = 0.
            start = area.Row
            ends = headings[1:] + [area.Row + area.Rows.Count]
            starts = [start] + headings[1:]
            for a,b in zip(starts,ends):
                height = float(sheet.Range(sheet.Cells(a,area.Column),sheet.Cells(b-1,area.Column)).Height)*scale
                if used and used + height > page_height and height <= page_height:
                    break_rows.append(a)
                    used = height
                else:
                    used = (used + height) % page_height
            if break_rows:
                plan['reason'] += ' Calculation headings guided section pagination.'
    if break_rows:
        # Explicit zoom preserves manual breaks; leave a small physical-width tolerance.
        setup.Zoom = max(10, int(plan['scale'] * 98))
        sheet.ResetAllPageBreaks()
        for row in break_rows:
            if row <= area.Row or row >= area.Row + area.Rows.Count:
                raise ValueError(f'Section row {row} is outside the report area.')
            sheet.HPageBreaks.Add(Before=sheet.Cells(row, 1))
    else:
        apply_page_setup(sheet,Zoom=False,FitToPagesWide=1,FitToPagesTall=False)
        if any(sheet.HPageBreaks(i).Type == -4135 for i in range(1,sheet.HPageBreaks.Count+1)):
            issues.append('Native fit-to-width may ignore authored manual page breaks; use section break rows to preserve sections.')
    configured = time.perf_counter()
    sheet.ExportAsFixedFormat(0, str(output), 0, True, False)
    if break_rows:
        spill = any(area.Column < sheet.VPageBreaks(i).Location.Column < area.Column+area.Columns.Count
                    for i in range(1,sheet.VPageBreaks.Count+1))
        if spill:
            setup.Zoom = False
            setup.FitToPagesWide = 1
            setup.FitToPagesTall = False
            sheet.ExportAsFixedFormat(0,str(output),0,True,False)
            issues.append('Section pagination caused horizontal spill; native fit-to-width restored. Review section boundaries.')
    if plan['needs_review']:
        issues.append('Estimated body text is below the readability target.')
    plan['timings'] = dict(layout_seconds=round(configured-started,3),export_seconds=round(time.perf_counter()-configured,3))
    return plan, issues


def excel_request(excel, connection, request):
    workbook = guard = None
    try:
        # The first workbook controls Excel's calculation mode. Recreate this
        # guard for every file, including after recalculating a previous file.
        guard = excel.Workbooks.Add()
        excel.Calculation = -4135
        source = request['source']
        before = fingerprint(source)
        if request.get('expected_fingerprint',before) != before:
            raise ValueError('Source changed during preparation. Prepare again.')
        issues = preflight(source)
        if request.get('settings', {}).get('recalculate'):
            issues = [i for i in issues if 'formulas have no saved value' not in i]
        with tempfile.TemporaryDirectory(prefix='.civtools-excel-') as temp:
            staged = Path(temp, Path(source).name)
            shutil.copy2(source, staged)
            # Explicit blank password avoids an unattended modal password prompt.
            workbook = excel.Workbooks.Open(str(staged), UpdateLinks=0, ReadOnly=True,
                                            Password=request.get('password', ''), WriteResPassword='',
                                            IgnoreReadOnlyRecommended=True, AddToMru=False)
            guard.Close(False)
            guard = None
            excel.Calculation = -4135
            inventory = [inspect_sheet(workbook.Sheets(i)) for i in range(1, workbook.Sheets.Count + 1)]
            result = dict(source=source, fingerprint=before, sheets=inventory, issues=issues)
            if request['operation'] == 'prepare':
                actual = {s['name'] for s in inventory if not s['empty']}
                missing = set(request['selected']) - actual
                if missing:
                    raise ValueError('Selected sheets are now missing or empty: '+', '.join(sorted(missing))+'. Add the workbook again to inspect its new contents.')
                for record in inventory:
                    name = record['name']
                    if name not in request['selected']:
                        continue
                    settings = request['selected'][name]
                    if settings['recalculate']:
                        excel.CalculateFull()
                        if excel.CalculationState != 0:
                            raise ValueError('Excel calculation did not complete.')
                        issues.append('Results recalculated for this export; review before issuing.')
                        issues[:] = [issue for issue in issues if 'formulas have no saved value' not in issue]
                        break
                result['rendered'] = []
                for index, record in enumerate(inventory):
                    name = record['name']
                    if name not in request['selected'] or record['empty']:
                        continue
                    connection.send(('stage', f'Rendering {name}'))
                    output = Path(request['staging'], f'sheet-{index}.pdf')
                    workbook.Sheets(name).Visible = -1
                    plan, warnings = render_sheet(workbook.Sheets(name), record, request['selected'][name], output)
                    result['rendered'].append(dict(name=name, path=str(output), plan=plan, issues=warnings))
            workbook.Close(False)
            workbook = None
        if fingerprint(source) != before:
            raise ValueError('Source changed during preparation. Prepare again.')
        return result
    finally:
        if workbook is not None:
            try:
                workbook.Close(False)
            except Exception:
                pass
        if guard is not None:
            try:
                guard.Close(False)
            except Exception:
                pass
        workbook = guard = None


def excel_process(connection, request=None):
    """Serve a serial batch, recycling the whole application after an error."""
    import pythoncom
    import win32com.client
    import win32process
    pythoncom.CoInitialize()
    excel = None
    try:
        excel = win32com.client.DispatchEx('Excel.Application')
        connection.send(('pid', win32process.GetWindowThreadProcessId(excel.Hwnd)[1]))
        excel.Visible = False
        excel.DisplayAlerts = False
        excel.EnableEvents = False
        excel.AutomationSecurity = 3
        single = request is not None
        while True:
            current = request if single else connection.recv()
            if current is None:
                break
            result = excel_request(excel,connection,current)
            connection.send(('result',result))
            if single:
                break
    except EOFError:
        pass
    except Exception as error:
        connection.send(('error',str(error)))
    finally:
        if excel is not None:
            try:
                excel.Quit()
            except Exception:
                pass
        excel = None
        gc.collect()
        pythoncom.CoUninitialize()
        connection.close()
