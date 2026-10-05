import customtkinter as ctk
from tkinter import messagebox
import subprocess
import sys
import os
from pathlib import Path

# ── Lazy-loaded sub-apps (imported only when the user clicks Open) ──────────
_app_modules = {}

def _get_app(name):
    """Import a sub-app module on first use, cache it thereafter."""
    if name not in _app_modules:
        if name == "dxf_extractor":
            from .dxf_extractor_app import DxfExtractorApp
            _app_modules[name] = DxfExtractorApp
        elif name == "autocad_plotter":
            from .autocad_plotter import AutoCADPlotterApp
            _app_modules[name] = AutoCADPlotterApp
        elif name == "piperack_generator":
            from .piperack_generator import PipeRackApp
            _app_modules[name] = PipeRackApp
        elif name == "dj_parameter_assigner":
            from .dj_parameter_assigner import StaadDJTool
            _app_modules[name] = StaadDJTool
        elif name == "drawing_manager":
            from .drawing_manager import EILDrawingManger
            _app_modules[name] = EILDrawingManger
    return _app_modules[name]

# ── Color / font / dimension constants ──────────────────────────────────────
COLOR_PALETTE = {
    "primary":         "#114379",
    "primary_dark":    "#0D3866",
    "secondary":       "#7209b7",
    "accent":          "#f72585",
    "background":      "#f8f9fa",
    "surface":         "#ffffff",
    "surface_variant": "#e9ecef",
    "border":          "#dee2e6",
    "text_primary":    "#212529",
    "text_secondary":  "#495057",
    "text_tertiary":   "#6c757d",
    "success":         "#4cc9f0",
    "warning":         "#f8961e",
    "error":           "#ef233c",
    "card_1":          "#4285f4",
    "card_2":          "#4285f4",
    "card_3":          "#4285f4",
    "card_4":          "#4285f4",
    "card_5":          "#4285f4",
    "card_6":          "#4285f4",
}

FONT_CONFIG = {
    "header_title":    ("Segoe UI Semibold", 28),
    "header_subtitle": ("Segoe UI", 16),
    "card_title":      ("Segoe UI Semibold", 18),
    "card_description":("Segoe UI", 12),
    "button":          ("Segoe UI Semibold", 13),
    "footer":          ("Segoe UI", 12),
    "settings_title":  ("Segoe UI Semibold", 24),
    "settings_text":   ("Segoe UI", 12),
}

DIMENSIONS = {
    "card_width":     300,
    "card_height":    280,
    "button_height":  40,
    "corner_radius":  12,
    "header_height":  160,
    "footer_height":  60,
    "app_min_width":  1000,
    "app_min_height": 800,
}


def get_resource_path(relative_path):
    """
    Assets bundled via --add-data live in _MEIPASS (onedir/_internal).
    The data/ folder is placed manually next to the .exe, so we check
    both locations and return whichever exists.
    """
    if getattr(sys, 'frozen', False):
        # Check next to the .exe first (for manually placed data/ folder)
        exe_dir = os.path.dirname(sys.executable)
        candidate = os.path.join(exe_dir, relative_path)
        if os.path.exists(candidate):
            return candidate
        # Fall back to _MEIPASS (bundled assets like icons/images)
        return os.path.join(sys._MEIPASS, relative_path)

    return str(Path(__file__).resolve().parents[2] / relative_path)


