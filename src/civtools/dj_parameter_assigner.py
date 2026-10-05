import comtypes
import comtypes.client
from comtypes import automation
import ctypes
import pythoncom
from comtypes import IUnknown
import customtkinter as ctk
from tkinter import messagebox
import threading
import sys
import json
import os
from pathlib import Path
from datetime import datetime
from PIL import Image, ImageTk
import tkinter as tk

# ==================== CONSTANTS ====================
APP_NAME = "STAAD Pro DJ Parameter Tool"
COMPANY = "L&T Energy Hydrocarbon"

# Color scheme (same as before)
COLOR_PALETTE = {
    "primary": "#4285F4",
    "primary_dark": "#4285F4",
    "secondary": "#7209b7",
    "accent": "#f72585",
    "background": "#f8f9fa",
    "surface": "#ffffff",
    "surface_variant": "#495057",
    "border": "#dee2e6",
    "text_primary": "#212529",
    "text_secondary": "#495057",
    "success": "#4cc9f0",
    "warning": "#f8961e",
    "error": "#ef233c",
    "dark": {
        "background": "#1e1e1e",
        "surface": "#2d2d2d",
        "border": "#444444",
        "text_primary": "#f0f0f0",
        "text_secondary": "#aaaaaa"
    }
}

# Font settings (same as before)
FONT_FAMILY = "Segoe UI"
FONT_CONFIG = {
    "title": (FONT_FAMILY, 24, "bold"),
    "subtitle": (FONT_FAMILY, 14),
    "card_title": (FONT_FAMILY, 16, "bold"),
    "label": (FONT_FAMILY, 12),
    "button": (FONT_FAMILY, 14, "bold"),
    "status": (FONT_FAMILY, 12),
    "console": ("Consolas", 11),
    "help_title": (FONT_FAMILY, 16, "bold"),
    "help_text": (FONT_FAMILY, 12)
}

# Design codes mapping (same as before)
DESIGN_CODES = {
    "AISC 360-05": 1045,
    "AISC 360-10": 1061,
    "AISC 360-16": 1067,
    "AISC": 1002,
    "IS800 LSD": 1032,
    "IS800 WSD": 1052,
    "IS800 1984": 1009
}

# App dimensions (same as before)
DIMENSIONS = {
    "min_width": 580,
    "min_height": 800,
    "header_height": 140,
    "card_padding": 20,
    "input_width": 250,
    "button_height": 45
}

# ==================== COM UTILITY FUNCTIONS ====================
def make_safe_array_double(size):
    return automation._midlSAFEARRAY(ctypes.c_double).create([0]*size)

def make_safe_array_int(size):
    return automation._midlSAFEARRAY(ctypes.c_int).create([0]*size)

def make_safe_array_long(size):
    return automation._midlSAFEARRAY(ctypes.c_long).create([0]*size)

def make_variant_vt_ref(obj, var_type):
    var = automation.VARIANT()
    var._.c_void_p = ctypes.addressof(obj)
    var.vt = var_type | automation.VT_BYREF
    return var

