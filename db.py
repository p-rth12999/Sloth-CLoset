import sqlite3
import os
from typing import List, Dict

DB_PATH = "slothcloset.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS wardrobe (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            color TEXT NOT NULL,
            style_vibe TEXT NOT NULL,
            image_path TEXT,
            is_clean INTEGER DEFAULT 1
        )
    ''')
    conn.commit()
    conn.close()

def add_item(name: str, category: str, color: str, style_vibe: str, image_path: str = "") -> int:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        INSERT INTO wardrobe (name, category, color, style_vibe, image_path, is_clean)
        VALUES (?, ?, ?, ?, ?, 1)
    ''', (name, category, color, style_vibe, image_path))
    item_id = c.lastrowid
    conn.commit()
    conn.close()
    return item_id

def get_all_items() -> List[Dict]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('SELECT * FROM wardrobe ORDER BY id DESC')
    rows = [dict(row) for row in c.fetchall()]
    conn.close()
    return rows

def get_clean_items() -> List[Dict]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('SELECT * FROM wardrobe WHERE is_clean = 1 ORDER BY category')
    rows = [dict(row) for row in c.fetchall()]
    conn.close()
    return rows

def toggle_laundry_status(item_id: int, current_status: int):
    new_status = 0 if current_status == 1 else 1
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('UPDATE wardrobe SET is_clean = ? WHERE id = ?', (new_status, item_id))
    conn.commit()
    conn.close()

def mark_all_clean():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('UPDATE wardrobe SET is_clean = 1')
    conn.commit()
    conn.close()

def delete_item(item_id: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT image_path FROM wardrobe WHERE id = ?', (item_id,))
    row = c.fetchone()
    if row and row[0] and os.path.exists(row[0]):
        try:
            os.remove(row[0])
        except OSError:
            pass
    c.execute('DELETE FROM wardrobe WHERE id = ?', (item_id,))
    conn.commit()
    conn.close()

def seed_demo_wardrobe():
    """One-click lazy population so you can test the Deck Builder immediately."""
    demo_items = [
        ("Mustard Yellow Graphic Tee", "Top", "Mustard Yellow", "Casual / Streetwear", ""),
        ("Oversized Black Hoodie", "Layer / Jacket", "Pitch Black", "Cozy / Sloth Mode", ""),
        ("Olive Green Cargo Pants", "Bottom", "Olive Green", "Casual / Utility", ""),
        ("Classic Blue Relaxed Jeans", "Bottom", "Indigo Blue", "Everyday / Versatile", ""),
        ("Crisp White Oxford Shirt", "Top", "White", "Smart Casual / Date", ""),
        ("Grey Sweatpants", "Bottom", "Heather Grey", "Ultra Lazy / Lecture", ""),
        ("White Low-Top Sneakers", "Footwear", "White", "Clean / Versatile", ""),
        ("Black Canvas Slip-Ons", "Footwear", "Black", "Lazy / Quick Slip-on", "")
    ]
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    for name, cat, col, vibe, img in demo_items:
        c.execute('''
            INSERT INTO wardrobe (name, category, color, style_vibe, image_path, is_clean)
            VALUES (?, ?, ?, ?, ?, 1)
        ''', (name, cat, col, vibe, img))
    conn.commit()
    conn.close()