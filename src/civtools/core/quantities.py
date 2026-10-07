import os
import sys
import re
from pathlib import Path
import ezdxf
import openpyxl
from openpyxl.styles import Font, PatternFill, Border, Side, Alignment
from openpyxl.utils import get_column_letter
from ezdxf.entities.acad_table import read_acad_table_content
from .callbacks import ServiceCallbacks
from .callbacks import MessageKinds as messagebox

def write_to_excel(worksheet, data, current_row_idx, is_header=False, is_filename=False, is_error=False, method_type=None, start_col_offset=0):
    """
    Writes a row of data to the Excel worksheet with basic formatting.
    Returns the new current_row_idx after writing.
    start_col_offset: Number of columns to offset the start of data writing.
    """
    start_col = 1 + start_col_offset
    if is_filename:
        worksheet.cell(row=current_row_idx, column=start_col).value = data[0]
        worksheet.cell(row=current_row_idx, column=start_col).font = Font(bold=True)
        if method_type:
            worksheet.cell(row=current_row_idx, column=start_col + 1).value = method_type
            worksheet.cell(row=current_row_idx, column=start_col + 1).font = Font(italic=True, color='008080')
        return current_row_idx + 1
    if is_error:
        worksheet.cell(row=current_row_idx, column=start_col).value = data[0]
        worksheet.cell(row=current_row_idx, column=start_col + 1).value = data[1]
        worksheet.cell(row=current_row_idx, column=start_col + 1).font = Font(color='FF0000')
        return current_row_idx + 1
    for (col_index, cell_value) in enumerate(data):
        cell = worksheet.cell(row=current_row_idx, column=start_col + col_index)
        cell.value = cell_value
        if is_header:
            cell.font = Font(bold=True)
            cell.fill = PatternFill(start_color='C8C8C8', end_color='C8C8C8', fill_type='solid')
    return current_row_idx + 1

def extract_table_data_from_dxf(dxf_path, log_func):
    """
    Enhanced version that searches for tables in both model space and all paper space layouts.
    Extracts ALL "Approximate Quantities" tables found in any space.
    Returns a list of lists, where each inner list represents a row of data to be written to Excel,
    or a list with an error message.
    """
    filename = os.path.basename(dxf_path)
    extracted_rows = []
    try:
        doc = ezdxf.readfile(dxf_path)
    except ezdxf.DXFError as e:
        extracted_rows.append([filename, f'ERROR: Could not open DXF file - {e}'])
        log_func(f'ERROR: Could not open DXF file {filename}: {e}', is_error=True)
        return (extracted_rows, False)
    except Exception as e:
        extracted_rows.append([filename, f'ERROR: An unexpected error occurred - {e}'])
        log_func(f'ERROR: An unexpected error occurred with {filename}: {e}', is_error=True)
        return (extracted_rows, False)
    found_any_table = False
    tables_found_count = 0
    spaces_to_search = []
    spaces_to_search.append(('Model Space', doc.modelspace()))
    for layout_name in doc.layout_names():
        if layout_name != 'Model':
            try:
                layout = doc.layout(layout_name)
                spaces_to_search.append((f'Layout: {layout_name}', layout))
            except Exception as e:
                log_func(f"Warning: Could not access layout '{layout_name}' in {filename}: {e}", is_error=True)
    log_func(f'Searching {len(spaces_to_search)} spaces in {filename}')
    for (space_name, space) in spaces_to_search:
        for acad_table_entity in space.query('ACAD_TABLE'):
            try:
                table_content = read_acad_table_content(acad_table_entity)
                table_has_title = False
                for row in table_content:
                    for cell_value in row:
                        if any((phrase.upper() in str(cell_value).upper() for phrase in ['APPROXIMATE QUANTITIES', 'APPROXIMATE QUANTITY'])):
                            table_has_title = True
                            break
                    if table_has_title:
                        break
                if table_has_title and table_content:
                    tables_found_count += 1
                    method_info = f'Table #{tables_found_count} from {space_name}'
                    extracted_rows.append([filename, method_info, 'filename_header'])
                    for (i, row_data) in enumerate(table_content):
                        extracted_rows.append(row_data + (['is_header'] if i == 0 else []))
                    extracted_rows.append([])
                    log_func(f'SUCCESS: Extracted table #{tables_found_count} from {space_name} in {filename}')
                    found_any_table = True
            except Exception as e:
                log_func(f'Warning: Failed to read ACAD_TABLE content from {space_name} in {filename}: {e}', is_error=True)
                continue
    if found_any_table:
        log_func(f"SUMMARY: Found {tables_found_count} 'Approximate Quantities' tables in {filename}")
        return (extracted_rows, True)
    else:
        extracted_rows.append([filename, "No 'Approximate Quantities' table found in any space."])
        log_func(f"INFO: No 'Approximate Quantities' tables found in any space in {filename}", is_error=False)
        return (extracted_rows, False)

