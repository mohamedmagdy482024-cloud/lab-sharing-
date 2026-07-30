# Git Sync — Lab test matrix (Phase 5)

Run on **two machines** before production use. Check each box and note date/tester.

## Environment

| Machine | Role | OS | IP | Tester | Date |
|---------|------|-----|-----|--------|------|
| A | Main | | | | |
| B | Client | | | | |

---

## 1. Setup

- [ ] **Main:** Set as Main Device — Live Log shows `git://IP/repo_name`
- [ ] **Main:** Live Log shows `Server repo is bare (ready for push)`
- [ ] **Main:** Mirror folder exists after first Send (e.g. `UI_sampel-main_files`)
- [ ] **Client:** Connect & Clone into **empty** folder — all files present
- [ ] **Client:** `git remote -v` points to Main IP

---

## 2. Main → Client

- [ ] Main: edit file in **working folder** → banner lists modified filenames
- [ ] Main: **Send** → popup `Published to server @ …`
- [ ] Main: mirror folder contains updated file
- [ ] Client: green banner within 30s OR after TCP alert
- [ ] Client: **Receive** → file content matches Main
- [ ] Client: sends **PULL_ACK** — Main shows `Client synced @ hash`

---

## 3. Client → Main

- [ ] Client: edit → **Send** → Published
- [ ] Main: banner `hostname pushed`
- [ ] Main: **Receive** → file matches Client

---

## 4. Auto-pull (optional)

- [ ] Client: Auto-pull **On** — remote notify triggers Receive without click
- [ ] Main: Auto-pull **On** — client push triggers Receive

---

## 5. Reliability

- [ ] Restart Main app — daemon + paths unchanged
- [ ] Non-bare server auto-repairs on startup
- [ ] Edit wrong folder (not working copy) — **no** banner

---

## 6. Conflicts

- [ ] Both edit same line → conflict dialog
- [ ] Keep mine / Keep theirs → both converge after Send/Receive

---

## 7. Cross-platform (recommended)

- [ ] Ubuntu Main + Windows Client
- [ ] Windows Main + Windows Client
- [ ] Firewall: ports 9418, 57322, 57323 open on private network

---

## Notes / failures

```
(record issues here)
```
