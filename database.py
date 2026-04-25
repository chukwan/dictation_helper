import sqlite3
import os
from datetime import datetime

DB_NAME = "dictation_buddy.db"
RECORDINGS_DIR = "recordings"


def _get_connection():
    """Returns a SQLite connection with row_factory and foreign keys enabled."""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _to_relative_path(abs_path):
    """Converts an absolute path to a relative path from the current working directory."""
    if abs_path and os.path.isabs(abs_path):
        try:
            return os.path.relpath(abs_path, os.getcwd())
        except ValueError:
            return abs_path  # Different drive on Windows, keep absolute
    return abs_path


def _to_absolute_path(rel_path):
    """Converts a relative path back to absolute for file operations."""
    if rel_path and not os.path.isabs(rel_path):
        return os.path.join(os.getcwd(), rel_path)
    return rel_path


def _delete_audio_files(vocab_path, passage_path):
    """Safely deletes audio files from disk."""
    for path in (vocab_path, passage_path):
        if path:
            abs_path = _to_absolute_path(path)
            if abs_path and os.path.exists(abs_path):
                try:
                    os.remove(abs_path)
                except OSError as e:
                    print(f"Warning: Could not delete audio file {abs_path}: {e}")


def init_db():
    """Initializes the SQLite database and creates tables if they don't exist."""
    conn = _get_connection()
    try:
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
            pass  # Column already exists

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

        # Migration: convert absolute paths to relative paths
        try:
            cursor.execute('SELECT id, vocab_audio_path, passage_audio_path FROM sessions')
            for row in cursor.fetchall():
                new_vocab = _to_relative_path(row['vocab_audio_path']) if row['vocab_audio_path'] else row['vocab_audio_path']
                new_passage = _to_relative_path(row['passage_audio_path']) if row['passage_audio_path'] else row['passage_audio_path']
                if new_vocab != row['vocab_audio_path'] or new_passage != row['passage_audio_path']:
                    cursor.execute(
                        'UPDATE sessions SET vocab_audio_path=?, passage_audio_path=? WHERE id=?',
                        (new_vocab, new_passage, row['id'])
                    )
        except Exception:
            pass  # Non-critical migration

        conn.commit()
    finally:
        conn.close()


def save_session(name, vocab_list, vocab_audio_path, sentences, passage_audio_path, language="en"):
    """Saves a dictation session to the database."""
    conn = _get_connection()
    try:
        cursor = conn.cursor()

        # Store relative paths
        rel_vocab_path = _to_relative_path(vocab_audio_path)
        rel_passage_path = _to_relative_path(passage_audio_path)

        cursor.execute('''
            INSERT INTO sessions (name, vocab_audio_path, passage_audio_path, language)
            VALUES (?, ?, ?, ?)
        ''', (name, rel_vocab_path, rel_passage_path, language))
        session_id = cursor.lastrowid

        if vocab_list:
            for word in vocab_list:
                cursor.execute('INSERT INTO vocabulary (session_id, word) VALUES (?, ?)', (session_id, word))

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
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM sessions ORDER BY created_at DESC')
        sessions = []
        for row in cursor.fetchall():
            session = dict(row)
            session['vocab_audio_path'] = _to_absolute_path(session.get('vocab_audio_path'))
            session['passage_audio_path'] = _to_absolute_path(session.get('passage_audio_path'))
            sessions.append(session)
        return sessions
    except Exception as e:
        print(f"Error loading sessions: {e}")
        return []
    finally:
        conn.close()


def get_session_details(session_id):
    """Returns vocabulary and sentences for a specific session."""
    conn = _get_connection()
    try:
        cursor = conn.cursor()

        cursor.execute('SELECT word FROM vocabulary WHERE session_id = ?', (session_id,))
        vocab_list = [row['word'] for row in cursor.fetchall()]

        cursor.execute('SELECT content FROM sentences WHERE session_id = ?', (session_id,))
        sentences = [row['content'] for row in cursor.fetchall()]

        return vocab_list, sentences
    except Exception as e:
        print(f"Error loading session details for id={session_id}: {e}")
        return [], []
    finally:
        conn.close()