# ── Tool card ─────────────────────────────────────────────────────────────────
class ModernToolCard(ctk.CTkFrame):

    def __init__(self, parent, title, description, icon_path, color, command=None, **kwargs):
        super().__init__(
            parent,
            fg_color=COLOR_PALETTE["surface"],
            corner_radius=DIMENSIONS["corner_radius"],
            border_width=0,
            **kwargs,
        )
        self.command = command
        self.color = color
        self.is_hovered = False

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure((0, 1, 2, 3), weight=1)

        self._create_icon(icon_path)

        self.title_label = ctk.CTkLabel(
            self, text=title,
            font=FONT_CONFIG["card_title"],
            text_color=COLOR_PALETTE["text_primary"],
        )
        self.title_label.grid(row=1, column=0, pady=(0, 8))

        self.desc_label = ctk.CTkLabel(
            self, text=description,
            font=FONT_CONFIG["card_description"],
            text_color=COLOR_PALETTE["text_secondary"],
            wraplength=240, justify="center",
        )
        self.desc_label.grid(row=2, column=0, pady=(0, 20), padx=25)

        self.launch_button = ctk.CTkButton(
            self, text="Open",
            command=self.launch_tool,
            font=FONT_CONFIG["button"],
            fg_color=color,
            hover_color=self._darken_color(color, 20),
            text_color=COLOR_PALETTE["surface"],
            height=DIMENSIONS["button_height"],
            corner_radius=DIMENSIONS["corner_radius"],
        )
        self.launch_button.grid(row=3, column=0, pady=(0, 25), padx=30, sticky="ew")

        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self._bind_hover_to_children()

    def _create_icon(self, icon_path):
        try:
            from PIL import Image

            pil_image = Image.open(icon_path).resize((64, 64), Image.Resampling.LANCZOS)
            self.icon_image = ctk.CTkImage(
                light_image=pil_image, dark_image=pil_image, size=(64, 64)
            )
            icon_label = ctk.CTkLabel(self, image=self.icon_image, text="")
        except Exception as e:
            print(f"Warning: Could not load icon {icon_path}: {e}")
            icon_label = ctk.CTkLabel(
                self, text="🔧",
                font=("Segoe UI Symbol", 36),
                text_color=self.color,
            )
        icon_label.grid(row=0, column=0, pady=(30, 0))

    def _darken_color(self, hex_color, percent):
        rgb = tuple(int(hex_color[i:i+2], 16) for i in (1, 3, 5))
        d = tuple(max(0, int(c * (100 - percent) / 100)) for c in rgb)
        return f"#{d[0]:02x}{d[1]:02x}{d[2]:02x}"

    def _on_enter(self, event):
        if not self.is_hovered:
            self.is_hovered = True
            self.configure(fg_color=COLOR_PALETTE["surface_variant"], border_width=1,
                           border_color=COLOR_PALETTE["border"])

    def _on_leave(self, event):
        if self.is_hovered:
            self.is_hovered = False
            self.configure(fg_color=COLOR_PALETTE["surface"], border_width=0)

    def _bind_hover_to_children(self):
        for child in self.winfo_children():
            child.bind("<Enter>", self._on_enter)
            child.bind("<Leave>", self._on_leave)

    def launch_tool(self):
        if self.command:
            original_color = self.launch_button.cget("fg_color")
            self.launch_button.configure(
                state="disabled", text="Opening…",
                fg_color=COLOR_PALETTE["text_tertiary"],
            )
            self.after(10, self._execute_command, original_color)
        else:
            messagebox.showinfo(
                "Coming Soon",
                f"{self.title_label.cget('text')} will be available soon!",
            )

    def _execute_command(self, original_color):
        try:
            if callable(self.command):
                self.command()
            elif isinstance(self.command, (list, str)):
                subprocess.run(self.command, shell=True, check=True)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to launch: {e}")
        finally:
            self.launch_button.configure(
                state="normal", text="Open", fg_color=original_color
            )


