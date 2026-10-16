"""SQLite records have explicit provenance; no sample product claims are seeded."""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import uuid


def now():
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS products (
                    id TEXT PRIMARY KEY, barcode TEXT UNIQUE, name TEXT NOT NULL,
                    brand TEXT NOT NULL, category TEXT NOT NULL, record TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS uploads (
                    id TEXT PRIMARY KEY, path TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS reference_images (
                    id TEXT PRIMARY KEY, product_id TEXT NOT NULL REFERENCES products(id),
                    upload_id TEXT NOT NULL REFERENCES uploads(id), label TEXT NOT NULL,
                    source_url TEXT NOT NULL, features TEXT NOT NULL, phash TEXT NOT NULL,
                    feature_version TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS reference_product ON reference_images(product_id);
                CREATE TABLE IF NOT EXISTS scans (
                    id TEXT PRIMARY KEY, created_at TEXT NOT NULL, result TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS scan_date ON scans(created_at DESC);
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys = ON')
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def upsert_product(self, record):
        with self.connect() as db:
            db.execute('''INSERT INTO products VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET barcode=excluded.barcode, name=excluded.name,
                brand=excluded.brand, category=excluded.category, record=excluded.record''',
                (record['id'], record.get('barcode'), record['name'], record.get('brand', ''), record.get('category', ''), json.dumps(record)))

    def product(self, product_id):
        with self.connect() as db:
            row = db.execute('SELECT record FROM products WHERE id=?', (product_id,)).fetchone()
        return json.loads(row['record']) if row else None

    def by_barcode(self, barcode):
        with self.connect() as db:
            row = db.execute('SELECT record FROM products WHERE barcode=?', (barcode,)).fetchone()
        return json.loads(row['record']) if row else None

    def products(self, query='', limit=25, offset=0):
        # Literal substring matching: escape LIKE metacharacters and bind all inputs.
        escaped = query.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        pattern = '%' + escaped + '%'
        with self.connect() as db:
            rows = db.execute("SELECT record FROM products WHERE name LIKE ? ESCAPE '\\' OR brand LIKE ? ESCAPE '\\' OR category LIKE ? ESCAPE '\\' ORDER BY id LIMIT ? OFFSET ?", (pattern, pattern, pattern, limit, offset)).fetchall()
        return [json.loads(row['record']) for row in rows]

    def add_upload(self, image_id, path):
        with self.connect() as db:
            db.execute('INSERT INTO uploads VALUES (?, ?, ?)', (image_id, str(path), now()))

    def upload(self, image_id):
        with self.connect() as db:
            row = db.execute('SELECT * FROM uploads WHERE id=?', (image_id,)).fetchone()
        return dict(row) if row else None

    def add_reference(self, record):
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO reference_images VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                (record['id'], record['product_id'], record['upload_id'], record['label'], record['source_url'], json.dumps(record['features']), record['phash'], record['feature_version']))

    def references(self):
        with self.connect() as db:
            rows = db.execute('SELECT * FROM reference_images ORDER BY id').fetchall()
        result = [dict(row) for row in rows]
        for row in result:
            row['features'] = json.loads(row['features'])
        return result

    def save_scan(self, result):
        result = {**result, 'scan_id': uuid.uuid4().hex, 'created_at': now()}
        with self.connect() as db:
            db.execute('INSERT INTO scans VALUES (?, ?, ?)', (result['scan_id'], result['created_at'], json.dumps(result)))
        return result

    def history(self, limit=20, offset=0):
        with self.connect() as db:
            rows = db.execute('SELECT result FROM scans ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?', (limit, offset)).fetchall()
        return [json.loads(row['result']) for row in rows]

    def scan(self, scan_id):
        with self.connect() as db:
            row = db.execute('SELECT result FROM scans WHERE id=?', (scan_id,)).fetchone()
        return json.loads(row['result']) if row else None
