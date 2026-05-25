# Launch Checklist

Pre-flight + go/no-go gates for the v1 public launch.

## T-1 day (Day 6 evening)

- [ ] `docker compose up -d` on prod with latest image; `alembic upgrade head` clean
- [] Cold-start smoke (private window, fresh Google account):
  - landing → sign-in → dashboard with sample deck visible
  - add term `ubiquitous` → SSE finishes < 30s
  - start session on Starter Words → answer 5 correct + 2 wrong
  - psql: `SELECT mastery_score, mastery_level FROM user_term_stats LIMIT 5` shows non-default rows
- [ ] One manual `pg_dump` to `/var/backups/pycil/pre-launch.sql`
- [ ] OpenRouter dashboard: < 5% of $20 daily budget consumed during smoke
- [ ] Caddy access logs: only `200`s during smoke run
- [ ] Capture 4 screenshots (landing, dashboard, deck detail, learn) at 1280×800
- [ ] Record 15s GIF: add term → enrichment → study; compress with ffmpeg < 2 MB

## Go / no-go gates

| Gate | Pass criteria |
|------|---------------|
| Auth | Fresh Google account reaches `/dashboard` with sample seed |
| Generation | Term enrichment SSE completes ≤ 30s, definition is sensible |
| Learning | First-attempt-correct twice → ELO + interval update visible in DB |
| Budget | Daily LLM spend < 50% of cap during smoke |
| Logs | No 5xx in last 1h |

If any gate fails → fix → re-run smoke → recheck. Do not launch on red.

## Launch day (Day 7)

- [ ] Submit Show HN at peak traffic (~9am PT weekday). Title + body in `launch-copy/show-hn.md`
- [ ] Optional: Product Hunt listing using same screenshots + GIF
- [ ] Open monitoring tabs:
  1. Show HN comments
  2. `ssh vps 'docker compose logs -f --tail=200'`
  3. OpenRouter usage dashboard
  4. `psql -c 'SELECT count(*) FROM users'` polled hourly

## Triage protocol (during 4-hour window)

- **P0** — sign-in broken, 5xx, payment-relevant → drop everything, target deploy < 30 min
- **P1** — UI broken, slow, confusing → note, fix evening
- **P2+** — feature requests, nice-to-have → record in `plans/post-launch-feedback.md`

## Wrap (evening)

- [] Commit `docs/launch-retro.md` with: sign-ups, LLM spend, top 3 P0/P1, top 3 feature requests, 1-paragraph reflection
- [ ] Run `/ck:journal` for the sprint
