import os
from pathlib import Path
import sys
import json
import threading
from datetime import datetime
import io
import customtkinter as ctk
from tkinter import ttk, messagebox
from PIL import Image
import fitz  # PyMuPDF

CACHE_FILENAME = "pdf_metadata_cache.json"


class EILDrawingManger(ctk.CTkToplevel):
    def __init__(self, master=None):
        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")

        super().__init__(master)
        self.withdraw()
        self.title("Drawing Manager - EIL Standards")
        self.geometry("1000x800")

        self.setup_paths()

        self.current_pdfs = []
        self.filtered_pdfs = []
        self.selected_pdf = None
        self._metadata_cache = {}        # in-memory cache
        self._preview_cache = {}         # in-memory preview image cache
        self._loading = False

        self._load_cache_from_disk()
        self.create_gui()

        # Show window first, then load PDFs in background
        self.deiconify()
        self.after(50, self._start_background_load)

    # ------------------------------------------------------------------ #
    #  Path & cache setup
    # ------------------------------------------------------------------ #

    def setup_paths(self):
        if getattr(sys, 'frozen', False):
            # --onedir: data folder sits next to the .exe, not inside _MEIPASS
            self.base_path = os.path.dirname(sys.executable)
        else:
            self.base_path = str(Path(__file__).resolve().parents[2])

        self.data_path = os.path.join(self.base_path, "data")
        self.eil_path = os.path.join(self.data_path, "EIL STD")
        self.cache_path = os.path.join(self.data_path, CACHE_FILENAME)

        if not getattr(sys, 'frozen', False):
            os.makedirs(self.eil_path, exist_ok=True)

    def _load_cache_from_disk(self):
        """Load previously saved metadata cache (page counts, sizes, etc.)."""
        try:
            if os.path.exists(self.cache_path):
                with open(self.cache_path, "r", encoding="utf-8") as f:
                    self._metadata_cache = json.load(f)
        except Exception:
            self._metadata_cache = {}

    def _save_cache_to_disk(self):
        """Persist metadata cache so the next launch is instant."""
        try:
            os.makedirs(self.data_path, exist_ok=True)
            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump(self._metadata_cache, f)
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    #  GUI
    # ------------------------------------------------------------------ #

    def create_gui(self):
        main_frame = ctk.CTkFrame(self)
        main_frame.pack(fill=ctk.BOTH, expand=True, padx=10, pady=10)

        # Toolbar
        toolbar = ctk.CTkFrame(main_frame)
        toolbar.pack(fill=ctk.X, pady=(0, 10))

        ctk.CTkButton(toolbar, text="Refresh", command=self._start_background_load).pack(
            side=ctk.LEFT, padx=(10, 5), pady=10
        )

        self.status_label = ctk.CTkLabel(toolbar, text="", text_color="#888888")
        self.status_label.pack(side=ctk.LEFT, padx=10)

        search_frame = ctk.CTkFrame(toolbar)
        search_frame.pack(side=ctk.RIGHT, padx=10, pady=10)

        ctk.CTkLabel(search_frame, text="Search:").pack(side=ctk.LEFT, padx=(10, 5))
        self.search_var = ctk.StringVar()
        self.search_var.trace('w', self.filter_pdfs)
        ctk.CTkEntry(search_frame, textvariable=self.search_var, width=200).pack(
            side=ctk.LEFT, padx=(0, 10)
        )

        # Content
        content_frame = ctk.CTkFrame(main_frame)
        content_frame.pack(fill=ctk.BOTH, expand=True)

        # Left panel
        left_panel = ctk.CTkFrame(content_frame)
        left_panel.pack(side=ctk.LEFT, fill=ctk.BOTH, expand=True, padx=(0, 10))

        list_frame = ctk.CTkFrame(left_panel)
        list_frame.pack(fill=ctk.BOTH, expand=True, padx=10, pady=10)
        list_frame.grid_columnconfigure(0, weight=1)
        list_frame.grid_rowconfigure(0, weight=1)

        style = ttk.Style()
        style.theme_use("default")
        style.configure("Treeview",
                        background="#ffffff", foreground="#1a1a1a",
                        rowheight=25, fieldbackground="#f8f9fa",
                        bordercolor="#dee2e6", borderwidth=1)
        style.map('Treeview',
                  background=[('selected', '#007fff'), ('focus', '#e3f2fd')],
                  foreground=[('selected', '#ffffff')])
        style.configure("Treeview.Heading",
                        background="#f1f3f4", foreground="#1a1a1a",
                        relief="flat", font=('Segoe UI', 9, 'bold'))
        style.map("Treeview.Heading",
                  background=[('active', '#e8f0fe')],
                  foreground=[('active', '#1a1a1a')])

        self.pdf_tree = ttk.Treeview(
            list_frame,
            columns=('filename', 'size', 'pages'),
            show='headings',
            height=20
        )
        self.pdf_tree.heading('filename', text='Filename', anchor='w')
        self.pdf_tree.heading('size', text='Size (MB)', anchor='center')
        self.pdf_tree.heading('pages', text='Pages', anchor='center')
        self.pdf_tree.column('filename', width=400, anchor='w', stretch=True)
        self.pdf_tree.column('size', width=100, anchor='center')
        self.pdf_tree.column('pages', width=80, anchor='center')

        tree_scroll = ctk.CTkScrollbar(list_frame, command=self.pdf_tree.yview)
        self.pdf_tree.configure(yscrollcommand=tree_scroll.set)

        self.pdf_tree.grid(row=0, column=0, sticky='nsew')
        tree_scroll.grid(row=0, column=1, sticky='ns')

        self.pdf_tree.bind('<<TreeviewSelect>>', self.on_pdf_select)
        self.pdf_tree.bind('<Double-1>', self.open_pdf)

        # Right panel
        right_panel = ctk.CTkFrame(content_frame, width=400)
        right_panel.pack(side=ctk.RIGHT, fill=ctk.Y)
        right_panel.pack_propagate(False)

        preview_frame = ctk.CTkFrame(right_panel)
        preview_frame.pack(fill=ctk.X, padx=10, pady=10)

        ctk.CTkLabel(preview_frame, text="PDF Preview",
                     font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(10, 5))

        preview_container = ctk.CTkFrame(preview_frame, fg_color="#f8f9fa")
        preview_container.pack(padx=10, pady=10, fill=ctk.BOTH, expand=True)

        self.preview_label = ctk.CTkLabel(
            preview_container, text="Select a PDF to preview",
            height=300, text_color="#6c757d"
        )
        self.preview_label.pack(padx=10, pady=10, fill=ctk.BOTH, expand=True)

        details_frame = ctk.CTkFrame(right_panel)
        details_frame.pack(fill=ctk.BOTH, expand=True, padx=10, pady=10)

        ctk.CTkLabel(details_frame, text="PDF Details",
                     font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(10, 5))

        self.details_text = ctk.CTkTextbox(
            details_frame, height=100, fg_color="#f8f9fa",
            text_color="#1a1a1a", font=ctk.CTkFont(family="Consolas", size=12)
        )
        self.details_text.pack(fill=ctk.BOTH, expand=True, padx=10, pady=10)

        stats_frame = ctk.CTkFrame(right_panel, fg_color="#e3f2fd")
        stats_frame.pack(fill=ctk.X, padx=10, pady=(0, 10))

        self.stats_label = ctk.CTkLabel(
            stats_frame, text="Total PDFs: 0",
            font=ctk.CTkFont(size=14, weight="bold"), text_color="#1565c0"
        )
        self.stats_label.pack(padx=10, pady=10)

    # ------------------------------------------------------------------ #
    #  Background loading
    # ------------------------------------------------------------------ #

    def _start_background_load(self):
        """Kick off PDF scanning in a worker thread so the UI stays responsive."""
        if self._loading:
            return
        self._loading = True
        self.status_label.configure(text="Loading…")
        t = threading.Thread(target=self._load_pdfs_thread, daemon=True)
        t.start()

    def _load_pdfs_thread(self):
        """Worker: scan folder, use cache where possible, open PDF only if needed."""
        results = []
        cache_dirty = False

        if os.path.exists(self.eil_path):
            for filename in sorted(os.listdir(self.eil_path)):
                if not filename.lower().endswith('.pdf'):
                    continue
                filepath = os.path.join(self.eil_path, filename)
                info = self._get_pdf_info_cached(filepath)
                if info:
                    results.append(info)
                    if info.get('_cache_miss'):
                        cache_dirty = True

        if cache_dirty:
            self._save_cache_to_disk()

        # Update UI on the main thread
        self.after(0, lambda: self._on_load_complete(results))

    def _get_pdf_info_cached(self, filepath):
        """
        Return PDF metadata.  Opens the file with PyMuPDF ONLY if the file has
        changed since it was last cached (detected via mtime + size).
        """
        try:
            filename = os.path.basename(filepath)
            stat = os.stat(filepath)
            file_size = stat.st_size
            mtime = stat.st_mtime

            cached = self._metadata_cache.get(filepath)
            if (cached
                    and cached.get('mtime') == mtime
                    and cached.get('file_size') == file_size):
                # Cache hit — no need to open the PDF
                return {
                    'filename': filename,
                    'filepath': filepath,
                    'file_size': file_size,
                    'page_count': cached['page_count'],
                    'date_modified': cached['date_modified'],
                }

            # Cache miss — open PDF to get page count
            doc = fitz.open(filepath)
            page_count = len(doc)
            doc.close()

            date_modified = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')

            self._metadata_cache[filepath] = {
                'mtime': mtime,
                'file_size': file_size,
                'page_count': page_count,
                'date_modified': date_modified,
            }

            return {
                'filename': filename,
                'filepath': filepath,
                'file_size': file_size,
                'page_count': page_count,
                'date_modified': date_modified,
                '_cache_miss': True,
            }
        except Exception as e:
            print(f"Error getting PDF info for {filepath}: {e}")
            return None

    def _on_load_complete(self, results):
        """Called on the main thread once background scan finishes."""
        self._loading = False
        self.current_pdfs = results
        self.filtered_pdfs = results.copy()
        self._preview_cache.clear()  # invalidate old previews on refresh

        # Repopulate tree
        for item in self.pdf_tree.get_children():
            self.pdf_tree.delete(item)

        search_term = self.search_var.get().lower()
        for pdf_info in self.current_pdfs:
            if not search_term or search_term in pdf_info['filename'].lower():
                self.pdf_tree.insert(
                    '', 'end',
                    values=(
                        pdf_info['filename'],
                        f"{pdf_info['file_size'] / (1024 * 1024):.2f}",
                        pdf_info['page_count'],
                    )
                )

        self.status_label.configure(text="")
        self.update_stats()

    # ------------------------------------------------------------------ #
    #  Search / filter
    # ------------------------------------------------------------------ #

    def filter_pdfs(self, *args):
        search_term = self.search_var.get().lower()

        for item in self.pdf_tree.get_children():
            self.pdf_tree.delete(item)

        for pdf_info in self.current_pdfs:
            if not search_term or search_term in pdf_info['filename'].lower():
                self.pdf_tree.insert(
                    '', 'end',
                    values=(
                        pdf_info['filename'],
                        f"{pdf_info['file_size'] / (1024 * 1024):.2f}",
                        pdf_info['page_count'],
                    )
                )
        self.update_stats()

    # ------------------------------------------------------------------ #
    #  Selection & preview
    # ------------------------------------------------------------------ #

    def on_pdf_select(self, event):
        selection = self.pdf_tree.selection()
        if not selection:
            return

        filename = self.pdf_tree.item(selection[0])['values'][0]
        self.selected_pdf = next(
            (p for p in self.current_pdfs if p['filename'] == filename), None
        )

        if self.selected_pdf:
            self.load_pdf_details()
            # Generate preview in background to avoid blocking the UI
            threading.Thread(
                target=self._generate_preview_thread,
                args=(self.selected_pdf,),
                daemon=True
            ).start()

    def load_pdf_details(self):
        if not self.selected_pdf:
            return
        details = (
            f"File: {self.selected_pdf['filename']}\n"
            f"Size: {self.selected_pdf['file_size'] / (1024 * 1024):.2f} MB\n"
            f"Pages: {self.selected_pdf['page_count']}"
        )
        self.details_text.delete(1.0, ctk.END)
        self.details_text.insert(1.0, details)

    def _generate_preview_thread(self, pdf_info):
        """Render the first page thumbnail in a worker thread."""
        filepath = pdf_info['filepath']

        # Return cached image immediately if available
        if filepath in self._preview_cache:
            photo = self._preview_cache[filepath]
            self.after(0, lambda: self._set_preview_image(photo))
            return

        try:
            if not os.path.exists(filepath):
                self.after(0, lambda: self.preview_label.configure(
                    image=None, text="File not found", text_color="#dc3545"))
                return

            doc = fitz.open(filepath)
            page = doc.load_page(0)
            mat = fitz.Matrix(0.4, 0.4)
            pix = page.get_pixmap(matrix=mat)
            img_data = pix.tobytes("ppm")
            doc.close()

            pil_image = Image.open(io.BytesIO(img_data))
            pil_image.thumbnail((350, 400), Image.Resampling.LANCZOS)

            from PIL import ImageDraw
            bordered = Image.new(
                'RGB', (pil_image.width + 4, pil_image.height + 4), '#dee2e6'
            )
            bordered.paste(pil_image, (2, 2))

            photo = ctk.CTkImage(
                light_image=bordered, dark_image=bordered,
                size=(bordered.width, bordered.height)
            )

            # Only cache if this PDF is still selected when we finish
            self._preview_cache[filepath] = photo
            self.after(0, lambda: self._set_preview_image(photo))

        except Exception as e:
            msg = f"Preview unavailable\n{e}"
            self.after(0, lambda: self.preview_label.configure(
                image=None, text=msg, text_color="#dc3545"))

    def _set_preview_image(self, photo):
        """Apply a rendered preview thumbnail (must be called on main thread)."""
        # Guard: don't update if user has moved on to a different PDF
        if self.selected_pdf and self._preview_cache.get(
                self.selected_pdf['filepath']) is photo:
            self.preview_label.configure(image=photo, text="")

    # ------------------------------------------------------------------ #
    #  Open PDF
    # ------------------------------------------------------------------ #

    def open_pdf(self, event):
        selection = self.pdf_tree.selection()
        if not selection:
            return

        filename = self.pdf_tree.item(selection[0])['values'][0]
        filepath = next(
            (p['filepath'] for p in self.current_pdfs if p['filename'] == filename), None
        )

        if filepath:
            try:
                if not os.path.exists(filepath):
                    messagebox.showerror("Error", "PDF file not found!")
                    return
                if os.name == 'nt':
                    os.startfile(filepath)
                else:
                    os.system(f'open "{filepath}"')
            except Exception as e:
                messagebox.showerror("Error", f"Cannot open PDF: {e}")

    # ------------------------------------------------------------------ #
    #  Stats
    # ------------------------------------------------------------------ #

    def update_stats(self):
        total = len(self.current_pdfs)
        visible = len(self.pdf_tree.get_children())
        self.stats_label.configure(
            text=f"Total PDFs: {total}\nCurrently showing: {visible}"
        )


if __name__ == "__main__":
    try:
        root_for_testing = ctk.CTk()
        root_for_testing.withdraw()
        app = EILDrawingManger(root_for_testing)
        root_for_testing.mainloop()
    except Exception as e:
        print(f"Application error: {e}")
        print("Make sure you have installed the required packages:")
        print("pip install customtkinter Pillow PyMuPDF")