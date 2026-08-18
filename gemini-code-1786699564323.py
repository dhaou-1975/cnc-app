import os
import sys
import sqlite3
import threading
import time
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

# Importation sécurisée de PySerial pour éviter les crashs au lancement sous Windows 7
try:
    import serial
    import serial.tools.list_ports
    HAS_SERIAL = True
except Exception as e:
    HAS_SERIAL = False
    SERIAL_ERROR_MSG = str(e)

# --- CONFIGURATION INITIALE & BASE DE DONNÉES ---
DB_FILE = "cnc_manager.db"


def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Table Utilisateurs
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL
        )
    ''')

    # Comptes par défaut si la table est vide
    cursor.execute("SELECT COUNT(*) FROM users")
    if cursor.fetchone()[0] == 0:
        cursor.execute(
            "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
            ("admin", "admin123", "ADMIN")
        )
        cursor.execute(
            "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
            ("operateur", "1234", "OPERATOR")
        )

    # Table Catalogue (Modèles Windsurf)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS catalog (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            model_name TEXT UNIQUE NOT NULL,
            program_name TEXT,
            block_dim TEXT,
            volume TEXT,
            length TEXT,
            tools TEXT,
            fin_box TEXT,
            footstrap TEXT,
            remarks TEXT
        )
    ''')

    # Table Ordre de Fabrication (Liste de travail en cours)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS current_worklist (
            prio INTEGER PRIMARY KEY,
            model TEXT,
            program TEXT,
            block_dim TEXT,
            tools TEXT,
            remarks TEXT,
            block_num TEXT,
            pain_num TEXT,
            block_date TEXT,
            block_density TEXT
        )
    ''')

    # Table Historique d'Usinage
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS machining_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            operator_username TEXT,
            model_name TEXT,
            program_name TEXT,
            block_dim TEXT,
            block_num TEXT,
            pain_num TEXT,
            block_date TEXT,
            block_density TEXT,
            machined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    conn.commit()
    conn.close()


# --- FONCTIONS UTILITAIRES ---
def autofit_treeview_columns(tree, columns):
    for col in columns:
        max_len = len(col)
        for child in tree.get_children():
            val = str(tree.item(child, "values")[columns.index(col)])
            if len(val) > max_len:
                max_len = len(val)
        tree.column(col, width=max(max_len * 9, 80))


# --- FENÊTRE DE CONNEXION ---
class LoginDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Connexion - CNC Manager")
        self.geometry("320x200")
        self.resizable(False, False)
        self.user_data = None

        tk.Label(self, text="Nom d'utilisateur :").pack(pady=(15, 5))
        self.ent_user = tk.Entry(self)
        self.ent_user.pack()

        tk.Label(self, text="Mot de passe :").pack(pady=(10, 5))
        self.ent_pass = tk.Entry(self, show="*")
        self.ent_pass.pack()

        tk.Button(self, text="Se Connecter", command=self.check_login, width=15).pack(pady=15)
        self.bind('<Return>', lambda event: self.check_login())
        
        self.transient(parent)
        self.grab_set()

    def check_login(self):
        username = self.ent_user.get().strip()
        password = self.ent_pass.get().strip()

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT username, role FROM users WHERE username = ? AND password = ?", (username, password))
        res = cursor.fetchone()
        conn.close()

        if res:
            self.user_data = {"username": res[0], "role": res[1]}
            self.destroy()
        else:
            messagebox.showerror("Erreur", "Identifiants incorrects.")


# --- DIALOGUE ÉDITION BLOC/PAIN ---
class EditBlockInfoDialog(tk.Toplevel):
    def __init__(self, parent, item_data, on_save_callback):
        super().__init__(parent)
        self.title(f"Informations Blocs - Modèle : {item_data.get('model', '')}")
        self.geometry("350x250")
        self.resizable(False, False)
        self.item_data = item_data
        self.on_save_callback = on_save_callback

        tk.Label(self, text="N° Bloc :").grid(row=0, column=0, padx=10, pady=10, sticky="e")
        self.ent_block_num = tk.Entry(self)
        self.ent_block_num.insert(0, item_data.get("block_num", ""))
        self.ent_block_num.grid(row=0, column=1, padx=10, pady=10)

        tk.Label(self, text="N° Pain :").grid(row=1, column=0, padx=10, pady=10, sticky="e")
        self.ent_pain_num = tk.Entry(self)
        self.ent_pain_num.insert(0, item_data.get("pain_num", ""))
        self.ent_pain_num.grid(row=1, column=1, padx=10, pady=10)

        tk.Label(self, text="Date Réception :").grid(row=2, column=0, padx=10, pady=10, sticky="e")
        self.ent_date = tk.Entry(self)
        self.ent_date.insert(0, item_data.get("block_date", datetime.now().strftime("%Y-%m-%d")))
        self.ent_date.grid(row=2, column=1, padx=10, pady=10)

        tk.Label(self, text="Densité (kg/m³) :").grid(row=3, column=0, padx=10, pady=10, sticky="e")
        self.ent_density = tk.Entry(self)
        self.ent_density.insert(0, item_data.get("block_density", ""))
        self.ent_density.grid(row=3, column=1, padx=10, pady=10)

        tk.Button(self, text="Valider", command=self.save, width=12).grid(row=4, column=0, columnspan=2, pady=15)
        
        self.transient(parent)
        self.grab_set()

    def save(self):
        self.item_data["block_num"] = self.ent_block_num.get().strip()
        self.item_data["pain_num"] = self.ent_pain_num.get().strip()
        self.item_data["block_date"] = self.ent_date.get().strip()
        self.item_data["block_density"] = self.ent_density.get().strip()
        if self.on_save_callback:
            self.on_save_callback()
        self.destroy()


# --- DIALOGUE TRANSFERT PROGRAMME (RS-232 / PORT SÉRIE) ---
class CNCTransferDialog(tk.Toplevel):
    def __init__(self, parent, program_name):
        super().__init__(parent)
        self.title(f"Transfert RS-232 CNC - Programme : {program_name}")
        self.geometry("450x380")
        self.resizable(False, False)
        self.program_name = program_name

        if not HAS_SERIAL:
            messagebox.showerror("Module RS-232 Indisponible", f"Impossible d'initialiser le port série sur ce système.\nErreur : {SERIAL_ERROR_MSG}")
            self.destroy()
            return

        # Détection des ports
        try:
            available_ports = [p.device for p in serial.tools.list_ports.comports()]
        except Exception:
            available_ports = []
            
        if not available_ports:
            available_ports = ["COM1", "COM2", "COM3", "COM4"]

        # Configuration des champs de connexion
        frame_cfg = tk.LabelFrame(self, text=" Paramètres de Communication Série ", padx=10, pady=10)
        frame_cfg.pack(fill=tk.X, padx=10, pady=10)

        tk.Label(frame_cfg, text="Port COM :").grid(row=0, column=0, sticky="e", pady=5)
        self.cb_port = ttk.Combobox(frame_cfg, values=available_ports, width=12)
        self.cb_port.set(available_ports[0])
        self.cb_port.grid(row=0, column=1, pady=5, padx=5)

        tk.Label(frame_cfg, text="Vitesse (Bauds) :").grid(row=1, column=0, sticky="e", pady=5)
        self.cb_baud = ttk.Combobox(frame_cfg, values=["1200", "2400", "4800", "9600", "19200", "38400"], width=12)
        self.cb_baud.set("9600")
        self.cb_baud.grid(row=1, column=1, pady=5, padx=5)

        tk.Label(frame_cfg, text="Bits de données :").grid(row=2, column=0, sticky="e", pady=5)
        self.cb_databits = ttk.Combobox(frame_cfg, values=["7", "8"], width=12)
        self.cb_databits.set("7")
        self.cb_databits.grid(row=2, column=1, pady=5, padx=5)

        tk.Label(frame_cfg, text="Parité :").grid(row=3, column=0, sticky="e", pady=5)
        self.cb_parity = ttk.Combobox(frame_cfg, values=["EVEN", "ODD", "NONE"], width=12)
        self.cb_parity.set("EVEN")
        self.cb_parity.grid(row=3, column=1, pady=5, padx=5)

        # Fichier à transférer
        frame_file = tk.Frame(self)
        frame_file.pack(fill=tk.X, padx=10, pady=5)
        
        tk.Label(frame_file, text="Fichier :").pack(side=tk.LEFT)
        self.ent_filepath = tk.Entry(frame_file, width=32)
        self.ent_filepath.insert(0, f"programs/{self.program_name}.nc")
        self.ent_filepath.pack(side=tk.LEFT, padx=5)
        tk.Button(frame_file, text="Parcourir", command=self.browse_file).pack(side=tk.LEFT)

        # Barre de progression
        self.progress = ttk.Progressbar(self, orient="horizontal", length=410, mode="determinate")
        self.progress.pack(pady=15)

        # Bouton d'envoi
        self.btn_send = tk.Button(self, text=" Transmettre le Programme vers CNC ", command=self.start_transfer, bg="#4CAF50", fg="white", font=("Arial", 10, "bold"))
        self.btn_send.pack(pady=5)

        self.transient(parent)
        self.grab_set()

    def browse_file(self):
        f = filedialog.askopenfilename(filetypes=[("Fichiers CNC / G-Code", "*.nc *.pgm *.gcode *.txt"), ("Tous les fichiers", "*.*")])
        if f:
            self.ent_filepath.delete(0, tk.END)
            self.ent_filepath.insert(0, f)

    def start_transfer(self):
        filepath = self.ent_filepath.get().strip()
        if not os.path.exists(filepath):
            messagebox.showerror("Fichier Introuvable", f"Impossible de trouver le fichier G-code :\n{filepath}")
            return

        port = self.cb_port.get()
        baud = int(self.cb_baud.get())
        databits = serial.SEVENBITS if self.cb_databits.get() == "7" else serial.EIGHTBITS
        
        parity_val = self.cb_parity.get()
        if parity_val == "EVEN":
            parity = serial.PARITY_EVEN
        elif parity_val == "ODD":
            parity = serial.PARITY_ODD
        else:
            parity = serial.PARITY_NONE

        self.btn_send.config(state=tk.DISABLED)

        def transfer_worker():
            try:
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as file:
                    lines = file.readlines()

                ser = serial.Serial(
                    port=port,
                    baudrate=baud,
                    bytesize=databits,
                    parity=parity,
                    stopbits=serial.STOPBITS_TWO,
                    timeout=2
                )

                total_lines = len(lines)
                for idx, line in enumerate(lines):
                    ser.write(line.encode('ascii', errors='replace'))
                    time.sleep(0.01)
                    
                    progress_val = ((idx + 1) / total_lines) * 100
                    self.progress['value'] = progress_val
                    self.update_idletasks()

                ser.close()
                messagebox.showinfo("Succès", "Le transfert RS-232 vers la commande numérique s'est terminé avec succès.")
            except Exception as e:
                messagebox.showerror("Erreur RS-232", f"Une erreur s'est produite durant le transfert :\n{str(e)}")
            finally:
                self.btn_send.config(state=tk.NORMAL)

        threading.Thread(target=transfer_worker, daemon=True).start()


# --- APPLICATION PRINCIPALE ---
class CNCManagerApp:
    def __init__(self, root, user_data):
        self.root = root
        self.user = user_data
        self.root.title(f"CNC Manager - Ateliers Windsurf [{self.user['username']} - {self.user['role']}]")
        self.root.geometry("1150x680")
        self.is_running = True

        self.work_list = []
        self.catalog_rows = []
        self.history_rows = []

        # Configuration des styles
        style = ttk.Style()
        style.theme_use("clam")

        # Barre de recherche & Filtres
        top_frame = tk.Frame(self.root, bd=1, relief=tk.RAISED)
        top_frame.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)

        tk.Label(top_frame, text="Rechercher par :").pack(side=tk.LEFT, padx=5)
        self.cb_filter_col = ttk.Combobox(top_frame, state="readonly", width=15)
        self.cb_filter_col.pack(side=tk.LEFT, padx=5)

        self.ent_search = tk.Entry(top_frame, width=25)
        self.ent_search.pack(side=tk.LEFT, padx=5)
        self.ent_search.bind("<KeyRelease>", lambda e: self.filter_data())

        # Bloc Onglets
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)

        # Onglet Catalogue
        self.tab_cat = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_cat, text=" Catalogue Modèles ")
        self.setup_catalog_tab()

        # Onglet Liste d'Usinage (Ordre de Fabrication)
        self.tab_work = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_work, text=" Ordre d'Usinage ")
        self.setup_work_tab()

        # Onglet Historique (Admin uniquement)
        if self.user['role'] == 'ADMIN':
            self.tab_hist = ttk.Frame(self.notebook)
            self.notebook.add(self.tab_hist, text=" Historique Production ")
            self.setup_history_tab()

        # Barre de statut
        self.statusbar = tk.Label(self.root, text=" Prêt", bd=1, relief=tk.SUNKEN, anchor=tk.W)
        self.statusbar.pack(side=tk.BOTTOM, fill=tk.X)

        # Correspondance des recherches
        self.search_maps = {
            "cat": {"Modèle": 0, "Programme": 1, "Projet": 2, "Outils": 5},
            "work": {"Modèle": 1, "Programme": 2, "N° Bloc": 4, "N° Pain": 5},
            "history": {"Opérateur": 1, "Modèle": 2, "Programme": 3, "N° Bloc": 4}
        }

        self.load_catalog_data()
        self.load_saved_worklist()
        if self.user['role'] == 'ADMIN':
            self.load_history_data()

        self.start_auto_save_thread()
        self.root.protocol("WM_DELETE_WINDOW", self.on_app_close)

    def setup_catalog_tab(self):
        self.cat_cols = ("Modèle", "Programme", "Dimensions Bloc", "Volume", "Longueur", "Outils", "Fin Box", "Footstrap", "Remarques")
        self.tree_cat = ttk.Treeview(self.tab_cat, columns=self.cat_cols, show="headings", selectmode="extended")
        
        for col in self.cat_cols:
            self.tree_cat.heading(col, text=col)
            self.tree_cat.column(col, width=100)

        self.tree_cat.tag_configure('already_selected', background='#E0E0E0', foreground='#888888')

        sb = ttk.Scrollbar(self.tab_cat, orient="vertical", command=self.tree_cat.yview)
        self.tree_cat.configure(yscroll=sb.set)
        
        self.tree_cat.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        btn_frame = tk.Frame(self.tab_cat)
        btn_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=5)
        tk.Button(btn_frame, text="Ajouter les sélectionnés à l'Ordre de Fabrication", command=self.add_selected_to_worklist, bg="#4CAF50", fg="white").pack(side=tk.RIGHT, padx=10)

    def setup_work_tab(self):
        self.work_cols = ("Prio", "Modèle", "Programme", "Dimensions Bloc", "N° Bloc", "N° Pain", "Outils", "Remarques", "Date", "Densité")
        self.tree_work = ttk.Treeview(self.tab_work, columns=self.work_cols, show="headings", selectmode="browse")

        for col in self.work_cols:
            self.tree_work.heading(col, text=col)
            self.tree_work.column(col, width=90)

        self.tree_work.tag_configure('missing_info', background='#FFCDD2')

        sb = ttk.Scrollbar(self.tab_work, orient="vertical", command=self.tree_work.yview)
        self.tree_work.configure(yscroll=sb.set)

        self.tree_work.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        # Panneau de contrôle à droite
        ctrl_frame = tk.Frame(self.tab_work, width=160)
        ctrl_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=5, pady=5)

        tk.Button(ctrl_frame, text="Monter ▲", command=self.move_work_item_up, width=16).pack(pady=5)
        tk.Button(ctrl_frame, text="Descendre ▼", command=self.move_work_item_down, width=16).pack(pady=5)
        tk.Button(ctrl_frame, text="Saisir Bloc/Pain", command=self.edit_block_info, width=16, bg="#2196F3", fg="white").pack(pady=10)
        
        # Bouton de transfert RS-232 vers CNC
        tk.Button(ctrl_frame, text="Transférer CNC (RS232)", command=self.open_transfer_dialog, width=16, bg="#9C27B0", fg="white").pack(pady=10)

        tk.Button(ctrl_frame, text="Supprimer", command=self.remove_from_worklist, width=16, bg="#F44336", fg="white").pack(pady=5)
        tk.Button(ctrl_frame, text="Valider Usinage", command=self.validate_worklist, width=16, bg="#FF9800", fg="white").pack(side=tk.BOTTOM, pady=10)

    def setup_history_tab(self):
        self.hist_cols = ("ID", "Opérateur", "Modèle", "Programme", "Dimensions", "N° Bloc", "N° Pain", "Date Bloc", "Densité", "Date Usinage")
        self.tree_hist = ttk.Treeview(self.tab_hist, columns=self.hist_cols, show="headings")

        for col in self.hist_cols:
            self.tree_hist.heading(col, text=col)
            self.tree_hist.column(col, width=90)

        sb = ttk.Scrollbar(self.tab_hist, orient="vertical", command=self.tree_hist.yview)
        self.tree_hist.configure(yscroll=sb.set)

        self.tree_hist.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

    def open_transfer_dialog(self):
        selected = self.tree_work.selection()
        if not selected:
            messagebox.showwarning("Sélection", "Veuillez sélectionner une ligne dans l'Ordre d'Usinage pour transférer son programme.")
            return
        idx = self.tree_work.index(selected[0])
        prog_name = self.work_list[idx].get("program", "PROGRAM")
        CNCTransferDialog(self.root, prog_name)

    def on_tab_changed(self, event):
        selected_tab = self.notebook.select()
        tab_text = self.notebook.tab(selected_tab, "text").strip()

        if tab_text == "Catalogue Modèles":
            self.current_tab_key = "cat"
        elif tab_text == "Ordre d'Usinage":
            self.current_tab_key = "work"
        else:
            self.current_tab_key = "history"

        self.cb_filter_col['values'] = list(self.search_maps[self.current_tab_key].keys())
        self.cb_filter_col.current(0)
        self.filter_data()

    def load_catalog_data(self):
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT id, model_name, program_name, block_dim, volume, length, tools, fin_box, footstrap, remarks FROM catalog")
        self.catalog_rows = cursor.fetchall()
        conn.close()
        self.filter_data()

    def load_history_data(self):
        if self.user['role'] != 'ADMIN':
            return
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT id, operator_username, model_name, program_name, block_dim, block_num, pain_num, block_date, block_density, machined_at FROM machining_history ORDER BY id DESC")
        self.history_rows = cursor.fetchall()
        conn.close()
        self.filter_data()

    def check_match(self, query, value):
        return query.lower() in str(value).lower()

    def filter_data(self):
        query = self.ent_search.get().strip()
        selected_col_name = self.cb_filter_col.get()

        if self.current_tab_key == "cat":
            tree = self.tree_cat
            col_map = self.search_maps["cat"]
            col_idx = col_map.get(selected_col_name, 0)

            for item in tree.get_children():
                tree.delete(item)

            selected_models = [w["model"] for w in self.work_list]

            for r in self.catalog_rows:
                display_vals = r[1:]
                val_to_check = display_vals[col_idx] if col_idx < len(display_vals) else ""

                if self.check_match(query, val_to_check):
                    item_id = tree.insert("", tk.END, values=display_vals)
                    if display_vals[0] in selected_models:
                        tree.item(item_id, tags=('already_selected',))

        elif self.current_tab_key == "work":
            tree = self.tree_work
            col_map = self.search_maps["work"]
            col_idx = col_map.get(selected_col_name, 0)

            for item in tree.get_children():
                tree.delete(item)

            for item_data in self.work_list:
                row_vals = (
                    item_data.get("prio", ""),
                    item_data.get("model", ""),
                    item_data.get("program", ""),
                    item_data.get("block_dim", ""),
                    item_data.get("block_num", ""),
                    item_data.get("pain_num", ""),
                    item_data.get("tools", ""),
                    item_data.get("remarks", ""),
                    item_data.get("block_date", ""),
                    item_data.get("block_density", "")
                )
                val_to_check = row_vals[col_idx] if col_idx < len(row_vals) else ""
                if self.check_match(query, val_to_check):
                    item_id = tree.insert("", tk.END, values=row_vals)
                    if not item_data.get("block_num") or not item_data.get("pain_num"):
                        tree.item(item_id, tags=('missing_info',))

        elif self.current_tab_key == "history" and self.user['role'] == 'ADMIN':
            tree = self.tree_hist
            col_map = self.search_maps["history"]
            col_idx = col_map.get(selected_col_name, 0)

            for item in tree.get_children():
                tree.delete(item)

            if hasattr(self, 'history_rows'):
                for r in self.history_rows:
                    row_vals = r[0:]
                    val_to_check = row_vals[col_idx] if col_idx < len(row_vals) else ""
                    if self.check_match(query, val_to_check):
                        item_id = tree.insert("", tk.END, values=row_vals)
                        if not r[5] or not r[6]:
                            tree.item(item_id, tags=('missing_info',))

    def add_selected_to_worklist(self):
        selected_items = self.tree_cat.selection()
        if not selected_items:
            messagebox.showwarning("Sélection", "Veuillez sélectionner au moins un modèle dans le catalogue.")
            return

        added_count = 0
        for item in selected_items:
            vals = self.tree_cat.item(item, "values")
            model_name = vals[0]

            if any(w["model"] == model_name for w in self.work_list):
                continue

            prio_num = len(self.work_list) + 1
            new_entry = {
                "prio": f"P{prio_num}",
                "model": vals[0],
                "program": vals[1],
                "block_dim": vals[2],
                "tools": vals[5],
                "remarks": vals[8],
                "block_num": "",
                "pain_num": "",
                "block_date": datetime.now().strftime("%Y-%m-%d"),
                "block_density": ""
            }
            self.work_list.append(new_entry)
            added_count += 1

        self.refresh_work_tree()
        self.load_catalog_data()
        self.save_worklist_to_db()
        self.statusbar.config(text=f" {added_count} modèle(s) ajouté(s) à la liste de travail.")

    def refresh_work_tree(self):
        for idx, item in enumerate(self.work_list, start=1):
            item["prio"] = f"P{idx}"
        self.filter_data()
        autofit_treeview_columns(self.tree_work, self.work_cols)

    def move_work_item_up(self):
        selected = self.tree_work.selection()
        if not selected:
            return
        idx = self.tree_work.index(selected[0])
        if idx > 0:
            self.work_list[idx], self.work_list[idx - 1] = self.work_list[idx - 1], self.work_list[idx]
            self.refresh_work_tree()
            self.save_worklist_to_db()

    def move_work_item_down(self):
        selected = self.tree_work.selection()
        if not selected:
            return
        idx = self.tree_work.index(selected[0])
        if idx < len(self.work_list) - 1:
            self.work_list[idx], self.work_list[idx + 1] = self.work_list[idx + 1], self.work_list[idx]
            self.refresh_work_tree()
            self.save_worklist_to_db()

    def edit_block_info(self):
        selected = self.tree_work.selection()
        if not selected:
            messagebox.showwarning("Sélection", "Veuillez sélectionner une ligne dans l'Ordre de Fabrication.")
            return
        idx = self.tree_work.index(selected[0])
        item_data = self.work_list[idx]

        def on_save():
            self.refresh_work_tree()
            self.save_worklist_to_db()

        EditBlockInfoDialog(self.root, item_data, on_save)

    def remove_from_worklist(self):
        selected = self.tree_work.selection()
        if not selected:
            return
        idx = self.tree_work.index(selected[0])
        del self.work_list[idx]
        self.refresh_work_tree()
        self.load_catalog_data()
        self.save_worklist_to_db()

    def save_worklist_to_db(self):
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM current_worklist")
        for item in self.work_list:
            prio_val = int(item["prio"].replace("P", "")) if isinstance(item["prio"], str) else item["prio"]
            cursor.execute('''
                INSERT INTO current_worklist (prio, model, program, block_dim, tools, remarks, block_num, pain_num, block_date, block_density)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                prio_val, item["model"], item["program"], item["block_dim"],
                item["tools"], item["remarks"], item["block_num"], item["pain_num"],
                item["block_date"], item["block_density"]
            ))
        conn.commit()
        conn.close()
        self.statusbar.config(text=f" Liste de travail sauvegardée ({datetime.now().strftime('%H:%M:%S')}).")

    def load_saved_worklist(self):
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT prio, model, program, block_dim, tools, remarks, block_num, pain_num, block_date, block_density FROM current_worklist ORDER BY prio ASC")
        rows = cursor.fetchall()
        conn.close()

        self.work_list = []
        for r in rows:
            self.work_list.append({
                "prio": f"P{r[0]}",
                "model": r[1],
                "program": r[2],
                "block_dim": r[3],
                "tools": r[4],
                "remarks": r[5],
                "block_num": r[6],
                "pain_num": r[7],
                "block_date": r[8],
                "block_density": r[9]
            })
        self.refresh_work_tree()

    def validate_worklist(self):
        if not self.work_list:
            messagebox.showwarning("Attention", "La liste d'usinage est vide.")
            return

        missing = [w["model"] for w in self.work_list if not w["block_num"] or not w["pain_num"]]
        if missing:
            messagebox.showerror("Champs Manquants", f"Impossible de valider : les informations (N° Bloc / N° Pain) sont manquantes pour :\n- " + "\n- ".join(missing))
            return

        if not messagebox.askyesno("Validation Usinage", "Confirmez-vous l'enregistrement de ces usinages dans l'historique ?"):
            return

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        for w in self.work_list:
            cursor.execute('''
                INSERT INTO machining_history (operator_username, model_name, program_name, block_dim, block_num, pain_num, block_date, block_density)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                self.user["username"], w["model"], w["program"], w["block_dim"],
                w["block_num"], w["pain_num"], w["block_date"], w["block_density"]
            ))

        cursor.execute("DELETE FROM current_worklist")
        conn.commit()
        conn.close()

        self.work_list = []
        self.refresh_work_tree()
        self.load_catalog_data()
        if self.user['role'] == 'ADMIN':
            self.load_history_data()

        messagebox.showinfo("Succès", "Usinages validés et enregistrés avec succès dans l'historique !")

    def start_auto_save_thread(self):
        def auto_save_loop():
            while self.is_running:
                time.sleep(120)
                if self.is_running:
                    try:
                        self.save_worklist_to_db()
                    except Exception:
                        pass

        threading.Thread(target=auto_save_loop, daemon=True).start()

    def on_app_close(self):
        self.is_running = False
        try:
            self.save_worklist_to_db()
        except Exception:
            pass
        self.root.destroy()


# --- DÉMARRAGE DU PROGRAMME ---
if __name__ == "__main__":
    init_db()
    root = tk.Tk()
    root.withdraw()

    login_dlg = LoginDialog(root)
    root.wait_window(login_dlg)

    if login_dlg.user_data:
        root.deiconify()
        app = CNCManagerApp(root, login_dlg.user_data)
        root.mainloop()
    else:
        root.destroy()
