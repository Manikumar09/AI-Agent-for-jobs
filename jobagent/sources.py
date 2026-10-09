"""Source failures remain visible; no login, CAPTCHA or blocking bypass."""
import html
import re
import requests
from bs4 import BeautifulSoup
from .core import Job


def plain(value):
    return BeautifulSoup(html.unescape(value or ''), 'html.parser').get_text(' ', strip=True)


def get(url, **kw):
    r = requests.get(url, timeout=35, **kw)
    r.raise_for_status()
    return r.json()


def token(value):
    if not re.fullmatch(r'[A-Za-z0-9_-]+', value):
        raise ValueError('Invalid ATS board token')
    return value


def discover(config):
    jobs, errors = [], []
    from jobspy import scrape_jobs
    for site in config['sites']:
        for role in config['roles']:
            for location in config['locations']:
                try:
                    df = scrape_jobs(site_name=[site], search_term=role, location=location,
                                     country_indeed='India', hours_old=12,
                                     results_wanted=config['results_per_search'],
                                     fetch_description=True, linkedin_fetch_description=True)
                    for row in df.to_dict('records'):
                        def s(k):
                            v = row.get(k)
                            return '' if v is None or str(v) in ('nan', 'NaT', 'None') else str(v)
                        posted = s('date_posted')
                        # JobSpy usually normalizes timestamps to a date: do not invent precision.
                        jobs.append(Job(title=s('title'), company=s('company'), location=s('location'),
                                        url=s('job_url'), description=plain(s('description')), source=site,
                                        posted_at=posted or None, time_kind='date_only' if posted else 'unknown'))
                except Exception as exc:
                    errors.append(f'{site}/{role}/{location}: {type(exc).__name__}')
    for board in config.get('greenhouse', []):
        try:
            base = f'https://boards-api.greenhouse.io/v1/boards/{token(board)}/jobs'
            for row in get(base, params={'content': 'true'})['jobs']:
                # List updated_at is not publication time; detail first_published is.
                from .core import relevant
                j = Job(title=row['title'], company=board, location=row['location']['name'],
                        url=row['absolute_url'], description=plain(row.get('content')), source='greenhouse')
                if relevant(j):
                    detail = get(f'{base}/{row["id"]}')
                    j.posted_at = detail.get('first_published')
                    j.time_kind = 'published_exact' if j.posted_at else 'unknown'
                    jobs.append(j)
        except Exception as exc:
            errors.append(f'greenhouse/{board}: {type(exc).__name__}')
    for board in config.get('lever', []):
        try:
            skip = 0
            while True:
                rows = get(f'https://api.lever.co/v0/postings/{token(board)}', params={'mode': 'json', 'skip': skip, 'limit': 100})
                for r in rows:
                    description = plain(r.get('description')) + ' ' + ' '.join(plain(x.get('content')) for x in r.get('lists', []))
                    jobs.append(Job(title=r['text'], company=board, location=r.get('categories', {}).get('location', ''),
                                    url=r.get('applyUrl') or r['hostedUrl'], description=description, source='lever'))
                if len(rows) < 100:
                    break
                skip += 100
        except Exception as exc:
            errors.append(f'lever/{board}: {type(exc).__name__}')
    for cfg in config.get('workday', []):
        try:
            host = cfg['host']
            if not re.fullmatch(r'[a-z0-9-]+\.wd\d+\.myworkdayjobs\.com', host):
                raise ValueError('Invalid Workday host')
            tenant, site = token(cfg['tenant']), token(cfg['site'])
            for role in config['roles']:
                offset = 0
                while True:
                    base = f'https://{host}/wday/cxs/{tenant}/{site}'
                    response = requests.post(base + '/jobs', json={'appliedFacets': {}, 'limit': 20, 'offset': offset, 'searchText': role}, timeout=35)
                    response.raise_for_status()
                    data = response.json()
                    for r in data.get('jobPostings', []):
                        detail = get(base + r['externalPath']).get('jobPostingInfo', {})
                        posted = detail.get('startDate')
                        jobs.append(Job(title=r['title'], company=tenant, location=r.get('locationsText', ''),
                                        url=f'https://{host}/en-US/{site}' + r['externalPath'],
                                        description=plain(detail.get('jobDescription')), source='workday',
                                        posted_at=posted, time_kind='date_only' if posted else 'unknown'))
                    offset += 20
                    if offset >= data.get('total', 0) or not data.get('jobPostings'):
                        break
        except Exception as exc:
            errors.append(f'workday/{cfg.get("tenant")}: {type(exc).__name__}')
    return jobs, errors
