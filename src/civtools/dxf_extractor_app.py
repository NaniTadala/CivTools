import sys
import ezdxf
import os
import re
from pathlib import Path
import openpyxl
from openpyxl.styles import Font, PatternFill
from ezdxf.entities.acad_table import read_acad_table_content

# Using customtkinter for modern UI
import customtkinter as ctk
from tkinter import filedialog, messagebox
import threading
from PIL import Image, ImageTk # Import PIL for image handling

# Set customtkinter theme and color
ctk.set_appearance_mode("light")  # Modes: "System" (default), "Dark", "Light"
ctk.set_default_color_theme("dark-blue")  # Themes: "blue" (default), "green", "dark-blue"

# --- Core Logic Functions (remain largely the same as they are backend) ---

def write_to_excel(worksheet, data, current_row_idx, is_header=False, is_filename=False, is_error=False, method_type=None, start_col_offset=0):
    """
    Writes a row of data to the Excel worksheet with basic formatting.
    Returns the new current_row_idx after writing.
    start_col_offset: Number of columns to offset the start of data writing.
    """
    start_col = 1 + start_col_offset # Excel columns are 1-indexed

    if is_filename:
        worksheet.cell(row=current_row_idx, column=start_col).value = data[0]
        worksheet.cell(row=current_row_idx, column=start_col).font = Font(bold=True)
        if method_type:
            worksheet.cell(row=current_row_idx, column=start_col + 1).value = method_type
            worksheet.cell(row=current_row_idx, column=start_col + 1).font = Font(italic=True, color="008080")
        return current_row_idx + 1 # Move to next row for table data

    if is_error:
        worksheet.cell(row=current_row_idx, column=start_col).value = data[0] # Filename
        worksheet.cell(row=current_row_idx, column=start_col + 1).value = data[1] # Error message
        worksheet.cell(row=current_row_idx, column=start_col + 1).font = Font(color="FF0000")
        return current_row_idx + 1

    # For table data
    for col_index, cell_value in enumerate(data):
        cell = worksheet.cell(row=current_row_idx, column=start_col + col_index)
        cell.value = cell_value
        if is_header:
            cell.font = Font(bold=True)
            cell.fill = PatternFill(start_color="C8C8C8", end_color="C8C8C8", fill_type="solid")
    return current_row_idx + 1

def extract_table_data_from_dxf(dxf_path, log_func): # Removed 'worksheet' and 'current_row_idx'
    """
    Enhanced version that searches for tables in both model space and all paper space layouts.
    Extracts ALL "Approximate Quantities" tables found in any space.
    Returns a list of lists, where each inner list represents a row of data to be written to Excel,
    or a list with an error message.
    """
    filename = os.path.basename(dxf_path)
    extracted_rows = [] # This will collect all rows for the current DXF file

    try:
        doc = ezdxf.readfile(dxf_path)
    except ezdxf.DXFError as e:
        extracted_rows.append([filename, f"ERROR: Could not open DXF file - {e}"])
        log_func(f"ERROR: Could not open DXF file {filename}: {e}", is_error=True)
        return extracted_rows, False
    except Exception as e:
        extracted_rows.append([filename, f"ERROR: An unexpected error occurred - {e}"])
        log_func(f"ERROR: An unexpected error occurred with {filename}: {e}", is_error=True)
        return extracted_rows, False

    found_any_table = False
    tables_found_count = 0
    spaces_to_search = []

    # Add model space
    spaces_to_search.append(("Model Space", doc.modelspace()))

    # Add all paper space layouts
    for layout_name in doc.layout_names():
        if layout_name != "Model":  # Skip model space (already added)
            try:
                layout = doc.layout(layout_name)
                spaces_to_search.append((f"Layout: {layout_name}", layout))
            except Exception as e:
                log_func(f"Warning: Could not access layout '{layout_name}' in {filename}: {e}", is_error=True)

    log_func(f"Searching {len(spaces_to_search)} spaces in {filename}")

    # Search ALL spaces for ACAD_TABLE entities - don't stop after first one
    for space_name, space in spaces_to_search:

        for acad_table_entity in space.query("ACAD_TABLE"):
            try:
                table_content = read_acad_table_content(acad_table_entity)

                # Check if any cell contains the key phrase
                table_has_title = False
                for row in table_content:
                    for cell_value in row:
                        if any(phrase.upper() in str(cell_value).upper() for phrase in ["APPROXIMATE QUANTITIES", "APPROXIMATE QUANTITY"]):
                            table_has_title = True
                            break
                    if table_has_title:
                        break

                if table_has_title and table_content:
                    tables_found_count += 1

                    # Include space information and table number in the output
                    method_info = f"Table #{tables_found_count} from {space_name}"

                    # Append filename header with table info
                    extracted_rows.append([filename, method_info, "filename_header"]) # Added a flag to identify this row type

                    # Append table data
                    for i, row_data in enumerate(table_content):
                        # The `write_to_excel` currently handles bold/fill for headers.
                        # We'll need to replicate this or pass a flag for later formatting.
                        # For now, let's just append the data and handle formatting after batch write.
                        extracted_rows.append(row_data + (["is_header"] if i == 0 else [])) # Add flag for header row

                    extracted_rows.append([]) # Add an empty list for spacing between tables (becomes a blank row)
                    log_func(f"SUCCESS: Extracted table #{tables_found_count} from {space_name} in {filename}")
                    found_any_table = True

            except Exception as e:
                log_func(f"Warning: Failed to read ACAD_TABLE content from {space_name} in {filename}: {e}", is_error=True)
                continue

    # Final summary after searching all spaces
    if found_any_table:
        log_func(f"SUMMARY: Found {tables_found_count} 'Approximate Quantities' tables in {filename}")
        return extracted_rows, True
    else:
        extracted_rows.append([filename, "No 'Approximate Quantities' table found in any space."])
        log_func(f"INFO: No 'Approximate Quantities' tables found in any space in {filename}", is_error=False)
        return extracted_rows, False


# --- VBA Logic Re-implemented in Python ---

def parse_drawing_name(cell_value):
    return str(cell_value).strip().lower().replace(".dxf", "")

def is_drawing_name(cell_value):
    return cell_value is not None and ".dxf" in str(cell_value).lower()

def is_header_or_subtotal(cell_a, cell_b):
    lower_a = str(cell_a).strip().lower()
    
    if cell_a is None or cell_b is None: return True
    if str(cell_a).strip() == "" or str(cell_b).strip() == "": return True

    keywords = ["total", "description", "approximate quantities", "reinforcement",
                "insert plate", "structural steel", "file name",
                "extraction status / method", "summary", "subtotal"]
    
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
        workbook = openpyxl.load_workbook(mapping_filepath, data_only=True)
        
        target_sheet_name = 'Drawing_Structure_Mapping'
        ws = None

        if target_sheet_name in workbook.sheetnames:
            ws = workbook[target_sheet_name]
        else:
            raise ValueError(f"Required sheet '{target_sheet_name}' not found in the Excel file.")
        
        # Start reading from the second row (skip assumed header)
        for row_idx in range(2, ws.max_row + 1): 
            drawing_name_cell = ws.cell(row=row_idx, column=1).value
            structure_name_cell = ws.cell(row=row_idx, column=2).value
            
            if drawing_name_cell is None or structure_name_cell is None:
                continue

            drawing_name = str(drawing_name_cell).strip().lower()
            structure_name = str(structure_name_cell).strip()

            # Ensure we're not picking up empty or header-like values in subsequent rows
            if drawing_name and structure_name and not is_header_or_subtotal(drawing_name, structure_name):
                drawing_name = drawing_name.replace(".dxf", "")
                structure_dict[drawing_name] = structure_name
        return structure_dict
    except Exception as e:
        raise ValueError(f"Error reading structure mapping file '{mapping_filepath}': {e}")

