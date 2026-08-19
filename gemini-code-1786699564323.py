import sys
import os
import csv
import sqlite3
import datetime
import multiprocessing
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

# Support impression Windows / Linux
try:
    import win32api
    import win32print
except ImportError:
    win32print = None

# Support de la liaison série RS232 pour CNC NUM 1060
try:
    import serial
except ImportError:
    serial = None

if __name__ == '__main__':
    multiprocessing.freeze_support()

DB_FILE = "cnc_manager.db"

# --- INITIALISATION DE LA BASE DE DONNÉES ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # 1. Table Utilisateurs
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL
        )
    ''')

    # 2. Table Catalogue Modèles (11 colonnes Usi-Tab.csv + is_hidden)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS models_catalog (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            model_name TEXT NOT NULL,
            prog_name TEXT,
            block_dim TEXT,
            block_dim_bought TEXT,
            qty_per_block TEXT,
            z_between_pains TEXT,
            tools TEXT,
            caisson TEXT,
            top_plate TEXT,
            bottom_plate TEXT,
            remarks TEXT,
            is_hidden INTEGER DEFAULT 0
        )
    ''')

    # 3. Table Ordres de Fabrication (OF) avec données Brut & Traçabilité
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS work_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            of_number TEXT UNIQUE NOT NULL,
            model_name TEXT NOT NULL,
            prog_name TEXT,
            machine TEXT NOT NULL,
            assigned_operator TEXT NOT NULL,
            priority TEXT NOT NULL,
            block_num TEXT,
            block_density TEXT,
            pain_num TEXT,
            pain_weight TEXT,
            status TEXT DEFAULT 'En attente',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 4. Table Traçabilité
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS machining_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            of_number TEXT,
            operator TEXT NOT NULL,
            machine TEXT NOT NULL,
            model_name TEXT NOT NULL,
            real_time_min INTEGER,
            status TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Configuration utilisateurs par défaut
    cursor.execute("SELECT COUNT(*) FROM users")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO users (username, password, role) VALUES ('admin', 'admin123', 'Admin')")
        cursor.execute("INSERT INTO users (username, password, role) VALUES ('op1', 'op123', 'Operateur')")

    conn.commit()
    conn.close()


