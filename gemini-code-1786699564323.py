import sys
import os
import sqlite3
import multiprocessing
import tkinter as tk
from tkinter import ttk, messagebox

# --- OBLIGATOIRE EN TOUT PREMIER POUR PYINSTALLER SOUS WINDOWS ---
if __name__ == '__main__':
    multiprocessing.freeze_support()

DB_FILE = "cnc_manager.db"

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
        CREATE TABLE IF NOT EXISTS cnc_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            operator TEXT NOT NULL,
            machine TEXT NOT NULL,
            part_name TEXT NOT NULL,
            status TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute("SELECT COUNT(*) FROM users")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO users (username, password, role) VALUES ('admin', 'admin123', 'Admin')")
        cursor.execute("INSERT INTO users (username, password, role) VALUES ('operateur', 'op123', 'Operateur')")
    conn.commit()
    conn.close()


class CNCApplication(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("CNC Manager")
        self.geometry("400x250")
        
        # Centrer sur l'écran
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

        ttk.Label(self, text="CNC Manager", font=("Arial", 14, "bold")).pack(pady=15)

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

    # --- ÉCRAN PRINCIPAL ---
    def show_main_screen(self):
        self.clear_window()
        self.title(f"CNC Manager - Session : {self.current_user['username']} ({self.current_user['role']})")
        self.geometry("1000x550")

        # Centrage écran principal
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - (1000 // 2)
        y = (self.winfo_screenheight() // 2) - (550 // 2)
        self.geometry(f'1000x550+{x}+{y}')

        # Menu
        menubar = tk.Menu(self)
        menu_file = tk.Menu(menubar, tearoff=0)
        menu_file.add_command(label="Déconnexion", command=self.show_login_screen)
        menu_file.add_separator()
        menu_file.add_command(label="Quitter", command=self.destroy)
        menubar.add_cascade(label="Fichier", menu=menu_file)
        self.config(menu=menubar)

        # Formulaire
        frame_input = ttk.LabelFrame(self, text=" Nouveau suivi CNC ")
        frame_input.pack(fill="x", padx=10, pady=10)

        ttk.Label(frame_input, text="Machine:").grid(row=0, column=0, padx=5, pady=5)
        self.combo_machine = ttk.Combobox(frame_input, values=["NUM 1060", "5-Axes CNC", "Tour CNC", "Fraiseuse"], state="readonly")
        self.combo_machine.current(0)
        self.combo_machine.grid(row=0, column=1, padx=5, pady=5)

        ttk.Label(frame_input, text="Pièce / Fichier:").grid(row=0, column=2, padx=5, pady=5)
        self.entry_part = ttk.Entry(frame_input, width=25)
        self.entry_part.grid(row=0, column=3, padx=5, pady=5)

        ttk.Label(frame_input, text="Statut:").grid(row=0, column=4, padx=5, pady=5)
        self.combo_status = ttk.Combobox(frame_input, values=["En cours", "Terminé", "Maintenance"], state="readonly")
        self.combo_status.current(0)
        self.combo_status.grid(row=0, column=5, padx=5, pady=5)

        ttk.Button(frame_input, text="Enregistrer", command=self.add_log).grid(row=0, column=6, padx=10, pady=5)

        # Tableau
        frame_table = ttk.Frame(self)
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
        self.tree.column("part_name", width=220)
        self.tree.column("status", width=120)
        self.tree.column("timestamp", width=160, anchor="center")

        scrollbar = ttk.Scrollbar(frame_table, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.load_data()

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
            messagebox.showwarning("Attention", "Veuillez préciser le nom de la pièce.")
            return

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO cnc_logs (operator, machine, part_name, status) VALUES (?, ?, ?, ?)",
                       (self.current_user['username'], self.combo_machine.get(), part, self.combo_status.get()))
        conn.commit()
        conn.close()

        self.entry_part.delete(0, tk.END)
        self.load_data()

if __name__ == "__main__":
    init_db()
    app = CNCApplication()
    app.mainloop()
