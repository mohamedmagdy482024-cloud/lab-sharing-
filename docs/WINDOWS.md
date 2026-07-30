# Lab Sharing on Windows 11

Lab Sharing was built for **Ubuntu lab PCs**, but you can **develop and test on Windows 11** with a few prerequisites. For production use in the lab, Ubuntu remains the recommended setup.

## What works on Windows 11

| Feature | Windows 11 |
|---------|------------|
| PyQt6 GUI | Yes |
| Git Sync (Main or Client) | Yes, if **Git for Windows** is installed |
| `git daemon` (Main server) | Yes (included with Git for Windows) |
| File transfer (TCP) | Yes |
| Device discovery (UDP broadcast) | Yes (uses global broadcast fallback) |
| Change watcher | Yes (`watchdog`) |
| In-app banners / Live Log | Yes |

## Requirements

1. **Python 3.10+** — [python.org](https://www.python.org/downloads/) (check “Add to PATH”)
2. **Git for Windows** — [git-scm.com](https://git-scm.com/download/win)  
   - Verify in PowerShell: `git --version`
3. Install dependencies:

```powershell
cd "D:\path\to\lab-sharing"
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

## Windows firewall (Main device)

Allow inbound TCP for Git sync and messaging:

- **9418** — `git daemon` (clone/push/pull)
- **57322** — UDP device discovery
- **57323** — TCP sync alerts between apps

Windows may prompt on first run — choose **Allow on private networks**.

## Testing scenarios

### A) Laptop only (no Ubuntu yet)

- Set up **Main** on Windows: pick server bare folder + working folder → Initialize  
- Set up **Client** on same PC in another folder (use `127.0.0.1` as Main IP) — limited but tests commit/push/pull/verify

### B) Windows laptop + Ubuntu workstation (ideal)

- **Ubuntu at work** = Main (real server)  
- **Windows laptop** = Client (clone from `git://<ubuntu-ip>/<repo-name>`)  
- Both on same LAN / VPN

### C) Windows Main + Ubuntu Client

- Possible if Ubuntu can reach Windows IP on port 9418  
- Windows must stay awake; firewall must allow 9418

## Linux-only pieces (handled)

- ~~`pkill`~~ → uses PID file + `taskkill` on Windows  
- ~~`notify-send`~~ → optional PowerShell toast on Windows  
- `fcntl` network interfaces → fallback broadcast on Windows (still works on most LANs)

## Paths on Windows

Use normal Windows paths in the UI, e.g.:

- Server repo: `C:\Users\you\lab_server\programming`
- Working copy: `C:\Users\you\projects\programming`

Git internally normalizes paths for `git daemon`.

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `git is not recognized` | Install Git for Windows, restart terminal |
| Daemon fails / port 9418 | `netstat -ano \| findstr 9418` — free the port or stop old daemon |
| Client cannot clone | Ping Main IP; allow firewall; confirm repo name from Main Live Log |
| Fetch banner: Cannot reach server | Main app closed, daemon stopped, or wrong IP/repo name |

## Recommended workflow for you

1. Test **Sprint 1 changes** on **Windows 11** as Client or solo Main+Client locally.  
2. Deploy same code on **Ubuntu workstation** as Main in the lab.  
3. Point laptop Client at Ubuntu IP — same Git Sync flow as designed.