def filter_quantity(qty_text):
    """
    Removes common units and extraneous text from quantity string.
    """
    if qty_text is None: return ""
    result = str(qty_text).strip()

    units = ["cu.m", "MT", "NOS", "NO", "KG", "M"]
    for unit in units:
        result = re.sub(r'\b' + re.escape(unit) + r'\b', '', result, flags=re.IGNORECASE).strip()
    
    # Attempt to convert to float to validate if it's a number
    try:
        float(result)
        return result
    except ValueError:
        return "" # Not a valid number

def process_material_data(extracted_data, structure_dict):
    """
    Processes extracted DXF data to consolidate materials by structure.
    Returns (material_dict, material_list)
    material_dict: { (material_name, structure_name): total_quantity }
    material_list: { material_name: True (for unique tracking) }
    """
    material_dict = {} # (material, structure) -> quantity
    material_list = {} # unique materials
    
    current_drawing = ""

    for row_data in extracted_data:
        # Assuming the structure of extracted_data from Python's write_to_excel:
        # If it's a filename row: [filename_str, method_type_str]
        # If it's a data row: [material_str, quantity_str] (if 2 columns) or [col1, col2, ...]
        
        if not row_data:
            continue

        # Check for filename row: filename will be in col 0 (first element), method in col 1
        # and it will likely be a list of 2 items, or more if a table has 2 cols
        # The key is to check if col0 contains ".dxf"
        if len(row_data) >= 1 and is_drawing_name(row_data[0]):
            current_drawing = parse_drawing_name(row_data[0])
        elif current_drawing and len(row_data) >= 2: # This is a material/quantity row
            material_name = str(row_data[0]).strip()
            quantity_text = str(row_data[1]).strip()

            if is_header_or_subtotal(material_name, quantity_text): # Skip headers
                continue
            
            quantity = filter_quantity(quantity_text)

            if quantity and structure_dict.get(current_drawing):
                structure_name = structure_dict[current_drawing]
                combined_key = (material_name, structure_name)
                
                material_dict[combined_key] = material_dict.get(combined_key, 0.0) + float(quantity)
                material_list[material_name] = True
    
    return material_dict, material_list

def define_category_config():
    """Defines material categories and their patterns."""
    config = []
    config.append(("P.C.C", ["P.C.C", "PCC"]))
    config.append(("CONCRETE", ["CONCRETE"]))
    config.append(("REINFORCEMENT", ["T8", "T10", "T12", "T16", "T20", "T25", "T32", "T40"]))
    config.append(("INSERT PLATE", ["P-S", "IP-S", "I-S", "E-S", "P-I"]))
    config.append(("UC SECTIONS", ["UC"]))
    config.append(("UB SECTIONS", ["UB"]))
    config.append(("HE SECTIONS", ["HEA", "HEB", "HEM"]))
    config.append(("CHANNEL SECTIONS", ["ISMC", "CHANNEL"]))
    config.append(("ANGLE SECTIONS", ["ISA", "ANGLE"]))
    config.append(("CUT-TEE SECTIONS", ["CT"]))
    config.append(("PLATE SECTIONS", ["PLT", "PLATE"]))
    config.append(("CIRCULAR HOLLOW SECTIONS", ["RHS", "CHS"]))
    config.append(("RECTANGULAR HOLLOW SECTIONS", ["SHS"]))
    config.append(("ANCHOR BOLTS", ["M20", "M24", "M30 (TYPE-A)"]))
    config.append(("BASE PLATE", ["25 THK", "30 THK"]))
    config.append(("OTHER MATERIALS", []))  # Special category for leftovers
    return config

def collect_materials_in_category(material_list, materials_in_category, sorted_materials, group_patterns, category_name):
    """Collects materials for a specific category."""
    for key in material_list.keys():
        matched = False
        if category_name == "OTHER MATERIALS":
            if key not in sorted_materials: # Only include if not already categorized
                matched = True
        else:
            for pattern in group_patterns:
                if pattern.upper() in key.upper():
                    matched = True
                    break
        
        if matched:
            materials_in_category[key] = True
            sorted_materials[key] = True # Mark as categorized

def sort_reinforcement(arr):
    """Sorts reinforcement strings (e.g., T10, T12, T8)."""
    def get_number(s):
        match = re.search(r'\d+', s)
        return int(match.group()) if match else 0
    arr.sort(key=lambda x: get_number(x))

def quick_sort_strings(arr):
    """Performs a standard string sort."""
    arr.sort()

def setup_headers(ws, structure_dict):
    """Sets up headers for the consolidated output sheet."""
    # Column 1: Material
    ws.cell(row=1, column=1, value="Material").font = Font(bold=True)

    unique_structures = sorted(list(set(structure_dict.values()))) # Get unique and sorted structures

    col_index = 2
    structures_in_order = {} # Stores structure_name: column_index mapping
    for structure_name in unique_structures:
        ws.cell(row=1, column=col_index, value=structure_name.upper()).font = Font(bold=True)
        structures_in_order[structure_name] = col_index
        col_index += 1
    
    return col_index - 1, structures_in_order # Return last column index and structure order dict

def write_consolidated_data(ws, structures_in_order, material_dict, material_list, config):
    """Writes the consolidated data to the output worksheet."""
    current_row = 2
    sorted_materials_overall = {} # To track all materials that have been categorized

    for category_name, group_patterns in config:
        materials_in_this_category = {}
        
        collect_materials_in_category(material_list, materials_in_this_category, sorted_materials_overall, group_patterns, category_name)

        if materials_in_this_category:
            # Write category header
            cell = ws.cell(row=current_row, column=1, value=category_name)
            cell.font = Font(bold=True)
            cell.fill = PatternFill(start_color="DCDCDC", end_color="DCDCDC", fill_type="solid")
            current_row += 1

            material_names_array = list(materials_in_this_category.keys())
            if category_name == "REINFORCEMENT":
                sort_reinforcement(material_names_array)
            else:
                quick_sort_strings(material_names_array)
            
            for material_name in material_names_array:
                ws.cell(row=current_row, column=1, value=material_name)
                for structure_name, col_idx in structures_in_order.items():
                    key = (material_name, structure_name)
                    if key in material_dict:
                        ws.cell(row=current_row, column=col_idx, value=material_dict[key])
                current_row += 1
            
            current_row += 1 # Add spacing after each category

    return current_row # Return the next available row

from openpyxl.styles import Font, PatternFill, Border, Side, Alignment
from openpyxl.utils import get_column_letter

