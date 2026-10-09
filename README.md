# AI Agent for Jobs

A Python agent for Site Reliability Engineer, Observability Engineer and DevOps Engineer searches across India and remote roles accessible from India. Runs at **09:00 and 21:00 Asia/Kolkata**, prepares evidence-based DOCX variants, emails a Gmail digest with resumes and a daily XLSX activity log, and opens a headed browser for assisted application filling. **You review and click Submit yourself.**

## What is implemented

| Stage | Behavior |
|---|---|
| Discover | JobSpy: Indeed India, LinkedIn, Naukri; configured Greenhouse, Lever and Workday company boards |
| Time filter | Rolling 12 hours at actual run time; exact publication timestamps required by default |
| Uncertain dates | Date-only or missing publication dates go to a separate time-unverified queue |
| Fit | Gemini structured JSON; 4 years configured; India/remote eligibility reviewed conservatively |
| Tailor | Gemini ranks existing evidence; deterministic DOCX paragraph reordering preserves every original claim, formatting run and employment boundary |
| Skill gaps | Listed in digest, never inserted into the resume as skills you possess |
| Email | Gmail SMTP over TLS; prepared DOCX attachments, application URLs, daily XLSX activity and source failures |
| Apply | Local/headed Playwright helper fills exact recognized contact labels; you handle login, custom questions, upload fallback and final submission |
| State | SQLite restored from an encrypted Actions checkpoint, separate statuses and manual submission confirmation |
| Schedule | GitHub-hosted Ubuntu Actions runner at 09:00/21:00 IST; optional Linux cron |

This is a reviewable first implementation, not a guarantee that every job board/form works. No model by itself can discover jobs, render files, schedule tasks and submit forms: this repository coordinates those components.

## Quick start (Linux, Python 3.11+)

```bash
git clone https://github.com/Manikumar09/AI-Agent-for-jobs.git
cd AI-Agent-for-jobs
# Until the pull request is merged:
git switch feat/job-agent
bash scripts/setup.sh
.venv/bin/job-agent init --resume /absolute/path/Manikumar_Analyst.docx
```

`init` copies your original DOCX into ignored `private/resume.docx`, extracts name/contact details locally, and creates ignored `profile.yaml`. Review these fields before use. Set first/last name, current city, notice period, compensation expectations and work authorization yourself. Unknown answers remain blank and are never guessed. Your resume is never committed by these scripts.

Edit `.env`:

```dotenv
GEMINI_API_KEY=your-key
GEMINI_MODEL=gemini-3.8-flash
GMAIL_ADDRESS=your-address@gmail.com
GMAIL_APP_PASSWORD=your-google-app-password
DIGEST_TO=your-address@gmail.com
```

Choose an available **free-tier** Gemini model in your AI Studio project; model availability and quotas change. The model name is configurable and there is no paid fallback. Google lists free-tier content as usable for product improvement; this implementation omits resume contact paragraphs from LLM input, but career evidence still goes to Gemini. Enable Google 2-Step Verification and create an app password if your account supports it. Never paste secrets into GitHub issues or commit them.

```bash
# Discovery/filtering smoke test: no Gemini calls, no email, separate dry-run database.
./run.sh --dry-run
# Real execution: calls Gemini and emails DIGEST_TO.
./run.sh
.venv/bin/job-agent list
.venv/bin/job-agent apply JOB_ID
# After YOU submit successfully:
.venv/bin/job-agent mark-applied JOB_ID --evidence 'Confirmation reference or receipt note'
```

The browser helper requires a graphical Linux session (or your desktop with the same persistent state). It is not launched by scheduled/headless runs. Opening a form or uploading a file can transmit data to the employer even before final submission; the helper asks you to review the DOCX first. It never clicks navigation or submit buttons and does not solve CAPTCHAs. Custom/embedded forms may need manual filling. To use your desktop instead of the VM, run the same installation against a securely copied state/profile/output directory; resume paths in SQLite must be updated if the directory changes. Prefer one host as the authoritative state owner.

## Configure sources and confidence

`profile.yaml` contains role/location/source lists, score threshold (65), result cap and per-run LLM cap (8). These are starting defaults to tune, not validated hiring criteria.

Company ATS APIs require specific employers. Add board tokens, for example `greenhouse: [companytoken]` and `lever: [companytoken]`. Do not use those literal placeholders. Workday uses tenant-specific configuration:

```yaml
workday:
  - host: YOURTENANT.wd5.myworkdayjobs.com
    tenant: YOURTENANT
    site: External
```

Copy the actual host/tenant/site from the employer's career portal. Workday endpoints are not a universal supported public API and can change. Each adapter reports errors rather than claiming a failed fetch found zero jobs. Respect each site's access rules and limits; reduce searches if blocked. There are no proxy, evasion or credential-harvesting mechanisms.