def parse_drawing_name(cell_value):
    return str(cell_value).strip().lower().replace('.dxf', '')

def is_drawing_name(cell_value):
    return cell_value is not None and '.dxf' in str(cell_value).lower()

def is_header_or_subtotal(cell_a, cell_b):
    lower_a = str(cell_a).strip().lower()
    if cell_a is None or cell_b is None:
        return True
    if str(cell_a).strip() == '' or str(cell_b).strip() == '':
        return True
    keywords = ['total', 'description', 'approximate quantities', 'reinforcement', 'insert plate', 'structural steel', 'file name', 'extraction status / method', 'summary', 'subtotal']
    for kw in keywords:
        if kw in lower_a:
            return True
    return False

def read_structure_mapping(mapping_filepath):
    """
    Reads structure mapping from the first sheet of an Excel file.
    Returns a dictionary: {drawing_name (lowercase, no .dxf): structure_name}.
    """
    structure_dict = {}
    try:
        workbook = openpyxl.load_workbook(mapping_filepath, data_only=True, read_only=True)
        target_sheet_name = 'Drawing_Structure_Mapping'
        ws = None
        if target_sheet_name in workbook.sheetnames:
            ws = workbook[target_sheet_name]
        else:
            raise ValueError(f"Required sheet '{target_sheet_name}' not found in the Excel file.")
        for drawing_name_cell, structure_name_cell in ws.iter_rows(min_row=2, max_col=2, values_only=True):
            if drawing_name_cell is None or structure_name_cell is None:
                continue
            drawing_name = str(drawing_name_cell).strip().lower()
            structure_name = str(structure_name_cell).strip()
            if drawing_name and structure_name and (not is_header_or_subtotal(drawing_name, structure_name)):
                drawing_name = drawing_name.replace('.dxf', '')
                structure_dict[drawing_name] = structure_name
        return structure_dict
    except Exception as e:
        raise ValueError(f"Error reading structure mapping file '{mapping_filepath}': {e}")
    finally:
        if 'workbook' in locals():
            workbook.close()

def filter_quantity(qty_text):
    """
    Removes common units and extraneous text from quantity string.
    """
    if qty_text is None:
        return ''
    result = str(qty_text).strip()
    units = ['cu.m', 'MT', 'NOS', 'NO', 'KG', 'M']
    for unit in units:
        result = re.sub('\\b' + re.escape(unit) + '\\b', '', result, flags=re.IGNORECASE).strip()
    try:
        float(result)
        return result
    except ValueError:
        return ''

def process_material_data(extracted_data, structure_dict):
    """
    Processes extracted DXF data to consolidate materials by structure.
    Returns (material_dict, material_list)
    material_dict: { (material_name, structure_name): total_quantity }
    material_list: { material_name: True (for unique tracking) }
    """
    material_dict = {}
    material_list = {}
    current_drawing = ''
    for row_data in extracted_data:
        if not row_data:
            continue
        if len(row_data) >= 1 and is_drawing_name(row_data[0]):
            current_drawing = parse_drawing_name(row_data[0])
        elif current_drawing and len(row_data) >= 2:
            material_name = str(row_data[0]).strip()
            quantity_text = str(row_data[1]).strip()
            if is_header_or_subtotal(material_name, quantity_text):
                continue
            quantity = filter_quantity(quantity_text)
            if quantity and structure_dict.get(current_drawing):
                structure_name = structure_dict[current_drawing]
                combined_key = (material_name, structure_name)
                material_dict[combined_key] = material_dict.get(combined_key, 0.0) + float(quantity)
                material_list[material_name] = True
    return (material_dict, material_list)

def define_category_config():
    """Defines material categories and their patterns."""
    config = []
    config.append(('P.C.C', ['P.C.C', 'PCC']))
    config.append(('CONCRETE', ['CONCRETE']))
    config.append(('REINFORCEMENT', ['T8', 'T10', 'T12', 'T16', 'T20', 'T25', 'T32', 'T40']))
    config.append(('INSERT PLATE', ['P-S', 'IP-S', 'I-S', 'E-S', 'P-I']))
    config.append(('UC SECTIONS', ['UC']))
    config.append(('UB SECTIONS', ['UB']))
    config.append(('HE SECTIONS', ['HEA', 'HEB', 'HEM']))
    config.append(('CHANNEL SECTIONS', ['ISMC', 'CHANNEL']))
    config.append(('ANGLE SECTIONS', ['ISA', 'ANGLE']))
    config.append(('CUT-TEE SECTIONS', ['CT']))
    config.append(('PLATE SECTIONS', ['PLT', 'PLATE']))
    config.append(('CIRCULAR HOLLOW SECTIONS', ['RHS', 'CHS']))
    config.append(('RECTANGULAR HOLLOW SECTIONS', ['SHS']))
    config.append(('ANCHOR BOLTS', ['M20', 'M24', 'M30 (TYPE-A)']))
    config.append(('BASE PLATE', ['25 THK', '30 THK']))
    config.append(('OTHER MATERIALS', []))
    return config