class CNCApplication(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("CNC Production Manager & RS232 Transfer")
        self.geometry("400x250")

        self.update_idletasks()
        w, h = self.winfo_width(), self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (w // 2)
        y = (self.winfo_screenheight() // 2) - (h // 2)
        self.geometry(f'{w}x{h}+{x}+{y}')

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

        ttk.Label(frame, text="Utilisateur :").grid(row=0, column=0, sticky="w", pady=5)
        self.entry_user = ttk.Entry(frame, width=20)
        self.entry_user.grid(row=0, column=1, pady=5)
        self.entry_user.focus()

        ttk.Label(frame, text="Mot de passe :").grid(row=1, column=0, sticky="w", pady=5)
        self.entry_pass = ttk.Entry(frame, show="*", width=20)
        self.entry_pass.grid(row=1, column=1, pady=5)

        btn_frame = ttk.Frame(self)
        btn_frame.pack(pady=15)
        ttk.Button(btn_frame, text="Se connecter", command=self.check_login).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Quitter", command=self.destroy).pack(side="right", padx=5)

        self.bind('<Return>', lambda e: self.check_login())

    def check_login(self):
        user, pwd = self.entry_user.get().strip(), self.entry_pass.get().strip()
        if not user or not pwd:
            messagebox.showwarning("Erreur", "Veuillez remplir tous les champs.", parent=self)
            return

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
            messagebox.showerror("Erreur", "Identifiants invalides.", parent=self)

    # --- APPLICATION PRINCIPALE (4 ONGLETS) ---
    def show_main_screen(self):
        self.clear_window()
        self.title(f"CNC Manager - Session : {self.current_user['username']} [{self.current_user['role']}]")
        self.geometry("1280x740")

        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - (1280 // 2)
        y = (self.winfo_screenheight() // 2) - (740 // 2)
        self.geometry(f'1280x740+{x}+{y}')

        # Barre de Menu Principale
        menubar = tk.Menu(self)
        menu_file = tk.Menu(menubar, tearoff=0)
        menu_file.add_command(label="Importer (CSV)", command=self.import_usi_tab_csv)
        menu_file.add_command(label="Exporter (CSV)", command=self.export_catalog_csv)
        menu_file.add_command(label="Enregistrer", command=lambda: messagebox.showinfo("Succès", "Base de données synchronisée."))
        menu_file.add_separator()
        menu_file.add_command(label="Déconnexion", command=self.show_login_screen)
        menu_file.add_command(label="Quitter", command=self.destroy)
        menubar.add_cascade(label="Fichier", menu=menu_file)

        if self.current_user['role'] == 'Admin':
            menu_admin = tk.Menu(menubar, tearoff=0)
            menu_admin.add_command(label="Gestion des Utilisateurs", command=self.open_user_management)
            menubar.add_cascade(label="Administration", menu=menu_admin)

        self.config(menu=menubar)

        # Onglets
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=5)

        tab_catalog = ttk.Frame(self.notebook)
        tab_of = ttk.Frame(self.notebook)
        tab_tracking = ttk.Frame(self.notebook)
        tab_cnc = ttk.Frame(self.notebook)

        self.notebook.add(tab_catalog, text=" 1. Catalogue Modèles (Usi-Tab.csv) ")
        self.notebook.add(tab_of, text=" 2. Ordres de Fabrication (OF) ")
        self.notebook.add(tab_tracking, text=" 3. Traçabilité & Suivi ")
        self.notebook.add(tab_cnc, text=" 4. Transfert CNC (RS232 / NUM 1060) ")

        self.setup_catalog_tab(tab_catalog)
        self.setup_of_tab(tab_of)
        self.setup_tracking_tab(tab_tracking)
        self.setup_cnc_tab(tab_cnc)

    # --- FONCTION GENERALISEE D'IMPRESSION ---
    def print_treeview_data(self, tree, title):
        content = f"--- {title.upper()} ---\nDate: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
        cols = tree["columns"]
        headers = [tree.heading(col)["text"] for col in cols]
        content += " | ".join(headers) + "\n" + "-"*80 + "\n"

        for item in tree.get_children():
            values = tree.item(item)["values"]
            content += " | ".join([str(v) for v in values]) + "\n"

        temp_file = "print_temp.txt"
        with open(temp_file, "w", encoding="utf-8") as f:
            f.write(content)

        if win32print:
            try:
                printer_name = win32print.GetDefaultPrinter()
                win32api.ShellExecute(0, "print", temp_file, None, ".", 0)
                messagebox.showinfo("Impression", f"Document envoyé à l'imprimante : {printer_name}")
            except Exception as e:
                messagebox.showerror("Erreur Impression", str(e))
        else:
            os.system(f"notepad.exe {temp_file}")

    # --- ONGLET 1 : CATALOGUE & GESTION DES MODELES ---
    def setup_catalog_tab(self, parent):
        frame_tools = ttk.Frame(parent)
        frame_tools.pack(fill="x", padx=10, pady=5)

        ttk.Label(frame_tools, text="Rechercher :").pack(side="left", padx=5)
        self.entry_cat_search = ttk.Entry(frame_tools, width=20)
        self.entry_cat_search.pack(side="left", padx=5)
        self.entry_cat_search.bind("<KeyRelease>", lambda e: self.load_catalog_data())

        if self.current_user['role'] == 'Admin':
            ttk.Button(frame_tools, text="+ Ajouter Modèle", command=self.add_model_dialog).pack(side="left", padx=5)
            ttk.Button(frame_tools, text="- Supprimer Modèle", command=self.delete_model_dialog).pack(side="left", padx=5)
            ttk.Button(frame_tools, text="Cacher/Masquer Modèle", command=self.hide_model_dialog).pack(side="left", padx=5)

        ttk.Button(frame_tools, text="Imprimer Catalogue", command=lambda: self.print_treeview_data(self.tree_cat, "Catalogue Modeles")).pack(side="right", padx=5)

        frame_list = ttk.Frame(parent)
        frame_list.pack(fill="both", expand=True, padx=10, pady=5)

        cols = ("id", "model_name", "prog_name", "block_dim", "qty_per_block", "z_between_pains", "tools", "caisson", "top_plate", "bottom_plate", "remarks")
        self.tree_cat = ttk.Treeview(frame_list, columns=cols, show="headings")

        self.tree_cat.heading("id", text="ID")
        self.tree_cat.heading("model_name", text="Nom Model")
        self.tree_cat.heading("prog_name", text="Prog. Pain")
        self.tree_cat.heading("block_dim", text="Dimension Bloc")
        self.tree_cat.heading("qty_per_block", text="Qte/Bloc")
        self.tree_cat.heading("z_between_pains", text="Z d'Axe")
        self.tree_cat.heading("tools", text="Outils")
        self.tree_cat.heading("caisson", text="Caisson")
        self.tree_cat.heading("top_plate", text="Plaque Y")
        self.tree_cat.heading("bottom_plate", text="Plaque B")
        self.tree_cat.heading("remarks", text="Remarque")

        self.tree_cat.column("id", width=35, anchor="center")
        self.tree_cat.column("model_name", width=110)
        self.tree_cat.column("prog_name", width=110)
        self.tree_cat.column("block_dim", width=160)
        self.tree_cat.column("qty_per_block", width=65, anchor="center")
        self.tree_cat.column("z_between_pains", width=65, anchor="center")
        self.tree_cat.column("tools", width=100)
        self.tree_cat.column("caisson", width=60, anchor="center")
        self.tree_cat.column("top_plate", width=80)
        self.tree_cat.column("bottom_plate", width=80)
        self.tree_cat.column("remarks", width=120)

        scrollbar_y = ttk.Scrollbar(frame_list, orient="vertical", command=self.tree_cat.yview)
        scrollbar_x = ttk.Scrollbar(frame_list, orient="horizontal", command=self.tree_cat.xview)
        self.tree_cat.configure(yscrollcommand=scrollbar_y.set, xscrollcommand=scrollbar_x.set)

        self.tree_cat.pack(side="left", fill="both", expand=True)
        scrollbar_y.pack(side="right", fill="y")
        scrollbar_x.pack(side="bottom", fill="x")

        # Double clic pour créer directement un OF à partir d'un modèle
        self.tree_cat.bind("<Double-1>", self.on_model_double_click)

        self.load_catalog_data()

    def load_catalog_data(self):
        for item in self.tree_cat.get_children():
            self.tree_cat.delete(item)

        query = self.entry_cat_search.get().strip() if hasattr(self, 'entry_cat_search') else ""

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        if query:
            cursor.execute('''
                SELECT id, model_name, prog_name, block_dim, qty_per_block, z_between_pains, tools, caisson, top_plate, bottom_plate, remarks
                FROM models_catalog
                WHERE is_hidden=0 AND (model_name LIKE ? OR prog_name LIKE ? OR tools LIKE ?)
                ORDER BY id ASC
            ''', (f'%{query}%', f'%{query}%', f'%{query}%'))
        else:
            cursor.execute("SELECT id, model_name, prog_name, block_dim, qty_per_block, z_between_pains, tools, caisson, top_plate, bottom_plate, remarks FROM models_catalog WHERE is_hidden=0 ORDER BY id ASC")

        for row in cursor.fetchall():
            self.tree_cat.insert("", "end", values=row)
        conn.close()

    def import_usi_tab_csv(self):
        file_path = filedialog.askopenfilename(title="Sélectionner Usi-Tab.csv", filetypes=[("Fichiers CSV", "*.csv"), ("Tous", "*.*")])
        if not file_path:
            return

        try:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM models_catalog")

            count = 0
            with open(file_path, mode='r', encoding='latin1') as f:
                reader = csv.reader(f, delimiter=';')
                rows = [r for r in reader if any(field.strip() for field in r)]
                
                for r in rows[1:]:
                    if len(r) >= 11:
                        cursor.execute('''
                            INSERT INTO models_catalog (
                                model_name, prog_name, block_dim, block_dim_bought, qty_per_block,
                                z_between_pains, tools, caisson, top_plate, bottom_plate, remarks
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            r[0].strip(), r[1].strip(), r[2].replace('\n', ' ').strip(),
                            r[3].replace('\n', ' ').strip(), r[4].strip(), r[5].strip(),
                            r[6].replace('\n', ' ').strip(), r[7].strip(), r[8].strip(),
                            r[9].strip(), r[10].strip()
                        ))
                        count += 1

            conn.commit()
            conn.close()
            messagebox.showinfo("Succès", f"{count} modèles importés depuis Usi-Tab.csv.")
            self.load_catalog_data()
        except Exception as e:
            messagebox.showerror("Erreur", f"Erreur lors de l'importation :\n{str(e)}")

    def export_catalog_csv(self):
        file_path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("Fichiers CSV", "*.csv")])
        if not file_path:
            return
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT model_name, prog_name, block_dim, block_dim_bought, qty_per_block, z_between_pains, tools, caisson, top_plate, bottom_plate, remarks FROM models_catalog")
        rows = cursor.fetchall()
        conn.close()

        with open(file_path, mode='w', newline='', encoding='latin1') as f:
            writer = csv.writer(f, delimiter=';')
            writer.writerow(["Nom Model", "Prog. Pain", "Dimension Bloc", "Dimension Achetée", "Qte/Bloc", "Z d'Axe", "Outils", "Caisson", "Plaque Y", "Plaque B", "Remarque"])
            writer.writerows(rows)
        messagebox.showinfo("Export", "Catalogue exporté avec succès.")

    # Dialogue d'ajout manuel de modèle
    def add_model_dialog(self):
        win = tk.Toplevel(self)
        win.title("Ajouter un Modèle au Catalogue")
        win.geometry("400x450")

        fields = ["Nom Modèle", "Prog. Pain", "Dimension Bloc", "Qte/Bloc", "Z d'Axe", "Outils", "Caisson", "Plaque Top", "Plaque Bottom", "Remarques"]
        entries = {}

        for i, field in enumerate(fields):
            ttk.Label(win, text=f"{field} :").grid(row=i, column=0, padx=10, pady=3, sticky="w")
            e = ttk.Entry(win, width=25)
            e.grid(row=i, column=1, padx=10, pady=3)
            entries[field] = e

        def save():
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO models_catalog (model_name, prog_name, block_dim, qty_per_block, z_between_pains, tools, caisson, top_plate, bottom_plate, remarks)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', tuple(entries[f].get().strip() for f in fields))
            conn.commit()
            conn.close()
            messagebox.showinfo("Succès", "Modèle ajouté au catalogue.", parent=win)
            win.destroy()
            self.load_catalog_data()

        ttk.Button(win, text="Enregistrer", command=save).grid(row=len(fields), column=0, columnspan=2, pady=15)

    # Supprimer un modèle avec boite de recherche dynamique et confirmation
    def delete_model_dialog(self):
        win = tk.Toplevel(self)
        win.title("Supprimer un Modèle")
        win.geometry("400x300")

        ttk.Label(win, text="Rechercher le modèle à supprimer :").pack(pady=5)
        entry_search = ttk.Entry(win, width=30)
        entry_search.pack(pady=5)

        listbox = tk.Listbox(win, width=45, height=8)
        listbox.pack(pady=5)

        def update_list():
            listbox.delete(0, tk.END)
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("SELECT id, model_name FROM models_catalog WHERE model_name LIKE ?", (f'%{entry_search.get().strip()}%',))
            for row in cursor.fetchall():
                listbox.insert(tk.END, f"{row[0]} | {row[1]}")
            conn.close()

        entry_search.bind("<KeyRelease>", lambda e: update_list())
        update_list()

        def confirm_delete():
            sel = listbox.get(tk.ACTIVE)
            if not sel:
                return
            m_id, m_name = sel.split(" | ")[0], sel.split(" | ")[1]
            if messagebox.askyesno("Confirmation", f"Êtes-vous sûr de vouloir supprimer définitivement le modèle '{m_name}' ?", parent=win):
                conn = sqlite3.connect(DB_FILE)
                cursor = conn.cursor()
                cursor.execute("DELETE FROM models_catalog WHERE id=?", (m_id,))
                conn.commit()
                conn.close()
                messagebox.showinfo("Supprimé", "Modèle supprimé.", parent=win)
                win.destroy()
                self.load_catalog_data()

        ttk.Button(win, text="Supprimer le modèle sélectionné", command=confirm_delete).pack(pady=10)

    # Masquer/Cacher un modèle
    def hide_model_dialog(self):
        win = tk.Toplevel(self)
        win.title("Cacher / Démasquer un Modèle")
        win.geometry("400x320")

        ttk.Label(win, text="Rechercher un modèle à cacher/afficher :").pack(pady=5)
        entry_search = ttk.Entry(win, width=30)
        entry_search.pack(pady=5)

        listbox = tk.Listbox(win, width=45, height=8)
        listbox.pack(pady=5)

        def update_list():
            listbox.delete(0, tk.END)
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("SELECT id, model_name, is_hidden FROM models_catalog WHERE model_name LIKE ?", (f'%{entry_search.get().strip()}%',))
            for row in cursor.fetchall():
                status = "[CACHÉ]" if row[2] == 1 else "[VISIBLE]"
                listbox.insert(tk.END, f"{row[0]} | {row[1]} {status}")
            conn.close()

        entry_search.bind("<KeyRelease>", lambda e: update_list())
        update_list()

        def toggle_hide():
            sel = listbox.get(tk.ACTIVE)
            if not sel:
                return
            m_id = sel.split(" | ")[0]
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("UPDATE models_catalog SET is_hidden = CASE WHEN is_hidden=1 THEN 0 ELSE 1 END WHERE id=?", (m_id,))
            conn.commit()
            conn.close()
            update_list()
            self.load_catalog_data()

        ttk.Button(win, text="Bascule Cacher / Afficher", command=toggle_hide).pack(pady=10)

    # --- ONGLET 2 : ORDRES DE FABRICATION (OF) & SAISIE DU BRUT ---
    def setup_of_tab(self, parent):
        frame_new = ttk.LabelFrame(parent, text=" Saisie de l'Ordre de Fabrication & Traçabilité Brut (Poste de Travail) ")
        frame_new.pack(fill="x", padx=10, pady=5)

        ttk.Label(frame_new, text="Modèle:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.entry_of_model = ttk.Entry(frame_new, width=20)
        self.entry_of_model.grid(row=0, column=1, padx=5, pady=5)

        ttk.Label(frame_new, text="Machine:").grid(row=0, column=2, padx=5, pady=5, sticky="w")
        self.combo_of_mach = ttk.Combobox(frame_new, values=["NUM 1060 (5-Axes)", "Fraiseuse EPS", "Tour CNC"], state="readonly", width=18)
        self.combo_of_mach.current(0)
        self.combo_of_mach.grid(row=0, column=3, padx=5, pady=5)

        ttk.Label(frame_new, text="Priorité:").grid(row=0, column=4, padx=5, pady=5, sticky="w")
        self.combo_of_prio = ttk.Combobox(frame_new, values=["Haute", "Normale", "Basse"], state="readonly", width=10)
        self.combo_of_prio.current(1)
        self.combo_of_prio.grid(row=0, column=5, padx=5, pady=5)

        # Données spécifiques Brut à saisir par l'opérateur
        ttk.Label(frame_new, text="N° Bloc:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.entry_block_num = ttk.Entry(frame_new, width=12)
        self.entry_block_num.grid(row=1, column=1, padx=5, pady=5)

        ttk.Label(frame_new, text="Densité Bloc:").grid(row=1, column=2, padx=5, pady=5, sticky="w")
        self.entry_block_density = ttk.Entry(frame_new, width=12)
        self.entry_block_density.grid(row=1, column=3, padx=5, pady=5)

        ttk.Label(frame_new, text="N° Pain:").grid(row=1, column=4, padx=5, pady=5, sticky="w")
        self.entry_pain_num = ttk.Entry(frame_new, width=10)
        self.entry_pain_num.grid(row=1, column=5, padx=5, pady=5)

        ttk.Label(frame_new, text="Poids Pain (g):").grid(row=2, column=0, padx=5, pady=5, sticky="w")
        self.entry_pain_weight = ttk.Entry(frame_new, width=12)
        self.entry_pain_weight.grid(row=2, column=1, padx=5, pady=5)

        ttk.Button(frame_new, text="Lancer l'OF Auto-Incrémenté", command=self.create_of_auto).grid(row=2, column=3, columnspan=3, padx=10, pady=5, sticky="ew")

        # Action directe & Impression
        frame_action = ttk.Frame(parent)
        frame_action.pack(fill="x", padx=10, pady=5)
        ttk.Button(frame_action, text=" Charger & Envoyer Programme de l'OF vers CNC (RS232)", command=self.transfer_selected_of_to_cnc).pack(side="left", padx=5)
        ttk.Button(frame_action, text="Imprimer Liste OF", command=lambda: self.print_treeview_data(self.tree_of, "Ordres de Fabrication")).pack(side="right", padx=5)

        # Tableau
        frame_list = ttk.Frame(parent)
        frame_list.pack(fill="both", expand=True, padx=10, pady=5)

        cols = ("id", "of_number", "model_name", "prog_name", "machine", "assigned_operator", "priority", "block_num", "block_density", "pain_num", "pain_weight", "status", "created_at")
        self.tree_of = ttk.Treeview(frame_list, columns=cols, show="headings")

        self.tree_of.heading("id", text="ID")
        self.tree_of.heading("of_number", text="N° OF")
        self.tree_of.heading("model_name", text="Modèle")
        self.tree_of.heading("prog_name", text="Prog. Pain")
        self.tree_of.heading("machine", text="Machine")
        self.tree_of.heading("assigned_operator", text="Opérateur")
        self.tree_of.heading("priority", text="Priorité")
        self.tree_of.heading("block_num", text="N° Bloc")
        self.tree_of.heading("block_density", text="Densité")
        self.tree_of.heading("pain_num", text="N° Pain")
        self.tree_of.heading("pain_weight", text="Poids (g)")
        self.tree_of.heading("status", text="Statut")
        self.tree_of.heading("created_at", text="Date/Heure Création")

        self.tree_of.column("id", width=35, anchor="center")
        self.tree_of.column("of_number", width=110, anchor="center")
        self.tree_of.column("model_name", width=110)
        self.tree_of.column("prog_name", width=100)
        self.tree_of.column("machine", width=120)
        self.tree_of.column("assigned_operator", width=90)
        self.tree_of.column("priority", width=70, anchor="center")
        self.tree_of.column("block_num", width=70, anchor="center")
        self.tree_of.column("block_density", width=70, anchor="center")
        self.tree_of.column("pain_num", width=70, anchor="center")
        self.tree_of.column("pain_weight", width=70, anchor="center")
        self.tree_of.column("status", width=90, anchor="center")
        self.tree_of.column("created_at", width=130, anchor="center")

        scrollbar = ttk.Scrollbar(frame_list, orient="vertical", command=self.tree_of.yview)
        self.tree_of.configure(yscrollcommand=scrollbar.set)
        self.tree_of.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.load_of_data()

    # Double-clic sur un modèle du catalogue : pré-remplit l'OF
    def on_model_double_click(self, event):
        selected = self.tree_cat.selection()
        if not selected:
            return
        item = self.tree_cat.item(selected[0])
        model_name = item['values'][1]

        self.notebook.select(1)
        self.entry_of_model.delete(0, tk.END)
        self.entry_of_model.insert(0, model_name)

    def generate_next_of_number(self):
        year = datetime.datetime.now().year
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM work_orders ORDER BY id DESC LIMIT 1")
        row = cursor.fetchone()
        conn.close()

        next_id = (row[0] + 1) if row else 1
        return f"OF{next_id:05d}/{year}"

    def create_of_auto(self):
        model_name = self.entry_of_model.get().strip()
        if not model_name:
            messagebox.showwarning("Attention", "Veuillez indiquer un modèle.")
            return

        b_num = self.entry_block_num.get().strip()
        b_dens = self.entry_block_density.get().strip()
        p_num = self.entry_pain_num.get().strip()
        p_weight = self.entry_pain_weight.get().strip()

        # Avertissement si informations manquantes
        if not all([b_num, b_dens, p_num, p_weight]):
            messagebox.showwarning("Incomplet", "Des informations sur le brut sont manquantes.\nL'OF sera créé mais devra être complété ultérieurement.")

        of_num = self.generate_next_of_number()

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT prog_name FROM models_catalog WHERE model_name=?", (model_name,))
        row = cursor.fetchone()
        prog = row[0] if row else ""

        cursor.execute('''
            INSERT INTO work_orders (of_number, model_name, prog_name, machine, assigned_operator, priority, block_num, block_density, pain_num, pain_weight)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (of_num, model_name, prog, self.combo_of_mach.get(), self.current_user['username'], self.combo_of_prio.get(), b_num, b_dens, p_num, p_weight))

        conn.commit()
        conn.close()

        messagebox.showinfo("Succès", f"Ordre de fabrication {of_num} créé automatiquement.")
        self.load_of_data()

    def load_of_data(self):
        for item in self.tree_of.get_children():
            self.tree_of.delete(item)
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT id, of_number, model_name, prog_name, machine, assigned_operator, priority, block_num, block_density, pain_num, pain_weight, status, created_at FROM work_orders ORDER BY id DESC")
        for row in cursor.fetchall():
            self.tree_of.insert("", "end", values=row)
        conn.close()

    def transfer_selected_of_to_cnc(self):
        selected = self.tree_of.selection()
        if not selected:
            messagebox.showwarning("Attention", "Veuillez sélectionner un OF dans le tableau.")
            return

        item = self.tree_of.item(selected[0])
        of_num = item['values'][1]
        model_name = item['values'][2]
        prog_name = item['values'][3]

        self.notebook.select(3)
        self.lbl_file.config(text=f"OF: {of_num} | Modèle: {model_name} | Prog: {prog_name}", font=("Arial", 9, "bold"))
        self.txt_preview.delete("1.0", tk.END)
        self.txt_preview.insert(tk.END, f"% \n(PROGRAMME ASSOCIE A L'OF {of_num})\n(MODELE: {model_name})\n(PROGRAMME PAIN: {prog_name})\n\nG00 G90 G40\nM03 S12000\nG00 X0 Y0 Z50\n(G-CODE COMPATIBLE NUM 1060)\nM05\nM30\n%")

    # --- ONGLET 3 : TRAÇABILITÉ & SUIVI USINAGE ---
    def setup_tracking_tab(self, parent):
        frame_input = ttk.LabelFrame(parent, text=" Enregistrer une Étape d'Usinage ")
        frame_input.pack(fill="x", padx=10, pady=5)

        ttk.Label(frame_input, text="N° OF:").grid(row=0, column=0, padx=5, pady=5)
        self.entry_tr_of = ttk.Entry(frame_input, width=12)
        self.entry_tr_of.grid(row=0, column=1, padx=5, pady=5)

        ttk.Label(frame_input, text="Machine:").grid(row=0, column=2, padx=5, pady=5)
        self.combo_tr_mach = ttk.Combobox(frame_input, values=["NUM 1060 (5-Axes)", "Fraiseuse EPS", "Tour CNC"], state="readonly", width=16)
        self.combo_tr_mach.current(0)
        self.combo_tr_mach.grid(row=0, column=3, padx=5, pady=5)

        ttk.Label(frame_input, text="Modèle / Pièce:").grid(row=0, column=4, padx=5, pady=5)
        self.entry_tr_model = ttk.Entry(frame_input, width=20)
        self.entry_tr_model.grid(row=0, column=5, padx=5, pady=5)

        ttk.Label(frame_input, text="Temps Réel (min):").grid(row=1, column=0, padx=5, pady=5)
        self.entry_tr_time = ttk.Entry(frame_input, width=12)
        self.entry_tr_time.insert(0, "45")
        self.entry_tr_time.grid(row=1, column=1, padx=5, pady=5)

        ttk.Label(frame_input, text="Statut:").grid(row=1, column=2, padx=5, pady=5)
        self.combo_tr_stat = ttk.Combobox(frame_input, values=["Terminé", "En cours", "Maintenance", "En attente"], state="readonly", width=16)
        self.combo_tr_stat.current(0)
        self.combo_tr_stat.grid(row=1, column=3, padx=5, pady=5)

        ttk.Button(frame_input, text="Enregistrer l'Usinage", command=self.add_tracking_log).grid(row=1, column=4, columnspan=2, padx=10, pady=5, sticky="ew")

        frame_list = ttk.Frame(parent)
        frame_list.pack(fill="both", expand=True, padx=10, pady=5)

        ttk.Button(parent, text="Imprimer Historique Traçabilité", command=lambda: self.print_treeview_data(self.tree_track, "Tracabilite et Suivi")).pack(anchor="e", padx=10, pady=2)

        cols = ("id", "of_number", "operator", "machine", "model_name", "real_time_min", "status", "timestamp")
        self.tree_track = ttk.Treeview(frame_list, columns=cols, show="headings")

        self.tree_track.heading("id", text="ID")
        self.tree_track.heading("of_number", text="N° OF")
        self.tree_track.heading("operator", text="Opérateur")
        self.tree_track.heading("machine", text="Machine")
        self.tree_track.heading("model_name", text="Modèle / Pièce")
        self.tree_track.heading("real_time_min", text="Tps Réel (min)")
        self.tree_track.heading("status", text="Statut")
        self.tree_track.heading("timestamp", text="Date / Heure")

        self.tree_track.column("id", width=40, anchor="center")
        self.tree_track.column("of_number", width=90, anchor="center")
        self.tree_track.column("operator", width=100)
        self.tree_track.column("machine", width=140)
        self.tree_track.column("model_name", width=200)
        self.tree_track.column("real_time_min", width=90, anchor="center")
        self.tree_track.column("status", width=110, anchor="center")
        self.tree_track.column("timestamp", width=150, anchor="center")

        scrollbar = ttk.Scrollbar(frame_list, orient="vertical", command=self.tree_track.yview)
        self.tree_track.configure(yscrollcommand=scrollbar.set)
        self.tree_track.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.load_tracking_data()

    def add_tracking_log(self):
        model_name = self.entry_tr_model.get().strip()
        if not model_name:
            messagebox.showwarning("Attention", "Veuillez renseigner le modèle.")
            return

        try:
            t_real = int(self.entry_tr_time.get().strip())
        except ValueError:
            t_real = 0

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO machining_history (of_number, operator, machine, model_name, real_time_min, status)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (self.entry_tr_of.get().strip(), self.current_user['username'], self.combo_tr_mach.get(), model_name, t_real, self.combo_tr_stat.get()))

        if self.entry_tr_of.get().strip():
            cursor.execute("UPDATE work_orders SET status=? WHERE of_number=?", (self.combo_tr_stat.get(), self.entry_tr_of.get().strip()))

        conn.commit()
        conn.close()

        self.entry_tr_model.delete(0, tk.END)
        self.load_tracking_data()
        self.load_of_data()

    def load_tracking_data(self):
        for item in self.tree_track.get_children():
            self.tree_track.delete(item)
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT id, of_number, operator, machine, model_name, real_time_min, status, timestamp FROM machining_history ORDER BY id DESC")
        for row in cursor.fetchall():
            self.tree_track.insert("", "end", values=row)
        conn.close()

    # --- ONGLET 4 : TRANSFERT PROGRAMME CNC (RS232 / NUM 1060) ---
    def setup_cnc_tab(self, parent):
        frame_cfg = ttk.LabelFrame(parent, text=" Configuration Liaison RS232 (NUM 1060) ")
        frame_cfg.pack(fill="x", padx=10, pady=5)

        ttk.Label(frame_cfg, text="Port COM:").grid(row=0, column=0, padx=5, pady=5)
        self.entry_com = ttk.Entry(frame_cfg, width=10)
        self.entry_com.insert(0, "COM1")
        self.entry_com.grid(row=0, column=1, padx=5, pady=5)

        ttk.Label(frame_cfg, text="Vitesse (Baud):").grid(row=0, column=2, padx=5, pady=5)
        self.combo_baud = ttk.Combobox(frame_cfg, values=["2400", "4800", "9600", "19200"], state="readonly", width=10)
        self.combo_baud.current(2)
        self.combo_baud.grid(row=0, column=3, padx=5, pady=5)

        frame_trans = ttk.LabelFrame(parent, text=" Fichier Programme ISO / G-Code ")
        frame_trans.pack(fill="both", expand=True, padx=10, pady=5)

        ttk.Button(frame_trans, text="Charger un Fichier ISO Externe", command=self.select_gcode_file).pack(anchor="w", padx=10, pady=5)
        self.lbl_file = ttk.Label(frame_trans, text="Aucun fichier ou OF sélectionné.", font=("Arial", 9, "italic"))
        self.lbl_file.pack(anchor="w", padx=10, pady=2)

        self.txt_preview = tk.Text(frame_trans, height=10, width=80)
        self.txt_preview.pack(fill="both", expand=True, padx=10, pady=5)

        ttk.Button(frame_trans, text="Transférer à la CNC NUM 1060", command=self.send_to_cnc).pack(pady=10)

    def select_gcode_file(self):
        file_path = filedialog.askopenfilename(title="Sélectionner le fichier ISO", filetypes=[("Fichiers NC/ISO", "*.nc *.iso *.gcode *.txt"), ("Tous", "*.*")])
        if file_path:
            self.lbl_file.config(text=file_path, font=("Arial", 9, "bold"))
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    self.txt_preview.delete("1.0", tk.END)
                    self.txt_preview.insert(tk.END, content)
            except Exception as e:
                messagebox.showerror("Erreur", str(e))

    def send_to_cnc(self):
        if serial is None:
            messagebox.showerror("Erreur", "Module 'pyserial' non trouvé. Vérifiez l'installation.")
            return

        com_port = self.entry_com.get().strip()
        baud = int(self.combo_baud.get())
        gcode = self.txt_preview.get("1.0", tk.END).strip()

        if not gcode:
            messagebox.showwarning("Attention", "Zone de code vide.")
            return

        try:
            ser = serial.Serial(com_port, baudrate=baud, bytesize=serial.EIGHTBITS, parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE, timeout=3)
            ser.write(gcode.encode('ascii'))
            ser.close()
            messagebox.showinfo("Transfert CNC", f"Programme transmis à la NUM 1060 via {com_port} !")
        except Exception as e:
            messagebox.showerror("Erreur RS232", f"Échec de transfert sur {com_port} :\n{str(e)}")

    # --- ADMINISTRATION UTILISATEURS COMPLETE ---
    def open_user_management(self):
        win = tk.Toplevel(self)
        win.title("Gestion des Utilisateurs & Autorisations")
        win.geometry("550x400")

        frame_top = ttk.LabelFrame(win, text=" Nouveau / Modifier Utilisateur ")
        frame_top.pack(fill="x", padx=10, pady=5)

        ttk.Label(frame_top, text="Utilisateur:").grid(row=0, column=0, padx=5, pady=5)
        entry_u = ttk.Entry(frame_top, width=15)
        entry_u.grid(row=0, column=1, padx=5, pady=5)

        ttk.Label(frame_top, text="Mot de passe:").grid(row=0, column=2, padx=5, pady=5)
        entry_p = ttk.Entry(frame_top, width=15)
        entry_p.grid(row=0, column=3, padx=5, pady=5)

        ttk.Label(frame_top, text="Rôle:").grid(row=1, column=0, padx=5, pady=5)
        combo_r = ttk.Combobox(frame_top, values=["Admin", "Operateur"], state="readonly", width=12)
        combo_r.current(1)
        combo_r.grid(row=1, column=1, padx=5, pady=5)

        # Tableau d'affichage des comptes et mots de passe
        cols = ("id", "username", "password", "role")
        tree_u = ttk.Treeview(win, columns=cols, show="headings", height=8)
        tree_u.heading("id", text="ID")
        tree_u.heading("username", text="Utilisateur")
        tree_u.heading("password", text="Mot de Passe")
        tree_u.heading("role", text="Rôle")

        tree_u.column("id", width=40, anchor="center")
        tree_u.column("username", width=120)
        tree_u.column("password", width=120)
        tree_u.column("role", width=100, anchor="center")
        tree_u.pack(fill="both", expand=True, padx=10, pady=5)

        def load_users():
            for item in tree_u.get_children():
                tree_u.delete(item)
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("SELECT id, username, password, role FROM users")
            for row in cursor.fetchall():
                tree_u.insert("", "end", values=row)
            conn.close()

        def save_user():
            u, p, r = entry_u.get().strip(), entry_p.get().strip(), combo_r.get()
            if not u or not p:
                messagebox.showwarning("Erreur", "Remplissez tous les champs.", parent=win)
                return

            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO users (username, password, role) VALUES (?, ?, ?)", (u, p, r))
            conn.commit()
            conn.close()
            load_users()
            entry_u.delete(0, tk.END)
            entry_p.delete(0, tk.END)

        def delete_user():
            sel = tree_u.selection()
            if not sel:
                return
            u_id = tree_u.item(sel[0])['values'][0]
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM users WHERE id=?", (u_id,))
            conn.commit()
            conn.close()
            load_users()

        ttk.Button(frame_top, text="Enregistrer / Modifier", command=save_user).grid(row=1, column=2, columnspan=2, padx=5, pady=5)
        ttk.Button(win, text="Supprimer l'utilisateur sélectionné", command=delete_user).pack(pady=5)

        load_users()


if __name__ == "__main__":
    init_db()
    app = CNCApplication()
    app.mainloop()