**Strict time behavior:** JobSpy often returns dates rather than timestamps, Indeed's source filter can refer to when a job was indexed, Greenhouse list `updated_at` is not publication time, and Lever may omit a publication timestamp. Greenhouse detail `first_published` is used when available. Unverified jobs appear in the activity report but are not automatically tailored by default. Set `include_unverified: true` only if you want these additional candidates; their dates remain explicitly labeled unverified. This may be necessary to get useful volume from Naukri/LinkedIn/Indeed. No claim is made that these candidates were posted in the last 12 hours.

The strict rolling window is computed at actual run time. A delayed/missed scheduler can leave gaps; there is no automatic backfill disguised as last-12-hour results. URL canonicalization deduplicates within a source and common tracking variants. Cross-board reposts with different URLs can remain duplicates.

## Resume integrity

The original resume remains intact. The agent can prioritize existing bullets inside a contiguous body block, with blank paragraphs, headings, short labels and tabbed employment headers as boundaries. It never generates new professional claims, changes employers/dates, or promotes learning to production expertise. Some jobs may produce identical resumes when the evidence is already ordered appropriately. The current version does **not** freely rewrite a summary or introduce JD-only keywords. Missing required skills are listed separately for your review.

Validate the layout of each DOCX in Word/LibreOffice before application. Paragraph reordering preserves formatting but can alter page breaks. The implementation was tested against the provided resume and synthetic boundary fixtures; arbitrary templates require review.

## Scheduling option A: Linux VM cron (recommended)

Keep the checkout and state on persistent disk. Back up `state/` and your private profile/resume securely. Use only one scheduler.

On cron implementations supporting `CRON_TZ`, add via `crontab -e` (replace the paths):

```cron
CRON_TZ=Asia/Kolkata
0 9,21 * * * /absolute/path/AI-Agent-for-jobs/run.sh >> /absolute/path/job-agent.log 2>&1
```

If `CRON_TZ` is unsupported, use a UTC-configured machine and `30 3,15 * * *`. Setting only `TZ` inside the command does not change the cron trigger time. `run.sh` uses a restrictive umask, and Python holds an advisory lock to prevent overlapping scheduled runs. Dry runs never alter production state. Rotate your private log with the VM's logrotate facility.

## Scheduling option B: GitHub-hosted Actions (selected)

Uses `ubuntu-latest`; no VM or self-hosted runner is required. The cron is `30 3,15 * * *` UTC (09:00/21:00 IST). GitHub scheduled runs can start late, so this is not an exact-time SLA. Each run looks back 12 hours from its actual start. Merge the pull request to the default branch before activating.

### Private configuration

After the quick-start `init`, run locally with GitHub CLI authenticated (`gh auth login`):

```bash
.venv/bin/python scripts/configure_github.py
```

This stores your private DOCX (gzip/base64), profile and an encryption key as GitHub Secrets through stdin. It sets Hyderabad, 60 days' notice, and INR 12–14 lakh annual CTC. It uses the reviewed email extracted from your resume for both the recipient and default Gmail sender. It does not print secrets or commit private data. Review `profile.yaml` before and after setup. A compressed resume exceeding GitHub's secret-size limit is rejected with instructions. Back up `private/state-key` securely and retain it for existing checkpoints.

Add `GEMINI_API_KEY` and `GMAIL_APP_PASSWORD` under Repository Settings → Secrets and variables → Actions. The script supplies `PROFILE_YAML`, `RESUME_GZIP_B64`, `STATE_KEY`, and `GMAIL_ADDRESS`. You may override the model with the `GEMINI_MODEL` repository variable. Then set `JOB_AGENT_ENABLED=true` and manually run **Twice daily job search** with `bootstrap=true` **only on the first run**. Future scheduled runs restore the checkpoint automatically.

No secrets have been installed by this code change and the schedule is not yet activated. No Gemini or Gmail call was made during development.

### Checkpoint privacy and limits

Artifacts contain only Fernet-encrypted state; no plaintext resume/profile/database artifact is uploaded. The key remains in GitHub Secrets. Restore accepts only this workflow's default-branch scheduled/manual runs. A missing, expired or undecryptable checkpoint stops the run; it never silently resets deduplication. Every successful restore is followed by an encrypted save step, including partial run progress when possible. Concurrency is serialized.

Artifacts are retained for 7 days. Each successful run refreshes the checkpoint, but after a longer outage you must restore a backup or consciously bootstrap again. Abrupt runner termination/upload failure can still lose that run's changes and repeat a digest. This is rolling checkpoint storage, not a guaranteed permanent backup. Artifact storage has separate quotas; monitor it. Never expose the key or run untrusted code with these secrets.

### Application review on hosted Actions

A hosted runner cannot display an interactive browser on your desktop. Scheduled runs email application links and resumes for manual review/submission. The local `job-agent apply` helper still works with local state, but desktop changes are not automatically synchronized with cloud state. After submitting, manually run the Actions workflow with `application_id` and `evidence` to record the confirmed application in the cloud report. Leave `bootstrap=false`. These inputs record YOUR confirmation and never submit a form.

