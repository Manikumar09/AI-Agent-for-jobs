"""Headed assisted filling. No submit clicks or generated screening answers."""
import json
import re
from pathlib import Path
from urllib.parse import urlsplit
from .core import Job

LABELS = {
    'first_name': r'^first name\s*\*?$', 'last_name': r'^last name\s*\*?$',
    'full_name': r'^(full name|name)\s*\*?$', 'email': r'^email( address)?\s*\*?$',
    'phone': r'^(phone|phone number|mobile number)\s*\*?$',
    'linkedin': r'^linkedin( profile| url| profile url)?\s*\*?$',
}


def allowed_host(host):
    host = (host or '').lower()
    return any(host == h or host.endswith('.' + h) for h in
               ('greenhouse.io', 'lever.co', 'myworkdayjobs.com', 'linkedin.com', 'indeed.com', 'naukri.com', 'indeed.co.in'))


def prefill(page, answers):
    filled, missing = [], []
    for key, pattern in LABELS.items():
        if not answers.get(key):
            continue
        field = page.get_by_label(re.compile(pattern, re.I))
        if field.count() == 1 and field.is_visible() and field.is_editable():
            field.fill(str(answers[key]))
            filled.append(key)
        else:
            missing.append(key)
    return filled, missing


def assist(store, id, config):
    from playwright.sync_api import sync_playwright
    row = store.get(id)
    if row['status'] not in ('prepared', 'prefilled'):
        raise ValueError('Job must have a reviewed prepared resume first')
    job = Job.model_validate_json(row['payload'])
    if urlsplit(job.url).scheme != 'https' or not allowed_host(urlsplit(job.url).hostname):
        raise ValueError('Unrecognized application host; review and open the URL manually')
    resume = Path(row['resume'])
    if not resume.is_file():
        raise ValueError('Tailored resume missing')
    print('Review the DOCX first:', resume)
    if input('Type REVIEWED to open the application: ') != 'REVIEWED':
        return
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto(job.url, wait_until='domcontentloaded', timeout=60000)
        input('Log in / navigate to the application yourself. Press Enter when the form is visible: ')
        if not allowed_host(urlsplit(page.url).hostname):
            raise ValueError('Application redirected to an unrecognized host')
        filled, missing = prefill(page, config['answers'])
        print('Filled:', ', '.join(filled), '| Manual fields:', ', '.join(missing))
        # File upload can itself transmit personal data, so it follows the user's review.
        upload = page.get_by_label(re.compile(r'^resume\s*\*?$', re.I))
        if upload.count() == 1 and upload.evaluate('(e) => e.type') == 'file':
            upload.set_input_files(str(resume.resolve()))
        else:
            print('Upload the resume manually:', resume)
        store.update(id, status='prefilled')
        print('Review all fields and answer screening questions yourself. The helper NEVER clicks Submit.')
        input('Submit in the browser only if you approve. Press Enter to close the helper: ')
        browser.close()
    print('After a confirmed submission, run: job-agent mark-applied', id, '--evidence "confirmation reference"')
