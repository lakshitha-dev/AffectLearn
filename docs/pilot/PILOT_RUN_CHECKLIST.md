# Pilot run checklist (in person, local stack)

This replaces `deploy/azure/PHASE_A_RUN_CHECKLIST.md` for the pilot. That file still describes the
Azure deployment and some retired settings: the Bi-LSTM, and 20% prompt omission.

## Quick way: `pilot.ps1` (Windows PowerShell)

Every step below has a one-line command in `pilot.ps1`, at the repository root. If scripts are
blocked, run it as `powershell -ExecutionPolicy Bypass -File .\pilot.ps1 <command>`.

| Step | Command |
|---|---|
| First time, all in one: secrets, start, 4 dry-run accounts, status, readiness | `.\pilot.ps1 all` |
| Secrets file (`.env.pilot`, generated) | `.\pilot.ps1 setup` |
| Start, wait until healthy, seed the course | `.\pilot.ps1 start` |
| Real accounts, locked | `.\pilot.ps1 accounts -Count 30 -Seed <SEED> -Lock` |
| Health and frozen configuration | `.\pilot.ps1 status` |
| Freeze the configuration | `.\pilot.ps1 lock` |
| Pre-session readiness check (§B) | `.\pilot.ps1 check` |
| Participant sat down (§C.3) | `.\pilot.ps1 session-start -Code P007 -Device "Chrome 140, laptop camera"` |
| Participant left (§C.7) | `.\pilot.ps1 session-end -Code P007 -Reason completed -Notes "none"` |
| Erase a participant | `.\pilot.ps1 withdraw -Code P007` |
| Export / backup (§D) | `.\pilot.ps1 export` · `.\pilot.ps1 backup` |
| Stop (keep data) / delete everything | `.\pilot.ps1 stop` · `.\pilot.ps1 reset` |

The rest of this checklist gives the underlying commands.

## Underlying commands

In the commands below, the compose invocation is abbreviated. It stands for:

```
docker compose -f docker-compose.yml -f docker-compose.pilot.yml --env-file .env.pilot
```

## A. Once, before the pilot

**Gates** (`[DECIDE]` items in [protocol.md](protocol.md) §10):
- [ ] Ethics decision obtained and recorded in the information sheet.
- [ ] Supervisor sign-off on the protocol, the primary outcome and the treatment definition.
- [ ] Analysis plan fixed, dated and sent to the supervisor (or registered on OSF).

**The laptop:**
- [ ] Encrypted with BitLocker.
- [ ] Separate OS account for the pilot.
- [ ] Notifications off.
- [ ] Chrome up to date.
- [ ] Docker Compose ≥ 2.24.

**Code and secrets:**
- [ ] The code is on `develop` with every pilot PR merged. Record the commit:
  `git rev-parse --short HEAD` → `[COMMIT]`.
- [ ] `.env.pilot` created from `.env.pilot.example`, every value set. It is git-ignored and stays
  only on this laptop.

**Bring up the stack** (migrations run automatically):

```
APP_COMMIT=$(git rev-parse --short HEAD) <compose> up -d --build
```

- [ ] Stack is up.
- [ ] Seed the course content:

  ```
  <compose> exec api python -m app.db.seed_courses
  ```

- [ ] Check the parallel pre/post assessments exist for the study course.

**Create accounts:** participants, plus the demo-flagged readiness account. Record the seed in
protocol §2.

```
<compose> exec api python -m scripts.create_pilot_participants \
  --count <N> --seed <SEED> --out /app/pilot_accounts.csv --phase-b --lock --readiness
<compose> cp api:/app/pilot_accounts.csv ./pilot_accounts.csv
<compose> exec api rm /app/pilot_accounts.csv
```

- [ ] Accounts created and the CSV copied out.
- [ ] `pilot_accounts.csv` holds the passwords. Keep it encrypted (for example in a 7-Zip AES-256
  archive) and never commit it (it is git-ignored). Print a login slip per code if that is easier
  than typing from the file.

**Freeze the configuration.** Get an admin token, then check and lock:

