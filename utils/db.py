import sqlite3
import os
import csv
import time
from config import SCRIPT_DIR

DB_PATH = os.path.join(SCRIPT_DIR, 'data', 'tags.db')
CSV_PATH = os.path.join(SCRIPT_DIR, 'data', 'tags.csv')

def get_db_connection():
    """Create a database connection to the SQLite database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize the database and import tags if needed."""
    db_exists = os.path.exists(DB_PATH)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Create table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            post_count INTEGER DEFAULT 0
        )
    ''')
    
    # Create indices for performance
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_category_count ON tags(category, post_count DESC)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_name ON tags(name)')
    
    conn.commit()
    
    # Check if we need to import data
    cursor.execute('SELECT COUNT(*) FROM tags')
    count = cursor.fetchone()[0]
    
    if count == 0 and os.path.exists(CSV_PATH):
        print(f"[DB] Database empty. Importing tags from {CSV_PATH}...")
        import_tags_from_csv(conn)
    elif count > 0:
        print(f"[DB] Database initialized with {count} tags.")
        
    conn.close()

def import_tags_from_csv(conn):
    """Import tags from CSV file into the database."""
    start_time = time.time()
    cursor = conn.cursor()
    
    try:
        with open(CSV_PATH, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            to_db = []
            for row in reader:
                to_db.append((
                    row['name'],
                    row['category'],
                    int(row['post_count'])
                ))
            
            cursor.executemany('''
                INSERT INTO tags (name, category, post_count)
                VALUES (?, ?, ?)
            ''', to_db)
            
            conn.commit()
            elapsed = time.time() - start_time
            print(f"[DB] Imported {len(to_db)} tags in {elapsed:.2f} seconds.")
            
    except Exception as e:
        print(f"[DB] Error importing tags: {e}")
        conn.rollback()

def get_tags_by_category(category, limit=40, excluded_tags=None):
    """Get top tags for a category, optionally excluding some."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    query = "SELECT name FROM tags WHERE category = ?"
    params = [category]
    
    if excluded_tags:
        placeholders = ','.join(['?'] * len(excluded_tags))
        query += f" AND name NOT IN ({placeholders})"
        params.extend(excluded_tags)
        
    query += " ORDER BY post_count DESC LIMIT ?"
    params.append(limit)
    
    cursor.execute(query, params)
    tags = [row['name'] for row in cursor.fetchall()]
    
    conn.close()
    return tags
