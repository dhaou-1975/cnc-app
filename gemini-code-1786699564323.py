import sys
import os
import sqlite3
import multiprocessing
import tkinter as tk
from tkinter import ttk, messagebox

# Indispensable pour éviter les processus fantômes sous Windows 7 avec PyInstaller
if __name__ == '__main__':
    multiprocessing.freeze_support()

DB_FILE = "cnc_manager.db"

# --- INITIALISATION ET STRUCTURE COMPLÈTE DE LA BASE DE DONNÉES ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Table 1: Utilisateurs et Rôles
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL
        )
    ''')

    # Table 2: Catalogue des Modèles (Windsurf / E-Foil / Pièces)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS models_catalog (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            volume_l REAL,
            length_mm REAL,
            width_mm REAL,
            est_time_min INTEGER
        )
    ''')

    # Table 3: Historique d'Usinage & Suivi Atelier
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS machining_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            operator TEXT NOT NULL,
            machine TEXT NOT NULL,
            part_name TEXT NOT NULL,
            category TEXT NOT NULL,
            est_time_min INTEGER,
            status TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Table 4: Sauvegarde Liste de Travail
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS current_worklist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            part_name TEXT NOT NULL,
            machine TEXT NOT NULL,
            priority TEXT NOT NULL
        )
    ''')

    # Insertion des utilisateurs par défaut
    cursor.execute("SELECT COUNT(*) FROM users")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO users (username, password, role) VALUES ('admin', 'admin123', 'Admin')")
        cursor.execute("INSERT INTO users (username, password, role) VALUES ('operateur', 'op123', 'Operateur')")

    # Insertion du catalogue initial si vide
    cursor.execute("SELECT COUNT(*) FROM models_catalog")
    if cursor.fetchone()[0] == 0:
        initial_models = [
            ("WS-FREERIDE-115", "Flotteur Freeride 115L (Noyau EPS)", "Windsurf", 115.0, 2350.0, 680.0, 45),
            ("WS-WAVE-85", "Flotteur Wave 85L (Noyau EPS)", "Windsurf", 85.0, 2220.0, 580.0, 40),
            ("EFOIL-REC-PWR", "Receveur Boîtier PWR-Foil Composite", "E-Foil", 0.0, 450.0, 250.0, 30),
            ("EFOIL-BOARD-150", "Planche E-Foil Inflatable Core 150L", "E-Foil", 150.0, 1600.0, 710.0, 60),
            ("MOLD-FIN-CHINOOK", "Moule Insertion US Box Chinook", "Accessoires", 0.0, 300.0, 120.0, 25)
        ]
        cursor.executemany('''
            INSERT INTO models_catalog (code, name, category, volume_l, length_mm, width_mm, est_time_min)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', initial_models)

    conn.commit()
    conn.close()


