import os
import re
import math
import fnmatch
import subprocess
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
        self.root.geometry("1100x680")
        self.root.minsize(850, 520)

        self.all_data = []

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
        self.tree.heading("program", text="N° Programme (Fichier)", command=lambda: self.sort_column("program", False))
        self.tree.heading("tools", text="Outils (T...)", command=lambda: self.sort_column("tools", False))
        self.tree.heading("time_100", text="Temps (100%)", command=lambda: self.sort_column("time_100", False))
        self.tree.heading("time_70", text="Temps NUM 1060 (70%)", command=lambda: self.sort_column("time_70", False))

        self.tree.column("index", width=50, anchor=tk.CENTER)
        self.tree.column("model", width=250, anchor=tk.W)
        self.tree.column("program", width=200, anchor=tk.W)
        self.tree.column("tools", width=180, anchor=tk.W)
        self.tree.column("time_100", width=130, anchor=tk.CENTER)
        self.tree.column("time_70", width=160, anchor=tk.CENTER)

        # Style pour la sélection verte
        style = ttk.Style()
        style.theme_use("default")
        style.map("Treeview",
                  background=[('selected', '#2ecc71')],  # Vert clair
                  foreground=[('selected', '#ffffff')])  # Texte blanc

        vsb = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        hsb = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        table_frame.grid_rowconfigure(0, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)

        # Double-clic pour ouvrir dans le Bloc-notes
        self.tree.bind("<Double-1>", self.open_in_notepad)

    def _create_statusbar(self):
        self.statusbar = ttk.Label(
            self.root,
            text=" Prêt.",
            relief=tk.SUNKEN,
            anchor=tk.W
        )
        self.statusbar.pack(side=tk.BOTTOM, fill=tk.X)

    def estimate_machining_time(self, content):
        """
        Estimation cinématique du temps d'usinage
        Prend en compte l'avance F, le profil d'accélération et les rapides G0.
        """
        lines = content.splitlines()
        total_seconds = 0.0
        
        curr_x, curr_y, curr_z = 0.0, 0.0, 0.0
        feed_rate = 5000.0  # mm/min par défaut
        g_mode = "G1"
        rapid_rate = 15000.0  # mm/min pour G0 (NUM 1060)

        g_code_pattern = re.compile(r'([GXYZF])\s*([\-\+]?\d+\.?\d*)', re.IGNORECASE)

        for line in lines:
            line_clean = line.split(';')[0].split('(')[0].strip()
            if not line_clean:
                continue

            matches = g_code_pattern.findall(line_clean)
            if not matches:
                continue

            new_x, new_y, new_z = curr_x, curr_y, curr_z
            has_motion = False

            for cmd, val in matches:
                cmd = cmd.upper()
                v = float(val)

                if cmd == 'G':
                    g_num = int(v)
                    if g_num == 0:
                        g_mode = "G0"
                    elif g_num in (1, 2, 3):
                        g_mode = "G1"
                elif cmd == 'F':
                    if v > 0:
                        feed_rate = v
                elif cmd == 'X':
                    new_x = v
                    has_motion = True
                elif cmd == 'Y':
                    new_y = v
                    has_motion = True
                elif cmd == 'Z':
                    new_z = v
                    has_motion = True

            if has_motion:
                dist = math.sqrt((new_x - curr_x)**2 + (new_y - curr_y)**2 + (new_z - curr_z)**2)
                if dist > 0:
                    speed = rapid_rate if g_mode == "G0" else feed_rate
                    if speed <= 0:
                        speed = 3000.0
                    
                    time_min = dist / speed
                    time_sec = time_min * 60.0
                    
                    # Pénalité d'accélération/décélération pour micro-segments
                    if dist < 5.0 and g_mode == "G1":
                        time_sec *= 1.35
                    
                    total_seconds += time_sec

                curr_x, curr_y, curr_z = new_x, new_y, new_z

        return max(total_seconds, len(lines) * 0.15)

    def parse_cnc_file(self, filepath, filename):
        # 1. NOM DU PROGRAMME = NOM DU FICHIER
        prog_name = filename
        model_name = ""
        tools = []

        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

            lines = content.splitlines()

            # 2. EXTRACTION NOM DU MODÈLE DEPUIS $PAIN
            for line in lines[:30]:
                if "$PAIN" in line.upper():
                    # Exemple: "$PAIN 0021A PAD-10'6F" -> extraire "PAD-10'6F"
                    match = re.search(r'\$PAIN\s+\S+\s+(.+)', line, re.IGNORECASE)
                    if match:
                        model_name = match.group(1).strip()
                        break
                    else:
                        parts = line.strip().split()
                        if len(parts) >= 3:
                            model_name = " ".join(parts[2:]).strip()
                            break

            # Repli si pas de $PAIN explicite
            if not model_name:
                for line in lines[:25]:
                    clean_line = line.strip().lstrip('(%#$* ;')
                    if clean_line and not clean_line.startswith('G') and not clean_line.startswith('M') and len(clean_line) > 2:
                        model_name = clean_line[:35].strip()
                        break

            if not model_name:
                model_name = os.path.splitext(filename)[0]

            # 3. EXTRACTION OUTILS (Format: T1+T5+T8)
            raw_tools = re.findall(r'\bT(\d+)\b', content, re.IGNORECASE)
            if raw_tools:
                unique_tools = sorted(list(set(int(t) for t in raw_tools)))
                tools = [f"T{num}" for num in unique_tools]

            # 4. ESTIMATION DU TEMPS
            sec_100 = self.estimate_machining_time(content)

        except Exception:
            model_name = os.path.splitext(filename)[0]
            sec_100 = 0.0

        tools_str = "+".join(tools) if tools else "N/A"
        return model_name, prog_name, tools_str, sec_100

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
        # Scanner ABSOLUMENT TOUS LES FICHIERS (avec/sans extension, .bat, etc.)
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
                    "filepath": filepath
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
                match_tools = fnmatch.fnmatch(item["tools"].lower(), pattern)

                if not (match_model or match_prog or match_tools):
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
                ),
                tags=(item["filepath"],)
            )
            display_idx += 1

    def open_in_notepad(self, event):
        selected_item = self.tree.selection()
        if not selected_item:
            return

        tags = self.tree.item(selected_item[0], "tags")
        if tags:
            filepath = tags[0]
            if os.path.exists(filepath):
                try:
                    subprocess.Popen(["notepad.exe", filepath])
                except Exception as e:
                    messagebox.showerror("Erreur", f"Impossible d'ouvrir le fichier :\n{e}")

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