# ==================== HELP DIALOG ====================
class HelpDialog(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Usage Instructions")
        self.geometry("500x400")
        self.resizable(False, False)
        
        # Make dialog modal
        self.transient(parent)
        self.grab_set()
        
        # Center the dialog on parent
        self.after(10, self.center_on_parent)
        
        self.create_help_content()
        
    def center_on_parent(self):
        """Center the dialog on the parent window"""
        parent_x = self.master.winfo_x()
        parent_y = self.master.winfo_y()
        parent_width = self.master.winfo_width()
        parent_height = self.master.winfo_height()
        
        dialog_width = 600
        dialog_height = 700
        
        x = parent_x + (parent_width - dialog_width) // 2
        y = parent_y + (parent_height - dialog_height) // 2
        
        self.geometry(f"{dialog_width}x{dialog_height}+{x}+{y}")

    def resource_path(self, relative_path):
        """ Get absolute path to resource, works for dev and for PyInstaller """
        if getattr(sys, "frozen", False):
            base_path = sys._MEIPASS
        else:
            base_path = Path(__file__).resolve().parents[2]
        return os.path.join(base_path, relative_path)
        
    def create_help_content(self):
        """Create the help dialog content"""
        # Main container
        main_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="#f8f9fa")
        main_frame.pack(fill="both", expand=True)
        
        # Header
        header_frame = ctk.CTkFrame(main_frame, height=60, corner_radius=0, fg_color=COLOR_PALETTE["primary"])
        header_frame.pack(fill="x", pady=(0, 0))
        header_frame.pack_propagate(False)
        
        ctk.CTkLabel(
            header_frame,
            text="📖 Usage Instructions",
            font=FONT_CONFIG["help_title"],
            text_color="white"
        ).pack(expand=True)
        
        # Content frame with scrolling
        content_frame = ctk.CTkFrame(main_frame, corner_radius=0, fg_color="#f8f9fa")
        content_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Create bold font by modifying the existing one
        bold_font = (FONT_CONFIG["help_text"][0], FONT_CONFIG["help_text"][1], "bold")
        
        # Important Instructions section
        ctk.CTkLabel(
            content_frame,
            text="Important Instructions:",
            font=("Arial", 16, "bold"),
            justify="left",
            anchor="nw",
        ).pack(fill="x")
        
        ctk.CTkLabel(
            content_frame,
            text="1. Physical member shall be formed in STAAD by using form member command in STAAD before executing this program",
            font=FONT_CONFIG["help_text"],
            justify="left",
            anchor="nw",
            wraplength=500
        ).pack(fill="x", pady=(0, 10))
        
        # Try to load and display the image
        try:
            image = Image.open(self.resource_path("assets/images/snap.png"))
                # Resize image if it's too large
            max_width = 500
            if image.width > max_width:
                ratio = max_width / image.width
                new_height = int(image.height * ratio)
                image = image.resize((max_width, new_height), Image.Resampling.LANCZOS)
                
                # Convert to CTkImage
            ctk_image = ctk.CTkImage(light_image=image, dark_image=image, size=(350, 200))
                
                # Display image
            image_label = ctk.CTkLabel(
                content_frame,
                image=ctk_image,
                text=""
            )
            image_label.pack(pady=10)

            ctk.CTkLabel(
            content_frame,
            text="2. Since DJ/DFF is not code specific dependent, Design brief generated can be copied/cut re-framed in desired design brief",
            font=FONT_CONFIG["help_text"],
            justify="left",
            anchor="nw",
            wraplength=500
        ).pack(fill="x", pady=(0, 10))
            
            # How to use this tool section
            ctk.CTkLabel(
                content_frame,
                text="How to use this tool:",
                font=("Arial", 16, "bold"),
                justify="left",
                anchor="nw"
            ).pack(fill="x")
            
            ctk.CTkLabel(
                content_frame,
                text="""1. Configure Design Settings:
    • Select "New" to create a new design brief with chosen code
    • Select "Existing" to use an existing design brief number

2. Choose Member Selection:
    • "All Member": Process all members in the model
    • "All Member with Material": Process only members with specific material

3. Click "Assign DJ Parameters" to start the process""",
                font=FONT_CONFIG["help_text"],
                justify="left",
                anchor="nw",
                wraplength=500
            ).pack(fill="x", pady=(0, 10))
            
        except Exception as e:
            # If image loading fails, show error message
            error_label = ctk.CTkLabel(
                content_frame,
                text=f"[Image loading error: {str(e)}]",
                font=FONT_CONFIG["help_text"],
                text_color="red"
            )
            error_label.pack(pady=10)
        
        # Close button
        close_button = ctk.CTkButton(
            content_frame,
            text="Close",
            command=self.destroy,
            height=40,
            width=120,
            corner_radius=8,
            font=FONT_CONFIG["button"],
            fg_color=COLOR_PALETTE["primary"],
            hover_color=COLOR_PALETTE["primary_dark"]
        )
        close_button.pack(pady=20)

