# Fix: GDM Greeter Sync Services Conflict

**Date:** 2026-01-13
**Issue:** mimeapps-sync-gnome.service and dconf-sync-gnome.service failing with permission errors
**Status:** ✅ RESOLVED

---

## Problem Summary

The systemd user services `mimeapps-sync-gnome.service` and `dconf-sync-gnome.service` were crashing repeatedly with the error:

```
tee: /tmp/mimeapps-sync-gnome.log: Permission denied
```

The service had over 800+ restart attempts before we identified the root cause.

---

## Root Cause Analysis

### Issue 1: Services Running in GDM Greeter Session
The services were configured with `WantedBy=graphical-session.target`, which caused them to start in **ALL** graphical sessions, including:
- ✅ User's normal desktop session (correct)
- ❌ GDM greeter session (incorrect!)

The GDM greeter (temporary user, UID 60578) would create log files in `/tmp/` owned by the `gdm` user. When the actual user logged in, their services couldn't write to these files due to permission conflicts.

**Evidence:**
```bash
$ ls -la /tmp/mimeapps-sync-gnome.log
-rw-r--r-- 1 60578 gdm 538 jan 13 19:38 /tmp/mimeapps-sync-gnome.log

$ cat /tmp/mimeapps-sync-gnome.log
[2026-01-13 19:37:54] [gnome] Monitoring file: /run/gdm/home/gdm-greeter/.config/mimeapps.list
```

### Issue 2: Non-Isolated Log Files
Log files used a static path without user identification:
```bash
LOG_FILE="/tmp/mimeapps-sync-gnome.log"  # Same for all users!
```

---

## Solution Implemented

### 1. Prevent Execution in GDM Greeter (Primary Fix)
Added condition to all systemd service files to skip execution in GDM sessions:

```ini
[Unit]
Description=GNOME mimeapps (file associations) synchronization service
Documentation=man:mimeapps(5)
PartOf=graphical-session.target
After=graphical-session.target
# Don't run in GDM greeter sessions
ConditionPathExists=!/run/gdm/home/gdm-greeter  # ← NEW

[Service]
Type=simple
ExecStart=/usr/bin/mimeapps-sync-monitor-gnome
ExecStop=/usr/bin/mimeapps-sync-stop-gnome
Restart=on-failure
RestartSec=5

[Install]
WantedBy=graphical-session.target
```

### 2. Isolate Logs by User UID (Defense in Depth)
Changed log file paths to include user UID:

```bash
# Before
LOG_FILE="/tmp/mimeapps-sync-gnome.log"

# After
LOG_FILE="/tmp/mimeapps-sync-gnome-${UID}.log"
```

This ensures each user (including temporary GDM users) has their own log file, preventing permission conflicts even if the service somehow runs.

---

## Files Modified

### comm-gnome-config (7 files)
```
usr/bin/dconf-sync-monitor-gnome          - Added ${UID} to LOG_FILE
usr/bin/dconf-sync-stop-gnome             - Added ${UID} to LOG_FILE
usr/bin/mimeapps-sync-monitor-gnome       - Added ${UID} to LOG_FILE
usr/bin/mimeapps-sync-stop-gnome          - Added ${UID} to LOG_FILE
usr/bin/startgnome-community              - Added ${UID} to log_file
usr/lib/systemd/user/dconf-sync-gnome.service    - Added ConditionPathExists
usr/lib/systemd/user/mimeapps-sync-gnome.service - Added ConditionPathExists
```

### comm-xfce-config (7 files)
```
usr/bin/dconf-sync-monitor-xfce           - Added ${UID} to LOG_FILE
usr/bin/dconf-sync-stop-xfce              - Added ${UID} to LOG_FILE
usr/bin/mimeapps-sync-monitor-xfce        - Added ${UID} to LOG_FILE
usr/bin/mimeapps-sync-stop-xfce           - Added ${UID} to LOG_FILE
usr/bin/startxfce-community               - Added ${UID} to log_file
usr/lib/systemd/user/dconf-sync-xfce.service     - Added ConditionPathExists
usr/lib/systemd/user/mimeapps-sync-xfce.service  - Added ConditionPathExists
```

### comm-cinnamon-config (7 files)
```
usr/bin/dconf-sync-monitor-cinnamon       - Added ${UID} to LOG_FILE
usr/bin/dconf-sync-stop-cinnamon          - Added ${UID} to LOG_FILE
usr/bin/mimeapps-sync-monitor-cinnamon    - Added ${UID} to LOG_FILE
usr/bin/mimeapps-sync-stop-cinnamon       - Added ${UID} to LOG_FILE
usr/bin/startcinnamon-community           - Added ${UID} to log_file
usr/lib/systemd/user/dconf-sync-cinnamon.service    - Added ConditionPathExists
usr/lib/systemd/user/mimeapps-sync-cinnamon.service - Added ConditionPathExists
```

