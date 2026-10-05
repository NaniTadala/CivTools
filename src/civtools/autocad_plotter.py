from array import array
import customtkinter as ctk
from tkinter import filedialog, messagebox, scrolledtext
import openpyxl
from pyautocad import Autocad, APoint
import sys
import os
import time
import math
import threading # Import threading for long-running AutoCAD operations

class AutoCADPlotterApp(ctk.CTkToplevel):
    def __init__(self, master=None):
        super().__init__(master)
        self._ui_thread_id = threading.get_ident()
        # 1. Hide the window initially
        self.withdraw()
        self.title("AutoCAD Smart Mapper")
        self.geometry("700x600")

        # Configure grid layout
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure((0, 1, 2, 3), weight=1) # Adjusted for progress bar row

        self.dxf_files_paths = []
        self.mapping_excel_path = ""

        self.title("AutoCAD Smart Mapper")
        self.geometry("500x800") # Adjusted height as format section is removed
        self.resizable(False, False)

        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("dark-blue")

        self.excel_file_path = ""

        # Configure the main window's grid
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # --- Main Frame ---
        self.main_frame = ctk.CTkFrame(self, corner_radius=10, fg_color=("gray90", "gray13"))
        self.main_frame.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        self.main_frame.grid_columnconfigure(0, weight=1)
        # Configure main_frame rows for proper layout after removing format section
        self.main_frame.grid_rowconfigure(0, weight=0) # Title
        self.main_frame.grid_rowconfigure(1, weight=0) # Separator 1
        self.main_frame.grid_rowconfigure(2, weight=0) # File Selection (previously row 4, shifted up)
        self.main_frame.grid_rowconfigure(3, weight=0) # Separator 2
        self.main_frame.grid_rowconfigure(4, weight=0) # Settings (previously row 6, shifted up)
        self.main_frame.grid_rowconfigure(5, weight=0) # Separator 3
        self.main_frame.grid_rowconfigure(6, weight=0) # Plot Button (previously row 8, shifted up)
        self.main_frame.grid_rowconfigure(7, weight=1) # Console (previously row 9, shifted up and made expandable)


        # --- Title ---
        self.title_label = ctk.CTkLabel(self.main_frame, text="AutoCAD Smart Mapper",
                                            font=ctk.CTkFont(size=24, weight="bold"))
        self.title_label.grid(row=0, column=0, pady=(20, 15), sticky="n")

        # --- Separator 1 ---
        self.separator1 = ctk.CTkFrame(self.main_frame, height=2, fg_color="gray70")
        self.separator1.grid(row=1, column=0, sticky="ew", padx=10, pady=10)

        # --- File Selection Section --- (Previously row 4, now row 2)
        self.file_frame = ctk.CTkFrame(self.main_frame, corner_radius=8, fg_color="transparent")
        self.file_frame.grid(row=2, column=0, pady=10, padx=15, sticky="ew")
        self.file_frame.grid_columnconfigure(0, weight=1) # For file path label
        self.file_frame.grid_columnconfigure(1, weight=0) # For help button

        self.file_label_title = ctk.CTkLabel(self.file_frame, text="1. Select Excel Data File",
                                               font=ctk.CTkFont(size=16, weight="bold"))
        self.file_label_title.grid(row=0, column=0, sticky="w", pady=(5, 5), padx=5, columnspan=2)

        self.label_file_path = ctk.CTkLabel(self.file_frame, text="No Excel file selected.",
                                             wraplength=450, font=("Segoe UI", 12, "italic"),
                                             text_color="gray50")
        self.label_file_path.grid(row=1, column=0, pady=(0, 10), sticky="w", padx=5, columnspan=2)

        self.btn_select_file = ctk.CTkButton(self.file_frame, text="Browse Excel File...",
                                               command=self.select_excel_file,
                                               font=ctk.CTkFont(size=13, weight="bold"))
        self.btn_select_file.grid(row=2, column=0, pady=(0, 5), sticky="w", padx=5)

        # New: Help button for Excel format
        self.btn_help_excel_format = ctk.CTkButton(self.file_frame, text="?",
                                                    width=30, height=30,
                                                    font=ctk.CTkFont(size=16, weight="bold"),
                                                    command=self.show_excel_format_help)
        self.btn_help_excel_format.grid(row=2, column=1, pady=(0, 5), padx=(0, 5), sticky="e")


        # --- Separator 2 --- (Previously row 3, now row 3)
        self.separator2 = ctk.CTkFrame(self.main_frame, height=2, fg_color="gray70")
        self.separator2.grid(row=3, column=0, sticky="ew", padx=10, pady=10)

        # --- Settings Section --- (Previously row 6, now row 4)
        self.settings_frame = ctk.CTkFrame(self.main_frame, corner_radius=8, fg_color="transparent")
        self.settings_frame.grid(row=4, column=0, pady=10, padx=15, sticky="ew")
        self.settings_frame.grid_columnconfigure(1, weight=1)

        self.settings_label_title = ctk.CTkLabel(self.settings_frame, text="2. Plotting Parameters",
                                                     font=ctk.CTkFont(size=16, weight="bold"))
        self.settings_label_title.grid(row=0, column=0, columnspan=2, sticky=ctk.W, pady=(5, 10))

        self.label_text_height = ctk.CTkLabel(self.settings_frame, text="Text Height (AutoCAD Units):",
                                                     font=("Segoe UI", 12))
        self.label_text_height.grid(row=1, column=0, padx=(0, 10), pady=8, sticky=ctk.W)
        self.text_height_entry = ctk.CTkEntry(self.settings_frame, width=180, font=("Segoe UI", 12))
        self.text_height_entry.insert(0, "250")
        self.text_height_entry.grid(row=1, column=1, padx=(0, 0), pady=8, sticky=ctk.EW)

        self.label_text_offset = ctk.CTkLabel(self.settings_frame, text="Text Offset (from box bottom):",
                                                     font=("Segoe UI", 12))
        self.label_text_offset.grid(row=2, column=0, padx=(0, 10), pady=8, sticky=ctk.W)
        self.text_offset_entry = ctk.CTkEntry(self.settings_frame, width=180, font=("Segoe UI", 12))
        self.text_offset_entry.insert(0, "125")
        self.text_offset_entry.grid(row=2, column=1, padx=(0, 0), pady=8, sticky=ctk.EW)

        # --- Separator 3 --- (Previously row 4, now row 5)
        self.separator3 = ctk.CTkFrame(self.main_frame, height=2, fg_color="gray70")
        self.separator3.grid(row=5, column=0, sticky="ew", padx=10, pady=10)

        # --- Action Button --- (Previously row 8, now row 6)
        self.btn_plot = ctk.CTkButton(self.main_frame, text="🚀 Plot Boxes to AutoCAD",
                                           command=self.start_plot_thread, # Changed to start a thread
                                           state=ctk.DISABLED, width=250, height=45,
                                           font=ctk.CTkFont(size=16, weight="bold"), corner_radius=10)
        self.btn_plot.grid(row=6, column=0, pady=20)

        # --- Console Section --- (Previously row 9, now row 7)
        self.create_console_section(7)
        # 2. Show the window after everything is set up
        self.deiconify()

    def create_console_section(self, row_num):
        console_frame = ctk.CTkFrame(self.main_frame, corner_radius=10)
        console_frame.grid(row=row_num, column=0, sticky="nsew", padx=10, pady=(10, 10))
        console_frame.grid_columnconfigure(0, weight=1)
        console_frame.grid_rowconfigure(1, weight=1) # Allow console_log to expand

        console_title = ctk.CTkLabel(
            console_frame,
            text="📜 Console Log",
            font=ctk.CTkFont(size=16, weight="bold"),
            anchor="w"
        )
        console_title.grid(row=0, column=0, sticky="w", padx=15, pady=(10, 5))

        self.console_log = ctk.CTkTextbox(
            console_frame,
            height=200,
            font=("Consolas", 12),
            wrap="word",
            state="disabled"
        )
        self.console_log.grid(row=1, column=0, sticky="nsew", padx=15, pady=(0, 10))
        
        # Configure tags for colors - Updated for light theme
        self.console_log.tag_config("INFO", foreground="#2B2B2B")        # Dark gray for light theme
        self.console_log.tag_config("SUCCESS", foreground="#22741C")      # Dark green for light theme
        self.console_log.tag_config("WARNING", foreground="#CC6600")      # Dark orange for light theme
        self.console_log.tag_config("ERROR", foreground="#DC143C")        # Dark red for light theme

    def log_message(self, message, level="INFO"):
        """Logs a message to the console text widget with color-coding."""
        if threading.get_ident() != self._ui_thread_id:
            self.after(0, self.log_message, message, level)
            return

        self.console_log.configure(state="normal")
        self.console_log.insert(ctk.END, message + "\n", level)
        self.console_log.configure(state="disabled")
        self.console_log.yview(ctk.END) # Auto-scroll to the bottom
        self.update_idletasks() # Refresh GUI
        print(message) # Also print to system console for debugging
    
    def clear_console(self):
        if threading.get_ident() != self._ui_thread_id:
            self.after(0, self.clear_console)
            return
        self.console_log.configure(state="normal")
        self.console_log.delete("1.0", ctk.END)
        self.console_log.configure(state="disabled")

    def select_excel_file(self):
        file_path = filedialog.askopenfilename(
            title="Select Excel File",
            filetypes=(("Excel files", "*.xlsx *.xls"), ("All files", "*.*"))
        )
        if file_path:
            self.excel_file_path = file_path
            self.label_file_path.configure(text=f"Selected: {os.path.basename(file_path)}", text_color=("black", "white"))
            self.btn_plot.configure(state=ctk.NORMAL)
            self.log_message(f"Excel file selected: {file_path}", "SUCCESS")
        else:
            self.label_file_path.configure(text="No Excel file selected.", text_color="gray50")
            self.btn_plot.configure(state=ctk.DISABLED)
            self.log_message("File selection cancelled.", "WARNING")

    def show_excel_format_help(self):
        """Creates and displays a new Toplevel window with Excel format instructions."""
        help_window = ctk.CTkToplevel(self)
        help_window.title("Required Excel Format Help")
        help_window.geometry("500x300")
        help_window.transient(self) # Make it appear on top of the main window
        help_window.grab_set() # Make it modal (block interaction with main window)
        help_window.resizable(False, False)

        # Center the Toplevel window
        self.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() // 2) - (help_window.winfo_width() // 2)
        y = self.winfo_y() + (self.winfo_height() // 2) - (help_window.winfo_height() // 2)
        help_window.geometry(f"+{x}+{y}")


        help_frame = ctk.CTkFrame(help_window, corner_radius=8, fg_color="transparent")
        help_frame.pack(pady=10, padx=15, fill="both", expand=True)
        help_frame.grid_columnconfigure(0, weight=1)

        format_label_title = ctk.CTkLabel(help_frame, text="📋 Required Excel Format",
                                           font=ctk.CTkFont(size=18, weight="bold"))
        format_label_title.grid(row=0, column=0, sticky="w", pady=(5, 10), padx=5)

        instructions_text = "Your Excel file must have the following column structure (starting from row 2):"
        format_instructions_label = ctk.CTkLabel(help_frame, text=instructions_text,
                                                justify="left", font=("Segoe UI", 12),
                                                text_color=("gray20", "gray80"),
                                                wraplength=450)
        format_instructions_label.grid(row=1, column=0, pady=(5, 15), sticky="w", padx=5)

        table_frame = ctk.CTkFrame(help_frame, corner_radius=8, fg_color=("gray95", "gray20"))
        table_frame.grid(row=2, column=0, pady=(0, 10), sticky="ew", padx=5)
        table_frame.grid_columnconfigure((0, 1, 2, 3, 4), weight=1)

        headers = ["A", "B", "C", "D", "E"]
        descriptions = ["Center X", "Center Y", "Box Width", "Box Height", "Box ID"]
        data_types = ["(numeric)", "(numeric)", "(numeric > 0)", "(numeric > 0)", "(text/optional)"]

        for i, header in enumerate(headers):
            header_label = ctk.CTkLabel(table_frame, text=header,
                                         font=ctk.CTkFont(size=11, weight="bold"),
                                         fg_color=("gray85", "gray30"), corner_radius=5)
            header_label.grid(row=0, column=i, padx=2, pady=2, sticky="ew")

        for i, desc in enumerate(descriptions):
            desc_label = ctk.CTkLabel(table_frame, text=desc,
                                       font=("Segoe UI", 10),
                                       text_color=("gray30", "gray70"))
            desc_label.grid(row=1, column=i, padx=2, pady=2, sticky="ew")

        for i, dtype in enumerate(data_types):
            dtype_label = ctk.CTkLabel(table_frame, text=dtype,
                                        font=("Segoe UI", 9, "italic"),
                                        text_color=("gray50", "gray60"))
            dtype_label.grid(row=2, column=i, padx=2, pady=2, sticky="ew")

        # Add a close button
        close_button = ctk.CTkButton(help_window, text="Close", command=help_window.destroy)
        close_button.pack(pady=(0, 10))

        help_window.wait_window(help_window) # Wait for the Toplevel window to close

    def create_layer(self, acad_doc, layer_name, color_index):
        """Create or get existing layer with error handling."""
        try:
            layer = acad_doc.Layers.Item(layer_name)
            self.log_message(f"Layer '{layer_name}' already exists.", "INFO")
        except Exception:
            try:
                layer = acad_doc.Layers.Add(layer_name)
                layer.Color = color_index
                self.log_message(f"Layer '{layer_name}' created successfully.", "SUCCESS")
            except Exception as e:
                self.log_message(f"Warning: Could not create layer {layer_name}: {e}", "ERROR")
                return None
        return layer

    def start_plot_thread(self):
        """Validate UI input, then plot using AutoCAD on a COM-initialized worker."""
        if not self.excel_file_path:
            messagebox.showwarning("No File", "Please select an Excel file first.")
            return

        try:
            custom_text_height = float(self.text_height_entry.get())
            custom_offset_distance = float(self.text_offset_entry.get())
            if custom_text_height <= 0 or custom_offset_distance < 0:
                raise ValueError("Text Height must be positive, Offset must be non-negative.")
        except ValueError as e:
            messagebox.showerror("Input Error", f"Invalid input for text settings: {e}")
            self.log_message(f"Input Error: {e}", "ERROR")
            return

        self.btn_plot.configure(state=ctk.DISABLED)
        self.btn_select_file.configure(state=ctk.DISABLED)
        self.clear_console()
        threading.Thread(
            target=self.plot_boxes,
            args=(self.excel_file_path, custom_text_height, custom_offset_distance),
            daemon=True,
        ).start()

    def _show_plot_error(self, title, message):
        if threading.get_ident() != self._ui_thread_id:
            self.after(0, self._show_plot_error, title, message)
            return
        messagebox.showerror(title, message)

    def _finish_plot(self, result_message=None, error_title=None, error_message=None):
        self.btn_plot.configure(state=ctk.NORMAL)
        self.btn_select_file.configure(state=ctk.NORMAL)
        if error_title:
            messagebox.showerror(error_title, error_message)
        elif result_message:
            messagebox.showinfo("Plotting Complete!", result_message)

    def plot_boxes(self, excel_file_path, custom_text_height, custom_offset_distance):
        import pythoncom

        com_initialized = False
        try:
            pythoncom.CoInitialize()
            com_initialized = True
            self._plot_boxes_job(
                excel_file_path, custom_text_height, custom_offset_distance
            )
        except Exception as e:
            self.log_message(f"Plotting failed: {e}", "ERROR")
            self.after(0, self._finish_plot, None, "Plotting Error", str(e))
        finally:
            workbook = getattr(self, "_plot_workbook", None)
            if workbook is not None:
                workbook.close()
                self._plot_workbook = None
            if com_initialized:
                pythoncom.CoUninitialize()

    def _plot_boxes_job(self, excel_file_path, custom_text_height, custom_offset_distance):
        workbook = None
        self.log_message("--- Starting Plot Process ---", "INFO")
        self.log_message("Connecting to AutoCAD...", "INFO")

        try:
            acad = Autocad(create_if_not_exists=True)
            acad.app.Visible = True
            acad_doc = acad.doc
            self.log_message("✅ Connected to AutoCAD.", "SUCCESS")
        except Exception as e:
            self.log_message(f"❌ Failed to connect to AutoCAD: {e}", "ERROR")
            self.after(
                0,
                self._finish_plot,
                None,
                "AutoCAD Error",
                f"Cannot connect to AutoCAD: {e}\nPlease ensure AutoCAD is installed and running.",
            )
            return

        try:
            workbook = openpyxl.load_workbook(excel_file_path, data_only=True)
            self._plot_workbook = workbook
            sheet = workbook.active
            self.log_message("✅ Excel file opened successfully.", "SUCCESS")
        except Exception as e:
            self.log_message(f"❌ Failed to open Excel file: {e}", "ERROR")
            self.after(0, self._finish_plot, None, "Excel Error", f"Could not open Excel file: {e}")
            return

        last_row = sheet.max_row
        if last_row < 2:
            self.log_message("No plot data found in Excel file.", "WARNING")
            self.after(
                0,
                self._finish_plot,
                "No data found in the Excel file. Please ensure data starts from row 2.",
            )
            return

        self.create_layer(acad_doc, "AutomatedBOXES", 1)      # Red
        self.create_layer(acad_doc, "AutomatedBOXESTEXT", 2) # Yellow

        box_count = 0
        error_count = 0
        start_time = time.time()
        
        self.log_message(f"Found {last_row - 1} data rows. Starting to plot...", "INFO")

        for i in range(2, last_row + 1):
            try:
                center_x_val = sheet.cell(row=i, column=1).value
                center_y_val = sheet.cell(row=i, column=2).value
                box_width_val = sheet.cell(row=i, column=3).value
                box_height_val = sheet.cell(row=i, column=4).value
                box_id = sheet.cell(row=i, column=5).value

                if any(val is None for val in [center_x_val, center_y_val, box_width_val, box_height_val]):
                    self.log_message(f"Row {i}: Skipped - Missing one or more required values (X, Y, Width, Height).", "WARNING")
                    error_count += 1
                    continue
                
                # Try converting to float
                center_x = float(center_x_val)
                center_y = float(center_y_val)
                box_width = float(box_width_val)
                box_height = float(box_height_val)

                if box_width <= 0 or box_height <= 0:
                    self.log_message(f"Row {i}: Skipped - Width and Height must be positive numbers.", "WARNING")
                    error_count += 1
                    continue

                x1 = center_x - box_width / 2
                y1 = center_y - box_height / 2
                x2 = center_x + box_width / 2
                y2 = center_y + box_height / 2

                try:
                    rectangle_points = array(
                        "d",
                        [
                            x1, y1, 0.0,
                            x2, y1, 0.0,
                            x2, y2, 0.0,
                            x1, y2, 0.0,
                        ],
                    )
                    rectangle = acad_doc.ModelSpace.AddPolyline(rectangle_points)
                    rectangle.Closed = True
                    rectangle.Layer = "AutomatedBOXES"
                except Exception as e:
                    self.log_message(f"Row {i}: Failed to draw rectangle. Error: {e}", "ERROR")
                    error_count += 1
                    continue

                if box_id is not None and str(box_id).strip():
                    try:
                        acad_doc.ActiveLayer = acad_doc.Layers.Item("AutomatedBOXESTEXT")
                        text_insert_point = APoint(center_x, center_y - (box_height / 2) - custom_offset_distance)
                        text_obj = acad_doc.ModelSpace.AddText(str(box_id), text_insert_point, custom_text_height)
                        text_obj.Alignment = 7 # acAlignmentBottomCenter
                        text_obj.TextAlignmentPoint = text_insert_point
                    except Exception as e:
                        self.log_message(f"Row {i}: Could not add text label. Error: {e}", "WARNING")

                box_count += 1

            except (ValueError, TypeError) as e:
                self.log_message(f"Row {i}: Skipped - Invalid data format. Check if columns A-D are numeric. Error: {e}", "ERROR")
                error_count += 1
                continue
            except Exception as e:
                self.log_message(f"Row {i}: An unexpected error occurred: {e}", "ERROR")
                error_count += 1
                continue
        
        end_time = time.time()
        
        self.log_message("--- Plotting Process Finished ---", "INFO")

        result_message = f"✅ {box_count} boxes successfully plotted!"
        if error_count > 0:
            result_message += f"\n❌ {error_count} rows were skipped due to errors."
        
        result_message += f"\n\n🕒 Total time: {end_time - start_time:.2f} seconds."

        self.log_message(result_message, "SUCCESS" if error_count == 0 else "WARNING")
        self.after(0, self._finish_plot, result_message)

if __name__ == "__main__":
    # To make the app look sharp on high-DPI displays (Windows only)
    if sys.platform == "win32":
        try:
            from ctypes import windll
            windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    root_for_testing = ctk.CTk()
    root_for_testing.withdraw()
    app = AutoCADPlotterApp(root_for_testing)
    root_for_testing.mainloop()