```
TOKEN=$(curl -s -X POST localhost:8000/api/v1/auth/login -H 'content-type: application/json' \
  -d '{"emailAddress":"admin@affectlearn.io","password":"<SEED_ADMIN_PASSWORD>"}' | jq -r .accessToken)
curl -s localhost:8000/health/pipeline | jq .models.decision
curl -s -H "Authorization: Bearer $TOKEN" localhost:8000/api/v1/admin/config | jq .
curl -s -X POST -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  localhost:8000/api/v1/admin/config/lock -d '{"locked": true}'
```

- [ ] Configuration locked.
- [ ] 2–3 dry runs with non-participants (protocol §7), using demo-flagged accounts. Afterwards, run
  the export (§D) and check it end to end.

## B. Before each session day

- [ ] Stack up. `curl localhost:8000/health/pipeline` shows `"status": "ok"`.
- [ ] Readiness check passes. It uses the fake camera, on the demo-flagged account:

  ```
  cd frontend && npx playwright install chromium   # once
  PILOT_READINESS=1 PILOT_READINESS_PASSWORD=<READY password> PILOT_ADMIN_PASSWORD=<admin> \
    npx playwright test e2e/pilot-readiness.spec.ts
  ```

- [ ] Room: even lighting in front of the participant, no bright window behind them, the laptop
  camera at eye level, a quiet room.
- [ ] Participant codes for the day are ready, with the linking sheet and consent forms printed.

## C. Each participant (see [facilitator-script.md](facilitator-script.md))

1. [ ] Welcome and briefing. The participant signs the consent form. Write the code on the linking
   sheet.
2. [ ] Open a Chrome **Guest** window (profile menu → Guest) at `http://localhost:3000`.
3. [ ] Start the sitting:

   ```
   curl -s -X POST -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' \
     localhost:8000/api/v1/admin/pilot/sessions \
     -d '{"participantCode":"P007","protocolVersion":"pilot-1.0","device":{"browser":"Chrome <ver>","camera":"<laptop/external>"}}'
   ```

   Keep the returned `id`.
4. [ ] Sign in with the code's credentials. The participant does the in-app consent (matching the
   paper form), the camera choice and calibration.
5. [ ] Pre-questionnaire, pre-test, warm-up, the course (time-boxed), post-test, satisfaction, SUS,
   UEQ-S.
6. [ ] Debrief and interview notes. The notes go on paper, against the code, never the name.
7. [ ] End the sitting:

   ```
   curl -s -X POST -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' \
     localhost:8000/api/v1/admin/pilot/sessions/<id>/end \
     -d '{"endReason":"completed","deviationNotes":"none"}'
   ```

8. [ ] Log out. Close the Guest window. Check the camera light is off.

**If the participant withdraws and asks for deletion:**
- find their id with `GET /api/v1/admin/users?search=p007`;
- then call `POST /api/v1/admin/users/<id>/withdraw`;
- end the sitting as `withdrawn`.

## D. After each session day

- [ ] Integrity: `GET /api/v1/admin/research/events/gaps`. Sequence gaps should be empty or
  explained.
- [ ] Export the day's data and check the counts per participant:

  ```
  <compose> exec api python -m scripts.export_pilot --out /app/pilot_export
  <compose> cp api:/app/pilot_export ./pilot_export
  ```

  Keep the export encrypted. It is git-ignored.
- [ ] Encrypted database backup:

  ```
  <compose> exec -T db pg_dump -U postgres affectlearn > backup-<date>.sql
  ```

  Then encrypt the dump, store it off the laptop in an encrypted location, and delete the
  plaintext.
- [ ] Clear the container logs (`<compose> down` followed by `up` removes them). Research payloads
  are kept out of the logs (`RESEARCH_LOG_PAYLOADS=0`), but the logs still carry event envelopes.
- [ ] Update the participant-flow tally (enrolled / completed / withdrawn / technical) and the
  deviation log.

## E. After the pilot

- [ ] Final export, then the analysis (see [analysis-plan.md](analysis-plan.md)).
- [ ] Destroy the linking sheet after the withdrawal deadline.
- [ ] Delete `pilot_accounts.csv`.
- [ ] Delete the raw interaction windows on the schedule in the data management plan.
- [ ] Rotate `.env.pilot` secrets if the laptop is reused.