**Total:** 21 files across 3 repositories, 27 lines modified

---

## Commits Made

Each repository received the same fix with individual commits:

### comm-gnome-config
```
🐛 fix: Prevent sync services from running in GDM greeter and isolate logs by UID
```

### comm-xfce-config
```
🐛 fix: Prevent sync services from running in GDM greeter and isolate logs by UID
```

### comm-cinnamon-config
```
🐛 fix: Prevent sync services from running in GDM greeter and isolate logs by UID
```

---

## Verification Steps

After applying the fix, verify everything is working:

### 1. Check service status
```bash
systemctl --user status mimeapps-sync-gnome.service
systemctl --user status dconf-sync-gnome.service
```

Expected: `active (running)` with no errors

### 2. Check logs are using UID
```bash
ls -la /tmp/*sync*-${UID}.log
```

Expected: Files owned by your user, not gdm

### 3. Verify no permission errors
```bash
journalctl --user -u mimeapps-sync-gnome.service --since "5 minutes ago" | grep -i "permission"
```

Expected: No output

### 4. Verify ConditionPathExists is installed
```bash
cat /usr/lib/systemd/user/mimeapps-sync-gnome.service | grep ConditionPathExists
```

Expected: `ConditionPathExists=!/run/gdm/home/gdm-greeter`

### 5. Check sync is working
```bash
# mimeapps sync
diff /home/$USER/.config/mimeapps.list /home/$USER/.config/gnome.mimeapps.list

# dconf sync
ls -lh ~/.config/dconf/settings.gnome
```

Expected: Files should be identical or recently updated

---

## Post-Fix Status (2026-01-13 22:24)

✅ **All systems operational:**
- Services running stable for 18+ minutes with no crashes
- Logs correctly using UID-based filenames
- No permission errors in journalctl
- mimeapps.list and dconf settings syncing correctly
- Services NOT running in GDM greeter sessions

**Old GDM logs (can be safely removed):**
```bash
sudo rm -f /tmp/dconf-sync-gnome.log /tmp/mimeapps-sync-gnome.log
```

---

## Technical Notes

### Why `ConditionPathExists=!/run/gdm/home/gdm-greeter`?

The `!` prefix means "condition fails if path exists". The GDM greeter creates a temporary home directory at `/run/gdm/home/gdm-greeter` during the login screen. By checking for this path:
- **GDM greeter session:** Path exists → Condition fails → Service doesn't start ✅
- **User session:** Path doesn't exist → Condition passes → Service starts ✅

### Why Add UID to Logs?

Defense in depth. Even if the ConditionPathExists check somehow fails or is bypassed in future systemd versions, each user will have their own log file, preventing permission conflicts.

### systemd User Services vs System Services

These are **user services** (`/usr/lib/systemd/user/`), not system services. They:
- Run in the user's session context
- Use user's HOME and UID
- Start with `graphical-session.target`
- Are managed with `systemctl --user`

The GDM greeter also has a user session, which is why it was inadvertently running these services.

---

## Related Files

- `CLAUDE.md` - Project documentation for Claude Code
- Repository branches: `dev-talesam` (contains this fix)

---

## Future Considerations

If similar issues occur with other desktop environments or display managers:

1. Check if services are running in unexpected sessions:
   ```bash
   loginctl list-sessions
   ps aux | grep -E "service-name"
   ```

2. Add appropriate conditions to service files for other DMs:
   - LightDM: `ConditionPathExists=!/run/lightdm/`
   - SDDM: `ConditionPathExists=!/run/sddm/`
   - GDM: Already handled

3. Always isolate shared resources (logs, temp files) by UID or XDG_RUNTIME_DIR

---

## Questions or Issues?

If you encounter problems after this fix:

1. Check if the package was properly installed:
   ```bash
   pacman -Ql comm-gnome-config | grep "sync.*service"
   ```

2. Verify service files have the ConditionPathExists line

3. Restart user services:
   ```bash
   systemctl --user daemon-reload
   systemctl --user restart mimeapps-sync-gnome.service
   systemctl --user restart dconf-sync-gnome.service
   ```

4. Check for conflicting old service files in `~/.config/systemd/user/`

---

**End of Document**
