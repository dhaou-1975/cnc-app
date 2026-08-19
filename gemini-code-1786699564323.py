import os
import sys
import sqlite3
import multiprocessing
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

# Indispensable pour éviter la boucle de processus sous Windows 7 avec PyInstaller
if __name__ == '__main__':
    multiprocessing.freeze_support()

# --- BASE DE DONNÉES ---
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
    
    # Table Journaux CNC
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cnc_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            operator TEXT NOT NULL,
            machine TEXT NOT NULL,
            part_name TEXT NOT NULL,
            status TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Compte administrateur par défaut si la table est vide
    cursor.execute("SELECT COUNT(*) FROM users")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO users (username, password, role) VALUES ('admin', 'admin123', 'Admin')")
        cursor.execute("INSERT INTO users (username, password, role) VALUES ('operateur', 'op123', 'Operateur')")
        
    conn.commit()
    conn.close()

# --- FENÊTRE DE CONNEXION ---
class LoginDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Connexion - CNC Manager")
        self.geometry("350x220")
        self.resizable(False, False)
        self.user_data = None

        # Rendre la fenêtre toujours au premier plan et bloquante
        self.transient(parent)
        self.grab_set()

        # Centrer sur l'écran
        self.eval('tk::PlaceWindow . center')

        ttk.Label(self, text="CNC Manager - Authentification", font=("Arial", 11, "bold")).pack(pady=15)

        frame = ttk.Frame(self)
        frame.pack(pady=5, padx=20, fill="x")

        ttk.Label(frame, text="Utilisateur :").grid(row=0, column=0, sticky="w", pady=5)
        self.entry_user = ttk.Entry(frame)
        self.entry_user.grid(row=0, column=1, sticky="e", pady=5)
        self.entry_user.focus()

        ttk.Label(frame, text="Mot de passe :").grid(row=1, column=0, sticky="w", pady=5)
        self.entry_pass = ttk.Entry(frame, show="*")
        self.entry_pass.grid(row=1, column=1, sticky="e", pady=5)

        btn_frame = ttk.Frame(self)
        btn_frame.pack(pady=15)

        ttk.Button(btn_frame, text="Se connecter", command=self.check_login).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Quitter", command=self.destroy).pack(side="right", padx=5)

        self.bind('<Return>', lambda event: self.check_login())
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def check_login(self):
        user = self.entry_user.get().strip()
        pwd = self.entry_pass.get().strip()

        if not user or not pwd:
            messagebox.showwarning("Erreur", "Veuillez remplir tous les champs.", parent=self)
            return

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT username, role FROM users WHERE username=? AND password=?", (user, pwd))
        row = cursor.fetchone()
        conn.close()

        if row:
            self.user_data = {"username": row[0], "role": row[1]}
            self.destroy()
        else:
            messagebox.showerror("Accès refusé", "Nom d'utilisateur ou mot de passe incorrect.", parent=self)

    def on_close(self):
        self.user_data = None
        self.destroy()

