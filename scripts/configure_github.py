"""Run locally after gh auth login and job-agent init; sends secrets via stdin."""
import base64
import gzip
import os
from pathlib import Path
import subprocess
import yaml
from cryptography.fernet import Fernet

root = Path(__file__).resolve().parents[1]
profile_path = root / 'profile.yaml'
profile = yaml.safe_load(profile_path.read_text())
repo = 'Manikumar09/AI-Agent-for-jobs'
profile['answers']['location'] = 'Hyderabad'
profile['answers']['notice_period'] = '60 days'
profile['answers']['expected_salary'] = 'INR 12–14 lakh annual CTC; negotiable within this range based on the role budget'
profile['salary_preference'] = {'currency': 'INR', 'period': 'annual_ctc', 'minimum_lpa': 12, 'maximum_lpa': 14, 'unit_confirmed': True}
# Recipient and Gmail sender default to the reviewed resume email.
email = profile['answers']['email']
if not email: raise SystemExit('Review and fill the profile email first')
print('Review profile.yaml, including rating platform/company evidence, before enabling scheduling.')
profile_path.write_text(yaml.safe_dump(profile, sort_keys=False, allow_unicode=True))
os.chmod(profile_path, 0o600)
resume = base64.b64encode(gzip.compress((root / profile['resume']).read_bytes())).decode()
if len(resume.encode()) > 47000:
    raise SystemExit('Compressed resume exceeds GitHub secret limit; reduce embedded images first')
key_path = root / 'private/state-key'
if not key_path.exists():
    key_path.write_bytes(Fernet.generate_key())
    os.chmod(key_path, 0o600)
for name, value in {'PROFILE_YAML': profile_path.read_text(), 'RESUME_GZIP_B64': resume,
                    'STATE_KEY': key_path.read_text(), 'GMAIL_ADDRESS': email}.items():
    subprocess.run(['gh', 'secret', 'set', name, '--repo', repo], input=value, text=True, check=True)
print('Private configuration uploaded. Back up private/state-key securely; do not rotate it while checkpoints use it.')
print('Add GEMINI_API_KEY and GMAIL_APP_PASSWORD in repository Secrets. Complete the README activation steps.')