def format_summary_sheet(ws):
    """Applies formatting to the consolidated sheet."""
    last_row = ws.max_row
    last_col = ws.max_column

    # Apply borders to all cells
    for row_idx in range(1, last_row + 1):
        for col_idx in range(1, last_col + 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            cell.border = Border(
                left=Side(style='thin'),
                right=Side(style='thin'),
                top=Side(style='thin'),
                bottom=Side(style='thin')
            )
            
    # Format header row - set height to 80 pixels (60 points)
    ws.row_dimensions[1].height = 60
    
    # Header styling
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="4F81BD", end_color="4F81BD", fill_type="solid")
    for col_idx in range(1, last_col + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)

    # Autofit only the first column (column A)
    max_length = 0
    column_letter = get_column_letter(1)  # 'A'
    
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
    if adjusted_width > 100: adjusted_width = 100  # Max width cap
    ws.column_dimensions[column_letter].width = adjusted_width

def create_drawing_wise_sheet(workbook, extracted_data, structure_dict):
    """
    Creates a new sheet with materials by drawing columns with categorization.
    First column: Material names (categorized like Consolidated_Materials)
    Subsequent columns: Drawing names (without .dxf) with quantities
    """
    sheet_name = "Materials_by_Drawing"
    if sheet_name in workbook.sheetnames:
        del workbook[sheet_name]
    ws = workbook.create_sheet(sheet_name)
    ws.title = sheet_name
    
    # Process data to get material quantities by drawing
    drawing_materials = {}  # {drawing_name: {material_name: quantity}}
    material_set = set()  # Track all unique materials
    drawing_names = []  # Track drawing order
    
    current_drawing = ""
    
    for row_data in extracted_data:
        if not row_data:
            continue
            
        # Check for filename row
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
    
    # Create material_list dictionary for categorization
    material_list = {material: True for material in material_set}
    
    # Setup headers
    ws.cell(row=1, column=1, value="Material").font = Font(bold=True)
    
    # Create column headers for each drawing
    col_idx = 2
    drawing_columns = {}  # {drawing_name: column_index}
    for drawing_name in sorted(drawing_names):
        ws.cell(row=1, column=col_idx, value=drawing_name.upper()).font = Font(bold=True)
        drawing_columns[drawing_name] = col_idx
        col_idx += 1
    
    # Write categorized material data (same logic as consolidated sheet)
    current_row = 2
    sorted_materials_overall = {}  # To track all materials that have been categorized
    config = define_category_config()
    
    for category_name, group_patterns in config:
        materials_in_this_category = {}
        
        collect_materials_in_category(material_list, materials_in_this_category, sorted_materials_overall, group_patterns, category_name)

        if materials_in_this_category:
            # Write category header
            cell = ws.cell(row=current_row, column=1, value=category_name)
            cell.font = Font(bold=True)
            cell.fill = PatternFill(start_color="DCDCDC", end_color="DCDCDC", fill_type="solid")
            current_row += 1

            material_names_array = list(materials_in_this_category.keys())
            if category_name == "REINFORCEMENT":
                sort_reinforcement(material_names_array)
            else:
                quick_sort_strings(material_names_array)
            
            for material_name in material_names_array:
                ws.cell(row=current_row, column=1, value=material_name)
                
                # Fill quantities for each drawing
                for drawing_name, col_idx in drawing_columns.items():
                    if drawing_name in drawing_materials and material_name in drawing_materials[drawing_name]:
                        ws.cell(row=current_row, column=col_idx, value=drawing_materials[drawing_name][material_name])
                
                current_row += 1
            
            current_row += 1  # Add spacing after each category
    
    # Apply formatting
    format_summary_sheet(ws)
    
    return ws

# Helper function to check if a filename is a drawing name
def is_drawing_name(filename):
    return isinstance(filename, str) and ('.dxf' in filename.lower() or '.dwg' in filename.lower())

