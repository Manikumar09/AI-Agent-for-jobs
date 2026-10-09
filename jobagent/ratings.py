"""Only attributable, recent, exact-company ratings qualify; never LLM guesses."""
from datetime import date


def company_status(company, config, today):
    policy = config.get('company_policy', {})
    if not policy.get('enabled', False):
        return 'eligible'
    source = policy.get('source')
    if source not in ('ambitionbox', 'glassdoor'):
        return 'rating_pending'
    name = company.casefold().strip()
    entry = next((r for r in policy.get('verified_ratings', [])
                  if name in [str(x).casefold().strip() for x in [r.get('company', ''), *r.get('aliases', [])]]), None)
    if not entry or entry.get('source') != source or not entry.get('url', '').startswith('https://'):
        return 'rating_pending'
    try:
        age = (today - date.fromisoformat(entry['checked_on'])).days
        rating = float(entry['rating'])
    except (KeyError, TypeError, ValueError):
        return 'rating_pending'
    if not 0 <= age <= policy.get('max_age_days', 30) or not 0 <= rating <= 5:
        return 'rating_pending'
    if entry.get('category') not in ('mnc', 'startup'):
        return 'rating_pending'
    return 'eligible' if rating > policy.get('above', 3.5) else 'rating_below_threshold'