def get_session_by_id(session_id):
    """Returns full session metadata."""
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM sessions WHERE id = ?', (session_id,))
        row = cursor.fetchone()
        if row:
            session = dict(row)
            session['vocab_audio_path'] = _to_absolute_path(session.get('vocab_audio_path'))
            session['passage_audio_path'] = _to_absolute_path(session.get('passage_audio_path'))
            return session
        return None
    except Exception as e:
        print(f"Error loading session id={session_id}: {e}")
        return None
    finally:
        conn.close()


def update_session(session_id, vocab_list, vocab_audio_path, sentences, passage_audio_path, language):
    """Updates an existing session, cleaning up old audio files if paths changed."""
    conn = _get_connection()
    try:
        cursor = conn.cursor()

        # Fetch old paths before updating
        cursor.execute('SELECT vocab_audio_path, passage_audio_path FROM sessions WHERE id = ?', (session_id,))
        old = cursor.fetchone()
        old_vocab = old['vocab_audio_path'] if old else None
        old_passage = old['passage_audio_path'] if old else None

        # Store relative paths
        rel_vocab_path = _to_relative_path(vocab_audio_path)
        rel_passage_path = _to_relative_path(passage_audio_path)

        # Update session metadata
        cursor.execute('''
            UPDATE sessions
            SET vocab_audio_path = ?, passage_audio_path = ?, language = ?
            WHERE id = ?
        ''', (rel_vocab_path, rel_passage_path, language, session_id))

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

        # Clean up old audio files if paths changed
        if old_vocab and old_vocab != rel_vocab_path:
            _delete_audio_files(old_vocab, None)
        if old_passage and old_passage != rel_passage_path:
            _delete_audio_files(None, old_passage)

    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def delete_session(session_id):
    """Deletes a session, its associated data, and audio files from disk."""
    conn = _get_connection()
    try:
        cursor = conn.cursor()

        # Fetch audio paths before deleting
        cursor.execute('SELECT vocab_audio_path, passage_audio_path FROM sessions WHERE id = ?', (session_id,))
        row = cursor.fetchone()
        vocab_path = row['vocab_audio_path'] if row else None
        passage_path = row['passage_audio_path'] if row else None

        # Delete DB records
        cursor.execute('DELETE FROM vocabulary WHERE session_id = ?', (session_id,))
        cursor.execute('DELETE FROM sentences WHERE session_id = ?', (session_id,))
        cursor.execute('DELETE FROM sessions WHERE id = ?', (session_id,))
        conn.commit()

        # Clean up audio files after successful DB delete
        _delete_audio_files(vocab_path, passage_path)

    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def cleanup_orphaned_files():
    """Removes audio files in recordings/ that are not referenced by any session."""
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute('SELECT vocab_audio_path, passage_audio_path FROM sessions')
        db_files = set()
        for row in cursor.fetchall():
            if row['vocab_audio_path']:
                db_files.add(os.path.basename(row['vocab_audio_path']))
            if row['passage_audio_path']:
                db_files.add(os.path.basename(row['passage_audio_path']))

        recordings_dir = os.path.join(os.getcwd(), RECORDINGS_DIR)
        removed = []
        if os.path.isdir(recordings_dir):
            for f in os.listdir(recordings_dir):
                if f not in db_files:
                    filepath = os.path.join(recordings_dir, f)
                    try:
                        os.remove(filepath)
                        removed.append(f)
                    except OSError as e:
                        print(f"Warning: Could not remove orphaned file {filepath}: {e}")
        return removed
    except Exception as e:
        print(f"Error during orphan cleanup: {e}")
        return []
    finally:
        conn.close()
