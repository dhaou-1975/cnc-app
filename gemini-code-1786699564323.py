import os
import sys
import csv
import re
import sqlite3
import subprocess
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, font

APP_NAME = "CNC Manager - Ateliers Windsurf"
APP_VERSION = "v3.6.0"
DB_FILE = "cnc_factory.db"


def init_db():
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
        CREATE TABLE IF NOT EXISTS machining_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            operator_username TEXT NOT NULL,
            model_name TEXT NOT NULL,
            program_name TEXT NOT NULL,
            block_dim TEXT DEFAULT '',
            block_num TEXT NOT NULL,
            block_date TEXT NOT NULL,
            block_density TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    try:
        cursor.execute("ALTER TABLE machining_history ADD COLUMN block_dim TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass

    conn.commit()
    conn.close()


def get_user_count():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    count = cursor.fetchone()[0]
    conn.close()
    return count


def match_wildcard(pattern, text):
    """Recherche souple : si * est saisi, gère les jokers, sinon cherche le texte brut."""
    if not pattern or pattern.strip() == "":
        return True
    
    text = str(text) if text is not None else ""
    pattern = pattern.strip()
    
    if '*' in pattern:
        # Remplace * par .* pour le regex, mais gère correctement *1 (contient 1)
        cleaned_pattern = pattern.strip('*')
        if cleaned_pattern:
            return cleaned_pattern.lower() in text.lower()
        return True
    else:
        return pattern.lower() in text.lower()


def autofit_treeview_columns(tree, columns_dict):
    """Ajuste automatiquement la largeur des colonnes en fonction du contenu."""
    default_font = font.Font()
    for col_id, col_title in columns_dict.items():
        max_len = default_font.measure(col_title) + 20
        for item in tree.get_children():
            cell_val = str(tree.set(item, col_id))
            val_len = default_font.measure(cell_val) + 20
            if val_len > max_len:
                max_len = val_len
        tree.column(col_id, width=max(max_len, 80))


class LoginDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Authentification")
        self.geometry("380x230")
        self.resizable(False, False)
        self.grab_set()

        self.user_data = None

        ttk.Label(self, text="Connexion Atelier CNC", font=("Arial", 14, "bold")).pack(pady=10)

        frame = ttk.Frame(self, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="Nom d'utilisateur :").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.ent_user = ttk.Entry(frame)
        self.ent_user.grid(row=0, column=1, sticky=tk.EW, pady=5)
        self.ent_user.focus()

        ttk.Label(frame, text="Mot de passe :").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.ent_pass = ttk.Entry(frame, show="*")
        self.ent_pass.grid(row=1, column=1, sticky=tk.EW, pady=5)

        btn_box = ttk.Frame(self, padding=10)
        btn_box.pack(fill=tk.X)
        ttk.Button(btn_box, text="Se Connecter", command=self.check_login).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_box, text="Quitter", command=self.master.destroy).pack(side=tk.RIGHT)

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

        if not messagebox.askyesno("Confirmation", f"Voulez-vous vraiment enregistrer le modèle '{m_name}' ?"):
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