def collect_materials_in_category(material_list, materials_in_category, sorted_materials, group_patterns, category_name):
    """Collects materials for a specific category."""
    for key in material_list.keys():
        matched = False
        if category_name == 'OTHER MATERIALS':
            if key not in sorted_materials:
                matched = True
        else:
            for pattern in group_patterns:
                if pattern.upper() in key.upper():
                    matched = True
                    break
        if matched:
            materials_in_category[key] = True
            sorted_materials[key] = True

def sort_reinforcement(arr):
    """Sorts reinforcement strings (e.g., T10, T12, T8)."""

    def get_number(s):
        match = re.search('\\d+', s)
        return int(match.group()) if match else 0
    arr.sort(key=lambda x: get_number(x))

def quick_sort_strings(arr):
    """Performs a standard string sort."""
    arr.sort()

def setup_headers(ws, structure_dict):
    """Sets up headers for the consolidated output sheet."""
    ws.cell(row=1, column=1, value='Material').font = Font(bold=True)
    unique_structures = sorted(list(set(structure_dict.values())))
    col_index = 2
    structures_in_order = {}
    for structure_name in unique_structures:
        ws.cell(row=1, column=col_index, value=structure_name.upper()).font = Font(bold=True)
        structures_in_order[structure_name] = col_index
        col_index += 1
    return (col_index - 1, structures_in_order)

def write_consolidated_data(ws, structures_in_order, material_dict, material_list, config):
    """Writes the consolidated data to the output worksheet."""
    current_row = 2
    sorted_materials_overall = {}
    for (category_name, group_patterns) in config:
        materials_in_this_category = {}
        collect_materials_in_category(material_list, materials_in_this_category, sorted_materials_overall, group_patterns, category_name)
        if materials_in_this_category:
            cell = ws.cell(row=current_row, column=1, value=category_name)
            cell.font = Font(bold=True)
            cell.fill = PatternFill(start_color='DCDCDC', end_color='DCDCDC', fill_type='solid')
            current_row += 1
            material_names_array = list(materials_in_this_category.keys())
            if category_name == 'REINFORCEMENT':
                sort_reinforcement(material_names_array)
            else:
                quick_sort_strings(material_names_array)
            for material_name in material_names_array:
                ws.cell(row=current_row, column=1, value=material_name)
                for (structure_name, col_idx) in structures_in_order.items():
                    key = (material_name, structure_name)
                    if key in material_dict:
                        ws.cell(row=current_row, column=col_idx, value=material_dict[key])
                current_row += 1
            current_row += 1
    return current_row

