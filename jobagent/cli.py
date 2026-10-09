import argparse
import json
import os
import shutil
from pathlib import Path
from dotenv import load_dotenv
import yaml
from .core import Store, Job, now, freshness, relevant


def run(config, root, dry_run, fixture=None):
    from .tailor import facts, analyze, render
    from .digest import build, send
    root.mkdir(parents=True, exist_ok=True)
    # Dry-run state is isolated; it never consumes production deduplication/email state.
    work = root / ('dry-run' if dry_run else 'state')
    store = Store(work / 'jobs.db')
    at = now()
    if fixture:
        jobs = [Job.model_validate(j) for j in json.loads(Path(fixture).read_text())]
        errors = []
    else:
        from .sources import discover
        jobs, errors = discover(config)
    for job in jobs:
        try:
            if relevant(job):
                store.add(job, at)
        except ValueError:
            errors.append(f'{job.source}: invalid URL')
    source = facts(root / config['resume'])
    output = work / 'output'
    output.mkdir(parents=True, exist_ok=True)
    attempted = 0
    for row in store.rows():
        if row['status'] not in ('discovered', 'analysis_error', 'time_unverified'):
            continue
        job = Job.model_validate_json(row['payload'])
        fresh = freshness(job, at)
        store.update(row['id'], freshness=fresh)
        if fresh == 'outside_window':
            store.update(row['id'], status='outside_window')
            continue
        if fresh == 'unverified' and not config.get('include_unverified', False):
            store.update(row['id'], status='time_unverified')
            continue
        if not job.description.strip():
            errors.append(f'{job.id}: description missing; will retry discovery next run')
            continue
        if attempted >= config['max_jobs_per_run']:
            break
        attempted += 1
        if dry_run:
            # No fabricated AI result in offline test mode.
            store.update(row['id'], status='dry_run_candidate')
            continue
        try:
            analysis = analyze(job, source, config)
            if analysis.score < config['minimum_score'] or not analysis.location_eligible or not analysis.highlight_ids:
                store.update(row['id'], status='not_selected', analysis=analysis.model_dump_json())
                continue
            path = output / f'resume-{job.id}.docx'
            render(root / config['resume'], path, analysis, source)
            store.update(row['id'], status='prepared', analysis=analysis.model_dump_json(), resume=str(path.resolve()))
        except Exception as exc:
            store.update(row['id'], status='analysis_error')
            errors.append(f'{job.id}: analysis failed ({type(exc).__name__}); retry next run')
    text, files, pending = build(store, output, at, errors)
    if not dry_run:
        send(text, files)
        for row in pending:
            store.update(row['id'], emailed_at=at.isoformat())
    print(f'Processed {len(jobs)} source results; {len(pending)} prepared resumes; {len(errors)} errors. Report: {output}')
    for error in errors:
        print(error)
    if jobs == [] and errors:
        raise SystemExit('All discovery results empty with source errors; check source health')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--home', default=os.getenv('JOB_AGENT_HOME') or '.')
    sub = parser.add_subparsers(dest='command', required=True)
    init = sub.add_parser('init')
    init.add_argument('--resume', required=True)
    r = sub.add_parser('run')
    r.add_argument('--dry-run', action='store_true')
    r.add_argument('--fixture')
    sub.add_parser('list')
    a = sub.add_parser('apply'); a.add_argument('id')
    mark = sub.add_parser('mark-applied'); mark.add_argument('id'); mark.add_argument('--evidence', required=True)
    args = parser.parse_args()
    root = Path(args.home).resolve()
    load_dotenv(root / '.env')
    if args.command == 'init':
        root.mkdir(parents=True, exist_ok=True)
        target = root / 'private/resume.docx'
        if target.exists() or (root / 'profile.yaml').exists():
            parser.error('Profile already exists; refusing to overwrite')
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(args.resume, target)
        sample = Path(__file__).resolve().parents[1] / 'profile.example.yaml'
        config = yaml.safe_load(sample.read_text())
        # Contacts are extracted locally for review and never sent to Gemini.
        from docx import Document
        import re
        paragraphs = Document(target).paragraphs
        text = '\n'.join(p.text for p in paragraphs)
        config['answers']['full_name'] = paragraphs[0].text.strip()
        email = re.search(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', text)
        phone = re.search(r'\+\d[\d -]{9,}\d', text)
        linkedin = re.search(r'(?:https?://)?(?:www\.)?linkedin\.com/in/[\w-]+', text)
        if email: config['answers']['email'] = email.group()
        if phone: config['answers']['phone'] = phone.group()
        if linkedin: config['answers']['linkedin'] = 'https://' + linkedin.group().removeprefix('https://').removeprefix('http://')
        (root / 'profile.yaml').write_text(yaml.safe_dump(config, sort_keys=False))
        os.chmod(root / 'profile.yaml', 0o600)
        os.chmod(target, 0o600)
        print('Local profile created. Review contact extraction and fill unanswered fields in profile.yaml.')
        return
    config = yaml.safe_load((root / 'profile.yaml').read_text())
    if args.command == 'run':
        import fcntl
        with (root / '.run.lock').open('w') as lock:
            try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError: raise SystemExit('Another run is active')
            run(config, root, args.dry_run, args.fixture)
        return
    store = Store(root / 'state/jobs.db')
    if args.command == 'list':
        for row in store.rows():
            j = Job.model_validate_json(row['payload'])
            print(row['id'], row['status'], row['freshness'], j.title, j.company, j.url)
    elif args.command == 'apply':
        from .apply import assist
        assist(store, args.id, config)
    elif args.command == 'mark-applied':
        row = store.get(args.id)
        if row['status'] not in ('prepared', 'prefilled'):
            parser.error('Only prepared/prefilled jobs can be confirmed as applied')
        if not args.evidence.strip():
            parser.error('A confirmation reference is required')
        if input('Type SUBMITTED to confirm you submitted this application: ') == 'SUBMITTED':
            store.update(args.id, status='applied', applied_at=now().isoformat(), evidence=args.evidence)


if __name__ == '__main__':
    main()