class DeleteModelDialog(tk.Toplevel):
    def __init__(self, parent, main_app):
        super().__init__(parent)
        self.main_app = main_app
        self.title("Supprimer des Modèles")
        self.geometry("850x500")
        self.grab_set()

        ttk.Label(self, text="Recherche & Suppression de Modèles", font=("Arial", 12, "bold")).pack(pady=5)

        search_frame = ttk.Frame(self, padding=5)
        search_frame.pack(fill=tk.X)

        ttk.Label(search_frame, text="Rechercher :", font=("Arial", 9, "bold")).pack(side=tk.LEFT, padx=5)
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *args: self.filter_delete_list())
        ttk.Entry(search_frame, textvariable=self.search_var, width=30).pack(side=tk.LEFT, padx=5)

        ttk.Label(search_frame, text="Dans :").pack(side=tk.LEFT, padx=5)
        self.cmb_col = ttk.Combobox(search_frame, values=["Nom Modèle", "Programme Pain"], state="readonly", width=18)
        self.cmb_col.set("Nom Modèle")
        self.cmb_col.pack(side=tk.LEFT, padx=5)
        self.cmb_col.bind("<<ComboboxSelected>>", lambda e: self.filter_delete_list())

        tree_frame = ttk.Frame(self, padding=5)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        columns = ("id", "model", "program", "dim_block", "tools")
        self.tree_del = ttk.Treeview(tree_frame, columns=columns, show="headings", selectmode="extended")

        self.tree_del.heading("id", text="ID")
        self.tree_del.heading("model", text="Nom Modèle")
        self.tree_del.heading("program", text="Programme")
        self.tree_del.heading("dim_block", text="Dim. Bloc")
        self.tree_del.heading("tools", text="Outils")

        vsb = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree_del.yview)
        hsb = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL, command=self.tree_del.xview)
        self.tree_del.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree_del.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        hsb.pack(side=tk.BOTTOM, fill=tk.X)

        btn_box = ttk.Frame(self, padding=10)
        btn_box.pack(fill=tk.X)
        ttk.Button(btn_box, text="- Supprimer la sélection", command=self.delete_selected).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_box, text="Fermer", command=self.destroy).pack(side=tk.RIGHT)

        self.load_data()

    def load_data(self):
        for r in self.tree_del.get_children():
            self.tree_del.delete(r)

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT id, model_name, program_name, block_dim, tools FROM models_catalog")
        for row in cursor.fetchall():
            self.tree_del.insert("", tk.END, values=row)
        conn.close()

    def filter_delete_list(self):
        query = self.search_var.get().strip()
        col_idx = 1 if self.cmb_col.get() == "Nom Modèle" else 2

        for item in self.tree_del.get_children():
            vals = self.tree_del.item(item, "values")
            cell_val = str(vals[col_idx]) if len(vals) > col_idx else ""

            if match_wildcard(query, cell_val):
                self.tree_del.reattach(item, "", tk.END)
            else:
                self.tree_del.detach(item)

    def delete_selected(self):
        selected = self.tree_del.selection()
        if not selected:
            messagebox.showwarning("Attention", "Veuillez sélectionner au moins un modèle à supprimer.")
            return

        models_to_del = [self.tree_del.item(s, "values") for s in selected]
        names = ", ".join([m[1] for m in models_to_del])

        if not messagebox.askyesno("Confirmation", f"Voulez-vous vraiment supprimer définitivement ces {len(models_to_del)} modèle(s) ?\n\n({names})"):
            return

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        for m in models_to_del:
            cursor.execute("DELETE FROM models_catalog WHERE id=?", (m[0],))
        conn.commit()
        conn.close()

        messagebox.showinfo("Succès", "Modèle(s) supprimé(s) du catalogue.")
        self.load_data()
        self.main_app.load_catalog_data()


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
        ttk.Button(frame_actions, text="Modifier", command=self.edit_user).pack(fill=tk.X, pady=5)
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

        ttk.Button(frame_form, text="+ Ajouter", command=self.add_user).grid(row=0, column=6, padx=5)

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

    def add_user(self):
        u = self.ent_u.get().strip()
        p = self.ent_p.get().strip()
        r = self.cmb_r.get()

        if not u or not p:
            messagebox.showwarning("Erreur", "Saisissez un nom d'utilisateur et un mot de passe.")
            return

        if not messagebox.askyesno("Confirmation", f"Voulez-vous créer le compte utilisateur '{u}' ?"):
            return

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        try:
            cursor.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", (u, p, r))
            conn.commit()
            messagebox.showinfo("Succès", f"Compte '{u}' créé.")
            self.load_users()
            self.ent_u.delete(0, tk.END)
            self.ent_p.delete(0, tk.END)
        except sqlite3.IntegrityError:
            messagebox.showerror("Erreur", "Ce nom d'utilisateur existe déjà.")
        finally:
            conn.close()

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
            messagebox.showinfo("Succès", "Utilisateur supprimé.")

    def edit_user(self):
        selected = self.tree_users.selection()
        if not selected:
            messagebox.showwarning("Attention", "Sélectionnez un utilisateur à modifier.")
            return

        user_id, username, current_role = self.tree_users.item(selected[0], "values")

        dlg = tk.Toplevel(self)
        dlg.title(f"Modifier {username}")
        dlg.geometry("320x200")
        dlg.grab_set()

        ttk.Label(dlg, text=f"Modification de : {username}", font=("Arial", 10, "bold")).pack(pady=10)

        frame = ttk.Frame(dlg, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="Nouveau M.Passe :").grid(row=0, column=0, sticky=tk.W, pady=2)
        ent_new_p = ttk.Entry(frame, show="*")
        ent_new_p.grid(row=1, column=0, sticky=tk.EW, pady=5)

        ttk.Label(frame, text="Rôle :").grid(row=2, column=0, sticky=tk.W, pady=2)
        cmb_new_r = ttk.Combobox(frame, values=["OPERATEUR", "ADMIN"], state="readonly")
        cmb_new_r.set(current_role)
        cmb_new_r.grid(row=3, column=0, sticky=tk.EW, pady=5)

        def save_edits():
            if not messagebox.askyesno("Confirmation", f"Voulez-vous enregistrer les modifications pour '{username}' ?"):
                return

            new_pwd = ent_new_p.get().strip()
            new_role = cmb_new_r.get()

            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()

            if new_pwd:
                cursor.execute("UPDATE users SET password=?, role=? WHERE id=?", (new_pwd, new_role, user_id))
            else:
                cursor.execute("UPDATE users SET role=? WHERE id=?", (new_role, user_id))

            conn.commit()
            conn.close()
            dlg.destroy()
            self.load_users()
            messagebox.showinfo("Succès", "Modifications enregistrées.")

        ttk.Button(dlg, text="Enregistrer", command=save_edits).pack(pady=10)