def parse_extracted_data_for_comparison(extracted_data):
    """
    Parse extracted data to create a dictionary suitable for comparison.
    Returns: {(filename, layout): [(material, quantity), ...]}
    """
    data_dict = {}
    current_filename = ""
    current_layout = ""
    
    for row_data in extracted_data:
        if not row_data:
            continue
        
        # Handle flagged rows (remove flags before processing)
        clean_row_data = row_data
        is_filename_row = False
        is_header_row = False
        
        # Check for special flags and remove them
        if isinstance(row_data, list) and len(row_data) > 0:
            if "filename_header" in row_data:
                is_filename_row = True
                clean_row_data = [item for item in row_data if item != "filename_header"]
            elif "is_header" in row_data:
                is_header_row = True
                clean_row_data = [item for item in row_data if item != "is_header"]
        
        if not clean_row_data:
            continue
        
        # Check if this is a filename row with layout info
        if is_filename_row or (len(clean_row_data) >= 1 and is_drawing_name(str(clean_row_data[0]))):
            current_filename = str(clean_row_data[0])
            # Extract layout info from the second column if it exists
            if len(clean_row_data) >= 2 and clean_row_data[1]:
                current_layout = str(clean_row_data[1])
            else:
                current_layout = "Layout_1"
            
            file_layout_key = (current_filename, current_layout)
            if file_layout_key not in data_dict:
                data_dict[file_layout_key] = []
                
            
        elif current_filename and len(clean_row_data) >= 2 and not is_header_row:
            material_name = str(clean_row_data[0]).strip()
            quantity_text = str(clean_row_data[1]).strip()
            
            # Skip headers, subtotals, and empty rows
            if is_header_or_subtotal(material_name, quantity_text):
                continue
            
            # Skip rows that look like status messages or errors
            if "ERROR" in material_name.upper() or "ERROR" in quantity_text.upper():
                continue
                
            # Filter and validate quantity
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
    update_log_sheet_name = "Update_Log"

    # Remove existing Update_Log sheet if it exists to create fresh one
    if update_log_sheet_name in workbook.sheetnames:
        del workbook[update_log_sheet_name]

    worksheet_log = workbook.create_sheet(update_log_sheet_name)
    worksheet_log.title = update_log_sheet_name

    from datetime import datetime
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    changes_logged = 0
    current_row = 1 # Start from row 1 since the first header is removed

    # Get all unique file-layout combinations
    all_file_layouts = set(old_data_dict.keys()) | set(new_data_dict.keys())

    # Group by filename for proper organization
    files_dict = {}
    for filename, layout in all_file_layouts:
        if filename not in files_dict:
            files_dict[filename] = []
        files_dict[filename].append(layout)

    for filename in sorted(files_dict.keys()):
        layouts = sorted(files_dict[filename])

        for layout in layouts:
            file_layout_key = (filename, layout)

            old_materials = {}
            new_materials = {}

            # Get old materials for this file-layout
            if file_layout_key in old_data_dict:
                old_materials = {material: qty for material, qty in old_data_dict[file_layout_key]}

            # Get new materials for this file-layout
            if file_layout_key in new_data_dict:
                new_materials = {material: qty for material, qty in new_data_dict[file_layout_key]}

            # Get all unique materials from both old and new
            all_materials = set(old_materials.keys()) | set(new_materials.keys())

            if not all_materials:
                continue

            # Check for any actual changes for this file-layout before proceeding
            # This includes new materials, removed materials, or quantity changes
            actual_changes_in_layout = []
            for material in all_materials:
                old_qty = old_materials.get(material, 0)
                new_qty = new_materials.get(material, 0)
                
                # Only consider a material for logging if its quantity has actually changed
                if old_qty != new_qty:
                    actual_changes_in_layout.append((material, old_qty, new_qty))
            
            # If no actual changes in quantities, skip this file-layout entirely
            if not actual_changes_in_layout:
                continue

            # Add filename and layout header row
            worksheet_log.cell(row=current_row, column=1, value=filename)
            worksheet_log.cell(row=current_row, column=2, value=layout)
            
            # Apply formatting to filename row
            worksheet_log.cell(row=current_row, column=1).font = Font(bold=True)
            worksheet_log.cell(row=current_row, column=2).font = Font(italic=True, color="008080")
            
            current_row += 1
            
            # Update column headers to only include "DESCRIPTION", "OLD QUANTITY", "NEW QUANTITY", "CHANGE"
            worksheet_log.cell(row=current_row, column=1, value="DESCRIPTION")
            worksheet_log.cell(row=current_row, column=2, value="OLD QUANTITY")
            worksheet_log.cell(row=current_row, column=3, value="NEW QUANTITY")
            worksheet_log.cell(row=current_row, column=4, value="CHANGE")
            
            for col in range(1, 5): 
                cell = worksheet_log.cell(row=current_row, column=col)
                cell.font = Font(bold=True)
                cell.fill = PatternFill(start_color="C8C8C8", end_color="C8C8C8", fill_type="solid")
            
            current_row += 1
            
            # Group materials by category
            # This part needs to ensure that only the materials with actual_changes_in_layout are considered
            # for categorization and display.
            
            # Re-grouping based on actual_changes_in_layout to preserve original categorization intent
            categorized_changes = {}
            for material, old_qty, new_qty in actual_changes_in_layout:
                # Check if this looks like a category header
                if material.upper() in ['REINFORCEMENT', 'INSERT PLATE', 'ANCHOR BOLTS'] or material.isupper():
                    # If the category itself is a "material" that changed, we include it.
                    # Otherwise, it might just be a header for subsequent materials.
                    # For now, treat it as a potential category.
                    if material not in categorized_changes:
                        categorized_changes[material] = [] # Use the material name as category if it looks like one
                    # Add category as a "material" if it had a quantity change.
                    # This implies category names themselves could be billable items.
                    if old_qty != new_qty:
                         categorized_changes[material].append((material, old_qty, new_qty))
                else:
                    # Find the category this material belongs to in the original data or assume a default.
                    found_category = None
                    for cat, mats in material_groups_from_original_data(old_data_dict.get(file_layout_key, []) + new_data_dict.get(file_layout_key, [])):
                        if material in [m for m, q in mats]: # Check if material exists in this category
                            found_category = cat
                            break
                    if found_category not in categorized_changes:
                        categorized_changes[found_category] = []
                    categorized_changes[found_category].append((material, old_qty, new_qty))
            
            # If no categories were explicitly found or if all are uncategorized,
            # just use a single 'None' category for all changed materials
            if not categorized_changes and actual_changes_in_layout:
                categorized_changes[None] = actual_changes_in_layout


            # Sort categories for consistent output, with None (uncategorized) first
            sorted_categories = sorted(categorized_changes.keys(), key=lambda x: (x is not None, x or ''))

            for category in sorted_categories:
                materials_in_category = sorted(categorized_changes[category], key=lambda x: x[0]) # Sort materials alphabetically
                
                # Add materials in this category
                for material, old_qty, new_qty in materials_in_category:
                    # The condition old_qty != new_qty is already handled by actual_changes_in_layout,
                    # but keeping it here as a final safeguard.
                    if old_qty != new_qty:
                        change = new_qty - old_qty
                        
                        old_qty_str = f"{old_qty:.2f}" if old_qty != int(old_qty) else str(int(old_qty)) if old_qty != 0 else "-"
                        new_qty_str = f"{new_qty:.2f}" if new_qty != int(new_qty) else str(int(new_qty)) if new_qty != 0 else "-"
                        
                        if change > 0:
                            change_str = f"+{change:.2f}" if change != int(change) else f"+{int(change)}"
                            change_color = "008000"  # Green
                        elif abs(change) == old_qty:
                            change_str = "-"
                            change_color = "000000"
                        else:
                            change_str = f"{change:.2f}" if change != int(change) else f"{int(change)}"
                            change_color = "FF0000"  # Red
                        changes_logged += 1
                        
                        worksheet_log.cell(row=current_row, column=1, value=material)
                        worksheet_log.cell(row=current_row, column=2, value=old_qty_str)
                        worksheet_log.cell(row=current_row, column=3, value=new_qty_str)
                        worksheet_log.cell(row=current_row, column=4, value=change_str)
                        
                        worksheet_log.cell(row=current_row, column=4).font = Font(color=change_color, bold=True)
                        
                        current_row += 1
            
            # Add empty row between different file-layout combinations if changes were logged for this layout
            current_row += 1
    
    # Auto-fit columns in the log sheet
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
    
    log_func(f"Total changes logged: {changes_logged}")
    return changes_logged

# Helper function to reconstruct original material groups for accurate categorization in log
def material_groups_from_original_data(material_list):
    groups = []
    current_category = None
    current_group = []
    for material, qty in material_list:
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
# --- GUI Implementation ---