def format_summary_sheet(ws):
    """Applies formatting to the consolidated sheet."""
    last_row = ws.max_row
    last_col = ws.max_column
    for row_idx in range(1, last_row + 1):
        for col_idx in range(1, last_col + 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            cell.border = Border(left=Side(style='thin'), right=Side(style='thin'), top=Side(style='thin'), bottom=Side(style='thin'))
    ws.row_dimensions[1].height = 60
    header_font = Font(bold=True, color='FFFFFF')
    header_fill = PatternFill(start_color='4F81BD', end_color='4F81BD', fill_type='solid')
    for col_idx in range(1, last_col + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
    max_length = 0
    column_letter = get_column_letter(1)
    for cell in ws[column_letter]:
        try:
            if cell.value is not None:
                cell_value_str = str(cell.value)
                line_lengths = [len(line) for line in cell_value_str.split('\n')]
                if line_lengths:
                    current_max_length = max(line_lengths)
                    if current_max_length > max_length:
                        max_length = current_max_length
        except Exception:
            pass
    adjusted_width = (max_length + 2) * 1.2
    if adjusted_width > 100:
        adjusted_width = 100
    ws.column_dimensions[column_letter].width = adjusted_width

def create_drawing_wise_sheet(workbook, extracted_data, structure_dict):
    """
    Creates a new sheet with materials by drawing columns with categorization.
    First column: Material names (categorized like Consolidated_Materials)
    Subsequent columns: Drawing names (without .dxf) with quantities
    """
    sheet_name = 'Materials_by_Drawing'
    if sheet_name in workbook.sheetnames:
        del workbook[sheet_name]
    ws = workbook.create_sheet(sheet_name)
    ws.title = sheet_name
    drawing_materials = {}
    material_set = set()
    drawing_names = []
    current_drawing = ''
    for row_data in extracted_data:
        if not row_data:
            continue
        if len(row_data) >= 1 and is_drawing_name(row_data[0]):
            current_drawing = parse_drawing_name(row_data[0])
            if current_drawing not in drawing_materials:
                drawing_materials[current_drawing] = {}
                drawing_names.append(current_drawing)
        elif current_drawing and len(row_data) >= 2:
            material_name = str(row_data[0]).strip()
            quantity_text = str(row_data[1]).strip()
            if is_header_or_subtotal(material_name, quantity_text):
                continue
            quantity = filter_quantity(quantity_text)
            if quantity:
                material_set.add(material_name)
                if material_name in drawing_materials[current_drawing]:
                    drawing_materials[current_drawing][material_name] += float(quantity)
                else:
                    drawing_materials[current_drawing][material_name] = float(quantity)
    material_list = {material: True for material in material_set}
    ws.cell(row=1, column=1, value='Material').font = Font(bold=True)
    col_idx = 2
    drawing_columns = {}
    for drawing_name in sorted(drawing_names):
        ws.cell(row=1, column=col_idx, value=drawing_name.upper()).font = Font(bold=True)
        drawing_columns[drawing_name] = col_idx
        col_idx += 1
    current_row = 2
    sorted_materials_overall = {}
    config = define_category_config()
    for (category_name, group_patterns) in config:
        materials_in_this_category = {}
        collect_materials_in_category(material_list, materials_in_this_category, sorted_materials_overall, group_patterns, category_name)
        if materials_in_this_category:
            cell = ws.cell(row=current_row, column=1, value=category_name)
            cell.font = Font(bold=True)
            cell.fill = PatternFill(start_color='DCDCDC', end_color='DCDCDC', fill_type='solid')
            current_row += 1
            material_names_array = list(materials_in_this_category.keys())
            if category_name == 'REINFORCEMENT':
                sort_reinforcement(material_names_array)
            else:
                quick_sort_strings(material_names_array)
            for material_name in material_names_array:
                ws.cell(row=current_row, column=1, value=material_name)
                for (drawing_name, col_idx) in drawing_columns.items():
                    if drawing_name in drawing_materials and material_name in drawing_materials[drawing_name]:
                        ws.cell(row=current_row, column=col_idx, value=drawing_materials[drawing_name][material_name])
                current_row += 1
            current_row += 1
    format_summary_sheet(ws)
    return ws

def is_drawing_name(filename):
    return isinstance(filename, str) and ('.dxf' in filename.lower() or '.dwg' in filename.lower())

def parse_extracted_data_for_comparison(extracted_data):
    """
    Parse extracted data to create a dictionary suitable for comparison.
    Returns: {(filename, layout): [(material, quantity), ...]}
    """
    data_dict = {}
    current_filename = ''
    current_layout = ''
    for row_data in extracted_data:
        if not row_data:
            continue
        clean_row_data = row_data
        is_filename_row = False
        is_header_row = False
        if isinstance(row_data, list) and len(row_data) > 0:
            if 'filename_header' in row_data:
                is_filename_row = True
                clean_row_data = [item for item in row_data if item != 'filename_header']
            elif 'is_header' in row_data:
                is_header_row = True
                clean_row_data = [item for item in row_data if item != 'is_header']
        if not clean_row_data:
            continue
        if is_filename_row or (len(clean_row_data) >= 1 and is_drawing_name(str(clean_row_data[0]))):
            current_filename = str(clean_row_data[0])
            if len(clean_row_data) >= 2 and clean_row_data[1]:
                current_layout = str(clean_row_data[1])
            else:
                current_layout = 'Layout_1'
            file_layout_key = (current_filename, current_layout)
            if file_layout_key not in data_dict:
                data_dict[file_layout_key] = []
        elif current_filename and len(clean_row_data) >= 2 and (not is_header_row):
            material_name = str(clean_row_data[0]).strip()
            quantity_text = str(clean_row_data[1]).strip()
            if is_header_or_subtotal(material_name, quantity_text):
                continue
            if 'ERROR' in material_name.upper() or 'ERROR' in quantity_text.upper():
                continue
            quantity = filter_quantity(quantity_text)
            if quantity:
                try:
                    qty_float = float(quantity)
                    file_layout_key = (current_filename, current_layout)
                    if file_layout_key not in data_dict:
                        data_dict[file_layout_key] = []
                    data_dict[file_layout_key].append((material_name, qty_float))
                except ValueError:
                    continue
    return data_dict

def compare_and_log_changes(workbook, old_data_dict, new_data_dict, log_func):
    """
    Compare old and new extracted data and log changes to Update_Log sheet.
    Creates a sheet that mirrors DXF_Extracted_Data structure with additional columns.
    """
    update_log_sheet_name = 'Update_Log'
    if update_log_sheet_name in workbook.sheetnames:
        del workbook[update_log_sheet_name]
    worksheet_log = workbook.create_sheet(update_log_sheet_name)
    worksheet_log.title = update_log_sheet_name
    from datetime import datetime
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    changes_logged = 0
    current_row = 1
    all_file_layouts = set(old_data_dict.keys()) | set(new_data_dict.keys())
    files_dict = {}
    for (filename, layout) in all_file_layouts:
        if filename not in files_dict:
            files_dict[filename] = []
        files_dict[filename].append(layout)
    for filename in sorted(files_dict.keys()):
        layouts = sorted(files_dict[filename])
        for layout in layouts:
            file_layout_key = (filename, layout)
            old_materials = {}
            new_materials = {}
            if file_layout_key in old_data_dict:
                old_materials = {material: qty for (material, qty) in old_data_dict[file_layout_key]}
            if file_layout_key in new_data_dict:
                new_materials = {material: qty for (material, qty) in new_data_dict[file_layout_key]}
            all_materials = set(old_materials.keys()) | set(new_materials.keys())
            if not all_materials:
                continue
            actual_changes_in_layout = []
            for material in all_materials:
                old_qty = old_materials.get(material, 0)
                new_qty = new_materials.get(material, 0)
                if old_qty != new_qty:
                    actual_changes_in_layout.append((material, old_qty, new_qty))
            if not actual_changes_in_layout:
                continue
            worksheet_log.cell(row=current_row, column=1, value=filename)
            worksheet_log.cell(row=current_row, column=2, value=layout)
            worksheet_log.cell(row=current_row, column=1).font = Font(bold=True)
            worksheet_log.cell(row=current_row, column=2).font = Font(italic=True, color='008080')
            current_row += 1
            worksheet_log.cell(row=current_row, column=1, value='DESCRIPTION')
            worksheet_log.cell(row=current_row, column=2, value='OLD QUANTITY')
            worksheet_log.cell(row=current_row, column=3, value='NEW QUANTITY')
            worksheet_log.cell(row=current_row, column=4, value='CHANGE')
            for col in range(1, 5):
                cell = worksheet_log.cell(row=current_row, column=col)
                cell.font = Font(bold=True)
                cell.fill = PatternFill(start_color='C8C8C8', end_color='C8C8C8', fill_type='solid')
            current_row += 1
            categorized_changes = {}
            for (material, old_qty, new_qty) in actual_changes_in_layout:
                if material.upper() in ['REINFORCEMENT', 'INSERT PLATE', 'ANCHOR BOLTS'] or material.isupper():
                    if material not in categorized_changes:
                        categorized_changes[material] = []
                    if old_qty != new_qty:
                        categorized_changes[material].append((material, old_qty, new_qty))
                else:
                    found_category = None
                    for (cat, mats) in material_groups_from_original_data(old_data_dict.get(file_layout_key, []) + new_data_dict.get(file_layout_key, [])):
                        if material in [m for (m, q) in mats]:
                            found_category = cat
                            break
                    if found_category not in categorized_changes:
                        categorized_changes[found_category] = []
                    categorized_changes[found_category].append((material, old_qty, new_qty))
            if not categorized_changes and actual_changes_in_layout:
                categorized_changes[None] = actual_changes_in_layout
            sorted_categories = sorted(categorized_changes.keys(), key=lambda x: (x is not None, x or ''))
            for category in sorted_categories:
                materials_in_category = sorted(categorized_changes[category], key=lambda x: x[0])
                for (material, old_qty, new_qty) in materials_in_category:
                    if old_qty != new_qty:
                        change = new_qty - old_qty
                        old_qty_str = f'{old_qty:.2f}' if old_qty != int(old_qty) else str(int(old_qty)) if old_qty != 0 else '-'
                        new_qty_str = f'{new_qty:.2f}' if new_qty != int(new_qty) else str(int(new_qty)) if new_qty != 0 else '-'
                        if change > 0:
                            change_str = f'+{change:.2f}' if change != int(change) else f'+{int(change)}'
                            change_color = '008000'
                        elif abs(change) == old_qty:
                            change_str = '-'
                            change_color = '000000'
                        else:
                            change_str = f'{change:.2f}' if change != int(change) else f'{int(change)}'
                            change_color = 'FF0000'
                        changes_logged += 1
                        worksheet_log.cell(row=current_row, column=1, value=material)
                        worksheet_log.cell(row=current_row, column=2, value=old_qty_str)
                        worksheet_log.cell(row=current_row, column=3, value=new_qty_str)
                        worksheet_log.cell(row=current_row, column=4, value=change_str)
                        worksheet_log.cell(row=current_row, column=4).font = Font(color=change_color, bold=True)
                        current_row += 1
            current_row += 1
    for col in worksheet_log.columns:
        max_length = 0
        column = col[0].column_letter
        for cell in col:
            try:
                if cell.value is not None:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
            except:
                pass
        adjusted_width = min(max_length + 2, 50)
        worksheet_log.column_dimensions[column].width = adjusted_width
    log_func(f'Total changes logged: {changes_logged}')
    return changes_logged

def material_groups_from_original_data(material_list):
    groups = []
    current_category = None
    current_group = []
    for (material, qty) in material_list:
        if material.upper() in ['REINFORCEMENT', 'INSERT PLATE', 'ANCHOR BOLTS'] or material.isupper():
            if current_group:
                groups.append((current_category, current_group))
            current_category = material
            current_group = []
        else:
            current_group.append((material, qty))
    if current_group:
        groups.append((current_category, current_group))
    return groups

class QuantityService(ServiceCallbacks):

    def _run_extraction_process(self, dxf_files, mapping_excel_file):
        total_dxf_files = len(dxf_files)
        all_dxf_extracted_data = []
        selected_filenames = {os.path.basename(path).lower() for path in dxf_files}
        try:
            self._set_process_status(text='Loading Excel file...', text_color='blue')
            workbook = self.workbook = openpyxl.load_workbook(mapping_excel_file, keep_vba=Path(mapping_excel_file).suffix.lower() == '.xlsm')
            extracted_sheet_name = 'DXF_Extracted_Data'
            if extracted_sheet_name in workbook.sheetnames:
                worksheet_extracted = workbook[extracted_sheet_name]
                self._set_process_status(text=f"Updating existing '{extracted_sheet_name}' sheet...", text_color='blue')
            else:
                worksheet_extracted = workbook.create_sheet(extracted_sheet_name)
                worksheet_extracted.title = extracted_sheet_name
                header_font_excel = Font(bold=True, color='FFFFFF')
                header_fill_excel = PatternFill(start_color='4CAF50', end_color='4CAF50', fill_type='solid')
                worksheet_extracted.cell(row=1, column=1, value='File Name').font = header_font_excel
                worksheet_extracted.cell(row=1, column=1).fill = header_fill_excel
                worksheet_extracted.cell(row=1, column=2, value='Extraction Status').font = header_font_excel
                worksheet_extracted.cell(row=1, column=2).fill = header_fill_excel
            preserved_rows = []
            existing_dxf_files_in_sheet = set()
            old_extracted_data = []
            if worksheet_extracted.max_row > 1:
                for row_idx in range(2, worksheet_extracted.max_row + 1):
                    row_values = []
                    for col_idx in range(1, worksheet_extracted.max_column + 1):
                        row_values.append(worksheet_extracted.cell(row=row_idx, column=col_idx).value)
                    old_extracted_data.append(row_values)
                current_read_row = 2
                while current_read_row <= worksheet_extracted.max_row:
                    file_name_cell = worksheet_extracted.cell(row=current_read_row, column=1).value
                    if file_name_cell and is_drawing_name(file_name_cell):
                        base_filename = os.path.basename(str(file_name_cell)).lower()
                        existing_dxf_files_in_sheet.add(base_filename)
                        is_being_updated = base_filename in selected_filenames
                        if not is_being_updated:
                            while current_read_row <= worksheet_extracted.max_row:
                                row_data = [worksheet_extracted.cell(row=current_read_row, column=col).value for col in range(1, worksheet_extracted.max_column + 1)]
                                preserved_rows.append(row_data)
                                current_read_row += 1
                                if current_read_row <= worksheet_extracted.max_row:
                                    next_file_name_cell = worksheet_extracted.cell(row=current_read_row, column=1).value
                                    if next_file_name_cell and is_drawing_name(next_file_name_cell):
                                        break
                        else:
                            while current_read_row <= worksheet_extracted.max_row:
                                current_read_row += 1
                                if current_read_row <= worksheet_extracted.max_row:
                                    next_file_name_cell = worksheet_extracted.cell(row=current_read_row, column=1).value
                                    if next_file_name_cell and is_drawing_name(next_file_name_cell):
                                        break
                    else:
                        current_read_row += 1
            if worksheet_extracted.max_row > 1:
                worksheet_extracted.delete_rows(2, worksheet_extracted.max_row - 1)
            current_write_row = 2
            if preserved_rows:
                self._set_process_status(text=f'Restoring {len(preserved_rows)} rows of preserved data...', text_color='blue')
                for row_data in preserved_rows:
                    worksheet_extracted.append(row_data)
                current_write_row = worksheet_extracted.max_row + 1
                if preserved_rows:
                    worksheet_extracted.append([])
                    current_write_row += 1
            processed_count = 0
            new_files_count = 0
            updated_files_count = 0
            self._set_progress('configure', mode='determinate')
            self._set_progress('set', 0)
            for (i, full_path) in enumerate(dxf_files):
                filename = os.path.basename(full_path)
                base_filename_lower = filename.lower()
                if base_filename_lower in existing_dxf_files_in_sheet:
                    self._set_process_status(text=f'Updating existing entry: {filename} ({i + 1}/{total_dxf_files})', text_color='blue')
                    updated_files_count += 1
                else:
                    self._set_process_status(text=f'Adding new entry: {filename} ({i + 1}/{total_dxf_files})', text_color='blue')
                    new_files_count += 1
                (dxf_rows_for_file, success) = extract_table_data_from_dxf(full_path, lambda message, is_error=False: self._set_process_status(text=message, text_color='red' if is_error else 'blue'))
                if success:
                    processed_count += 1
                all_dxf_extracted_data.extend(dxf_rows_for_file)
                progress_value = (i + 1) / total_dxf_files
                self._set_progress('set', progress_value)
            self._set_process_status(text='Writing all extracted data to Excel...', text_color='blue')

            def apply_formatting_to_row(ws, row_idx, row_data, is_filename=False, is_error=False, is_header=False):
                start_col = 1
                if is_filename:
                    ws.cell(row=row_idx, column=start_col).font = Font(bold=True)
                    if len(row_data) > 1:
                        ws.cell(row=row_idx, column=start_col + 1).font = Font(italic=True, color='008080')
                elif is_error:
                    ws.cell(row=row_idx, column=start_col + 1).font = Font(color='FF0000')
                elif is_header:
                    for (col_idx, _) in enumerate(row_data):
                        cell = ws.cell(row=row_idx, column=start_col + col_idx)
                        cell.font = Font(bold=True)
                        cell.fill = PatternFill(start_color='C8C8C8', end_color='C8C8C8', fill_type='solid')
            for row_data_with_flags in all_dxf_extracted_data:
                row_to_write = []
                is_filename_header = False
                is_error_row = False
                is_table_header = False
                if 'filename_header' in row_data_with_flags:
                    is_filename_header = True
                    row_to_write = row_data_with_flags[:-1]
                elif 'is_header' in row_data_with_flags:
                    is_table_header = True
                    row_to_write = row_data_with_flags[:-1]
                elif len(row_data_with_flags) == 2 and 'ERROR' in str(row_data_with_flags[1]).upper():
                    is_error_row = True
                    row_to_write = row_data_with_flags
                else:
                    row_to_write = row_data_with_flags
                worksheet_extracted.append(row_to_write)
                apply_formatting_to_row(worksheet_extracted, worksheet_extracted.max_row, row_to_write, is_filename=is_filename_header, is_error=is_error_row, is_header=is_table_header)
            self._set_process_status(text='Adjusting column widths...', text_color='blue')
            for col in worksheet_extracted.columns:
                max_length = 0
                column = col[0].column_letter
                for cell in col:
                    try:
                        if cell.value is not None:
                            cell_value_str = str(cell.value)
                            line_lengths = [len(line) for line in cell_value_str.split('\n')]
                            if line_lengths:
                                current_max_length = max(line_lengths)
                                if current_max_length > max_length:
                                    max_length = current_max_length
                                if max_length < 5:
                                    max_length = 5
                    except:
                        pass
                adjusted_width = (max_length + 2) * 1.2
                if adjusted_width > 100:
                    adjusted_width = 100
                worksheet_extracted.column_dimensions[column].width = adjusted_width
            if old_extracted_data:
                self._set_process_status(text='Comparing data for changes...', text_color='blue')
                old_data_dict = parse_extracted_data_for_comparison(old_extracted_data)
                new_data_dict = parse_extracted_data_for_comparison(preserved_rows + all_dxf_extracted_data)
                changes_count = compare_and_log_changes(workbook, old_data_dict, new_data_dict, lambda msg: self._set_process_status(text=f'Change tracking: {msg}', text_color='blue'))
                if changes_count > 0:
                    self._set_process_status(text=f'Logged {changes_count} changes to Update_Log sheet', text_color='blue')
            self._set_process_status(text='Saving extraction results...', text_color='blue')
            if processed_count == 0:
                raise ValueError("No Approximate Quantities tables were extracted. Check the selected drawings and activity log.")
            self.counts = {"successful": processed_count, "failed": total_dxf_files - processed_count}
            workbook.save(mapping_excel_file)
            self._set_progress('set', 1)
            self._set_process_status(text='✓ Extraction completed successfully!', text_color='green')
            update_log_exists = 'Update_Log' in workbook.sheetnames
            changes_message = ''
            if update_log_exists and old_extracted_data:
                changes_message = f"\n\nChanges tracked in 'Update_Log' sheet with color coding:\n• Green: Increases (+)\n• Red: Decreases (-)"
            self._show_message(messagebox.showinfo, 'Success', f'Extraction completed successfully!\n\nNew files added: {new_files_count}\nExisting files updated: {updated_files_count}{changes_message}\n\nResults saved to: {os.path.basename(mapping_excel_file)}')
        except Exception as e:
            self._set_progress('set', 0)
            self._set_process_status(text='✗ Extraction failed', text_color='red')
            self._show_message(messagebox.showerror, 'Error', f'An error occurred during extraction:\n{str(e)}')
        finally:
            self._set_progress('stop')
            self._set_progress('grid_remove')
            self._enable_buttons()

    def _run_consolidation_process(self, mapping_excel_file):
        try:
            self._set_process_status(text='Loading Excel file for consolidation...', text_color='blue')
            self._set_progress('configure', mode='indeterminate')
            self._set_progress('start')
            workbook = self.workbook = openpyxl.load_workbook(mapping_excel_file, keep_vba=Path(mapping_excel_file).suffix.lower() == '.xlsm')
            extracted_sheet_name = 'DXF_Extracted_Data'
            if extracted_sheet_name not in workbook.sheetnames:
                self._set_process_status(text=f"Error: '{extracted_sheet_name}' sheet not found.", text_color='red')
                self._show_message(messagebox.showerror, 'Error', f"The sheet '{extracted_sheet_name}' was not found in the Excel file. Please run extraction first.")
                return
            worksheet_extracted = workbook[extracted_sheet_name]
            all_extracted_data = []
            for row_idx in range(2, worksheet_extracted.max_row + 1):
                row_values = []
                for col_idx in range(1, worksheet_extracted.max_column + 1):
                    row_values.append(worksheet_extracted.cell(row=row_idx, column=col_idx).value)
                all_extracted_data.append(row_values)
            if not all_extracted_data:
                self._set_process_status(text='No data found in DXF_Extracted_Data sheet for consolidation.', text_color='orange')
                self._show_message(messagebox.showwarning, 'No Data', "No data found in 'DXF_Extracted_Data' sheet. Please ensure DXF extraction was successful.")
                return
            self._set_process_status(text=f'Read {len(all_extracted_data)} rows from extracted data.', text_color='blue')
            self._set_process_status(text='Performing MTO consolidation...', text_color='blue')
            structure_dict = read_structure_mapping(mapping_excel_file)
            self._set_process_status(text=f'Loaded {len(structure_dict)} structure mappings.', text_color='blue')
            (material_dict, material_list) = process_material_data(all_extracted_data, structure_dict)
            self._set_process_status(text=f'Consolidated {len(material_list)} unique materials.', text_color='blue')
            consolidated_sheet_name = 'Consolidated_Materials'
            if consolidated_sheet_name in workbook.sheetnames:
                del workbook[consolidated_sheet_name]
            worksheet_consolidated = workbook.create_sheet(consolidated_sheet_name)
            self._set_process_status(text='Setting up consolidated sheet headers...', text_color='blue')
            (last_col_index, structures_in_order) = setup_headers(worksheet_consolidated, structure_dict)
            config = define_category_config()
            self._set_process_status(text='Writing consolidated data...', text_color='blue')
            write_consolidated_data(worksheet_consolidated, structures_in_order, material_dict, material_list, config)
            self._set_process_status(text='Formatting consolidated sheet...', text_color='blue')
            format_summary_sheet(worksheet_consolidated)
            self._set_process_status(text='Creating materials by drawing sheet...', text_color='blue')
            create_drawing_wise_sheet(workbook, all_extracted_data, structure_dict)
            self._set_process_status(text='Materials by drawing sheet created successfully!', text_color='blue')
            self._set_process_status(text='Saving consolidation results...', text_color='blue')
            workbook.save(mapping_excel_file)
            self._set_progress('set', 1)
            self._set_process_status(text='✓ Consolidation completed successfully!', text_color='green')
            self._show_message(messagebox.showinfo, 'Success', f'Consolidation completed successfully!\n\nSheets updated/created:\n- Consolidated_Materials\n- Materials_by_Drawing\n\nResults saved to: {os.path.basename(mapping_excel_file)}')
        except Exception as e:
            self._set_progress('set', 0)
            self._set_process_status(text='✗ Consolidation failed', text_color='red')
            self._show_message(messagebox.showerror, 'Error', f'An error occurred during consolidation:\n{str(e)}')
        finally:
            self._set_progress('stop')
            self._set_progress('grid_remove')
            self._enable_buttons()
