import os
import sys
import csv
import re
import sqlite3
import threading
import time
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, font

APP_NAME = "CNC Manager - Ateliers Windsurf"
APP_VERSION = "v4.3.0"
DB_FILE = "cnc_factory.db"


def init_db():
    """Initialise la base de données SQLite et garantit le compte admin."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS models_catalog (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            model_name TEXT NOT NULL UNIQUE,
            program_name TEXT NOT NULL,
            block_dim TEXT,
            block_dim_bought TEXT,
            qty_per_block TEXT,
            z_between_boards TEXT,
            tools TEXT,
            caisson TEXT,
            plaque_gamma TEXT,
            plaque_beta TEXT,
            remarks TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS current_worklist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prio INTEGER,
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

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS machining_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            operator_username TEXT NOT NULL,
            model_name TEXT NOT NULL,
            program_name TEXT NOT NULL,
            block_dim TEXT DEFAULT '',
            block_num TEXT NOT NULL,
            pain_num TEXT DEFAULT '',
            block_date TEXT NOT NULL,
            block_density TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute("PRAGMA table_info(machining_history)")
    cols = [col[1] for col in cursor.fetchall()]
    if "pain_num" not in cols:
        cursor.execute("ALTER TABLE machining_history ADD COLUMN pain_num TEXT DEFAULT ''")

    cursor.execute("PRAGMA table_info(current_worklist)")
    cols_work = [col[1] for col in cursor.fetchall()]
    if "pain_num" not in cols_work:
        cursor.execute("ALTER TABLE current_worklist ADD COLUMN pain_num TEXT DEFAULT ''")

    cursor.execute('''
        INSERT INTO users (username, password, role)
        VALUES ('admin', 'admin', 'ADMIN')
        ON CONFLICT(username) DO UPDATE SET password='admin', role='ADMIN'
    ''')

    conn.commit()
    conn.close()


def autofit_treeview_columns(tree, columns_dict):
    """Ajuste la largeur des colonnes automatiquement en fonction du contenu."""
    default_font = font.Font()
    for col_id, col_title in columns_dict.items():
        max_len = default_font.measure(col_title) + 25
        for item in tree.get_children():
            cell_val = str(tree.set(item, col_id))
            val_len = default_font.measure(cell_val) + 25
            if val_len > max_len:
                max_len = val_len
        tree.column(col_id, width=max(max_len, 90))


class LoginDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Authentification")
        self.geometry("400x260")
        self.resizable(False, False)
        self.grab_set()

        self.user_data = None

        ttk.Label(self, text="Connexion Atelier CNC", font=("Arial", 14, "bold")).pack(pady=10)

        frame = ttk.Frame(self, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="Nom d'utilisateur :").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.ent_user = ttk.Entry(frame)
        self.ent_user.insert(0, "admin")
        self.ent_user.grid(row=0, column=1, sticky=tk.EW, pady=5)
        self.ent_user.focus()

        ttk.Label(frame, text="Mot de passe :").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.ent_pass = ttk.Entry(frame, show="*")
        self.ent_pass.grid(row=1, column=1, sticky=tk.EW, pady=5)

        btn_box = ttk.Frame(self, padding=10)
        btn_box.pack(fill=tk.X)
        ttk.Button(btn_box, text="Se Connecter", command=self.check_login).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_box, text="Réinitialiser Admin", command=self.force_reset_admin).pack(side=tk.LEFT, padx=5)

        self.bind('<Return>', lambda event: self.check_login())

    def check_login(self):
        user = self.ent_user.get().strip()
        pwd = self.ent_pass.get().strip()

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT username, role FROM users WHERE username=? AND password=?", (user, pwd))
        row = cursor.fetchone()
        conn.close()

        if row:
            self.user_data = {"username": row[0], "role": row[1]}
            self.destroy()
        else:
            messagebox.showerror("Erreur", "Nom d'utilisateur ou mot de passe incorrect.")

    def force_reset_admin(self):
        if messagebox.askyesno("Réinitialisation", "Forcer le compte 'admin' avec le mot de passe 'admin' ?"):
            init_db()
            self.ent_user.delete(0, tk.END)
            self.ent_user.insert(0, "admin")
            self.ent_pass.delete(0, tk.END)
            self.ent_pass.insert(0, "admin")
            messagebox.showinfo("Succès", "Le compte 'admin' a été réinitialisé.\n\nNom: admin\nMot de passe: admin")


class AddModelDialog(tk.Toplevel):
    def __init__(self, parent, main_app):
        super().__init__(parent)
        self.main_app = main_app
        self.title("Ajouter un Nouveau Modèle")
        self.geometry("520x480")
        self.resizable(False, False)
        self.grab_set()

        ttk.Label(self, text="Nouveau Modèle au Catalogue", font=("Arial", 12, "bold")).pack(pady=10)

        frame = ttk.Frame(self, padding=15)
        frame.pack(fill=tk.BOTH, expand=True)

        fields = [
            ("Nom Modèle * :", "model_name", 35),
            ("Nom Programme Pain * :", "program_name", 35),
            ("Dimension Bloc :", "block_dim", 35),
            ("Qté par Bloc :", "qty_per_block", 15),
            ("Z entre 2 Pains :", "z_between_boards", 15),
            ("Outils :", "tools", 30),
            ("Caisson :", "caisson", 20),
            ("Plaque Gamma :", "plaque_gamma", 20),
            ("Plaque Beta :", "plaque_beta", 20),
            ("Remarques :", "remarks", 35)
        ]

        self.entries = {}
        for idx, (label, key, width) in enumerate(fields):
            ttk.Label(frame, text=label).grid(row=idx, column=0, sticky=tk.W, pady=3)
            ent = ttk.Entry(frame, width=width)
            ent.grid(row=idx, column=1, sticky=tk.W, pady=3, padx=5)
            self.entries[key] = ent

        btn_box = ttk.Frame(self, padding=10)
        btn_box.pack(fill=tk.X)
        ttk.Button(btn_box, text="Enregistrer Modèle", command=self.save_model).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_box, text="Annuler", command=self.destroy).pack(side=tk.RIGHT)

    def save_model(self):
        m_name = self.entries["model_name"].get().strip()
        p_name = self.entries["program_name"].get().strip()

        if not m_name or not p_name:
            messagebox.showwarning("Champs requis", "Le 'Nom Modèle' et le 'Nom Programme' sont obligatoires.")
            return

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM models_catalog WHERE LOWER(model_name) = LOWER(?)", (m_name,))
        if cursor.fetchone():
            messagebox.showerror("Modèle Existant", f"Le modèle '{m_name}' existe déjà dans le catalogue !")
            conn.close()
            return

        vals = tuple(self.entries[k].get().strip() for k in [
            "model_name", "program_name", "block_dim", "qty_per_block",
            "z_between_boards", "tools", "caisson", "plaque_gamma", "plaque_beta", "remarks"
        ])

        cursor.execute('''
            INSERT INTO models_catalog (model_name, program_name, block_dim, qty_per_block, z_between_boards, tools, caisson, plaque_gamma, plaque_beta, remarks)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', vals)

        conn.commit()
        conn.close()

        messagebox.showinfo("Succès", f"Le modèle '{m_name}' a été ajouté au catalogue.")
        self.main_app.load_catalog_data()
        self.destroy()


class UserManagementDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Gestion des Utilisateurs")
        self.geometry("560x420")
        self.grab_set()

        ttk.Label(self, text="Gestion des Comptes & Autorisations", font=("Arial", 12, "bold")).pack(pady=5)

        frame_list = ttk.Frame(self, padding=5)
        frame_list.pack(fill=tk.BOTH, expand=True)

        self.tree_users = ttk.Treeview(frame_list, columns=("id", "username", "role"), show="headings", selectmode="browse")
        self.tree_users.heading("id", text="ID")
        self.tree_users.heading("username", text="Utilisateur")
        self.tree_users.heading("role", text="Rôle")
        self.tree_users.column("id", width=50, anchor=tk.CENTER)
        self.tree_users.column("username", width=220)
        self.tree_users.column("role", width=200)
        self.tree_users.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        frame_actions = ttk.Frame(frame_list, padding=5)
        frame_actions.pack(side=tk.RIGHT, fill=tk.Y)
        ttk.Button(frame_actions, text="- Supprimer", command=self.delete_user).pack(fill=tk.X, pady=5)

        frame_form = ttk.LabelFrame(self, text=" Saisie Utilisateur ", padding=10)
        frame_form.pack(fill=tk.X, padx=10, pady=10)

        ttk.Label(frame_form, text="Nom:").grid(row=0, column=0, padx=2)
        self.ent_u = ttk.Entry(frame_form, width=12)
        self.ent_u.grid(row=0, column=1, padx=2)

        ttk.Label(frame_form, text="M.Passe:").grid(row=0, column=2, padx=2)
        self.ent_p = ttk.Entry(frame_form, width=12, show="*")
        self.ent_p.grid(row=0, column=3, padx=2)

        ttk.Label(frame_form, text="Rôle:").grid(row=0, column=4, padx=2)
        self.cmb_r = ttk.Combobox(frame_form, values=["OPERATEUR", "ADMIN"], width=11, state="readonly")
        self.cmb_r.set("OPERATEUR")
        self.cmb_r.grid(row=0, column=5, padx=2)

        ttk.Button(frame_form, text="+ Ajouter/Maj", command=self.add_or_update_user).grid(row=0, column=6, padx=5)

        self.load_users()

    def load_users(self):
        for item in self.tree_users.get_children():
            self.tree_users.delete(item)
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT id, username, role FROM users")
        for row in cursor.fetchall():
            self.tree_users.insert("", tk.END, values=row)
        conn.close()

    def add_or_update_user(self):
        u = self.ent_u.get().strip()
        p = self.ent_p.get().strip()
        r = self.cmb_r.get()

        if not u or not p:
            messagebox.showwarning("Erreur", "Saisissez un nom d'utilisateur et un mot de passe.")
            return

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO users (username, password, role) VALUES (?, ?, ?)
            ON CONFLICT(username) DO UPDATE SET password=?, role=?
        ''', (u, p, r, p, r))
        conn.commit()
        conn.close()

        messagebox.showinfo("Succès", f"Compte '{u}' enregistré.")
        self.load_users()
        self.ent_u.delete(0, tk.END)
        self.ent_p.delete(0, tk.END)

    def delete_user(self):
        selected = self.tree_users.selection()
        if not selected:
            messagebox.showwarning("Attention", "Sélectionnez un utilisateur à supprimer.")
            return

        user_id, username, role = self.tree_users.item(selected[0], "values")

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT count(*) FROM users WHERE role='ADMIN'")
        admin_count = cursor.fetchone()[0]

        if role == 'ADMIN' and admin_count <= 1:
            messagebox.showerror("Erreur", "Impossible de supprimer le dernier compte Administrateur !")
            conn.close()
            return

        if messagebox.askyesno("Confirmation", f"Voulez-vous supprimer l'utilisateur '{username}' ?"):
            cursor.execute("DELETE FROM users WHERE id=?", (user_id,))
            conn.commit()
            conn.close()
            self.load_users()


class CNCManagerApp:
    def __init__(self, root, current_user):
        self.root = root
        self.user = current_user
        self.root.title(f"{APP_NAME} - Connecté : {self.user['username']} [{self.user['role']}]")
        self.root.geometry("1300x800")

        self.work_list = []
        self.current_tab_key = "catalog"

        style = ttk.Style()
        style.configure("Treeview", rowheight=28)

        self.root.protocol("WM_DELETE_WINDOW", self.on_app_close)

        self._create_menu()
        self._create_header()
        self._create_toolbar()
        self._create_notebook()
        self._create_statusbar()

        self.load_saved_worklist()
        self.load_catalog_data()

        self.is_running = True
        self.start_auto_save_thread()

    def _create_menu(self):
        menubar = tk.Menu(self.root)

        file_menu = tk.Menu(menubar, tearoff=0)
        if self.user['role'] == 'ADMIN':
            file_menu.add_command(label="Importer Fichier CSV...", command=self.import_csv)
        file_menu.add_command(label="Sauvegarder la Liste", command=self.save_worklist_to_db)
        file_menu.add_command(label="Actualiser", command=self.refresh_all_data)
        file_menu.add_separator()
        file_menu.add_command(label="Quitter", command=self.on_app_close)
        menubar.add_cascade(label="Fichier", menu=file_menu)

        tools_menu = tk.Menu(menubar, tearoff=0)
        tools_menu.add_command(label="+ Ajouter un Modèle", command=lambda: AddModelDialog(self.root, self))
        menubar.add_cascade(label="Outils", menu=tools_menu)

        if self.user['role'] == 'ADMIN':
            admin_menu = tk.Menu(menubar, tearoff=0)
            admin_menu.add_command(label="Gestion Utilisateurs", command=lambda: UserManagementDialog(self.root))
            menubar.add_cascade(label="Administration", menu=admin_menu)

        self.root.config(menu=menubar)

    def _create_header(self):
        header_frame = ttk.Frame(self.root, padding=10)
        header_frame.pack(fill=tk.X)

        ttk.Label(header_frame, text=APP_NAME, font=("Arial", 16, "bold")).pack(side=tk.LEFT)
        user_info = f"Utilisateur : {self.user['username']} | Accès : {self.user['role']}"
        ttk.Label(header_frame, text=user_info, font=("Arial", 10, "italic"), foreground="blue").pack(side=tk.RIGHT)

        ttk.Separator(self.root, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=10)

    def _create_toolbar(self):
        toolbar = ttk.Frame(self.root, padding=10)
        toolbar.pack(fill=tk.X)

        if self.user['role'] == 'ADMIN':
            ttk.Button(toolbar, text="Importer CSV", command=self.import_csv).pack(side=tk.LEFT, padx=5)

        ttk.Button(toolbar, text="Actualiser", command=self.refresh_all_data).pack(side=tk.LEFT, padx=5)
        ttk.Button(toolbar, text="💾 Sauvegarder la Liste", command=self.save_worklist_to_db).pack(side=tk.LEFT, padx=5)

        ttk.Label(toolbar, text="Rechercher :", font=("Arial", 9, "bold")).pack(side=tk.LEFT, padx=(20, 5))

        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *args: self.filter_data())

        self.ent_search = ttk.Entry(toolbar, textvariable=self.search_var, width=25)
        self.ent_search.pack(side=tk.LEFT, padx=5)

        ttk.Label(toolbar, text="Dans :").pack(side=tk.LEFT, padx=(10, 5))

        self.search_maps = {
            "catalog": {
                "Nom Modèle": 0,
                "Programme Pain": 1,
                "Dim. Bloc": 2,
                "Outils": 5,
                "Caisson": 6,
                "Plaque Gamma": 7,
                "Plaque Beta": 8,
                "Remarques": 9
            },
            "work": {
                "Priorité": 0,
                "Nom du Modèle": 1,
                "Programme Pain": 2,
                "Dimension Bloc": 3,
                "N° / ID Bloc": 4,
                "N° Pain (Polystyrène)": 5,
                "N° Outils": 6,
                "Remarques": 7,
                "Date Réception": 8,
                "Densité (kg/m³)": 9
            },
            "history": {
                "N°": 0,
                "Opérateur": 1,
                "Modèle": 2,
                "Programme": 3,
                "Dim. Bloc": 4,
                "N° Bloc": 5,
                "N° Pain": 6,
                "Date Réception": 7
            }
        }

        self.cmb_search_col = ttk.Combobox(toolbar, state="readonly", width=22)
        self.cmb_search_col.pack(side=tk.LEFT, padx=5)
        self.cmb_search_col.bind("<<ComboboxSelected>>", lambda e: self.filter_data())

    def _update_search_combobox_for_tab(self, tab_key):
        self.current_tab_key = tab_key
        options = list(self.search_maps[tab_key].keys())
        self.cmb_search_col['values'] = options
        if options:
            self.cmb_search_col.set(options[0])

    def _create_notebook(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.tab_catalog = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_catalog, text="Catalogue Modèles")
        self._setup_catalog_tree(self.tab_catalog)

        self.tab_work = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_work, text="Ordre de Fabrication (Zone Opérateur)")
        self._setup_work_tree(self.tab_work)

        # Seul l'administrateur accède à cette fenêtre, nommée "Historique Usinages"
        if self.user['role'] == 'ADMIN':
            self.tab_history = ttk.Frame(self.notebook)
            self.notebook.add(self.tab_history, text="Historique Usinages")
            self._setup_history_tree(self.tab_history)

        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)
        self._update_search_combobox_for_tab("catalog")

    def _on_tab_changed(self, event):
        idx = self.notebook.index(self.notebook.select())
        if idx == 0:
            self._update_search_combobox_for_tab("catalog")
        elif idx == 1:
            self._update_search_combobox_for_tab("work")
        elif idx == 2 and self.user['role'] == 'ADMIN':
            self._update_search_combobox_for_tab("history")
        self.filter_data()

    def _setup_catalog_tree(self, parent):
        container = ttk.Frame(parent, padding=5)
        container.pack(fill=tk.BOTH, expand=True)

        self.cat_cols = {
            "model": "Nom Modèle",
            "program": "Programme Pain",
            "dim_block": "Dim. Bloc",
            "qty": "Qté/Bloc",
            "z_between": "Z entre 2",
            "tools": "Outils",
            "caisson": "Caisson",
            "p_gamma": "Plaque Gamma",
            "p_beta": "Plaque Beta",
            "remarks": "Remarques"
        }

        self.tree_cat = ttk.Treeview(container, columns=tuple(self.cat_cols.keys()), show="headings", selectmode="extended")

        for col, text in self.cat_cols.items():
            self.tree_cat.heading(col, text=text, command=lambda _c=col: self.sort_treeview(self.tree_cat, _c, False))

        self.tree_cat.tag_configure('already_selected', background='#D0D0D0', foreground='#333333')

        vsb = ttk.Scrollbar(container, orient=tk.VERTICAL, command=self.tree_cat.yview)
        hsb = ttk.Scrollbar(container, orient=tk.HORIZONTAL, command=self.tree_cat.xview)
        self.tree_cat.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree_cat.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        hsb.pack(side=tk.BOTTOM, fill=tk.X)

        self.tree_cat.bind("<Double-1>", lambda e: self.add_selected_to_worklist())

        btn_bar = ttk.Frame(parent, padding=5)
        btn_bar.pack(fill=tk.X)
        ttk.Button(btn_bar, text="+ Ajouter les modèles sélectionnés à ma Liste du Jour", command=self.add_selected_to_worklist).pack(side=tk.RIGHT)

    def _setup_work_tree(self, parent):
        container = ttk.Frame(parent, padding=5)
        container.pack(fill=tk.BOTH, expand=True)

        self.work_cols = {
            "prio": "Priorité",
            "model": "Nom du Modèle",
            "program": "Programme Pain",
            "block_dim": "Dimension Bloc",
            "block_num": "N° / ID Bloc",
            "pain_num": "N° Pain (Polystyrène)",
            "tools": "N° Outils",
            "remarks": "Remarques",
            "block_date": "Date Réception",
            "block_density": "Densité (kg/m³)"
        }

        self.tree_work = ttk.Treeview(container, columns=tuple(self.work_cols.keys()), show="headings", selectmode="browse")

        for col, text in self.work_cols.items():
            self.tree_work.heading(col, text=text, command=lambda _c=col: self.sort_treeview(self.tree_work, _c, False))

        # Tag avec FOND ROUGE vif et texte blanc pour informations manquantes
        self.tree_work.tag_configure('missing_info', background='#D32F2F', foreground='white')

        vsb = ttk.Scrollbar(container, orient=tk.VERTICAL, command=self.tree_work.yview)
        hsb = ttk.Scrollbar(container, orient=tk.HORIZONTAL, command=self.tree_work.xview)
        self.tree_work.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree_work.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        hsb.pack(side=tk.BOTTOM, fill=tk.X)

        btn_bar = ttk.Frame(parent, padding=10)
        btn_bar.pack(fill=tk.X)

        prio_frame = ttk.LabelFrame(btn_bar, text=" Modifier Ordre / Priorité ", padding=5)
        prio_frame.pack(side=tk.LEFT, padx=5)
        ttk.Button(prio_frame, text="▲ Monter", command=self.move_work_item_up).pack(side=tk.LEFT, padx=2)
        ttk.Button(prio_frame, text="▼ Descendre", command=self.move_work_item_down).pack(side=tk.LEFT, padx=2)

        ttk.Button(btn_bar, text="Renseigner / Editer Bloc & N° Pain", command=self.edit_block_info).pack(side=tk.LEFT, padx=10)
        ttk.Button(btn_bar, text="- Retirer de la liste", command=self.remove_from_worklist).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_bar, text="Valider & Enregistrer Usinage du Jour", command=self.validate_worklist).pack(side=tk.RIGHT, padx=5)

    def _setup_history_tree(self, parent):
        container = ttk.Frame(parent, padding=5)
        container.pack(fill=tk.BOTH, expand=True)

        self.hist_cols = {
            "id": "N°",
            "op": "Opérateur",
            "model": "Modèle",
            "program": "Programme",
            "dim_block": "Dim. Bloc",
            "block": "N° Bloc",
            "pain": "N° Pain (Polystyrène)",
            "date": "Date Réception",
            "density": "Densité",
            "timestamp": "Horodatage Validation"
        }

        self.tree_hist = ttk.Treeview(container, columns=tuple(self.hist_cols.keys()), show="headings")

        for col, text in self.hist_cols.items():
            self.tree_hist.heading(col, text=text, command=lambda _c=col: self.sort_treeview(self.tree_hist, _c, False))

        # Tag avec FOND ROUGE vif et texte blanc pour informations manquantes
        self.tree_hist.tag_configure('missing_info', background='#D32F2F', foreground='white')

        vsb = ttk.Scrollbar(container, orient=tk.VERTICAL, command=self.tree_hist.yview)
        hsb = ttk.Scrollbar(container, orient=tk.HORIZONTAL, command=self.tree_hist.xview)
        self.tree_hist.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree_hist.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        hsb.pack(side=tk.BOTTOM, fill=tk.X)

    def _create_statusbar(self):
        self.statusbar = ttk.Label(self.root, text=" Prêt.", relief=tk.SUNKEN, anchor=tk.W)
        self.statusbar.pack(side=tk.BOTTOM, fill=tk.X)

    def sort_treeview(self, tree, col, reverse):
        """Trie le tableau au clic sur l'entête de colonne (façon Explorateur Windows)."""
        data = [(tree.set(k, col), k) for k in tree.get_children('')]

        def convert(val):
            try:
                return float(val[0].replace('P', ''))
            except ValueError:
                return val[0].lower()

        data.sort(key=convert, reverse=reverse)

        for index, (val, k) in enumerate(data):
            tree.move(k, '', index)

        tree.heading(col, command=lambda: self.sort_treeview(tree, col, not reverse))

    def import_csv(self):
        file_path = filedialog.askopenfilename(filetypes=[("Fichiers CSV", "*.csv"), ("Tous les fichiers", "*.*")])
        if not file_path:
            return

        if not messagebox.askyesno("Confirmation", "Voulez-vous importer ce fichier CSV dans le catalogue ?"):
            return

        try:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            count = 0

            with open(file_path, 'r', encoding='utf-8-sig', errors='ignore') as f:
                sample = f.read(2048)
                delimiter = ';' if ';' in sample else ','
                f.seek(0)

                reader = csv.reader(f, delimiter=delimiter)
                next(reader, None)

                for row in reader:
                    if row and len(row) >= 2:
                        try:
                            cursor.execute('''
                                INSERT INTO models_catalog (model_name, program_name, block_dim, block_dim_bought, qty_per_block, z_between_boards, tools, caisson, plaque_gamma, plaque_beta, remarks)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ''', (
                                row[0].strip(), row[1].strip(),
                                row[2].strip() if len(row) > 2 else '',
                                row[3].strip() if len(row) > 3 else '',
                                row[4].strip() if len(row) > 4 else '',
                                row[5].strip() if len(row) > 5 else '',
                                row[6].strip() if len(row) > 6 else '',
                                row[7].strip() if len(row) > 7 else '',
                                row[8].strip() if len(row) > 8 else '',
                                row[9].strip() if len(row) > 9 else '',
                                row[10].strip() if len(row) > 10 else ''
                            ))
                            count += 1
                        except sqlite3.IntegrityError:
                            pass

            conn.commit()
            conn.close()
            messagebox.showinfo("Succès", f"{count} modèle(s) importé(s) avec succès !")
            self.load_catalog_data()
        except Exception as e:
            messagebox.showerror("Erreur Importation", f"Erreur lors de la lecture du fichier :\n{e}")

    def refresh_all_data(self):
        self.search_var.set("")
        self.load_catalog_data()
        self.refresh_work_tree()
        if self.user['role'] == 'ADMIN':
            self.load_history_data()

    def load_catalog_data(self):
        for row in self.tree_cat.get_children():
            self.tree_cat.delete(row)

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT id, model_name, program_name, block_dim, qty_per_block, z_between_boards, tools, caisson, plaque_gamma, plaque_beta, remarks FROM models_catalog")
        self.catalog_rows = cursor.fetchall()
        conn.close()

        self.filter_data()
        autofit_treeview_columns(self.tree_cat, self.cat_cols)

    def load_history_data(self):
        for r in self.tree_hist.get_children():
            self.tree_hist.delete(r)

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT id, operator_username, model_name, program_name, block_dim, block_num, pain_num, block_date, block_density, timestamp FROM machining_history ORDER BY id DESC")
        self.history_rows = cursor.fetchall()
        conn.close()

        self.filter_data()
        autofit_treeview_columns(self.tree_hist, self.hist_cols)

    def check_match(self, query_str, cell_value):
        """Recherche souple prenant en compte les zéros au début (ex: '0', '012') et les sous-chaînes."""
        if not query_str:
            return True
        q = str(query_str).strip().lower()
        c = str(cell_value).strip().lower()
        return q in c

    def filter_data(self):
        query = self.search_var.get().strip()
        selected_col_name = self.cmb_search_col.get()

        if self.current_tab_key == "catalog":
            tree = self.tree_cat
            col_map = self.search_maps["catalog"]
            col_idx = col_map.get(selected_col_name, 0)

            for item in tree.get_children():
                tree.delete(item)

            selected_models = [w["model"] for w in self.work_list]

            if hasattr(self, 'catalog_rows'):
                for r in self.catalog_rows:
                    db_id = r[0]
                    display_values = r[1:]
                    cell_val = str(display_values[col_idx]) if len(display_values) > col_idx and display_values[col_idx] is not None else ""

                    if self.check_match(query, cell_val):
                        model_name = display_values[0]
                        tags = ('already_selected',) if model_name in selected_models else ()
                        tree.insert("", tk.END, iid=str(db_id), values=display_values, tags=tags)

        elif self.current_tab_key == "work":
            self.refresh_work_tree()

        elif self.current_tab_key == "history" and self.user['role'] == 'ADMIN':
            tree = self.tree_hist
            col_map = self.search_maps["history"]
            col_idx = col_map.get(selected_col_name, 1)

            for item in tree.get_children():
                tree.delete(item)

            if hasattr(self, 'history_rows'):
                for row in self.history_rows:
                    cell_val = str(row[col_idx]) if len(row) > col_idx and row[col_idx] is not None else ""

                    if self.check_match(query, cell_val):
                        # FOND ROUGE si information manquante
                        block_val = str(row[5]).strip().upper() if len(row) > 5 else ""
                        pain_val = str(row[6]).strip().upper() if len(row) > 6 else ""

                        is_missing = ("NON" in block_val or not block_val) or ("NON" in pain_val or not pain_val)
                        tags = ('missing_info',) if is_missing else ()
                        tree.insert("", tk.END, values=row, tags=tags)

    def add_selected_to_worklist(self):
        selected = self.tree_cat.selection()
        if not selected:
            return

        added_count = 0
        for item_id in selected:
            vals = self.tree_cat.item(item_id, "values")
            work_item = {
                "model": vals[0],
                "program": vals[1],
                "block_dim": vals[2],
                "tools": vals[5],
                "remarks": vals[9],
                "block_num": "",
                "pain_num": "",
                "block_date": "",
                "block_density": ""
            }
            self.work_list.append(work_item)
            added_count += 1

        self.save_worklist_to_db()
        self.load_catalog_data()
        self.refresh_work_tree()
        self.statusbar.config(text=f" {added_count} modèle(s) ajouté(s) à la liste de fabrication.")

    def refresh_work_tree(self):
        for r in self.tree_work.get_children():
            self.tree_work.delete(r)

        query = self.search_var.get().strip() if self.current_tab_key == "work" else ""
        selected_col_name = self.cmb_search_col.get() if self.current_tab_key == "work" else ""
        col_map = self.search_maps["work"]
        col_idx = col_map.get(selected_col_name, 1)

        for idx, item in enumerate(self.work_list):
            prio = f"P{idx + 1}"
            vals = (
                prio,
                item["model"],
                item["program"],
                item["block_dim"],
                item["block_num"] if item["block_num"] else "NON RENSEIGNÉ",
                item["pain_num"] if item.get("pain_num") else "NON RENSEIGNÉ",
                item["tools"],
                item["remarks"],
                item["block_date"],
                item["block_density"]
            )

            cell_val = str(vals[col_idx]) if len(vals) > col_idx and vals[col_idx] is not None else ""

            if self.check_match(query, cell_val):
                # FOND ROUGE si information manquante
                is_missing = (not item["block_num"]) or (not item.get("pain_num")) or (item["block_num"] == "NON RENSEIGNÉ") or (item.get("pain_num") == "NON RENSEIGNÉ")
                tags = ('missing_info',) if is_missing else ()
                self.tree_work.insert("", tk.END, iid=str(idx), values=vals, tags=tags)

        autofit_treeview_columns(self.tree_work, self.work_cols)

    def move_work_item_up(self):
        selected = self.tree_work.selection()
        if not selected:
            return
        idx = int(selected[0])
        if idx > 0:
            self.work_list[idx], self.work_list[idx - 1] = self.work_list[idx - 1], self.work_list[idx]
            self.save_worklist_to_db()
            self.refresh_work_tree()
            self.tree_work.selection_set(str(idx - 1))

    def move_work_item_down(self):
        selected = self.tree_work.selection()
        if not selected:
            return
        idx = int(selected[0])
        if idx < len(self.work_list) - 1:
            self.work_list[idx], self.work_list[idx + 1] = self.work_list[idx + 1], self.work_list[idx]
            self.save_worklist_to_db()
            self.refresh_work_tree()
            self.tree_work.selection_set(str(idx + 1))

    def remove_from_worklist(self):
        selected = self.tree_work.selection()
        if not selected:
            messagebox.showwarning("Attention", "Sélectionnez une ligne à retirer.")
            return

        idx = int(selected[0])
        del self.work_list[idx]
        self.save_worklist_to_db()
        self.load_catalog_data()
        self.refresh_work_tree()

    def edit_block_info(self):
        selected = self.tree_work.selection()
        if not selected:
            messagebox.showwarning("Attention", "Veuillez sélectionner un modèle dans la liste du jour.")
            return

        idx = int(selected[0])
        item = self.work_list[idx]

        dlg = tk.Toplevel(self.root)
        dlg.title(f"Saisie Bloc & Pain : {item['model']}")
        dlg.geometry("420x350")
        dlg.resizable(False, False)
        dlg.grab_set()

        ttk.Label(dlg, text=f"Informations Bloc pour {item['model']}", font=("Arial", 10, "bold")).pack(pady=10)

        frame = ttk.Frame(dlg, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="Dimension Bloc :").grid(row=0, column=0, sticky=tk.W, pady=5)
        ent_dim = ttk.Entry(frame)
        ent_dim.insert(0, item["block_dim"])
        ent_dim.grid(row=0, column=1, sticky=tk.EW, pady=5)

        ttk.Label(frame, text="N° / ID Bloc * :").grid(row=1, column=0, sticky=tk.W, pady=5)
        ent_num = ttk.Entry(frame)
        ent_num.insert(0, item["block_num"])
        ent_num.grid(row=1, column=1, sticky=tk.EW, pady=5)

        ttk.Label(frame, text="N° Pain (Polystyrène) * :").grid(row=2, column=0, sticky=tk.W, pady=5)
        ent_pain = ttk.Entry(frame)
        ent_pain.insert(0, item.get("pain_num", ""))
        ent_pain.grid(row=2, column=1, sticky=tk.EW, pady=5)

        ttk.Label(frame, text="Date Réception :").grid(row=3, column=0, sticky=tk.W, pady=5)
        ent_date = ttk.Entry(frame)
        ent_date.insert(0, item["block_date"] or datetime.now().strftime("%Y-%m-%d"))
        ent_date.grid(row=3, column=1, sticky=tk.EW, pady=5)

        ttk.Label(frame, text="Densité (kg/m³) :").grid(row=4, column=0, sticky=tk.W, pady=5)
        ent_density = ttk.Entry(frame)
        ent_density.insert(0, item["block_density"])
        ent_density.grid(row=4, column=1, sticky=tk.EW, pady=5)

        def save_info():
            item["block_dim"] = ent_dim.get().strip()
            item["block_num"] = ent_num.get().strip()
            item["pain_num"] = ent_pain.get().strip()
            item["block_date"] = ent_date.get().strip()
            item["block_density"] = ent_density.get().strip()
            self.save_worklist_to_db()
            self.refresh_work_tree()
            dlg.destroy()

        btn_box = ttk.Frame(dlg, padding=10)
        btn_box.pack(fill=tk.X)
        ttk.Button(btn_box, text="Valider", command=save_info).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_box, text="Plus tard", command=dlg.destroy).pack(side=tk.RIGHT, padx=5)

    def save_worklist_to_db(self):
        try:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM current_worklist")
            for idx, item in enumerate(self.work_list):
                cursor.execute('''
                    INSERT INTO current_worklist (prio, model, program, block_dim, tools, remarks, block_num, pain_num, block_date, block_density)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    idx + 1, item["model"], item["program"], item["block_dim"],
                    item["tools"], item["remarks"], item["block_num"],
                    item.get("pain_num", ""), item["block_date"], item["block_density"]
                ))
            conn.commit()
            conn.close()
            now_str = datetime.now().strftime("%H:%M:%S")
            self.statusbar.config(text=f" Liste sauvegardée en base de données à {now_str}.")
        except Exception as e:
            self.statusbar.config(text=f" Erreur lors de la sauvegarde : {e}")

    def load_saved_worklist(self):
        try:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("SELECT model, program, block_dim, tools, remarks, block_num, pain_num, block_date, block_density FROM current_worklist ORDER BY prio ASC")
            rows = cursor.fetchall()
            conn.close()

            self.work_list = []
            for r in rows:
                self.work_list.append({
                    "model": r[0],
                    "program": r[1],
                    "block_dim": r[2],
                    "tools": r[3],
                    "remarks": r[4],
                    "block_num": r[5],
                    "pain_num": r[6],
                    "block_date": r[7],
                    "block_density": r[8]
                })
        except Exception:
            self.work_list = []

    def start_auto_save_thread(self):
        def auto_save_loop():
            while self.is_running:
                time.sleep(300)
                if self.is_running:
                    self.save_worklist_to_db()

        t = threading.Thread(target=auto_save_loop, daemon=True)
        t.start()

    def validate_worklist(self):
        if not self.work_list:
            messagebox.showwarning("Attention", "Votre liste du jour est vide !")
            return

        missing = [item["model"] for item in self.work_list if not item["block_num"] or not item.get("pain_num")]

        msg = f"Voulez-vous valider et enregistrer l'usinage de ces {len(self.work_list)} modèle(s) ?"
        if missing:
            msg += f"\n\nAttention : {len(missing)} modèle(s) ont des données manquantes (N° Bloc / N° Pain sur fond rouge)."

        if not messagebox.askyesno("Confirmation", msg):
            return

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        for item in self.work_list:
            cursor.execute('''
                INSERT INTO machining_history (operator_username, model_name, program_name, block_dim, block_num, pain_num, block_date, block_density)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                self.user["username"],
                item["model"],
                item["program"],
                item["block_dim"],
                item["block_num"] if item["block_num"] else "NON RENSEIGNÉ",
                item.get("pain_num") if item.get("pain_num") else "NON RENSEIGNÉ",
                item["block_date"],
                item["block_density"]
            ))

        conn.commit()
        conn.close()

        messagebox.showinfo("Succès", "Usinage du jour validé et archivé dans l'historique de traçabilité !")
        if self.user['role'] == 'ADMIN':
            self.load_history_data()

    def on_app_close(self):
        self.is_running = False
        self.save_worklist_to_db()

        missing_count = sum(1 for item in self.work_list if not item["block_num"] or not item.get("pain_num"))
        if missing_count > 0:
            resp = messagebox.askyesno(
                "Données Incomplètes",
                f"Attention : Vous avez {missing_count} modèle(s) dans votre liste avec des informations non renseignées (sur fond rouge).\n\n"
                "Voulez-vous vraiment quitter ?"
            )
            if not resp:
                return
        self.root.destroy()


def main():
    init_db()

    root = tk.Tk()
    root.withdraw()

    login_dlg = LoginDialog(root)
    root.wait_window(login_dlg)

    if login_dlg.user_data:
        root.deiconify()
        app = CNCManagerApp(root, login_dlg.user_data)
        root.mainloop()


if __name__ == "__main__":
    main()