class CNCManagerApp:
    def __init__(self, root, current_user):
        self.root = root
        self.user = current_user
        self.root.title(f"{APP_NAME} - Connecté : {self.user['username']} [{self.user['role']}]")
        self.root.geometry("1280x780")

        self.red_flagged_items = set()
        self.work_list = []

        self._create_menu()
        self._create_header()
        self._create_toolbar()
        self._create_notebook()
        self._create_statusbar()

        self.load_catalog_data()

    def _create_menu(self):
        menubar = tk.Menu(self.root)

        file_menu = tk.Menu(menubar, tearoff=0)
        if self.user['role'] == 'ADMIN':
            file_menu.add_command(label="Importer Fichier CSV...", command=self.import_csv)
        file_menu.add_command(label="Actualiser", command=self.load_catalog_data)
        file_menu.add_separator()
        file_menu.add_command(label="Quitter", command=self.root.quit)
        menubar.add_cascade(label="Fichier", menu=file_menu)

        tools_menu = tk.Menu(menubar, tearoff=0)
        tools_menu.add_command(label="+ Ajouter un Modèle", command=lambda: AddModelDialog(self.root, self))
        tools_menu.add_command(label="- Supprimer un Modèle", command=lambda: DeleteModelDialog(self.root, self))
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

        ttk.Button(toolbar, text="Actualiser", command=self.load_catalog_data).pack(side=tk.LEFT, padx=5)

        ttk.Label(toolbar, text="Rechercher :", font=("Arial", 9, "bold")).pack(side=tk.LEFT, padx=(20, 5))

        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *args: self.filter_data())
        ttk.Entry(toolbar, textvariable=self.search_var, width=25).pack(side=tk.LEFT, padx=5)

        ttk.Label(toolbar, text="Dans :").pack(side=tk.LEFT, padx=(10, 5))

        self.search_col_map = {
            "Nom Modèle": 0,
            "Programme Pain": 1,
            "Dim. Bloc": 2,
            "Outils": 5,
            "Remarques": 9
        }

        self.cmb_search_col = ttk.Combobox(toolbar, values=list(self.search_col_map.keys()), state="readonly", width=18)
        self.cmb_search_col.set("Nom Modèle")
        self.cmb_search_col.pack(side=tk.LEFT, padx=5)
        self.cmb_search_col.bind("<<ComboboxSelected>>", lambda e: self.filter_data())

    def _create_notebook(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.tab_catalog = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_catalog, text="Catalogue Modèles")
        self._setup_catalog_tree(self.tab_catalog)

        self.tab_work = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_work, text="Ordre de Fabrication (Mon Travail du Jour)")
        self._setup_work_tree(self.tab_work)

        if self.user['role'] == 'ADMIN':
            self.tab_history = ttk.Frame(self.notebook)
            self.notebook.add(self.tab_history, text="Historique Usinages (Admin)")
            self._setup_history_tree(self.tab_history)

    def _setup_catalog_tree(self, parent):
        frame = ttk.Frame(parent, padding=5)
        frame.pack(fill=tk.BOTH, expand=True)

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

        self.tree_cat = ttk.Treeview(frame, columns=tuple(self.cat_cols.keys()), show="headings", selectmode="extended")

        for col, text in self.cat_cols.items():
            self.tree_cat.heading(col, text=text)

        self.tree_cat.tag_configure('red_flag', background='#ff7675', foreground='white')

        vsb = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self.tree_cat.yview)
        hsb = ttk.Scrollbar(frame, orient=tk.HORIZONTAL, command=self.tree_cat.xview)
        self.tree_cat.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree_cat.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        hsb.pack(side=tk.BOTTOM, fill=tk.X)

        self.tree_cat.bind("<Button-3>", self.show_context_menu)
        self.tree_cat.bind("<Double-1>", lambda e: self.add_selected_to_worklist())

        btn_bar = ttk.Frame(parent, padding=5)
        btn_bar.pack(fill=tk.X)
        ttk.Button(btn_bar, text="+ Ajouter les modèles sélectionnés à ma Liste du Jour", command=self.add_selected_to_worklist).pack(side=tk.RIGHT)

    def _setup_work_tree(self, parent):
        frame = ttk.Frame(parent, padding=5)
        frame.pack(fill=tk.BOTH, expand=True)

        self.work_cols = {
            "model": "Nom du Modèle",
            "program": "Programme Pain",
            "block_dim": "Dimension Bloc",
            "block_num": "N° du Bloc Matière",
            "block_date": "Date Réception",
            "block_density": "Densité (kg/m³)"
        }

        self.tree_work = ttk.Treeview(frame, columns=tuple(self.work_cols.keys()), show="headings", selectmode="browse")

        for col, text in self.work_cols.items():
            self.tree_work.heading(col, text=text)

        vsb = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self.tree_work.yview)
        hsb = ttk.Scrollbar(frame, orient=tk.HORIZONTAL, command=self.tree_work.xview)
        self.tree_work.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree_work.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        hsb.pack(side=tk.BOTTOM, fill=tk.X)

        btn_bar = ttk.Frame(parent, padding=10)
        btn_bar.pack(fill=tk.X)

        ttk.Button(btn_bar, text="Renseigner Infos Bloc Matière", command=self.edit_block_info).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_bar, text="- Retirer de la liste du jour", command=self.remove_from_worklist).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_bar, text="Valider & Enregistrer Usinage du Jour", command=self.validate_worklist).pack(side=tk.RIGHT, padx=5)

    def _setup_history_tree(self, parent):
        filter_frame = ttk.Frame(parent, padding=5)
        filter_frame.pack(fill=tk.X)

        ttk.Label(filter_frame, text="Filtrer Historique :", font=("Arial", 9, "bold")).pack(side=tk.LEFT, padx=5)
        self.hist_filter_var = tk.StringVar()
        self.hist_filter_var.trace_add("write", lambda *args: self.filter_history_data())
        ttk.Entry(filter_frame, textvariable=self.hist_filter_var, width=30).pack(side=tk.LEFT, padx=5)

        frame = ttk.Frame(parent, padding=5)
        frame.pack(fill=tk.BOTH, expand=True)

        self.hist_cols = {
            "id": "N°",
            "op": "Opérateur",
            "model": "Modèle",
            "program": "Programme",
            "dim_block": "Dim. Bloc",
            "block": "N° Bloc",
            "date": "Date Bloc",
            "density": "Densité",
            "timestamp": "Validation"
        }

        self.tree_hist = ttk.Treeview(frame, columns=tuple(self.hist_cols.keys()), show="headings")

        for col, text in self.hist_cols.items():
            self.tree_hist.heading(col, text=text)

        vsb = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self.tree_hist.yview)
        hsb = ttk.Scrollbar(frame, orient=tk.HORIZONTAL, command=self.tree_hist.xview)
        self.tree_hist.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree_hist.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        hsb.pack(side=tk.BOTTOM, fill=tk.X)

    def _create_statusbar(self):
        self.statusbar = ttk.Label(self.root, text=" Prêt.", relief=tk.SUNKEN, anchor=tk.W)
        self.statusbar.pack(side=tk.BOTTOM, fill=tk.X)

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

    def load_catalog_data(self):
        for row in self.tree_cat.get_children():
            self.tree_cat.delete(row)

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT id, model_name, program_name, block_dim, qty_per_block, z_between_boards, tools, caisson, plaque_gamma, plaque_beta, remarks FROM models_catalog")
        rows = cursor.fetchall()
        conn.close()

        for r in rows:
            db_id = r[0]
            display_values = r[1:]
            item_id = self.tree_cat.insert("", tk.END, values=display_values, tags=(str(db_id),))
            if db_id in self.red_flagged_items:
                self.tree_cat.item(item_id, tags=(str(db_id), 'red_flag'))

        autofit_treeview_columns(self.tree_cat, self.cat_cols)

        if self.user['role'] == 'ADMIN':
            self.load_history_data()

        self.filter_data()
        self.statusbar.config(text=f" {len(rows)} modèle(s) présent(s) dans le catalogue.")

    def load_history_data(self):
        if self.user['role'] != 'ADMIN':
            return

        for row in self.tree_hist.get_children():
            self.tree_hist.delete(row)

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT id, operator_username, model_name, program_name, block_dim, block_num, block_date, block_density, timestamp FROM machining_history ORDER BY id DESC")
        for r in cursor.fetchall():
            self.tree_hist.insert("", tk.END, values=r)
        conn.close()

        autofit_treeview_columns(self.tree_hist, self.hist_cols)
        self.filter_history_data()

    def filter_data(self):
        """Filtrage instantané du catalogue : réaffiche tout dès que le champ est vide."""
        query = self.search_var.get().strip()
        selected_col_name = self.cmb_search_col.get()
        col_idx = self.search_col_map.get(selected_col_name, 0)

        for item in self.tree_cat.get_children():
            vals = self.tree_cat.item(item, "values")
            cell_value = str(vals[col_idx]) if len(vals) > col_idx else ""

            if not query or match_wildcard(query, cell_value):
                self.tree_cat.reattach(item, "", tk.END)
            else:
                self.tree_cat.detach(item)

    def filter_history_data(self):
        if self.user['role'] != 'ADMIN':
            return

        query = self.hist_filter_var.get().strip()

        for item in self.tree_hist.get_children():
            vals = self.tree_hist.item(item, "values")
            op_match = match_wildcard(query, str(vals[1]))
            model_match = match_wildcard(query, str(vals[2]))
            date_match = match_wildcard(query, str(vals[6]))

            if not query or op_match or model_match or date_match:
                self.tree_hist.reattach(item, "", tk.END)
            else:
                self.tree_hist.detach(item)

    def show_context_menu(self, event):
        item = self.tree_cat.identify_row(event.y)
        if not item:
            return
        self.tree_cat.selection_set(item)

        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="Marquer / Démarquer en Rouge", command=lambda: self.toggle_red_flag(item))
        menu.add_command(label="Ouvrir le fichier programme", command=lambda: self.open_program_notepad(item))
        menu.post(event.x_root, event.y_root)

    def toggle_red_flag(self, item):
        tags = self.tree_cat.item(item, "tags")
        db_id = int(tags[0])

        if db_id in self.red_flagged_items:
            self.red_flagged_items.remove(db_id)
            self.tree_cat.item(item, tags=(str(db_id),))
        else:
            self.red_flagged_items.add(db_id)
            self.tree_cat.item(item, tags=(str(db_id), 'red_flag'))

    def open_program_notepad(self, item):
        vals = self.tree_cat.item(item, "values")
        prog_name = vals[1]
        if sys.platform == "win32":
            try:
                subprocess.Popen(["notepad.exe", f"{prog_name}.txt"])
            except Exception:
                messagebox.showinfo("Programme", f"Programme sélectionné : {prog_name}")
        else:
            messagebox.showinfo("Programme", f"Programme sélectionné : {prog_name}")

    def add_selected_to_worklist(self):
        selected = self.tree_cat.selection()
        if not selected:
            messagebox.showwarning("Attention", "Veuillez sélectionner au moins un modèle.")
            return

        for s in selected:
            vals = self.tree_cat.item(s, "values")
            item_data = {
                "model": vals[0],
                "program": vals[1],
                "block_dim": vals[2],
                "block_num": "Saisir...",
                "block_date": datetime.today().strftime('%Y-%m-%d'),
                "block_density": "28"
            }
            self.work_list.append(item_data)

        self.refresh_work_tree()
        self.notebook.select(self.tab_work)

    def refresh_work_tree(self):
        for row in self.tree_work.get_children():
            self.tree_work.delete(row)
        for item in self.work_list:
            self.tree_work.insert("", tk.END, values=(
                item["model"], item["program"], item["block_dim"], item["block_num"], item["block_date"], item["block_density"]
            ))
        autofit_treeview_columns(self.tree_work, self.work_cols)

    def edit_block_info(self):
        selected = self.tree_work.selection()
        if not selected:
            messagebox.showwarning("Attention", "Sélectionnez un modèle dans votre liste de travail.")
            return

        idx = self.tree_work.index(selected[0])
        item = self.work_list[idx]

        dlg = tk.Toplevel(self.root)
        dlg.title("Fiche Bloc Matière")
        dlg.geometry("350x250")

        ttk.Label(dlg, text="N° du Bloc Matière :").pack(pady=2)
        ent_num = ttk.Entry(dlg)
        ent_num.insert(0, item["block_num"])
        ent_num.pack(pady=2)

        ttk.Label(dlg, text="Date Réception Bloc :").pack(pady=2)
        ent_date = ttk.Entry(dlg)
        ent_date.insert(0, item["block_date"])
        ent_date.pack(pady=2)

        ttk.Label(dlg, text="Densité du Bloc (kg/m³) :").pack(pady=2)
        ent_dens = ttk.Entry(dlg)
        ent_dens.insert(0, item["block_density"])
        ent_dens.pack(pady=2)

        def save():
            item["block_num"] = ent_num.get()
            item["block_date"] = ent_date.get()
            item["block_density"] = ent_dens.get()
            self.refresh_work_tree()
            dlg.destroy()

        ttk.Button(dlg, text="Enregistrer", command=save).pack(pady=10)

    def remove_from_worklist(self):
        selected = self.tree_work.selection()
        if selected:
            idx = self.tree_work.index(selected[0])
            del self.work_list[idx]
            self.refresh_work_tree()

    def validate_worklist(self):
        if not self.work_list:
            messagebox.showwarning("Attention", "Votre liste de travail est vide.")
            return

        if not messagebox.askyesno("Enregistrement", "Voulez-vous valider et enregistrer cet ordre d'usinage dans l'historique ?"):
            return

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        for item in self.work_list:
            cursor.execute('''
                INSERT INTO machining_history (operator_username, model_name, program_name, block_dim, block_num, block_date, block_density)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (self.user['username'], item['model'], item['program'], item['block_dim'], item['block_num'], item['block_date'], item['block_density']))
        conn.commit()
        conn.close()

        messagebox.showinfo("Succès", "Ordre d'usinage du jour enregistré avec succès !")
        self.work_list.clear()
        self.refresh_work_tree()
        if self.user['role'] == 'ADMIN':
            self.load_history_data()


if __name__ == "__main__":
    init_db()

    root = tk.Tk()
    root.withdraw()

    user_count = get_user_count()

    if user_count == 0:
        messagebox.showinfo(
            "Premier Démarrage", 
            "Aucun utilisateur enregistré.\nLe logiciel s'ouvre en mode Administrateur.\nUtilisez le menu 'Administration' pour créer vos comptes."
        )
        current_user = {"username": "Admin Initial", "role": "ADMIN"}
    else:
        login = LoginDialog(root)
        root.wait_window(login)
        current_user = login.user_data

    if current_user:
        root.deiconify()
        app = CNCManagerApp(root, current_user)
        root.mainloop()
    else:
        sys.exit(0)
