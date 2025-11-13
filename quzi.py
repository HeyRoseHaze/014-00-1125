import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog
import sqlite3
import json
import os
from datetime import datetime, timezone

DB_PATH = os.path.join(os.path.dirname(__file__), 'quizlet_clone_data.db')

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
    CREATE TABLE IF NOT EXISTS decks (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    ''')
    c.execute('''
    CREATE TABLE IF NOT EXISTS cards (
        id INTEGER PRIMARY KEY,
        deck_id INTEGER NOT NULL,
        front TEXT,
        back TEXT,
        correct_count INTEGER DEFAULT 0,
        seen_count INTEGER DEFAULT 0,
        created_at TEXT,
        FOREIGN KEY(deck_id) REFERENCES decks(id) ON DELETE CASCADE
    )
    ''')
    conn.commit()
    return conn

class Model:
    def __init__(self, conn):
        self.conn = conn

    def all_decks(self):
        c = self.conn.cursor()
        c.execute('SELECT id, name FROM decks ORDER BY name')
        return c.fetchall()

    def add_deck(self, name):
        c = self.conn.cursor()
        c.execute('INSERT INTO decks (name, created_at) VALUES (?, ?)', (name, datetime.now(timezone.utc).isoformat()))
        self.conn.commit()
        return c.lastrowid

    def rename_deck(self, deck_id, new_name):
        c = self.conn.cursor()
        c.execute('UPDATE decks SET name=? WHERE id=?', (new_name, deck_id))
        self.conn.commit()

    def delete_deck(self, deck_id):
        c = self.conn.cursor()
        c.execute('DELETE FROM cards WHERE deck_id=?', (deck_id,))
        c.execute('DELETE FROM decks WHERE id=?', (deck_id,))
        self.conn.commit()

    def cards_in_deck(self, deck_id):
        c = self.conn.cursor()
        c.execute('SELECT id, front, back, correct_count, seen_count FROM cards WHERE deck_id=? ORDER BY id', (deck_id,))
        return c.fetchall()

    def add_card(self, deck_id, front, back):
        c = self.conn.cursor()
        c.execute('INSERT INTO cards (deck_id, front, back, created_at) VALUES (?, ?, ?, ?)', (deck_id, front, back, datetime.now(timezone.utc).isoformat()))
        self.conn.commit()
        return c.lastrowid

    def update_card(self, card_id, front, back):
        c = self.conn.cursor()
        c.execute('UPDATE cards SET front=?, back=? WHERE id=?', (front, back, card_id))
        self.conn.commit()

    def delete_card(self, card_id):
        c = self.conn.cursor()
        c.execute('DELETE FROM cards WHERE id=?', (card_id,))
        self.conn.commit()

    def record_result(self, card_id, correct):
        c = self.conn.cursor()
        if correct:
            c.execute('UPDATE cards SET correct_count = correct_count + 1, seen_count = seen_count + 1 WHERE id=?', (card_id,))
        else:
            c.execute('UPDATE cards SET seen_count = seen_count + 1 WHERE id=?', (card_id,))
        self.conn.commit()

    def export_deck_json(self, deck_id, path):
        c = self.conn.cursor()
        c.execute('SELECT name FROM decks WHERE id=?', (deck_id,))
        row = c.fetchone()
        if not row:
            raise ValueError('Deck not found')
        deck_name = row[0]
        c.execute('SELECT front, back, correct_count, seen_count, created_at FROM cards WHERE deck_id=?', (deck_id,))
        cards = [dict(front=r[0], back=r[1], correct_count=r[2], seen_count=r[3], created_at=r[4]) for r in c.fetchall()]
        payload = dict(name=deck_name, exported_at=datetime.now(timezone.utc).isoformat(), cards=cards)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    def import_deck_json(self, path):
        with open(path, 'r', encoding='utf-8') as f:
            payload = json.load(f)
        name = payload.get('name') or f'Deck {datetime.now(timezone.utc).isoformat()}'
        deck_id = self.add_deck(name)
        for card in payload.get('cards', []):
            self.add_card(deck_id, card.get('front',''), card.get('back',''))
        return deck_id



class App(tk.Tk):
    def __init__(self, model):
        super().__init__()
        self.title('Quizlet Clone (Tkinter)')
        self.geometry('900x500')
        self.model = model
        self.selected_deck_id = None
        self.selected_card_id = None
        self.study_queue = []

        self.create_widgets()
        self.load_decks()

    def create_widgets(self):

        menubar = tk.Menu(self)
        filemenu = tk.Menu(menubar, tearoff=0)
        filemenu.add_command(label='Import deck (JSON)...', command=self.import_deck)
        filemenu.add_command(label='Export selected deck (JSON)...', command=self.export_deck)
        filemenu.add_separator()
        filemenu.add_command(label='Exit', command=self.quit)
        menubar.add_cascade(label='File', menu=filemenu)
        studymenu = tk.Menu(menubar, tearoff=0)
        studymenu.add_command(label='Start study of selected deck', command=self.start_study)
        menubar.add_cascade(label='Study', menu=studymenu)
        self.config(menu=menubar)


        left = ttk.Frame(self, width=200)
        left.pack(side='left', fill='y', padx=6, pady=6)
        middle = ttk.Frame(self)
        middle.pack(side='left', fill='both', expand=True, padx=6, pady=6)
        right = ttk.Frame(self, width=300)
        right.pack(side='right', fill='y', padx=6, pady=6)


        ttk.Label(left, text='Decks').pack(anchor='w')
        self.decks_list = tk.Listbox(left)
        self.decks_list.pack(fill='y', expand=True)
        self.decks_list.bind('<<ListboxSelect>>', self.on_deck_select)
        btns = ttk.Frame(left)
        btns.pack(fill='x')
        ttk.Button(btns, text='Add', command=self.add_deck).pack(side='left', fill='x', expand=True)
        ttk.Button(btns, text='Rename', command=self.rename_deck).pack(side='left', fill='x', expand=True)
        ttk.Button(btns, text='Delete', command=self.delete_deck).pack(side='left', fill='x', expand=True)


        ttk.Label(middle, text='Cards in deck').pack(anchor='w')
        self.cards_list = tk.Listbox(middle)
        self.cards_list.pack(fill='both', expand=True)
        self.cards_list.bind('<<ListboxSelect>>', self.on_card_select)


        ttk.Label(right, text='Card editor').pack(anchor='w')
        ttk.Label(right, text='Front').pack(anchor='w')
        self.front_text = tk.Text(right, height=6, width=40)
        self.front_text.pack()
        ttk.Label(right, text='Back').pack(anchor='w')
        self.back_text = tk.Text(right, height=6, width=40)
        self.back_text.pack()
        ebtns = ttk.Frame(right)
        ebtns.pack(fill='x', pady=6)
        ttk.Button(ebtns, text='Add Card', command=self.add_card).pack(side='left', fill='x', expand=True)
        ttk.Button(ebtns, text='Update Card', command=self.update_card).pack(side='left', fill='x', expand=True)
        ttk.Button(ebtns, text='Delete Card', command=self.delete_card).pack(side='left', fill='x', expand=True)


    def load_decks(self):
        self.decks_list.delete(0, tk.END)
        self.decks = self.model.all_decks()
        for deck in self.decks:
            self.decks_list.insert(tk.END, deck[1])

    def add_deck(self):
        name = simpledialog.askstring('New deck', 'Deck name:')
        if name:
            self.model.add_deck(name)
            self.load_decks()

    def rename_deck(self):
        sel = self.decks_list.curselection()
        if not sel:
            messagebox.showinfo('Info', 'Select a deck first')
            return
        i = sel[0]
        deck_id, deck_name = self.decks[i]
        new_name = simpledialog.askstring('Rename deck', 'New name:', initialvalue=deck_name)
        if new_name:
            self.model.rename_deck(deck_id, new_name)
            self.load_decks()

    def delete_deck(self):
        sel = self.decks_list.curselection()
        if not sel:
            messagebox.showinfo('Info', 'Select a deck first')
            return
        i = sel[0]
        deck_id, deck_name = self.decks[i]
        if messagebox.askyesno('Delete', f'Delete deck "{deck_name}" and all its cards?'):
            self.model.delete_deck(deck_id)
            self.selected_deck_id = None
            self.load_decks()
            self.cards_list.delete(0, tk.END)

    def on_deck_select(self, evt=None):
        sel = self.decks_list.curselection()
        if not sel:
            return
        i = sel[0]
        self.selected_deck_id = self.decks[i][0]
        self.load_cards(self.selected_deck_id)

    # ---------- Card actions ----------
    def load_cards(self, deck_id):
        self.cards_list.delete(0, tk.END)
        self.cards = self.model.cards_in_deck(deck_id)
        for c in self.cards:
            # show front (shortened)
            front = c[1] or ''
            preview = front.replace('\n', ' ')[:60]
            stats = f" (✓{c[3]} / seen {c[4]})"
            self.cards_list.insert(tk.END, preview + stats)

    def on_card_select(self, evt=None):
        sel = self.cards_list.curselection()
        if not sel:
            return
        i = sel[0]
        card = self.cards[i]
        self.selected_card_id = card[0]
        self.front_text.delete('1.0', tk.END)
        self.front_text.insert('1.0', card[1] or '')
        self.back_text.delete('1.0', tk.END)
        self.back_text.insert('1.0', card[2] or '')

    def add_card(self):
        if not self.selected_deck_id:
            messagebox.showinfo('Info', 'Select a deck first')
            return
        front = self.front_text.get('1.0', tk.END).strip()
        back = self.back_text.get('1.0', tk.END).strip()
        if not front and not back:
            messagebox.showinfo('Info', 'Card is empty')
            return
        self.model.add_card(self.selected_deck_id, front, back)
        self.load_cards(self.selected_deck_id)

    def update_card(self):
        if not self.selected_card_id:
            messagebox.showinfo('Info', 'Select a card first')
            return
        front = self.front_text.get('1.0', tk.END).strip()
        back = self.back_text.get('1.0', tk.END).strip()
        self.model.update_card(self.selected_card_id, front, back)
        self.load_cards(self.selected_deck_id)

    def delete_card(self):
        if not self.selected_card_id:
            messagebox.showinfo('Info', 'Select a card first')
            return
        if messagebox.askyesno('Delete', 'Delete selected card?'):
            self.model.delete_card(self.selected_card_id)
            self.selected_card_id = None
            self.load_cards(self.selected_deck_id)


    def export_deck(self):
        if not self.selected_deck_id:
            messagebox.showinfo('Info', 'Select a deck to export')
            return
        path = filedialog.asksaveasfilename(defaultextension='.json', filetypes=[('JSON files','*.json')])
        if not path:
            return
        try:
            self.model.export_deck_json(self.selected_deck_id, path)
            messagebox.showinfo('Exported', 'Deck exported successfully')
        except Exception as e:
            messagebox.showerror('Error', str(e))

    def import_deck(self):
        path = filedialog.askopenfilename(filetypes=[('JSON files','*.json')])
        if not path:
            return
        try:
            deck_id = self.model.import_deck_json(path)
            messagebox.showinfo('Imported', 'Deck imported successfully')
            self.load_decks()
        except Exception as e:
            messagebox.showerror('Error', str(e))


    def start_study(self):
        if not self.selected_deck_id:
            messagebox.showinfo('Info', 'Select a deck to study')
            return

        cards = self.model.cards_in_deck(self.selected_deck_id)
        if not cards:
            messagebox.showinfo('Info', 'Selected deck has no cards')
            return

        self.study_queue = [{'id':c[0], 'front':c[1], 'back':c[2]} for c in cards]
        StudyWindow(self, self.model)

class StudyWindow(tk.Toplevel):
    def __init__(self, parent, model):
        super().__init__(parent)
        self.title('Study')
        self.geometry('600x400')
        self.parent = parent
        self.model = model
        self.queue = parent.study_queue.copy()
        self.current = None

        self.create_widgets()
        self.next_card()

    def create_widgets(self):
        self.front_lbl = tk.Label(self, text='', font=('Arial', 18), wraplength=560, justify='center')
        self.front_lbl.pack(pady=20, padx=10, expand=True)
        btns = ttk.Frame(self)
        btns.pack(pady=6)
        ttk.Button(btns, text='Flip', command=self.flip).pack(side='left', padx=6)
        ttk.Button(btns, text='Correct', command=lambda: self.mark(True)).pack(side='left', padx=6)
        ttk.Button(btns, text='Incorrect', command=lambda: self.mark(False)).pack(side='left', padx=6)
        ttk.Button(btns, text='Close', command=self.destroy).pack(side='left', padx=6)
        self.back_shown = False

    def next_card(self):
        if not self.queue:
            messagebox.showinfo('Done', 'You finished the queue!')
            self.destroy()
            return
        self.current = self.queue.pop(0)
        self.front_lbl.config(text=self.current['front'] or '(empty)')
        self.back_shown = False

    def flip(self):
        if not self.current:
            return
        if not self.back_shown:
            self.front_lbl.config(text=self.current['back'] or '(empty)')
            self.back_shown = True
        else:
            self.front_lbl.config(text=self.current['front'] or '(empty)')
            self.back_shown = False

    def mark(self, correct):
        if not self.current:
            return
        self.model.record_result(self.current['id'], correct)
        if correct:

            pass
        else:

            self.queue.append(self.current)
        self.next_card()



if __name__ == '__main__':
    conn = init_db()
    model = Model(conn)
    app = App(model)
    app.mainloop()
    conn.close()