# --- APPLICATION PRINCIPALE ---
class CNCManagerApp:
    def __init__(self, root, user_info):
        self.root = root
        self.user_info = user_info
        self.root.title(f"CNC Manager - Session : {user_info['username']} ({user_info['role']})")
        
        # Interface
        self.setup_ui()
        self.load_data()

    def setup_ui(self):
        # Barre de menu
        menubar = tk.Menu(self.root)
        
        menu_file = tk.Menu(menubar, tearoff=0)
        menu_file.add_command(label="Déconnexion", command=self.logout)
        menu_file.add_separator()
        menu_file.add_command(label="Quitter", command=self.root.quit)
        menubar.add_cascade(label="Fichier", menu=menu_file)

        if self.user_info['role'] == 'Admin':
            menu_admin = tk.Menu(menubar, tearoff=0)
            menu_admin.add_command(label="Gestion des utilisateurs", command=self.manage_users)
            menubar.add_cascade(label="Administration", menu=menu_admin)

        self.root.config(menu=menubar)

        # Zone de saisie
        frame_input = ttk.LabelFrame(self.root, text=" Nouvel enregistrement ")
        frame_input.pack(fill="x", padx=10, pady=5)

        ttk.Label(frame_input, text="Machine:").grid(row=0, column=0, padx=5, pady=5)
        self.combo_machine = ttk.Combobox(frame_input, values=["NUM 1060", "5-Axes CNC", "Tour CNC", "Fraiseuse"])
        self.combo_machine.current(0)
        self.combo_machine.grid(row=0, column=1, padx=5, pady=5)

        ttk.Label(frame_input, text="Pièce / Fichier:").grid(row=0, column=2, padx=5, pady=5)
        self.entry_part = ttk.Entry(frame_input)
        self.entry_part.grid(row=0, column=3, padx=5, pady=5)

        ttk.Label(frame_input, text="Statut:").grid(row=0, column=4, padx=5, pady=5)
        self.combo_status = ttk.Combobox(frame_input, values=["En cours", "Terminé", "Erreur / Maintenance"])
        self.combo_status.current(0)
        self.combo_status.grid(row=0, column=5, padx=5, pady=5)

        ttk.Button(frame_input, text="Ajouter", command=self.add_log).grid(row=0, column=6, padx=10, pady=5)

        # Tableau (Treeview)
        frame_table = ttk.Frame(self.root)
        frame_table.pack(fill="both", expand=True, padx=10, pady=5)

        columns = ("id", "operator", "machine", "part_name", "status", "timestamp")
        self.tree = ttk.Treeview(frame_table, columns=columns, show="headings")

        self.tree.heading("id", text="ID")
        self.tree.heading("operator", text="Opérateur")
        self.tree.heading("machine", text="Machine")
        self.tree.heading("part_name", text="Pièce")
        self.tree.heading("status", text="Statut")
        self.tree.heading("timestamp", text="Date / Heure")

        self.tree.column("id", width=40, anchor="center")
        self.tree.column("operator", width=100)
        self.tree.column("machine", width=120)
        self.tree.column("part_name", width=200)
        self.tree.column("status", width=120)
        self.tree.column("timestamp", width=150, anchor="center")

        scrollbar = ttk.Scrollbar(frame_table, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    def load_data(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT id, operator, machine, part_name, status, timestamp FROM cnc_logs ORDER BY id DESC")
        for row in cursor.fetchall():
            self.tree.insert("", "end", values=row)
        conn.close()

    def add_log(self):
        part = self.entry_part.get().strip()
        if not part:
            messagebox.showwarning("Attention", "Veuillez indiquer le nom de la pièce.")
            return

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO cnc_logs (operator, machine, part_name, status) VALUES (?, ?, ?, ?)",
                       (self.user_info['username'], self.combo_machine.get(), part, self.combo_status.get()))
        conn.commit()
        conn.close()

        self.entry_part.delete(0, tk.END)
        self.load_data()

    def manage_users(self):
        messagebox.showinfo("Administration", "Module de gestion des utilisateurs actif.")

    def logout(self):
        self.root.destroy()
        os.execl(sys.executable, sys.executable, *sys.argv)

# --- INVOCATION PRINCIPALE ---
def main():
    init_db()

    root = tk.Tk()
    # Rend la fenêtre invisible sans suspendre la boucle graphique Windows 7
    root.withdraw()

    login_dlg = LoginDialog(root)
    root.wait_window(login_dlg)

    if login_dlg.user_data:
        root.deiconify()
        root.geometry("1100x600")
        root.eval('tk::PlaceWindow . center')
        root.focus_force()
        app = CNCManagerApp(root, login_dlg.user_data)
        root.mainloop()
    else:
        root.destroy()
        sys.exit(0)

if __name__ == "__main__":
    main()