# ── Main window ───────────────────────────────────────────────────────────────
class CivToolsApp(ctk.CTk):

    def __init__(self):
        super().__init__()

        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")

        self.title("CivTools")
        self.geometry(f"{DIMENSIONS['app_min_width']}x{DIMENSIONS['app_min_height']}")
        self.minsize(DIMENSIONS["app_min_width"], DIMENSIONS["app_min_height"])
        self.configure(fg_color=COLOR_PALETTE["background"])
        self.resizable(False, False)

        self._set_icon()

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._create_modern_header()
        self._create_modern_content()
        self._create_modern_footer()

        self.running_instances = {}

    def _set_icon(self):
        try:
            from PIL import Image

            self.iconbitmap(get_resource_path("assets/icons/logo.ico"))
            if os.name == 'nt':
                import ctypes
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                    "Larsen & Toubro.CivTools"
                )
        except Exception:
            print("Icon not found or unsupported")

    # ── Header ────────────────────────────────────────────────────────────────
    def _create_modern_header(self):
        header_frame = ctk.CTkFrame(
            self, height=DIMENSIONS["header_height"],
            corner_radius=0, fg_color=COLOR_PALETTE["surface"], border_width=0,
        )
        header_frame.grid(row=0, column=0, sticky="ew")
        header_frame.grid_columnconfigure(0, weight=1)
        header_frame.grid_rowconfigure(0, weight=1)

        try:
            from PIL import Image

            bg_img = Image.open(get_resource_path("assets/images/background4.png"))
            orig_w, orig_h = bg_img.size
            disp_w = min(orig_w, 1920)
            disp_h = min(orig_h, DIMENSIONS["header_height"])
            bg_image = ctk.CTkImage(bg_img, size=(disp_w, disp_h))
            ctk.CTkLabel(header_frame, image=bg_image, text="",
                         width=disp_w, height=disp_h).place(x=0, y=0)
        except FileNotFoundError:
            print("Background image not found")

    # ── Content / cards ───────────────────────────────────────────────────────
    def _create_modern_content(self):
        main_frame = ctk.CTkFrame(
            self, corner_radius=0,
            fg_color=COLOR_PALETTE["background"], border_width=0,
        )
        main_frame.grid(row=1, column=0, sticky="nsew")
        main_frame.grid_columnconfigure((0, 1, 2, 3, 4, 5), weight=1, uniform="cols")
        main_frame.grid_rowconfigure((0, 1), weight=1, uniform="rows")

        tools = [
            {
                "title": "DXF Quantity Extractor",
                "description": "Extract and consolidate material quantities from DXF files with Excel integration",
                "icon_path": get_resource_path("assets/icons/dxf_extractor.png"),
                "color": COLOR_PALETTE["card_1"],
                "command": self.launch_dxf_extractor,
            },
            {
                "title": "STAAD DJ Parameter Tool",
                "description": "Assign DJ parameters to STAAD models",
                "icon_path": get_resource_path("assets/icons/dj_parameter.png"),
                "color": COLOR_PALETTE["card_4"],
                "command": self.launch_dj_parameter_assigner,
            },
            {
                "title": "STAAD Pipe Rack Modeler",
                "description": "Model a preliminary pipe rack structure in STAAD.Pro",
                "icon_path": get_resource_path("assets/icons/pipe_rack.png"),
                "color": COLOR_PALETTE["card_3"],
                "command": self.launch_piperack_generator,
            },
            {
                "title": "AutoCAD Smart Mapper",
                "description": "Intelligent AutoCAD plotting system with Excel-driven coordinate mapping",
                "icon_path": get_resource_path("assets/icons/autocad_mapper.png"),
                "color": COLOR_PALETTE["card_2"],
                "command": self.launch_autocad_plotter,
            },
            {
                "title": "EIL Standards Library",
                "description": "Manage EIL standard engineering documents",
                "icon_path": get_resource_path("assets/icons/standards_library.png"),
                "color": COLOR_PALETTE["card_5"],
                "command": self.launch_drawing_manager,
            },
        ]

        for i, tool in enumerate(tools):
            if i < 3:
                row, col = 0, i * 2
            else:
                row, col = 1, (i - 3) * 2 + 1

            ModernToolCard(
                main_frame,
                title=tool["title"],
                description=tool["description"],
                icon_path=tool["icon_path"],
                color=tool["color"],
                command=tool["command"],
                width=DIMENSIONS["card_width"],
                height=DIMENSIONS["card_height"],
            ).grid(row=row, column=col, columnspan=2, padx=20, pady=20, sticky="nsew")

    # ── Footer ────────────────────────────────────────────────────────────────
    def _create_modern_footer(self):
        footer_frame = ctk.CTkFrame(
            self, height=DIMENSIONS["footer_height"],
            corner_radius=0, fg_color=COLOR_PALETTE["surface"], border_width=0,
        )
        footer_frame.grid(row=2, column=0, sticky="ew")

        ctk.CTkFrame(footer_frame, height=1, fg_color=COLOR_PALETTE["border"],
                     corner_radius=0).grid(row=0, column=0, columnspan=2, sticky="ew")

        content_frame = ctk.CTkFrame(footer_frame, fg_color="transparent", corner_radius=0)
        content_frame.grid(row=1, column=0, columnspan=2, sticky="ew", padx=40, pady=20)

        ctk.CTkLabel(
            content_frame,
            text="© 2025 L&T Energy Hydrocarbon - CivTools",
            font=FONT_CONFIG["footer"],
            text_color=COLOR_PALETTE["text_secondary"],
        ).grid(row=0, column=0, sticky="w")

        tutorials_frame = ctk.CTkFrame(content_frame, fg_color="transparent", corner_radius=0)
        tutorials_frame.grid(row=0, column=1, sticky="e")

        try:
            from PIL import Image

            video_icon = ctk.CTkImage(
                light_image=Image.open(get_resource_path("assets/icons/video-tutorial.png")),
                dark_image =Image.open(get_resource_path("assets/icons/video-tutorial.png")),
                size=(20, 20),
            )
            btn_kwargs = dict(image=video_icon, text="  Video Tutorials", compound="left")
        except Exception:
            btn_kwargs = dict(text="Video Tutorials")

        ctk.CTkButton(
            tutorials_frame,
            font=FONT_CONFIG["footer"],
            text_color="black",
            fg_color="transparent",
            border_width=0,
            corner_radius=8,
            hover_color="#F2F5F8",
            command=self._open_video_tutorials,
            **btn_kwargs,
        ).grid(row=0, column=0)

        footer_frame.grid_columnconfigure(0, weight=1)
        content_frame.grid_columnconfigure(0, weight=1)
        content_frame.grid_columnconfigure(1, weight=0)

    def _open_video_tutorials(self):
        local_path = os.environ.get("CIVTOOLS_TUTORIALS_PATH")
        if not local_path:
            self._show_error_dialog(
                "Tutorials Not Configured",
                "Set the CIVTOOLS_TUTORIALS_PATH environment variable to your tutorials folder.",
            )
            return
        try:
            os.startfile(local_path)
        except FileNotFoundError:
            self._show_error_dialog("Path Not Found",
                                    "The video tutorials folder was not found.\nPlease check if the path exists.")
        except Exception:
            self._show_error_dialog("Error", "Unable to open video tutorials.\nPlease contact support.")

    def _show_error_dialog(self, title, message):
        dlg = ctk.CTkToplevel(self)
        dlg.title(title)
        dlg.geometry("300x150")
        dlg.resizable(False, False)
        dlg.transient(self)
        dlg.grab_set()
        ctk.CTkLabel(dlg, text=message, font=FONT_CONFIG["settings_text"]).pack(pady=30)
        ctk.CTkButton(dlg, text="OK", command=dlg.destroy, width=80).pack(pady=10)

    # ── Generic sub-app launcher ──────────────────────────────────────────────
    def _launch(self, key, display_name, app_class_name):
        """Generic launcher: prevents duplicate windows, cleans up on close."""
        if key in self.running_instances:
            messagebox.showinfo("Info", f"{display_name} is already running.")
            return
        try:
            AppClass = _get_app(app_class_name)   # lazy import here
            window = AppClass(self)
            self.running_instances[key] = window

            def on_close():
                self.running_instances.pop(key, None)
                window.destroy()

            window.protocol("WM_DELETE_WINDOW", on_close)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to launch {display_name}: {e}")

    def launch_dxf_extractor(self):
        self._launch("dxf_extractor", "DXF Extractor", "dxf_extractor")

    def launch_autocad_plotter(self):
        self._launch("autocad_plotter", "AutoCAD Plotter", "autocad_plotter")

    def launch_piperack_generator(self):
        self._launch("piperack_generator", "Pipe Rack Generator", "piperack_generator")

    def launch_dj_parameter_assigner(self):
        self._launch("dj_parameter_assigner", "STAAD DJ Parameter Tool", "dj_parameter_assigner")

    def launch_drawing_manager(self):
        self._launch("drawing_manager", "EIL Standard Drawing Manager", "drawing_manager")

    def launch_sop_pr_ts(self):
        try:
            if getattr(sys, "frozen", False):
                pdf_path = os.path.join(
                    os.path.dirname(sys.executable), "data", "SOP_PR_TS.pdf"
                )
            else:
                pdf_path = get_resource_path(os.path.join("data", "SOP_PR_TS.pdf"))
            if not os.path.isfile(pdf_path):
                raise FileNotFoundError(f"SOP document not found: {pdf_path}")
            if sys.platform == 'win32':
                os.startfile(pdf_path)
            elif sys.platform == 'darwin':
                subprocess.run(['open', pdf_path])
            else:
                subprocess.run(['xdg-open', pdf_path])
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open SOP document: {e}")


# ── Entry point ───────────────────────────────────────────────────────────────
def main():
    try:
        app = CivToolsApp()
        app.mainloop()
    except Exception as e:
        messagebox.showerror("Error", f"Application failed to start: {e}")


if __name__ == "__main__":
    main()