### Company and salary criteria

The confirmed salary target is INR 12–14 lakh annual CTC. Gemini extracts a maximum annual INR budget only with an exact JD evidence quote. Explicit budgets below INR 12 lakh are excluded; undisclosed budgets remain eligible. This does not invent an offer or fill a job-specific salary answer without review.

Company policy is strictly **greater than 3.5/5**, and company category must be `mnc` or `startup`. The platform is awaiting your choice of AmbitionBox or Glassdoor. Unknown, stale (over 30 days), unsupported or unverified ratings are held as `rating_pending`; they are never estimated by Gemini. Add verified company records in the private profile and rerun the configuration script:

```yaml
company_policy:
  enabled: true
  source: ambitionbox  # or glassdoor, after confirmation
  above: 3.5
  max_age_days: 30
  verified_ratings:
    - company: Exact employer name
      aliases: []
      category: mnc  # or startup
      source: ambitionbox
      rating: 4.0
      url: https://www.ambitionbox.com/ACTUAL-COMPANY-RATING-PAGE
      checked_on: YYYY-MM-DD
```

The record above is a schema example, not a verified company. There is no automated licensed ratings feed configured. Until platform and real evidence are provided, this filter deliberately holds all companies. Discovery searches the configured sources; it cannot guarantee coverage of every Indian MNC/startup or every career portal. Company-specific ATS board lists still need configuration.

### Cost

Standard GitHub-hosted runners are free for public repositories. GitHub Free includes 2,000 minutes/month and 500 MB artifact storage for private repositories, shared with other account usage. Two 10-minute runs/day is approximately 600 minutes/month; actual search durations vary. This workflow has a 25-minute timeout per run. Larger runners, excess storage/usage and external services have separate billing. Use GitHub billing budgets with stop-usage enabled where available if you require zero overage. Gemini free-tier quotas are separate; no paid model fallback is configured.

Sources checked 2026-10-09: [GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions), [artifact retention](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/download-workflow-artifacts).

## Daily report and recovery

`state/output/job-activity-YYYY-MM-DD.xlsx` contains jobs discovered **or confirmed applied** that day in IST, plus source errors. The 21:00 digest is the daily-so-far report; later manual applications are included in the next digest's **Applied history** sheet even when they belong to a previous date. That sheet and the persistent database retain the complete confirmed application history. Prepared/prefilled are never counted as submitted.

An email failure leaves prepared items unsent for retry, including when their discovery window has passed. An SMTP accept followed by a local crash can cause a repeated digest (at-least-once delivery); job state prevents repeated preparation. LLM errors retry on a later run while the exact posting remains in-window. Source metadata is refreshed on rediscovery. Daily reports are regenerated on each run. Reducing caps may leave some jobs unprocessed before their 12-hour window ends.

## Tests

```bash
.venv/bin/python -m pytest -q
```

Tests cover time boundaries, timestamp uncertainty, ID-preserving URL normalization, persisted deduplication, encrypted checkpoint round-trip/wrong-key rejection, strict company-rating filters, resume claim/format/employer preservation, rejected invented evidence, formula-injection prevention, IST daily reporting, fill-only behavior, and an offline dry-run that fails if Gmail or Gemini is called. CI runs the same suite. Live source/Gemini/Gmail and real application forms need a credentialed smoke test after setup.

## Existing free/open-source options evaluated

| Project | Relevant functionality | Tradeoff |
|---|---|---|
| [JobSpy](https://github.com/speedyapply/JobSpy) | Multi-board job discovery, including India sources | A scraping library, not a complete agent; date precision and access vary |
| [ApplyPilot fork](https://github.com/ibarrajo/ApplyPilot) | Discovery, ranking, tailoring, application flow and Gmail tracking | Broader system; its README lists additional tooling for full application automation; free source does not mean all services are free |
| [Original AIHawk URL](https://github.com/feder-cr/Jobs_Applier_AI_Agent_AIHawk) | Historical job application project | At review time this URL redirected to `feder-cr/invisible_dots`; not treated as a maintained drop-in solution |

A small custom agent was selected to preserve DOCX formatting and enforce manual submission. Research checked 2026-10-09. API documentation: [Gemini models](https://ai.google.dev/gemini-api/docs/models), [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing), [structured outputs](https://ai.google.dev/gemini-api/docs/structured-output), [Greenhouse Job Board](https://docs.greenhouse.io/job-board.html), [Lever postings](https://github.com/lever/postings-api).

## Remaining activation requirements

- Choose AmbitionBox or Glassdoor and supply verified rating records or an authorized data feed.
- Add Gmail app password and Gemini API key directly to GitHub Secrets.
- Upload the private profile/resume with the configuration script, merge, and run the explicit first bootstrap.
- Review the first digest before relying on scheduled results.