class DxfExtractorApp(ctk.CTkToplevel): # Renamed from App to DXFExtractorApp for clarity if needed
    def __init__(self, master=None): # Add parent_root argument
        super().__init__(master)
        self._ui_thread_id = threading.get_ident()
        # 1. Hide the window initially
        self.withdraw()
        self.title("DXF Quantity Table Extractor & MTO Consolidator")
        self.geometry("700x600")
        self.resizable(False, False)

        # Configure grid layout
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure((0, 1, 2, 3), weight=1) # Adjusted for progress bar row

        self.dxf_files_paths = []
        self.mapping_excel_path = ""

        # Load icons
        try:
            self.dxf_icon = ctk.CTkImage(light_image=Image.open(self.resource_path("assets/icons/file_icon.png")),
                                            dark_image=Image.open(self.resource_path("assets/icons/file_icon.png")),
                                            size=(60, 60))
            self.excel_icon = ctk.CTkImage(light_image=Image.open(self.resource_path("assets/icons/excel_icon.png")),
                                            dark_image=Image.open(self.resource_path("assets/icons/excel_icon.png")),
                                            size=(60, 60))
        except FileNotFoundError:
            messagebox.showerror("Icon Error", "Could not find icon files (file_icon.png, excel_icon.png). "
                                                    "Please ensure they are bundled with the executable.")
            self.dxf_icon = None
            self.excel_icon = None

        self.create_widgets()
        # 2. Show the window after everything is set up
        self.deiconify()

    # ... (rest of your App class methods: resource_path, create_widgets, browse_dxf_files, etc.)
    def resource_path(self, relative_path):
        """ Get absolute path to resource, works for dev and for PyInstaller """
        if getattr(sys, "frozen", False):
            base_path = sys._MEIPASS
        else:
            base_path = Path(__file__).resolve().parents[2]
        return os.path.join(base_path, relative_path)

    def _ui_call(self, callback, *args, **kwargs):
        if threading.get_ident() == self._ui_thread_id:
            return callback(*args, **kwargs)
        self.after(0, lambda: callback(*args, **kwargs))

    def _set_process_status(self, **kwargs):
        self._ui_call(self.process_status.configure, **kwargs)

    def _set_progress(self, method, *args, **kwargs):
        self._ui_call(getattr(self.progressbar, method), *args, **kwargs)

    def _show_message(self, method, *args):
        self._ui_call(method, *args)

    def create_widgets(self):
        # Header frame
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.grid(row=0, column=0, pady=(20, 10), sticky="nsew")
        header_frame.grid_columnconfigure(0, weight=1)

        # Main title
        header_label = ctk.CTkLabel(header_frame, 
                                text="Quantity Table Extraction & MTO Consolidation", 
                                font=ctk.CTkFont(size=20, weight="bold"))
        header_label.grid(row=0, column=0, pady=(0, 5), sticky="n")

        # Usage Instructions button (centered and underlined)
        help_button = ctk.CTkButton(header_frame, 
                                text="Usage Instructions", 
                                command=self.show_help,
                                width=180,
                                height=30,
                                corner_radius=6,
                                font=ctk.CTkFont(size=16, underline=True, weight="bold"),
                                fg_color="transparent",
                                hover_color="#e9ecef",
                                text_color="#2196F3")
        help_button.grid(row=1, column=0, sticky="n")

        # Main frame for side-by-side buttons
        main_frame = ctk.CTkFrame(self)
        main_frame.grid(row=1, column=0, padx=30, pady=10, sticky="ew")
        main_frame.grid_columnconfigure((0, 1), weight=1) 

        # Step 1: DXF Files Selection Module (Left side)
        step1_frame = ctk.CTkFrame(main_frame)
        step1_frame.grid(row=0, column=0, padx=(10, 5), pady=15, sticky="ew")
        step1_frame.grid_columnconfigure(0, weight=1)

        # DXF Button
        self.dxf_button = ctk.CTkButton(step1_frame, text="Select DXF Files", 
                                            image=self.dxf_icon, compound="top",
                                            command=self.browse_dxf_files,
                                            width=180, height=100,
                                            font=ctk.CTkFont(size=14, weight="bold"),
                                            fg_color="#2196F3", hover_color="#1976D2")
        if self.dxf_icon is None:
            self.dxf_button.configure(text="📁 Select DXF Files", image=None)
        self.dxf_button.grid(row=0, column=0, pady=15)

        # DXF Status Text
        self.dxf_status = ctk.CTkLabel(step1_frame, text="No DXF files selected", 
                                        font=ctk.CTkFont(size=12),
                                        text_color="gray")
        self.dxf_status.grid(row=1, column=0, pady=(0, 5)) 

        # Clear DXF Selection Button
        self.clear_dxf_button = ctk.CTkButton(step1_frame, text="Clear Selection",
                                                command=self.clear_dxf_selection,
                                                width=180, height=30,
                                                font=ctk.CTkFont(size=12),
                                                fg_color="#D32F2F", hover_color="#C62828")
        self.clear_dxf_button.grid(row=2, column=0, pady=(5, 15)) 

        # Step 2: Excel File Selection Module (Right side)
        step2_frame = ctk.CTkFrame(main_frame)
        step2_frame.grid(row=0, column=1, padx=(5, 10), pady=15, sticky="ew")
        step2_frame.grid_columnconfigure(0, weight=1)

        # Excel Button
        self.excel_button = ctk.CTkButton(step2_frame, text="Select Excel File", 
                                            image=self.excel_icon, compound="top",
                                            command=self.browse_mapping_excel_file,
                                            width=180, height=100,
                                            font=ctk.CTkFont(size=14, weight="bold"),
                                            fg_color="#4CAF50", hover_color="#45A049")
        if self.excel_icon is None:
            self.excel_button.configure(text="📊 Select Excel File", image=None)
        self.excel_button.grid(row=0, column=0, pady=15)

        # Excel Status Text
        self.excel_status = ctk.CTkLabel(step2_frame, text="No Excel file selected", 
                                            font=ctk.CTkFont(size=12),
                                            text_color="gray")
        self.excel_status.grid(row=1, column=0, pady=(0, 5))

        # Clear Excel Selection Button (NEW)
        self.clear_excel_button = ctk.CTkButton(step2_frame, text="Clear Selection",
                                                command=self.clear_excel_selection,
                                                width=180, height=30,
                                                font=ctk.CTkFont(size=12),
                                                fg_color="#D32F2F", hover_color="#C62828")
        self.clear_excel_button.grid(row=2, column=0, pady=(5, 15))

        # Step 3: Process Module (Two buttons side by side)
        step3_frame = ctk.CTkFrame(self)
        step3_frame.grid(row=2, column=0, padx=30, pady=10, sticky="ew")
        step3_frame.grid_columnconfigure((0, 1), weight=1) 

        # Extract Button
        self.extract_button = ctk.CTkButton(step3_frame, text="Extract DXF Data", 
                                                command=self.start_extraction_thread,
                                                width=180, height=60,
                                                font=ctk.CTkFont(size=14, weight="bold"),
                                                fg_color="#FF9800", hover_color="#F57C00")
        self.extract_button.grid(row=0, column=0, padx=(10, 5), pady=15)

        # Consolidate Button
        self.consolidate_button = ctk.CTkButton(step3_frame, text="Consolidate Data", 
                                                    command=self.start_consolidation_thread,
                                                    width=180, height=60,
                                                    font=ctk.CTkFont(size=14, weight="bold"),
                                                    fg_color="#9C27B0", hover_color="#7B1FA2")
        self.consolidate_button.grid(row=0, column=1, padx=(5, 10), pady=15)

        # Process Status Text
        self.process_status = ctk.CTkLabel(step3_frame, text="Ready to process", 
                                            font=ctk.CTkFont(size=14),
                                            text_color="gray")
        self.process_status.grid(row=1, column=0, columnspan=2, pady=(0, 5)) 

        # Progress Bar
        self.progressbar = ctk.CTkProgressBar(step3_frame, mode="determinate", height=10)
        self.progressbar.grid(row=2, column=0, columnspan=2, padx=10, pady=(0, 15), sticky="ew")
        self.progressbar.set(0) # Initialize to 0
        self.progressbar.grid_remove() # HIDE THE PROGRESS BAR INITIALLY

        # Footer with version or additional info
        footer_label = ctk.CTkLabel(self, text="Select files above and Start Processing", 
                                        font=ctk.CTkFont(size=12),
                                        text_color="gray")
        footer_label.grid(row=3, column=0, pady=(5, 20), sticky="") 
        
        # Initial status updates to set button states correctly
        self.update_dxf_status()
        self.update_excel_status()

    def browse_dxf_files(self):
        files_selected = filedialog.askopenfilenames(
            filetypes=[("DXF files", "*.dxf")],
            title="Select DXF files"
        )
        if files_selected:
            for file_path in files_selected:
                if file_path not in self.dxf_files_paths:
                    self.dxf_files_paths.append(file_path)
            self.update_dxf_status()

    def clear_dxf_selection(self):
        self.dxf_files_paths = []
        self.update_dxf_status()
        self.process_status.configure(text="DXF file selection cleared.", text_color="blue")

    def update_dxf_status(self):
        count = len(self.dxf_files_paths)
        if count == 0:
            self.dxf_status.configure(text="No DXF files selected", text_color="gray")
            self.clear_dxf_button.configure(state='disabled')
        elif count == 1:
            filename = os.path.basename(self.dxf_files_paths[0])
            if len(filename) > 25:
                filename = filename[:22] + "..."
            self.dxf_status.configure(text=f"Selected: {filename}", text_color="green")
            self.clear_dxf_button.configure(state='normal')
        else:
            self.dxf_status.configure(text=f"Selected: {count} DXF files", text_color="green")
            self.clear_dxf_button.configure(state='normal')

    def browse_mapping_excel_file(self):
        file_selected = filedialog.askopenfilename(
            filetypes=[("Excel files", "*.xlsx;*.xlsm")],
            title="Select Excel file with Drawing_Structure_Mapping sheet"
        )
        if file_selected:
            self.mapping_excel_path = file_selected
            self.update_excel_status()

    def clear_excel_selection(self):
        self.mapping_excel_path = ""
        self.update_excel_status()
        self.process_status.configure(text="Excel file selection cleared.", text_color="blue")

    def update_excel_status(self):
        if self.mapping_excel_path:
            filename = os.path.basename(self.mapping_excel_path)
            if len(filename) > 25:
                filename = filename[:22] + "..."
            self.excel_status.configure(text=f"Selected: {filename}", text_color="green")
            self.clear_excel_button.configure(state='normal')
        else:
            self.excel_status.configure(text="No Excel file selected", text_color="gray")
            self.clear_excel_button.configure(state='disabled')

    def start_extraction_thread(self):
        if not self.dxf_files_paths:
            messagebox.showerror("Error", "Please select at least one DXF file.")
            return
        if not self.mapping_excel_path:
            messagebox.showerror("Error", "Please select an Excel file with DXF_Extracted_Data in it.")
            return

        self.progressbar.grid() 
        self.process_status.configure(text="Extracting... Please wait", text_color="orange")
        self.extract_button.configure(state='disabled', text="Extracting...")
        self.dxf_button.configure(state='disabled')
        self.clear_dxf_button.configure(state='disabled')
        self.excel_button.configure(state='disabled')
        self.clear_excel_button.configure(state='disabled')
        self.consolidate_button.configure(state='disabled')
        self.progressbar.set(0)
        self.progressbar.start()

        process_thread = threading.Thread(
            target=self._run_extraction_process,
            args=(list(self.dxf_files_paths), self.mapping_excel_path),
            daemon=True,
        )
        process_thread.start()

    def start_consolidation_thread(self):
        if not self.mapping_excel_path:
            messagebox.showerror("Error", "Please select an Excel file with 'DXF_Extracted_Data' in it.")
            return

        self.progressbar.grid()
        self.process_status.configure(text="Consolidating... Please wait", text_color="orange")
        self.consolidate_button.configure(state='disabled', text="Consolidating...")
        self.dxf_button.configure(state='disabled')
        self.clear_dxf_button.configure(state='disabled')
        self.excel_button.configure(state='disabled')
        self.clear_excel_button.configure(state='disabled')
        self.extract_button.configure(state='disabled')
        self.progressbar.set(0)
        self.progressbar.start()

        process_thread = threading.Thread(
            target=self._run_consolidation_process,
            args=(self.mapping_excel_path,),
            daemon=True,
        )
        process_thread.start()

    def _run_extraction_process(self, dxf_files, mapping_excel_file):

        total_dxf_files = len(dxf_files)
        all_dxf_extracted_data = []

        try:
            self._set_process_status(text="Loading Excel file...", text_color="blue")

            workbook = openpyxl.load_workbook(
                mapping_excel_file,
                keep_vba=Path(mapping_excel_file).suffix.lower() == ".xlsm",
            )
            extracted_sheet_name = "DXF_Extracted_Data"

            if extracted_sheet_name in workbook.sheetnames:
                worksheet_extracted = workbook[extracted_sheet_name]
                self._set_process_status(text=f"Updating existing '{extracted_sheet_name}' sheet...", text_color="blue")
            else:
                worksheet_extracted = workbook.create_sheet(extracted_sheet_name)
                worksheet_extracted.title = extracted_sheet_name
                header_font_excel = Font(bold=True, color="FFFFFF")
                header_fill_excel = PatternFill(start_color="4CAF50", end_color="4CAF50", fill_type="solid")
                worksheet_extracted.cell(row=1, column=1, value="File Name").font = header_font_excel
                worksheet_extracted.cell(row=1, column=1).fill = header_fill_excel
                worksheet_extracted.cell(row=1, column=2, value="Extraction Status").font = header_font_excel
                worksheet_extracted.cell(row=1, column=2).fill = header_fill_excel

            preserved_rows = []
            existing_dxf_files_in_sheet = set()
            old_extracted_data = []  # Store old data for comparison

            if worksheet_extracted.max_row > 1:
                # First pass: collect all existing data for comparison
                for row_idx in range(2, worksheet_extracted.max_row + 1):
                    row_values = []
                    for col_idx in range(1, worksheet_extracted.max_column + 1):
                        row_values.append(worksheet_extracted.cell(row=row_idx, column=col_idx).value)
                    old_extracted_data.append(row_values)
                
                # Second pass: preserve data that won't be updated
                current_read_row = 2
                while current_read_row <= worksheet_extracted.max_row:
                    file_name_cell = worksheet_extracted.cell(row=current_read_row, column=1).value

                    if file_name_cell and is_drawing_name(file_name_cell):
                        base_filename = os.path.basename(str(file_name_cell)).lower()
                        existing_dxf_files_in_sheet.add(base_filename)

                        is_being_updated = False
                        for selected_dxf_path in dxf_files:
                            if os.path.basename(selected_dxf_path).lower() == base_filename:
                                is_being_updated = True
                                break

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
                self._set_process_status(text=f"Restoring {len(preserved_rows)} rows of preserved data...", text_color="blue")
                for row_data in preserved_rows:
                    worksheet_extracted.append(row_data)
                current_write_row = worksheet_extracted.max_row + 1
                if preserved_rows:
                    worksheet_extracted.append([])
                    current_write_row += 1

            processed_count = 0
            new_files_count = 0
            updated_files_count = 0

            self._set_progress("configure", mode="determinate")
            self._set_progress("set", 0)

            for i, full_path in enumerate(dxf_files):
                filename = os.path.basename(full_path)
                base_filename_lower = filename.lower()

                if base_filename_lower in existing_dxf_files_in_sheet:
                    self._set_process_status(text=f"Updating existing entry: {filename} ({i+1}/{total_dxf_files})", text_color="blue")
                    updated_files_count += 1
                else:
                    self._set_process_status(text=f"Adding new entry: {filename} ({i+1}/{total_dxf_files})", text_color="blue")
                    new_files_count += 1

                dxf_rows_for_file, success = extract_table_data_from_dxf(
                    full_path,
                    lambda message, is_error=False: self._set_process_status(
                        text=message,
                        text_color="red" if is_error else "blue",
                    ),
                )
                if success:
                    processed_count += 1

                all_dxf_extracted_data.extend(dxf_rows_for_file)

                progress_value = (i + 1) / total_dxf_files
                self._set_progress("set", progress_value)

            self._set_process_status(text="Writing all extracted data to Excel...", text_color="blue")
            
            def apply_formatting_to_row(ws, row_idx, row_data, is_filename=False, is_error=False, is_header=False):
                start_col = 1
                
                if is_filename:
                    ws.cell(row=row_idx, column=start_col).font = Font(bold=True)
                    if len(row_data) > 1:
                        ws.cell(row=row_idx, column=start_col + 1).font = Font(italic=True, color="008080")
                elif is_error:
                    ws.cell(row=row_idx, column=start_col + 1).font = Font(color="FF0000")
                elif is_header:
                    for col_idx, _ in enumerate(row_data):
                        cell = ws.cell(row=row_idx, column=start_col + col_idx)
                        cell.font = Font(bold=True)
                        cell.fill = PatternFill(start_color="C8C8C8", end_color="C8C8C8", fill_type="solid")

            for row_data_with_flags in all_dxf_extracted_data:
                row_to_write = []
                is_filename_header = False
                is_error_row = False
                is_table_header = False
                
                if "filename_header" in row_data_with_flags:
                    is_filename_header = True
                    row_to_write = row_data_with_flags[:-1]
                elif "is_header" in row_data_with_flags:
                    is_table_header = True
                    row_to_write = row_data_with_flags[:-1]
                elif len(row_data_with_flags) == 2 and "ERROR" in str(row_data_with_flags[1]).upper():
                    is_error_row = True
                    row_to_write = row_data_with_flags
                else:
                    row_to_write = row_data_with_flags

                worksheet_extracted.append(row_to_write)
                
                apply_formatting_to_row(
                    worksheet_extracted, 
                    worksheet_extracted.max_row,
                    row_to_write, 
                    is_filename=is_filename_header, 
                    is_error=is_error_row, 
                    is_header=is_table_header
                )

            self._set_process_status(text="Adjusting column widths...", text_color="blue")
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
                if adjusted_width > 100: adjusted_width = 100
                worksheet_extracted.column_dimensions[column].width = adjusted_width

            # Parse old and new data for comparison
            if old_extracted_data:
                self._set_process_status(text="Comparing data for changes...", text_color="blue")
                old_data_dict = parse_extracted_data_for_comparison(old_extracted_data)
                new_data_dict = parse_extracted_data_for_comparison(all_dxf_extracted_data)
                
                # Log changes
                changes_count = compare_and_log_changes(
                    workbook, 
                    old_data_dict, 
                    new_data_dict, 
                    lambda msg: self._set_process_status(text=f"Change tracking: {msg}", text_color="blue")
                )
                
                if changes_count > 0:
                    self._set_process_status(text=f"Logged {changes_count} changes to Update_Log sheet", text_color="blue")

            self._set_process_status(text="Saving extraction results...", text_color="blue")
            workbook.save(mapping_excel_file)

            self._set_progress("set", 1)
            self._set_process_status(text="✓ Extraction completed successfully!", text_color="green")
            # Check if changes were logged
            update_log_exists = "Update_Log" in workbook.sheetnames
            changes_message = ""
            if update_log_exists and old_extracted_data:
                changes_message = f"\n\nChanges tracked in 'Update_Log' sheet with color coding:\n• Green: Increases (+)\n• Red: Decreases (-)"

            self._show_message(messagebox.showinfo, "Success", f"Extraction completed successfully!\n\nNew files added: {new_files_count}\nExisting files updated: {updated_files_count}{changes_message}\n\nResults saved to: {os.path.basename(mapping_excel_file)}")

        except Exception as e:
            self._set_progress("set", 0)
            self._set_process_status(text="✗ Extraction failed", text_color="red")
            self._show_message(messagebox.showerror, "Error", f"An error occurred during extraction:\n{str(e)}")

        finally:
            self._set_progress("stop")
            self._set_progress("grid_remove")
            self._enable_buttons()

    def _run_consolidation_process(self, mapping_excel_file):

        try:
            self._set_process_status(text="Loading Excel file for consolidation...", text_color="blue")
            self._set_progress("configure", mode="indeterminate")
            self._set_progress("start")
            
            workbook = openpyxl.load_workbook(
                mapping_excel_file,
                keep_vba=Path(mapping_excel_file).suffix.lower() == ".xlsm",
            )

            extracted_sheet_name = "DXF_Extracted_Data"
            if extracted_sheet_name not in workbook.sheetnames:
                self._set_process_status(text=f"Error: '{extracted_sheet_name}' sheet not found.", text_color="red")
                self._show_message(messagebox.showerror, "Error", f"The sheet '{extracted_sheet_name}' was not found in the Excel file. Please run extraction first.")
                return

            worksheet_extracted = workbook[extracted_sheet_name]
            all_extracted_data = []
            for row_idx in range(2, worksheet_extracted.max_row + 1):
                row_values = []
                for col_idx in range(1, worksheet_extracted.max_column + 1): 
                    row_values.append(worksheet_extracted.cell(row=row_idx, column=col_idx).value)
                all_extracted_data.append(row_values)
            
            if not all_extracted_data:
                self._set_process_status(text="No data found in DXF_Extracted_Data sheet for consolidation.", text_color="orange")
                self._show_message(messagebox.showwarning, "No Data", "No data found in 'DXF_Extracted_Data' sheet. Please ensure DXF extraction was successful.")
                return

            self._set_process_status(text=f"Read {len(all_extracted_data)} rows from extracted data.", text_color="blue")

            self._set_process_status(text="Performing MTO consolidation...", text_color="blue")
            
            structure_dict = read_structure_mapping(mapping_excel_file)
            self._set_process_status(text=f"Loaded {len(structure_dict)} structure mappings.", text_color="blue")

            material_dict, material_list = process_material_data(all_extracted_data, structure_dict)
            self._set_process_status(text=f"Consolidated {len(material_list)} unique materials.", text_color="blue")

            consolidated_sheet_name = "Consolidated_Materials"
            if consolidated_sheet_name in workbook.sheetnames:
                del workbook[consolidated_sheet_name]
            worksheet_consolidated = workbook.create_sheet(consolidated_sheet_name)
            
            self._set_process_status(text="Setting up consolidated sheet headers...", text_color="blue")
            last_col_index, structures_in_order = setup_headers(worksheet_consolidated, structure_dict)
            
            config = define_category_config()
            self._set_process_status(text="Writing consolidated data...", text_color="blue")
            write_consolidated_data(worksheet_consolidated, structures_in_order, material_dict, material_list, config)
            
            self._set_process_status(text="Formatting consolidated sheet...", text_color="blue")
            format_summary_sheet(worksheet_consolidated)

            self._set_process_status(text="Creating materials by drawing sheet...", text_color="blue")
            create_drawing_wise_sheet(workbook, all_extracted_data, structure_dict)
            self._set_process_status(text="Materials by drawing sheet created successfully!", text_color="blue")

            self._set_process_status(text="Saving consolidation results...", text_color="blue")
            workbook.save(mapping_excel_file)
            
            self._set_progress("set", 1)
            self._set_process_status(text="✓ Consolidation completed successfully!", text_color="green")
            self._show_message(messagebox.showinfo, "Success", f"Consolidation completed successfully!\n\nSheets updated/created:\n- Consolidated_Materials\n- Materials_by_Drawing\n\nResults saved to: {os.path.basename(mapping_excel_file)}")
            
        except Exception as e:
            self._set_progress("set", 0)
            self._set_process_status(text="✗ Consolidation failed", text_color="red")
            self._show_message(messagebox.showerror, "Error", f"An error occurred during consolidation:\n{str(e)}")
        
        finally:
            self._set_progress("stop")
            self._set_progress("grid_remove")
            self._enable_buttons()

    def _enable_buttons(self):
        if threading.get_ident() != self._ui_thread_id:
            self.after(0, self._enable_buttons)
            return
        self.extract_button.configure(state='normal', text="Extract DXF Data")
        self.consolidate_button.configure(state='normal', text="Consolidate Data")
        self.dxf_button.configure(state='normal')
        self.excel_button.configure(state='normal')
        self.update_dxf_status()
        self.update_excel_status()
        if "failed" in self.process_status.cget("text").lower() or \
        "completed" in self.process_status.cget("text").lower():
            self.process_status.configure(text="Ready to process", text_color="gray")
        self.progressbar.set(0)
    
    def show_help(self):
        """Display help window with usage instructions"""
        help_window = ctk.CTkToplevel(self)
        help_window.title("Help - Usage Instructions")
        help_window.geometry("650x700")
        help_window.resizable(True, True)
        
        # Make help window modal
        help_window.transient(self)
        help_window.grab_set()
        
        # Configure grid
        help_window.grid_columnconfigure(0, weight=1)
        help_window.grid_rowconfigure(1, weight=1)
        
        # Header
        header_label = ctk.CTkLabel(help_window, 
                                text="Usage Instructions", 
                                font=ctk.CTkFont(size=16, weight="bold"))
        header_label.grid(row=0, column=0, pady=20, padx=20, sticky="ew")
        
        # Scrollable text frame
        text_frame = ctk.CTkFrame(help_window)
        text_frame.grid(row=1, column=0, padx=20, pady=(0, 10), sticky="nsew")
        text_frame.grid_columnconfigure(0, weight=1)
        
        # Create content with separate labels for different formatting
        current_row = 0
        
        # Main heading
        main_heading = ctk.CTkLabel(text_frame, 
                                text="USAGE INSTRUCTIONS:", 
                                font=ctk.CTkFont(size=14, weight="bold"),
                                justify="left")
        main_heading.grid(row=current_row, column=0, padx=10, sticky="w")
        current_row += 1
        
        # Section 1 heading
        section1_heading = ctk.CTkLabel(text_frame, 
                                    text="1. EXTRACT DXF DATA:", 
                                    font=ctk.CTkFont(size=12, weight="bold"),
                                    justify="left")
        section1_heading.grid(row=current_row, column=0, padx=10, sticky="w")
        current_row += 1
        
        # Section 1 content
        section1_content = """
• DXF files should contain Approximate Quantites Table with "APPROXIMATE QUANTITIES"
  or "APPROXIMATE QUANTITY" as heading created using AutoCAD Native Table
• Click "Select DXF Files" to choose one or more DXF files
• Click "Extract DXF Data" to process the selected DXF files
• The app will read quantity tables from each DXF file
• Results are saved to "DXF_Extracted_Data" sheet in your Excel file"""
        
        section1_text = ctk.CTkLabel(text_frame, 
                                    text=section1_content, 
                                    font=ctk.CTkFont(size=12),
                                    justify="left",
                                    wraplength=550)
        section1_text.grid(row=current_row, column=0, padx=20, pady=(2, 10), sticky="w")
        current_row += 1

        # Section 2 heading
        section2_heading = ctk.CTkLabel(text_frame, 
                                    text="2. CONSOLIDATE DATA:", 
                                    font=ctk.CTkFont(size=12, weight="bold"),
                                    justify="left")
        section2_heading.grid(row=current_row, column=0, padx=10, pady=(10, 2), sticky="w")
        current_row += 1
        
        # Section 2 content - split into two parts for image insertion
        section2_content_part1 = """• Excel file should contain Drawing Name matching File name and Structure name in sheet named
    "Drawing_Structure_Mapping" for consolidation"""
        
        section2_text_part1 = ctk.CTkLabel(text_frame, 
                                        text=section2_content_part1, 
                                        font=ctk.CTkFont(size=12),
                                        justify="left",
                                        wraplength=550)
        section2_text_part1.grid(row=current_row, column=0, padx=20, pady=(2, 5), sticky="w")
        current_row += 1
        
        # Add image after the mapping explanation
        try:
            mapping_image = ctk.CTkImage(light_image=Image.open(self.resource_path("assets/images/snap2.png")),
                                        dark_image=Image.open(self.resource_path("assets/images/snap2.png")),
                                        size=(400, 100))  # Adjust size as needed
            image_label = ctk.CTkLabel(text_frame, image=mapping_image, text="")
            image_label.grid(row=current_row, column=0, padx=20, pady=10, sticky="w")
            current_row += 1
        except FileNotFoundError:
            # If image not found, show a placeholder text
            image_placeholder = ctk.CTkLabel(text_frame, 
                                            text="[Image: Drawing_Structure_Mapping example - snap2.png not found]",
                                            font=ctk.CTkFont(size=10, style="italic"),
                                            text_color="gray")
            image_placeholder.grid(row=current_row, column=0, padx=20, pady=5, sticky="w")
            current_row += 1
        
        # Section 2 content - remaining part
        section2_content_part2 = """• Click "Consolidate Data" to create MTO reports
    • This processes the extracted data and creates:
        - "Consolidated_Materials" sheet (summary by structure)
        - "Materials_by_Drawing" sheet (summary by drawing)"""
        
        section2_text_part2 = ctk.CTkLabel(text_frame, 
                                        text=section2_content_part2, 
                                        font=ctk.CTkFont(size=12),
                                        justify="left",
                                        wraplength=550)
        section2_text_part2.grid(row=current_row, column=0, padx=20, pady=(5, 10), sticky="w")
        current_row += 1
        
        # Important notes heading
        notes_heading = ctk.CTkLabel(text_frame, 
                                    text="IMPORTANT NOTES:", 
                                    font=ctk.CTkFont(size=12, weight="bold"),
                                    justify="left")
        notes_heading.grid(row=current_row, column=0, padx=10, pady=(10, 2), sticky="w")
        current_row += 1
        
        # Important notes content
        notes_content = """
• Ensure DXF files contain valid quantity tables created using AutoCAD native Table
• Check that Excel file is not open in another program
• Verify the "Drawing_Structure_Mapping" sheet exists and has correct structure
• Large files may take longer to process"""
        
        notes_text = ctk.CTkLabel(text_frame, 
                                text=notes_content, 
                                font=ctk.CTkFont(size=12),
                                justify="left",
                                wraplength=550)
        notes_text.grid(row=current_row, column=0, padx=20, pady=(2, 10), sticky="w")
        
        # Close button
        close_button = ctk.CTkButton(help_window, 
                                    text="Close", 
                                    command=help_window.destroy,
                                    width=100)
        close_button.grid(row=2, column=0, pady=20)
        
        # Center the help window
        help_window.after(100, lambda: help_window.focus_set())


if __name__ == "__main__":
    root_for_testing = ctk.CTk()
    root_for_testing.withdraw()
    app = DxfExtractorApp(root_for_testing)
    root_for_testing.mainloop()