# ==================== MAIN APPLICATION ====================
class StaadDJTool(ctk.CTkToplevel):
    def __init__(self, master=None):
        super().__init__(master)
        self._ui_thread_id = threading.get_ident()
        # 1. Hide the window initially
        self.withdraw()

        self.setup_window()
        self.load_settings()
        self.setup_ui()

        self.running = False
        self.staad_connection = None
        self.log_history = []

        # 2. Show the window after everything is set up
        self.deiconify()
        
    # ==================== UI SETUP (same as before) ====================
    def setup_window(self):
        """Configure the main window properties"""
        self.title(f"{APP_NAME}")
        self.geometry(f"{DIMENSIONS['min_width']}x{DIMENSIONS['min_height']}")
        self.minsize(DIMENSIONS["min_width"], DIMENSIONS["min_height"])
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.resizable(False, False)
        
        # Set theme
        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")

    def load_settings(self):
        """Load application settings from file"""
        if getattr(sys, "frozen", False):
            app_data = Path(os.environ.get("APPDATA", Path.home()))
            settings_dir = app_data / "CivTools"
            legacy_settings_file = Path(sys.executable).resolve().parent / "staad_dj_settings.json"
        else:
            settings_dir = Path(__file__).resolve().parents[2]
            legacy_settings_file = settings_dir / "staad_dj_settings.json"
        self.settings_file = str(settings_dir / "staad_dj_settings.json")
        default_settings = {
            "design_brief": "New",
            "brief_number": "2",
            "design_code": "IS800 LSD",
            "member_selection": "All Member with Material",
            "material": "STEEL",
            "window_size": [DIMENSIONS["min_width"], DIMENSIONS["min_height"]],
            "theme": "system"
        }
        
        try:
            settings_path = Path(self.settings_file)
            if settings_path.exists():
                with settings_path.open("r", encoding="utf-8") as f:
                    self.settings = json.load(f)
                    # Ensure all keys exist
                    for key in default_settings:
                        if key not in self.settings:
                            self.settings[key] = default_settings[key]
            elif legacy_settings_file.exists():
                with legacy_settings_file.open("r", encoding="utf-8") as f:
                    self.settings = json.load(f)
            else:
                self.settings = default_settings.copy()
        except (OSError, json.JSONDecodeError) as error:
            self.settings = default_settings.copy()
            messagebox.showwarning(
                "Settings Warning",
                f"Could not load STAAD DJ settings; defaults will be used.\n{error}",
            )

    def save_settings(self):
        """Save current settings to file"""
        try:
            settings_path = Path(self.settings_file)
            settings_path.parent.mkdir(parents=True, exist_ok=True)
            with settings_path.open("w", encoding="utf-8") as f:
                json.dump(self.settings, f, indent=4)
        except Exception as e:
            self.log_error(f"Failed to save settings: {str(e)}")

    def setup_ui(self):
        """Create all UI elements"""
        # Main container
        self.main_frame = ctk.CTkFrame(self, corner_radius=0)
        self.main_frame.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)
        self.main_frame.grid_columnconfigure(0, weight=1)
        self.main_frame.grid_rowconfigure(1, weight=1)

        # Header
        self.create_header()

        # Main content area with scroll
        self.content_frame = ctk.CTkFrame(
            self.main_frame, 
            corner_radius=0,
            fg_color=self.get_color("background")
        )
        self.content_frame.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)
        self.content_frame.grid_columnconfigure(0, weight=1)

        # Configuration sections
        self.create_config_section()
        self.create_member_section()
        self.create_action_buttons()
        self.create_status_section()

        # Initialize UI state
        self.on_brief_type_change()
        self.on_member_selection_change()

    def create_header(self):
        """Create the application header with help button"""
        header_frame = ctk.CTkFrame(
            self.main_frame,
            height=DIMENSIONS["header_height"],
            corner_radius=0,
            fg_color=self.get_color("primary"),
            border_width=0
        )
        header_frame.grid(row=0, column=0, sticky="ew", padx=0, pady=0)
        header_frame.grid_columnconfigure(0, weight=1)

        # Help button in top right corner
        help_button = ctk.CTkButton(
            header_frame,
            text="?",
            command=self.show_help,
            width=30,
            height=30,
            corner_radius=15,
            font=ctk.CTkFont(size=16, weight="bold"),
            fg_color="white",
            hover_color="#f0f0f0",
            text_color=self.get_color("primary")
        )
        help_button.place(x=350, y=10)

        # Title and subtitle
        title_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        title_frame.pack(expand=True)

        ctk.CTkLabel(
            title_frame,
            text=APP_NAME,
            font=FONT_CONFIG["title"],
            text_color="white"
        ).pack(pady=(10, 0))

        ctk.CTkLabel(
            title_frame,
            text=f"{COMPANY}",
            font=FONT_CONFIG["subtitle"],
            text_color="white"
        ).pack(pady=(0, 15))

    def show_help(self):
        """Show the help dialog"""
        if not hasattr(self, 'help_dialog') or not self.help_dialog.winfo_exists():
            self.help_dialog = HelpDialog(self)
        else:
            self.help_dialog.focus()

    def create_config_section(self):
        """Create design configuration section with centered help button above"""
        # Create a container frame for the help button and config card
        container = ctk.CTkFrame(
            self.content_frame,
            fg_color="transparent"
        )
        container.grid(row=0, column=0, sticky="ew", padx=DIMENSIONS["card_padding"], pady=(10, 5))
        container.grid_columnconfigure(0, weight=1)

        # Help button (centered)
        help_frame = ctk.CTkFrame(container, fg_color="transparent")
        help_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 5))
        help_frame.grid_columnconfigure(0, weight=1)  # Center the button
        
        help_button = ctk.CTkButton(
            help_frame,
            text="Usage Instructions",
            command=self.show_help,
            width=150,
            height=30,
            corner_radius=6,
            font=ctk.CTkFont(family=FONT_FAMILY, size=16, underline=True, weight="bold"),
            fg_color="transparent",
            hover_color="#e9ecef",
            text_color=COLOR_PALETTE["primary"],
        )
        help_button.grid(row=0, column=0)  # Centered in the frame

        # Design Configuration card
        card = self.create_card("Design Configuration", "⚙️")
        card.grid(row=1, column=0, sticky="ew", padx=DIMENSIONS["card_padding"], pady=(10, 5))

        # Rest of the original config section code...
        self.design_brief_var = ctk.StringVar(value=self.settings["design_brief"])
        self.create_label_combo(
            card, "Design Brief Type:", ["New", "Existing"],
            self.design_brief_var, self.on_brief_type_change, 1
        )

        self.brief_number_var = ctk.StringVar(value=self.settings["brief_number"])
        self.brief_num_label, self.brief_num_entry = self.create_label_entry(
            card, "Brief Number:", self.brief_number_var, 2
        )

        self.design_code_var = ctk.StringVar(value=self.settings["design_code"])
        self.code_label, self.code_combo = self.create_label_combo(
            card, "Design Code:", list(DESIGN_CODES.keys()),
            self.design_code_var, None, 3
        )

    def create_member_section(self):
        """Create member selection section with selection instructions"""
        card = self.create_card("Member Selection", "📋")
        card.grid(row=2, column=0, sticky="ew", padx=DIMENSIONS["card_padding"], pady=(10, 5))

        # Member Selection Method
        self.member_selection_var = ctk.StringVar(value=self.settings["member_selection"])
        self.create_label_combo(
            card, "Selection Method:", 
            ["All Member", "All Member with Material"],  # Removed "Selected Member" option
            self.member_selection_var, self.on_member_selection_change, 1
        )

        # Material Name (for "All Member with Material")
        self.material_var = ctk.StringVar(value=self.settings["material"])
        self.material_label, self.material_entry = self.create_label_entry(
            card, "Material Name:", self.material_var, 2
        )
        
        self.on_member_selection_change()

    def create_action_buttons(self):
        """Create action buttons section"""
        frame = ctk.CTkFrame(
            self.content_frame,
            fg_color="transparent"
        )
        frame.grid(row=3, column=0, sticky="ew", padx=DIMENSIONS["card_padding"], pady=10)
        frame.grid_columnconfigure(0, weight=1)

        # Primary action button
        self.assign_btn = ctk.CTkButton(
            frame,
            text="🚀 Assign DJ Parameters",
            command=self.start_assignment_process,
            height=DIMENSIONS["button_height"],
            corner_radius=8,
            font=FONT_CONFIG["button"],
            fg_color=self.get_color("primary"),
            hover_color=self.get_color("primary_dark")
        )
        self.assign_btn.pack(fill="x", pady=5)

    def create_status_section(self):
        """Create status/log section"""
        card = self.create_card("Status Log", "📊")
        card.grid(row=4, column=0, sticky="nsew", padx=DIMENSIONS["card_padding"], pady=(5, 20))
        card.grid_rowconfigure(0, weight=1)  # Allow the console frame to expand
        card.grid_columnconfigure(0, weight=1)

        # Console-like status display
        self.console_frame = ctk.CTkFrame(
            card,
            height=150,
            corner_radius=6,
            fg_color="#f0f0f0" if ctk.get_appearance_mode() == "Light" else "#252525"
        )
        self.console_frame.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        self.console_frame.grid_columnconfigure(0, weight=1)

        self.console_text = ctk.CTkTextbox(
            self.console_frame,
            wrap="word",
            font=FONT_CONFIG["console"],
            fg_color="#f0f0f0" if ctk.get_appearance_mode() == "Light" else "#252525",
            text_color="#333333" if ctk.get_appearance_mode() == "Light" else "#cccccc"
        )
        self.console_text.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)
        self.console_text.configure(state="disabled")

        # Progress bar
        self.progress_bar = ctk.CTkProgressBar(
            card,
            height=8,
            corner_radius=4,
            progress_color=self.get_color("primary")
        )
        self.progress_bar.grid(row=1, column=0, sticky="ew", padx=5, pady=(0, 10))

        # Status label
        self.status_label = ctk.CTkLabel(
            card,
            text="Ready to connect to STAAD Pro...",
            font=FONT_CONFIG["status"],
            anchor="w",
            justify="left"
        )
        self.status_label.grid(row=2, column=0, sticky="ew", padx=5, pady=(0, 5))

    def create_card(self, title, icon=None):
        """Create a standardized card container"""
        card = ctk.CTkFrame(
            self.content_frame,
            corner_radius=10,
            border_width=1,
            border_color=self.get_color("border"),
            fg_color=self.get_color("surface")
        )
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(0, weight=0)  # Title row doesn't expand
        card.grid_rowconfigure(1, weight=1)  # Content row expands

        # Card title
        title_frame = ctk.CTkFrame(card, fg_color="transparent")
        title_frame.grid(row=0, column=0, sticky="ew", padx=15, pady=(12, 5))

        if icon:
            ctk.CTkLabel(
                title_frame,
                text=icon,
                font=ctk.CTkFont(size=18),
                anchor="w"
            ).grid(row=0, column=0, sticky="w", padx=(0, 10))

        ctk.CTkLabel(
            title_frame,
            text=title,
            font=FONT_CONFIG["card_title"],
            anchor="w"
        ).grid(row=0, column=1, sticky="ew", padx=0, pady=0)

        return card

    def create_label_combo(self, parent, label_text, values, variable, command, row):
        """Create a label + combobox pair"""
        label = ctk.CTkLabel(
            parent,
            text=label_text,
            font=FONT_CONFIG["label"],
            anchor="w"
        )
        label.grid(row=row, column=0, sticky="w", padx=20, pady=5)

        combo = ctk.CTkComboBox(
            parent,
            values=values,
            variable=variable,
            command=command,
            width=DIMENSIONS["input_width"],
            height=36,
            corner_radius=8,
            dropdown_fg_color=self.get_color("surface"),
            button_color=self.get_color("primary"),
            button_hover_color=self.get_color("primary_dark"),
            font=FONT_CONFIG["label"]
        )
        combo.grid(row=row, column=1, sticky="w", padx=20, pady=5)

        return label, combo

    def create_label_entry(self, parent, label_text, variable, row):
        """Create a label + entry pair"""
        label = ctk.CTkLabel(
            parent,
            text=label_text,
            font=FONT_CONFIG["label"],
            anchor="w"
        )
        label.grid(row=row, column=0, sticky="w", padx=20, pady=5)

        entry = ctk.CTkEntry(
            parent,
            textvariable=variable,
            width=DIMENSIONS["input_width"],
            height=36,
            corner_radius=8,
            font=FONT_CONFIG["label"]
        )
        entry.grid(row=row, column=1, sticky="w", padx=20, pady=5)

        return label, entry

    def get_color(self, color_name):
        """Get the appropriate color based on current theme"""
        mode = ctk.get_appearance_mode().lower()
        if mode == "dark" and color_name in COLOR_PALETTE["dark"]:
            return COLOR_PALETTE["dark"][color_name]
        return COLOR_PALETTE.get(color_name, "#ffffff")

    # ==================== UI EVENT HANDLERS ====================
    def on_brief_type_change(self, event=None):
        """Handle design brief type selection change"""
        if self.design_brief_var.get() == "New":
            self.brief_num_label.grid_remove()
            self.brief_num_entry.grid_remove()
            self.code_label.grid()
            self.code_combo.grid()
        else:
            self.code_label.grid_remove()
            self.code_combo.grid_remove()
            self.brief_num_label.grid()
            self.brief_num_entry.grid()

    def on_member_selection_change(self, event=None):
        """Handle member selection method change"""
        selection_method = self.member_selection_var.get()
        
        if selection_method == "All Member with Material":
            self.material_label.grid()
            self.material_entry.grid()
        else:  # "All Member"
            self.material_label.grid_remove()
            self.material_entry.grid_remove()

    # ==================== LOGGING FUNCTIONS ====================
    def log_message(self, message, status=None):
        """Add a message to the console log"""
        if threading.get_ident() != self._ui_thread_id:
            self.after(0, self.log_message, message, status)
            return

        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted_msg = f"[{timestamp}] {message}\n"
        
        self.console_text.configure(state="normal")
        self.console_text.insert("end", formatted_msg)
        self.console_text.configure(state="disabled")
        self.console_text.see("end")
        
        self.log_history.append(formatted_msg)
        
        if status:
            self.status_label.configure(text=message)
        
        self.update()

    def log_error(self, message):
        """Log an error message"""
        self.log_message(f"ERROR: {message}", status=True)
        self._set_status_color("error")

    def log_success(self, message):
        """Log a success message"""
        self.log_message(f"SUCCESS: {message}", status=True)
        self._set_status_color("success")

    def log_warning(self, message):
        """Log a warning message"""
        self.log_message(f"WARNING: {message}", status=True)
        self._set_status_color("warning")

    def _set_status_color(self, color_name):
        if threading.get_ident() != self._ui_thread_id:
            self.after(0, self._set_status_color, color_name)
            return
        self.status_label.configure(text_color=self.get_color(color_name))

    def update_progress(self, value):
        """Update the progress bar"""
        if threading.get_ident() != self._ui_thread_id:
            self.after(0, self.update_progress, value)
            return
        self.progress_bar.set(value)
        self.update()

    # ==================== STAAD PRO FUNCTIONS ====================
    def start_assignment_process(self):
        """Start the DJ parameter assignment process in a separate thread"""
        if self.running:
            return
            
        self.running = True
        self.assign_btn.configure(state="disabled")
        self.status_label.configure(text_color=self.get_color("text_primary"))
        
        # Save current settings
        self.settings.update({
            "design_brief": self.design_brief_var.get(),
            "brief_number": self.brief_number_var.get(),
            "design_code": self.design_code_var.get(),
            "member_selection": self.member_selection_var.get(),
            "material": self.material_var.get()
        })
        self.save_settings()
        
        config = {
            "brief_option": self.design_brief_var.get(),
            "existing_brief_number": (
                int(self.brief_number_var.get())
                if self.brief_number_var.get().isdigit()
                else 1
            ),
            "design_code": self.design_code_var.get(),
            "member_selection": self.member_selection_var.get(),
            "material_filter": self.material_var.get(),
        }
        thread = threading.Thread(
            target=self._assignment_worker, args=(config,), daemon=True
        )
        thread.start()

    def _assignment_worker(self, config):
        com_initialized = False
        try:
            pythoncom.CoInitialize()
            com_initialized = True
            self.assign_dj_parameters(config)
        except Exception as error:
            self.log_error(f"Assignment worker failed: {error}")
        finally:
            try:
                if com_initialized:
                    pythoncom.CoUninitialize()
            finally:
                self.running = False
                self.after(0, self._enable_assignment_button)

    def _enable_assignment_button(self):
        self.assign_btn.configure(state="normal")

    def connect_to_staad(self):
        """Connect to STAAD Pro using comtypes with proper error handling"""
        self.log_message("Connecting to STAAD Pro...")
        
        try:
            # Try to get active STAAD instance first
            try:
                staad = comtypes.client.GetActiveObject("StaadPro.OpenSTAAD")
                self.log_message("Connected to existing STAAD Pro instance")
            except:
                # If no active instance, try to create a new one
                try:
                    staad = comtypes.client.CreateObject("StaadPro.OpenSTAAD")
                    self.log_message("Created new STAAD Pro connection")
                except Exception as e:
                    raise Exception(f"Failed to create STAAD connection: {str(e)}")
            
            # Verify connection by checking for open model
            file_name = ctypes.c_char_p(None)
            file_path = ctypes.c_char_p(None)
            file_name_vt = make_variant_vt_ref(file_name, automation.VT_BSTR)
            file_path_vt = make_variant_vt_ref(file_path, automation.VT_BSTR)
            staad._FlagAsMethod("GetSTAADFile")
            
            staad.GetSTAADFile(file_name_vt, file_path_vt)
            
            if not file_name.value:
                raise Exception("No STAAD model is currently open")
            
            # FIX 1: Decode the model name properly
            model_name = file_name.value.decode('utf-8') if isinstance(file_name.value, bytes) else file_name.value
            self.log_message(f"Connected to STAAD model: {model_name}")
            return staad
            
        except Exception as e:
            error_msg = (
                f"Failed to connect to STAAD Pro: {str(e)}\n\n"
                "Ensure STAAD.Pro CONNECT Edition is running and model is open\n"
            )
            self.log_error(error_msg)
            return None

    def assign_dj_parameters(self, config):
        """Main function to assign DJ parameters using COM automation"""
        try:
            self.log_message("Starting DJ parameter assignment...")
            self.update_progress(0.1)
            
            # Connect to STAAD Pro
            staad = self.connect_to_staad()
            if not staad:
                return
                
            try:
                # Get design code number
                code = DESIGN_CODES.get(config["design_code"], 1032)
                self.update_progress(0.3)
                
                # Flag all required methods
                geometry = staad.Geometry
                prop = staad.Property
                design = staad.Design
                
                # Flag geometry methods
                geometry._FlagAsMethod("GetPhysicalMemberCount")
                geometry._FlagAsMethod("GetPhysicalMemberList")
                geometry._FlagAsMethod("GetAnalyticalMemberCountForPhysicalMember")
                geometry._FlagAsMethod("GetAnalyticalMembersForPhysicalMember")
                geometry._FlagAsMethod("GetMemberIncidence")
                
                # Flag property methods
                prop._FlagAsMethod("GetBeamMaterialName")
                
                # Flag design methods
                design._FlagAsMethod("CreateDesignBrief")
                design._FlagAsMethod("GetDesignBriefCode")
                design._FlagAsMethod("AssignDesignParameter")
                
                # Get physical member count
                pcnt = geometry.GetPhysicalMemberCount()
                
                if pcnt == 0:
                    self.log_error("No physical members found in the model")
                    return
                    
                self.log_message(f"Found {pcnt} physical members")
                self.update_progress(0.4)
                
                # Get physical member list
                safe_array_pmem = make_safe_array_long(pcnt)
                pmem = make_variant_vt_ref(safe_array_pmem, automation.VT_ARRAY | automation.VT_I4)
                geometry.GetPhysicalMemberList(pmem)
                
                # Initialize counters
                processed_count = 0
                brf = 0  # Brief number
                
                self.log_message("Starting member processing...")
                self.update_progress(0.5)
                
                # FIX 2: Check existing brief and display its code
                if config["brief_option"] == "Existing":
                    try:
                        brf = config["existing_brief_number"]
                        codx = design.GetDesignBriefCode(brf)
                        if codx == 0:
                            self.log_error(f"Design Parameter {brf} not available in model")
                            return
                        
                        # Find the design code name from the number
                        existing_code_name = "Unknown"
                        for name, code_num in DESIGN_CODES.items():
                            if code_num == codx:
                                existing_code_name = name
                                break
                        
                        self.log_message(f"Using existing design brief: {brf} (Code: {existing_code_name} - {codx})")
                    except Exception as e:
                        self.log_error(f"Error checking existing brief: {str(e)}")
                        return
                else:
                    # For new brief, use the selected code
                    self.log_message(f"Using design code: {config['design_code']} (Code: {code})")
                
                # Process each physical member
                for j in range(pcnt):
                    current_pmem = pmem[0][j]
                    
                    # Get analytical member count for this physical member
                    anln = geometry.GetAnalyticalMemberCountForPhysicalMember(current_pmem)
                    
                    # Skip if no analytical members
                    if anln == 0:
                        continue
                    
                    # Get analytical members for this physical member
                    safe_array_selb = make_safe_array_long(anln)
                    selb = make_variant_vt_ref(safe_array_selb, automation.VT_ARRAY | automation.VT_I4)
                    
                    anl = ctypes.c_long(0)
                    anl_vt = make_variant_vt_ref(anl, automation.VT_I4)
                    
                    geometry.GetAnalyticalMembersForPhysicalMember(current_pmem, anl_vt, selb)
                    
                    # Check material if filtering is required
                    if config["member_selection"] == "All Member with Material":
                        if anln > 0:
                            try:
                                mat1 = prop.GetBeamMaterialName(selb[0][0])
                                if mat1 != config["material_filter"]:
                                    continue
                            except:
                                continue
                    
                    processed_count += 1
                    
                    # Get start and end nodes
                    node_a = ctypes.c_long(0)
                    node_b = ctypes.c_long(0)
                    node_a_vt = make_variant_vt_ref(node_a, automation.VT_I4)
                    node_b_vt = make_variant_vt_ref(node_b, automation.VT_I4)
                    
                    geometry.GetMemberIncidence(selb[0][0], node_a_vt, node_b_vt)
                    dj1_value = float(node_a.value)
                    
                    geometry.GetMemberIncidence(selb[0][anln-1], node_a_vt, node_b_vt)
                    dj2_value = float(node_b.value)
                    
                    # Create new design brief only for "New" option
                    if config["brief_option"] == "New":
                        if brf == 0:
                            brf = design.CreateDesignBrief(code)    
                            self.log_message(f"Created new design brief: {brf}")
                    
                    # Assign DJ parameters
                    design.AssignDesignParameter(brf, "DJ1", dj1_value, selb)
                    design.AssignDesignParameter(brf, "DJ2", dj2_value, selb)
                    
                    # Update progress
                    progress = 0.5 + (0.5 * (j + 1) / pcnt)
                    self.update_progress(progress)
                    
                    if (j + 1) % 10 == 0 or (j + 1) == pcnt:
                        self.log_message(f"Processed member {j + 1}/{pcnt}")
                
                # Final status
                if config["member_selection"] == "All Member with Material":
                    if processed_count == 0:
                        self.log_error(f"No members with material '{config['material_filter']}'")
                    else:
                        self.log_success(f"Assigned to {processed_count} members with material '{config['material_filter']}'")
                else:
                    self.log_success(f"Assigned to {processed_count} members")
                
                self.update_progress(1.0)
                
            except Exception as e:
                self.log_error(f"COM Error: {str(e)}")
                import traceback
                self.log_message(traceback.format_exc())
            finally:
                # Simple and silent cleanup
                if 'staad' in locals():
                    staad = None  # Let Python handle the cleanup
                    
                    
        except Exception as e:
            self.log_error(f"Process Error: {str(e)}")

# ==================== MAIN EXECUTION ====================
if __name__ == "__main__":
    try:
        root_for_testing = ctk.CTk()
        root_for_testing.withdraw()
        app = StaadDJTool(root_for_testing)
        root_for_testing.mainloop()
    except Exception as e:
        messagebox.showerror("Fatal Error", f"Application failed to start:\n{str(e)}")