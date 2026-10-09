from __future__ import annotations
import hashlib
import json
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from pydantic import BaseModel, Field

UTC = timezone.utc


def now():
    return datetime.now(UTC)


def canonical(url):
    p = urlsplit(url)
    if p.scheme != 'https' or not p.hostname:
        raise ValueError('Only HTTPS job URLs accepted')
    # Keep semantic IDs such as Indeed jk and Workday query parameters.
    query = [(k, v) for k, v in parse_qsl(p.query) if not k.lower().startswith('utm_') and k not in ('trk', 'trackingId')]
    return urlunsplit(('https', p.netloc.lower(), p.path.rstrip('/'), urlencode(sorted(query)), ''))


class Job(BaseModel):
    title: str
    company: str
    location: str = ''
    url: str
    description: str = ''
    source: str
    posted_at: str | None = None
    time_kind: str = 'unknown'

    @property
    def id(self):
        return hashlib.sha256(canonical(self.url).encode()).hexdigest()[:20]


def freshness(job, at):
    if job.time_kind != 'published_exact' or not job.posted_at:
        return 'unverified'
    try:
        dt = datetime.fromisoformat(job.posted_at.replace('Z', '+00:00'))
        if dt.tzinfo is None:
            return 'unverified'
        return 'verified' if at - timedelta(hours=12) <= dt <= at else 'outside_window'
    except ValueError:
        return 'unverified'


def relevant(job):
    return bool(re.search(r'site reliability|\bsre\b|observability|dev\s*ops', job.title, re.I))


class Analysis(BaseModel):
    score: int = Field(ge=0, le=100)
    location_eligible: bool
    location_reason: str
    missing_skills: list[str]
    rationale: str
    # Extractive tailoring: exact original paragraphs are appended as highlights.
    highlight_ids: list[int] = Field(max_length=5)


class Store:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS jobs (
          id TEXT PRIMARY KEY, payload TEXT NOT NULL, first_seen TEXT NOT NULL,
          freshness TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'discovered',
          analysis TEXT, resume TEXT, emailed_at TEXT, applied_at TEXT, evidence TEXT);
        ''')

    def add(self, job, at):
        self.db.execute('INSERT OR IGNORE INTO jobs(id,payload,first_seen,freshness) VALUES(?,?,?,?)',
                        (job.id, job.model_dump_json(), at.isoformat(), freshness(job, at)))
        # Enrich rediscovered records without resetting submission/digest state.
        self.db.execute("UPDATE jobs SET payload=? WHERE id=? AND status IN ('discovered','analysis_error','time_unverified')",
                        (job.model_dump_json(), job.id))
        self.db.commit()

    def rows(self):
        return self.db.execute('SELECT * FROM jobs ORDER BY first_seen DESC').fetchall()

    def update(self, id, **values):
        allowed = {'status', 'analysis', 'resume', 'emailed_at', 'applied_at', 'evidence', 'freshness'}
        if not values or not values.keys() <= allowed:
            raise ValueError('Invalid state update')
        self.db.execute('UPDATE jobs SET ' + ','.join(f'{k}=?' for k in values) + ' WHERE id=?', (*values.values(), id))
        self.db.commit()

    def get(self, id):
        row = self.db.execute('SELECT * FROM jobs WHERE id=?', (id,)).fetchone()
        if row is None:
            raise ValueError('Unknown job ID')
        return row
