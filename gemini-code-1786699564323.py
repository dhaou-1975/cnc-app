import os
import re
import fnmatch
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# ==========================================
# METADONNÉES DE L'APPLICATION
# ==========================================
APP_NAME = "CNC Manager"
APP_VERSION = "v1.0.0"
APP_AUTHOR = "Bouzaien Dhaou"
APP_DATE = "Août 2026"


class CNCAnalyzerApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"{APP_NAME} {APP_VERSION}")
        self.root.geometry("1050x650")
        self.root.minsize(800, 500)

        # Structure de données globale
        self.all_data = []

        # Construction de l'interface graphique
        self._create_header()
        self._create_toolbar()
        self._create_treeview()
        self._create_statusbar()

    def _create_header(self):
        header_frame = ttk.Frame(self.root, padding=10)
        header_frame.pack(fill=tk.X)

        title_lbl = ttk.Label(
            header_frame,
            text=APP_NAME,
            font=("Arial", 16, "bold")
        )
        title_lbl.pack(side=tk.LEFT)

        meta_text = f"Version: {APP_VERSION}  |  Auteur: {APP_AUTHOR}  |  Date: {APP_DATE}"
        meta_lbl = ttk.Label(
            header_frame,
            text=meta_text,
            font=("Arial", 9, "italic"),
            foreground="gray"
        )
        meta_lbl.pack(side=tk.RIGHT)

        ttk.Separator(self.root, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=10, pady=(5, 0))

    def _create_toolbar(self):
        toolbar = ttk.Frame(self.root, padding=10)
        toolbar.pack(fill=tk.X)

        btn_browse = ttk.Button(
            toolbar,
            text="📁 Choisir un dossier...",
            command=self.browse_folder
        )
        btn_browse.pack(side=tk.LEFT, padx=(0, 15))

        ttk.Label(toolbar, text="Rechercher :").pack(side=tk.LEFT, padx=(0, 5))
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *args: self.filter_data())
        
        search_entry = ttk.Entry(toolbar, textvariable=self.search_var, width=35)
        search_entry.pack(side=tk.LEFT, padx=(0, 10))

        self.lbl_folder = ttk.Label(
            toolbar,
            text="Aucun dossier sélectionné",
            font=("Arial", 9, "italic"),
            foreground="gray"
        )
        self.lbl_folder.pack(side=tk.LEFT, padx=(10, 0))

    def _create_treeview(self):
        table_frame = ttk.Frame(self.root, padding=10)
        table_frame.pack(fill=tk.BOTH, expand=True)

        columns = ("index", "model", "program", "tools", "time_100", "time_70")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")

        self.tree.heading("index", text="N°", command=lambda: self.sort_column("index", False))
        self.tree.heading("model", text="Nom du Modèle", command=lambda: self.sort_column("model", False))
        self.tree.heading("program", text="N° Programme", command=lambda: self.sort_column("program", False))
        self.tree.heading("tools", text="Outils (T...)", command=lambda: self.sort_column("tools", False))
        self.tree.heading("time_100", text="Temps (100%)", command=lambda: self.sort_column("time_100", False))
        self.tree.heading("time_70", text="Temps NUM 1060 (70%)", command=lambda: self.sort_column("time_70", False))

        self.tree.column("index", width=60, anchor=tk.CENTER)
        self.tree.column("model", width=260, anchor=tk.W)
        self.tree.column("program", width=120, anchor=tk.CENTER)
        self.tree.column("tools", width=200, anchor=tk.W)
        self.tree.column("time_100", width=130, anchor=tk.CENTER)
        self.tree.column("time_70", width=160, anchor=tk.CENTER)

        vsb = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        hsb = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        table_frame.grid_rowconfigure(0, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)

    def _create_statusbar(self):
        self.statusbar = ttk.Label(
            self.root,
            text=" Prêt.",
            relief=tk.SUNKEN,
            anchor=tk.W
        )
        self.statusbar.pack(side=tk.BOTTOM, fill=tk.X)

    def parse_cnc_file(self, filepath, filename):
        model_name = ""
        prog_name = ""
        tools = []
        total_time_seconds = 0.0

        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

            lines = content.splitlines()
            header_lines = lines[:25]
            full_header_text = "\n".join(header_lines)

            # --- 1. EXTRACTION N° PROGRAMME ---
            prog_match = re.search(r'\$PAIN\s+([A-Za-z0-9_\-]+)', full_header_text, re.IGNORECASE)
            if not prog_match:
                prog_match = re.search(r'%([A-Za-z0-9_\-]+)', full_header_text)
            if not prog_match:
                prog_match = re.search(r'\b(O\d{4,5})\b', full_header_text, re.IGNORECASE)

            if prog_match:
                prog_name = prog_match.group(1)
            else:
                prog_name = os.path.splitext(filename)[0]

            # --- 2. EXTRACTION NOM DU MODÈLE ---
            model_match = re.search(r'([A-Za-z0-9_\-\']+(?:PAD|BOARD|MOULE|SURF|SKIL|PADDEL)[A-Za-z0-9_\-\']*)', full_header_text, re.IGNORECASE)
            if model_match:
                model_name = model_match.group(1)
            else:
                for line in header_lines:
                    clean_line = line.strip().lstrip('(%#$* ;')
                    if clean_line and not clean_line.startswith('G') and not clean_line.startswith('M') and len(clean_line) > 2:
                        model_name = clean_line[:35].strip()
                        break
            if not model_name:
                model_name = os.path.splitext(filename)[0]

            # --- 3. BALAYAGE COMPLET DU FICHIER POUR LES OUTILS (T1+T5+T8...) ---
            # Recherche de toutes les occurrences T1, T01, T5, etc. dans tout le fichier
            raw_tools = re.findall(r'\bT(\d+)\b', content, re.IGNORECASE)
            if raw_tools:
                # Conversion en entiers pour éliminer les doublons et trier numériquement (T1, T2, T5, T10)
                unique_tool_nums = sorted(list(set(int(t) for t in raw_tools)))
                tools = [f"T{num}" for num in unique_tool_nums]

            # --- 4. CALCUL DU TEMPS ---
            time_match = re.search(r'TIME\s*=\s*(\d+)', full_header_text, re.IGNORECASE)
            if time_match:
                total_time_seconds = float(time_match.group(1))
            else:
                total_time_seconds = len(lines) * 0.8

        except Exception as e:
            model_name = os.path.splitext(filename)[0]
            prog_name = "N/A"

        # Assemblage sous la forme T1+T5+T8
        tools_str = "+".join(tools) if tools else "N/A"
        return model_name, prog_name, tools_str, total_time_seconds

    @staticmethod
    def format_time(seconds):
        m, s = divmod(int(seconds), 60)
        h, m = divmod(m, 60)
        if h > 0:
            return f"{h}h {m:02d}m {s:02d}s"
        return f"{m:02d}m {s:02d}s"

    def browse_folder(self):
        folder = filedialog.askdirectory(title="Sélectionner le dossier des fichiers d'usinage")
        if not folder:
            return

        self.lbl_folder.config(text=folder, foreground="black")
        
        self.all_data.clear()
        for row in self.tree.get_children():
            self.tree.delete(row)

        idx = 1
        for root_dir, _, files in os.walk(folder):
            for file in files:
                filepath = os.path.join(root_dir, file)
                model, prog, tools, sec_100 = self.parse_cnc_file(filepath, file)
                sec_70 = sec_100 / 0.70 if sec_100 > 0 else 0

                item = {
                    "raw_index": idx,
                    "model": model,
                    "program": prog,
                    "tools": tools,
                    "sec_100": sec_100,
                    "sec_70": sec_70,
                    "time_100_str": self.format_time(sec_100),
                    "time_70_str": self.format_time(sec_70),
                    "filename": file
                }
                self.all_data.append(item)
                idx += 1

        self.filter_data()
        self.statusbar.config(text=f" {len(self.all_data)} fichier(s) chargé(s) depuis : {folder}")

    def filter_data(self):
        query = self.search_var.get().strip()

        for row in self.tree.get_children():
            self.tree.delete(row)

        display_idx = 1
        for item in self.all_data:
            if query:
                pattern = query.lower()
                if not pattern.startswith("*") and not pattern.endswith("*"):
                    pattern = f"*{pattern}*"

                match_model = fnmatch.fnmatch(item["model"].lower(), pattern)
                match_prog = fnmatch.fnmatch(item["program"].lower(), pattern)
                match_file = fnmatch.fnmatch(item["filename"].lower(), pattern)
                match_tools = fnmatch.fnmatch(item["tools"].lower(), pattern)

                if not (match_model or match_prog or match_file or match_tools):
                    continue

            self.tree.insert(
                "",
                tk.END,
                values=(
                    display_idx,
                    item["model"],
                    item["program"],
                    item["tools"],
                    item["time_100_str"],
                    item["time_70_str"]
                )
            )
            display_idx += 1

    def sort_column(self, col, reverse):
        l = [(self.tree.set(k, col), k) for k in self.tree.get_children('')]
        
        def parse_val(v):
            nums = re.findall(r'\d+', str(v))
            return int(nums[0]) if nums else 0

        if col in ("index", "time_100", "time_70"):
            l.sort(key=lambda t: parse_val(t[0]), reverse=reverse)
        else:
            l.sort(key=lambda t: str(t[0]).lower(), reverse=reverse)

        for index, (val, k) in enumerate(l):
            self.tree.move(k, '', index)

        self.tree.heading(col, command=lambda: self.sort_column(col, not reverse))


if __name__ == "__main__":
    root = tk.Tk()
    app = CNCAnalyzerApp(root)
    root.mainloop()
