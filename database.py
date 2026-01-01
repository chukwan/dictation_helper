import sqlite3
import os
from datetime import datetime

DB_NAME = "dictation_buddy.db"

def init_db():
    """Initializes the SQLite database and creates tables if they don't exist."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Sessions table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            vocab_audio_path TEXT,
            passage_audio_path TEXT,
            language TEXT DEFAULT 'en',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Check if language column exists (migration for existing db)
    try:
        cursor.execute('ALTER TABLE sessions ADD COLUMN language TEXT DEFAULT "en"')
    except sqlite3.OperationalError:
        pass # Column already exists
    
    # Vocabulary table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS vocabulary (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER,
            word TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions (id)
        )
    ''')
    
    # Sentences table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sentences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER,
            content TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions (id)
        )
    ''')
    
    conn.commit()
    conn.close()

def save_session(name, vocab_list, vocab_audio_path, sentences, passage_audio_path, language="en"):
    """
    Saves a dictation session to the database.
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    try:
        # Insert session
        cursor.execute('''
            INSERT INTO sessions (name, vocab_audio_path, passage_audio_path, language) 
            VALUES (?, ?, ?, ?)
        ''', (name, vocab_audio_path, passage_audio_path, language))
        session_id = cursor.lastrowid
        
        # Insert vocabulary
        if vocab_list:
            for word in vocab_list:
                cursor.execute('INSERT INTO vocabulary (session_id, word) VALUES (?, ?)', (session_id, word))
            
        # Insert sentences
        if sentences:
            for sentence in sentences:
                cursor.execute('INSERT INTO sentences (session_id, content) VALUES (?, ?)', (session_id, sentence))
            
        conn.commit()
        return session_id
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def get_all_sessions():
    """Returns a list of all sessions ordered by creation date (newest first)."""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM sessions ORDER BY created_at DESC')
    sessions = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return sessions

def get_session_details(session_id):
    """Returns vocabulary and sentences for a specific session."""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute('SELECT word FROM vocabulary WHERE session_id = ?', (session_id,))
    vocab_list = [row['word'] for row in cursor.fetchall()]
    
    cursor.execute('SELECT content FROM sentences WHERE session_id = ?', (session_id,))
    sentences = [row['content'] for row in cursor.fetchall()]
    
    conn.close()
    return vocab_list, sentences

def get_session_by_id(session_id):
    """Returns full session metadata."""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM sessions WHERE id = ?', (session_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def update_session(session_id, vocab_list, vocab_audio_path, sentences, passage_audio_path, language):
    """Updates an existing session."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        # Update session metadata
        cursor.execute('''
            UPDATE sessions 
            SET vocab_audio_path = ?, passage_audio_path = ?, language = ?
            WHERE id = ?
        ''', (vocab_audio_path, passage_audio_path, language, session_id))
        
        # Clear old content
        cursor.execute('DELETE FROM vocabulary WHERE session_id = ?', (session_id,))
        cursor.execute('DELETE FROM sentences WHERE session_id = ?', (session_id,))
        
        # Insert new content
        if vocab_list:
            for word in vocab_list:
                cursor.execute('INSERT INTO vocabulary (session_id, word) VALUES (?, ?)', (session_id, word))
        
        if sentences:
            for sentence in sentences:
                cursor.execute('INSERT INTO sentences (session_id, content) VALUES (?, ?)', (session_id, sentence))
                
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def delete_session(session_id):
    """Deletes a session and its associated data."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute('DELETE FROM vocabulary WHERE session_id = ?', (session_id,))
        cursor.execute('DELETE FROM sentences WHERE session_id = ?', (session_id,))
        cursor.execute('DELETE FROM sessions WHERE id = ?', (session_id,))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()