class CNCApplication(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("CNC Program Manager & Time Estimator - Windsurf/E-Foil")
        self.geometry("400x250")

        # Centrage écran
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f'{width}x{height}+{x}+{y}')

        self.current_user = None
        self.show_login_screen()

    def clear_window(self):
        for widget in self.winfo_children():
            widget.destroy()

    # --- ÉCRAN DE CONNEXION ---
    def show_login_screen(self):
        self.clear_window()
        self.title("Connexion - CNC Manager")
        self.geometry("380x240")

        ttk.Label(self, text="CNC Manager - Atelier Composite", font=("Arial", 12, "bold")).pack(pady=15)

        frame = ttk.Frame(self)
        frame.pack(pady=5, padx=20)

        ttk.Label(frame, text="Utilisateur :").grid(row=0, column=0, sticky="w", pady=5, padx=5)
        self.entry_user = ttk.Entry(frame, width=20)
        self.entry_user.grid(row=0, column=1, pady=5, padx=5)
        self.entry_user.focus()

        ttk.Label(frame, text="Mot de passe :").grid(row=1, column=0, sticky="w", pady=5, padx=5)
        self.entry_pass = ttk.Entry(frame, show="*", width=20)
        self.entry_pass.grid(row=1, column=1, pady=5, padx=5)

        btn_frame = ttk.Frame(self)
        btn_frame.pack(pady=15)

        ttk.Button(btn_frame, text="Se connecter", command=self.check_login).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Quitter", command=self.destroy).pack(side="right", padx=5)

        self.bind('<Return>', lambda event: self.check_login())

    def check_login(self):
        user = self.entry_user.get().strip()
        pwd = self.entry_pass.get().strip()

        if not user or not pwd:
            messagebox.showwarning("Erreur", "Veuillez remplir tous les champs.", parent=self)
            return

        try:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("SELECT username, role FROM users WHERE username=? AND password=?", (user, pwd))
            row = cursor.fetchone()
            conn.close()

            if row:
                self.current_user = {"username": row[0], "role": row[1]}
                self.unbind('<Return>')
                self.show_main_screen()
            else:
                messagebox.showerror("Accès refusé", "Utilisateur ou mot de passe incorrect.", parent=self)
        except Exception as e:
            messagebox.showerror("Erreur Base de données", str(e), parent=self)

    # --- ÉCRAN PRINCIPAL COMPLET ---
    def show_main_screen(self):
        self.clear_window()
        self.title(f"CNC Manager - Session : {self.current_user['username']} ({self.current_user['role']})")
        self.geometry("1150x650")

        # Centrage
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - (1150 // 2)
        y = (self.winfo_screenheight() // 2) - (650 // 2)
        self.geometry(f'1150x650+{x}+{y}')

        # Barre de Menu
        menubar = tk.Menu(self)
        menu_file = tk.Menu(menubar, tearoff=0)
        menu_file.add_command(label="Déconnexion", command=self.show_login_screen)
        menu_file.add_separator()
        menu_file.add_command(label="Quitter", command=self.destroy)
        menubar.add_cascade(label="Fichier", menu=menu_file)

        if self.current_user['role'] == 'Admin':
            menu_admin = tk.Menu(menubar, tearoff=0)
            menu_admin.add_command(label="Gestion Catalogue / Utilisateurs", command=lambda: messagebox.showinfo("Admin", "Accès administration actif."))
            menubar.add_cascade(label="Administration", menu=menu_admin)

        self.config(menu=menubar)

        # Structure à onglets
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=10, pady=5)

        # Onglet 1: Suivi Atelier & Lancement
        tab_tracking = ttk.Frame(notebook)
        notebook.add(tab_tracking, text=" Suivi & Lancement Usinage ")
        self.setup_tracking_tab(tab_tracking)

        # Onglet 2: Catalogue Modèles (Windsurf / E-Foil)
        tab_catalog = ttk.Frame(notebook)
        notebook.add(tab_catalog, text=" Catalogue Modèles & Spécifications ")
        self.setup_catalog_tab(tab_catalog)

    # --- SUIVI ET LANCEMENT USINAGE ---
    def setup_tracking_tab(self, parent):
        # Formulaire
        frame_input = ttk.LabelFrame(parent, text=" Nouvel Usinage / Programme ")
        frame_input.pack(fill="x", padx=10, pady=5)

        ttk.Label(frame_input, text="Machine:").grid(row=0, column=0, padx=5, pady=5)
        self.combo_machine = ttk.Combobox(frame_input, values=["NUM 1060 (5-Axes)", "Fraiseuse 3-Axes EPS", "Tour CNC"], state="readonly", width=18)
        self.combo_machine.current(0)
        self.combo_machine.grid(row=0, column=1, padx=5, pady=5)

        ttk.Label(frame_input, text="Catégorie:").grid(row=0, column=2, padx=5, pady=5)
        self.combo_cat = ttk.Combobox(frame_input, values=["Windsurf", "E-Foil", "Accessoires / Moules"], state="readonly", width=18)
        self.combo_cat.current(0)
        self.combo_cat.grid(row=0, column=3, padx=5, pady=5)

        ttk.Label(frame_input, text="Pièce / Fichier:").grid(row=0, column=4, padx=5, pady=5)
        self.entry_part = ttk.Entry(frame_input, width=22)
        self.entry_part.grid(row=0, column=5, padx=5, pady=5)

        ttk.Label(frame_input, text="Temps Est. (min):").grid(row=0, column=6, padx=5, pady=5)
        self.entry_time = ttk.Entry(frame_input, width=8)
        self.entry_time.insert(0, "45")
        self.entry_time.grid(row=0, column=7, padx=5, pady=5)

        ttk.Label(frame_input, text="Statut:").grid(row=1, column=0, padx=5, pady=5)
        self.combo_status = ttk.Combobox(frame_input, values=["En cours", "Terminé", "En attente Material", "Maintenance"], state="readonly", width=18)
        self.combo_status.current(0)
        self.combo_status.grid(row=1, column=1, padx=5, pady=5)

        ttk.Button(frame_input, text="Enregistrer l'usinage", command=self.add_log).grid(row=1, column=5, columnspan=3, padx=10, pady=5, sticky="ew")

        # Filtre et recherche
        frame_filter = ttk.Frame(parent)
        frame_filter.pack(fill="x", padx=10, pady=2)
        ttk.Label(frame_filter, text="Rechercher / Filtrer :").pack(side="left", padx=5)
        self.entry_search = ttk.Entry(frame_filter, width=30)
        self.entry_search.pack(side="left", padx=5)
        self.entry_search.bind("<KeyRelease>", lambda e: self.load_tracking_data())

        # Tableau
        frame_table = ttk.Frame(parent)
        frame_table.pack(fill="both", expand=True, padx=10, pady=5)

        columns = ("id", "operator", "machine", "category", "part_name", "est_time_min", "status", "timestamp")
        self.tree_tracking = ttk.Treeview(frame_table, columns=columns, show="headings")

        self.tree_tracking.heading("id", text="ID")
        self.tree_tracking.heading("operator", text="Opérateur")
        self.tree_tracking.heading("machine", text="Machine")
        self.tree_tracking.heading("category", text="Catégorie")
        self.tree_tracking.heading("part_name", text="Pièce / Fichier NC")
        self.tree_tracking.heading("est_time_min", text="Tps (min)")
        self.tree_tracking.heading("status", text="Statut")
        self.tree_tracking.heading("timestamp", text="Date / Heure")

        self.tree_tracking.column("id", width=40, anchor="center")
        self.tree_tracking.column("operator", width=100)
        self.tree_tracking.column("machine", width=140)
        self.tree_tracking.column("category", width=120)
        self.tree_tracking.column("part_name", width=220)
        self.tree_tracking.column("est_time_min", width=70, anchor="center")
        self.tree_tracking.column("status", width=110)
        self.tree_tracking.column("timestamp", width=150, anchor="center")

        scrollbar = ttk.Scrollbar(frame_table, orient="vertical", command=self.tree_tracking.yview)
        self.tree_tracking.configure(yscrollcommand=scrollbar.set)

        self.tree_tracking.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.load_tracking_data()

    def load_tracking_data(self):
        for item in self.tree_tracking.get_children():
            self.tree_tracking.delete(item)

        search_query = self.entry_search.get().strip() if hasattr(self, 'entry_search') else ""

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        if search_query:
            cursor.execute('''
                SELECT id, operator, machine, category, part_name, est_time_min, status, timestamp 
                FROM machining_history 
                WHERE part_name LIKE ? OR operator LIKE ? OR machine LIKE ?
                ORDER BY id DESC
            ''', (f'%{search_query}%', f'%{search_query}%', f'%{search_query}%'))
        else:
            cursor.execute('''
                SELECT id, operator, machine, category, part_name, est_time_min, status, timestamp 
                FROM machining_history 
                ORDER BY id DESC
            ''')

        for row in cursor.fetchall():
            self.tree_tracking.insert("", "end", values=row)
        conn.close()

    def add_log(self):
        part = self.entry_part.get().strip()
        if not part:
            messagebox.showwarning("Attention", "Veuillez préciser le nom de la pièce.")
            return

        try:
            t_est = int(self.entry_time.get().strip())
        except ValueError:
            t_est = 0

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO machining_history (operator, machine, category, part_name, est_time_min, status) 
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (self.current_user['username'], self.combo_machine.get(), self.combo_cat.get(), part, t_est, self.combo_status.get()))
        conn.commit()
        conn.close()

        self.entry_part.delete(0, tk.END)
        self.load_tracking_data()

    # --- CATALOGUE MODÈLES ---
    def setup_catalog_tab(self, parent):
        frame_table = ttk.Frame(parent)
        frame_table.pack(fill="both", expand=True, padx=10, pady=10)

        columns = ("id", "code", "name", "category", "volume_l", "length_mm", "width_mm", "est_time_min")
        self.tree_catalog = ttk.Treeview(frame_table, columns=columns, show="headings")

        self.tree_catalog.heading("id", text="ID")
        self.tree_catalog.heading("code", text="Code Modèle")
        self.tree_catalog.heading("name", text="Description Modèle")
        self.tree_catalog.heading("category", text="Catégorie")
        self.tree_catalog.heading("volume_l", text="Vol. (L)")
        self.tree_catalog.heading("length_mm", text="Long. (mm)")
        self.tree_catalog.heading("width_mm", text="Larg. (mm)")
        self.tree_catalog.heading("est_time_min", text="Temps Est. (min)")

        self.tree_catalog.column("id", width=40, anchor="center")
        self.tree_catalog.column("code", width=120)
        self.tree_catalog.column("name", width=250)
        self.tree_catalog.column("category", width=110)
        self.tree_catalog.column("volume_l", width=70, anchor="center")
        self.tree_catalog.column("length_mm", width=80, anchor="center")
        self.tree_catalog.column("width_mm", width=80, anchor="center")
        self.tree_catalog.column("est_time_min", width=100, anchor="center")

        scrollbar = ttk.Scrollbar(frame_table, orient="vertical", command=self.tree_catalog.yview)
        self.tree_catalog.configure(yscrollcommand=scrollbar.set)

        self.tree_catalog.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.load_catalog_data()

    def load_catalog_data(self):
        for item in self.tree_catalog.get_children():
            self.tree_catalog.delete(item)

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT id, code, name, category, volume_l, length_mm, width_mm, est_time_min FROM models_catalog ORDER BY id ASC")
        for row in cursor.fetchall():
            self.tree_catalog.insert("", "end", values=row)
        conn.close()

if __name__ == "__main__":
    init_db()
    app = CNCApplication()
    app.mainloop()
