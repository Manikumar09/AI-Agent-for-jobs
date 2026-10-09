"""GitHub-hosted bootstrap and encrypted checkpoint transport.

Never uploads plaintext private state. Missing checkpoints fail closed unless an
explicit manual bootstrap is requested. Uses only the current workflow's default-
branch artifacts; untrusted PR artifacts cannot replace production state.
"""
import base64
import gzip
import io
import json
import os
from pathlib import Path
import sys
import zipfile
import requests
import yaml
from cryptography.fernet import Fernet

ROOT = Path(os.environ.get('JOB_AGENT_HOME', '.')).resolve()


def cipher():
    return Fernet(os.environ['STATE_KEY'].encode())


def pack(root):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        for path in (root / 'state').rglob('*'):
            if path.is_file():
                z.write(path, path.relative_to(root).as_posix())
    return cipher().encrypt(buf.getvalue())


def unpack(blob, root):
    raw = cipher().decrypt(blob)
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        for info in z.infolist():
            dest = (root / info.filename).resolve()
            if not dest.is_relative_to((root / 'state').resolve()) or info.file_size > 100_000_000:
                raise ValueError('Invalid checkpoint member')
        z.extractall(root)
    # Runner workspace paths can change between machines/checkouts.
    from jobagent.core import Store
    store = Store(root / 'state/jobs.db')
    for row in store.rows():
        if row['resume']:
            store.update(row['id'], resume=str(root / 'state/output' / Path(row['resume']).name))


def api(path):
    response = requests.get('https://api.github.com/repos/' + os.environ['GITHUB_REPOSITORY'] + path,
                            headers={'Authorization': 'Bearer ' + os.environ['GH_TOKEN'], 'Accept': 'application/vnd.github+json'}, timeout=60)
    response.raise_for_status()
    return response.json()


def restore():
    key = cipher()  # validate before doing any work
    ROOT.mkdir(parents=True, exist_ok=True)
    profile = yaml.safe_load(os.environ['PROFILE_YAML'])
    profile['resume'] = 'private/resume.docx'
    (ROOT / 'profile.yaml').write_text(yaml.safe_dump(profile))
    (ROOT / 'private').mkdir(exist_ok=True)
    (ROOT / 'private/resume.docx').write_bytes(gzip.decompress(base64.b64decode(os.environ['RESUME_GZIP_B64'], validate=True)))
    # Address comes from the reviewed profile, never hard-coded into public code.
    email = profile['answers']['email']
    if not email or '\n' in email or '\r' in email:
        raise ValueError('Valid profile email required')
    with open(os.environ['GITHUB_ENV'], 'a') as f:
        f.write('DIGEST_TO=' + email + '\n')
    branch = os.environ['DEFAULT_BRANCH']
    # Get this workflow's identity, then filter artifacts to its default branch.
    current = api('/actions/runs/' + os.environ['GITHUB_RUN_ID'])
    selected = None
    page = 1
    while not selected:
        artifacts = api(f'/actions/artifacts?name=job-agent-checkpoint&per_page=100&page={page}')['artifacts']
        if not artifacts:
            break
        for a in artifacts:
            run = a.get('workflow_run') or {}
            if a['expired'] or run.get('head_branch') != branch:
                continue
            info = api('/actions/runs/' + str(run['id']))
            if info['workflow_id'] == current['workflow_id'] and info['event'] in ('schedule', 'workflow_dispatch'):
                selected = a
                break
        page += 1
    if selected:
        response = requests.get(selected['archive_download_url'], headers={'Authorization': 'Bearer ' + os.environ['GH_TOKEN']}, timeout=60)
        response.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(response.content)) as z:
            unpack(z.read('checkpoint.enc'), ROOT)
    elif os.environ.get('ALLOW_BOOTSTRAP') != 'true':
        raise RuntimeError('No retained checkpoint. Use an explicit manual bootstrap only after reviewing deduplication loss.')
    else:
        (ROOT / 'state').mkdir(exist_ok=True)
    (ROOT / '.checkpoint-ready').touch()


def confirm():
    from jobagent.core import Store, now
    id = os.environ.get('APPLICATION_ID', '')
    if not id:
        return
    evidence = os.environ.get('APPLICATION_EVIDENCE', '').strip()
    if not evidence:
        raise ValueError('Submission confirmation evidence required')
    store = Store(ROOT / 'state/jobs.db')
    row = store.get(id)
    if row['status'] not in ('prepared', 'prefilled'):
        raise ValueError('Only prepared applications may be confirmed')
    store.update(id, status='applied', applied_at=now().isoformat(), evidence=evidence)


if __name__ == '__main__':
    os.umask(0o077)
    action = sys.argv[1]
    if action == 'restore': restore()
    elif action == 'confirm': confirm()
    elif action == 'save':
        if not (ROOT / '.checkpoint-ready').exists():
            raise RuntimeError('Refusing to replace a checkpoint after restore failure')
        Path('checkpoint.enc').write_bytes(pack(ROOT))
