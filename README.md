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
| State | Persistent SQLite on the VM, separate statuses and manual submission confirmation |
| Schedule | Linux cron or GitHub Actions controlling a dedicated self-hosted VM runner |

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

## Scheduling option B: GitHub Actions + persistent VM

The provided workflow uses a **self-hosted** runner labelled `linux` and `job-agent`, not an ephemeral GitHub-hosted runner. This deliberately avoids keeping a personal database in Git or relying on evictable Actions caches. GitHub's schedule is `30 3,15 * * *` UTC; scheduled runs can be delayed. Scheduling starts only on the default branch and after configuration.

1. Prefer a private repository for the runner setup. This repository was public at implementation time; do not add private files or expose a self-hosted runner to untrusted workflows/PRs.
2. Install reviewed code and the profile on the VM outside the runner's checkout directory, using the quick start above. Use an account without unnecessary system privileges.
3. Configure a dedicated GitHub Actions runner with label `job-agent`. The scheduled workflow executes installed code; it does not fetch PR code. After reviewing updates, deploy them manually on the VM.
4. Add repository secrets: `GEMINI_API_KEY`, `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`, `DIGEST_TO`.
5. Add variables: `GEMINI_MODEL`, `JOB_AGENT_INSTALL_DIR` (absolute checkout path), `JOB_AGENT_HOME` (absolute directory containing profile.yaml/private/state; can equal install directory), and finally `JOB_AGENT_ENABLED=true`.
6. Merge the workflow, run it manually once, confirm the email and report, then leave the schedule enabled. Do not also enable cron.

No credential or runner has been provisioned by generating this code. No live search, LLM scoring, email or application submission was performed during development. GitHub-hosted runner mode with encrypted durable remote state can be added later; it is not implemented here.

## Daily report and recovery

`state/output/job-activity-YYYY-MM-DD.xlsx` contains jobs discovered **or confirmed applied** that day in IST, plus source errors. The 21:00 digest is the daily-so-far report; later manual applications are included in the next digest's **Applied history** sheet even when they belong to a previous date. That sheet and the persistent database retain the complete confirmed application history. Prepared/prefilled are never counted as submitted.

An email failure leaves prepared items unsent for retry, including when their discovery window has passed. An SMTP accept followed by a local crash can cause a repeated digest (at-least-once delivery); job state prevents repeated preparation. LLM errors retry on a later run while the exact posting remains in-window. Source metadata is refreshed on rediscovery. Daily reports are regenerated on each run. Reducing caps may leave some jobs unprocessed before their 12-hour window ends.

## Tests

```bash
.venv/bin/python -m pytest -q
```

Tests cover time boundaries, timestamp uncertainty, ID-preserving URL normalization, persisted deduplication, resume claim/format/employer preservation, rejected invented evidence, formula-injection prevention, IST daily reporting, fill-only behavior, and an offline dry-run that fails if Gmail or Gemini is called. CI runs the same suite. Live source/Gemini/Gmail and real application forms need a credentialed smoke test after setup.

## Existing free/open-source options evaluated

| Project | Relevant functionality | Tradeoff |
|---|---|---|
| [JobSpy](https://github.com/speedyapply/JobSpy) | Multi-board job discovery, including India sources | A scraping library, not a complete agent; date precision and access vary |
| [ApplyPilot fork](https://github.com/ibarrajo/ApplyPilot) | Discovery, ranking, tailoring, application flow and Gmail tracking | Broader system; its README lists additional tooling for full application automation; free source does not mean all services are free |
| [Original AIHawk URL](https://github.com/feder-cr/Jobs_Applier_AI_Agent_AIHawk) | Historical job application project | At review time this URL redirected to `feder-cr/invisible_dots`; not treated as a maintained drop-in solution |

A small custom agent was selected to preserve DOCX formatting and enforce manual submission. Research checked 2026-10-09. API documentation: [Gemini models](https://ai.google.dev/gemini-api/docs/models), [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing), [structured outputs](https://ai.google.dev/gemini-api/docs/structured-output), [Greenhouse Job Board](https://docs.greenhouse.io/job-board.html), [Lever postings](https://github.com/lever/postings-api).

## Remaining setup answers

- Which Gmail address should receive digests? Sender and recipient can be the same.
- What are your current city, notice period, current/expected compensation and work authorization?
- Which companies should the Greenhouse/Lever/Workday adapters monitor?
- Strict verified 12-hour results only, or include separately labeled uncertain-date postings?
- VM cron or a dedicated self-hosted GitHub Actions runner?

Keep credentials in `.env` / GitHub Secrets, not in answers posted publicly.
