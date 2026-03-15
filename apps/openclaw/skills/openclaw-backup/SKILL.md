---
name: openclaw-backup
description: "Backup and restore the .openclaw state directory. Use when: (1) before making major config changes, (2) before installing many skills, (3) on a schedule to protect against data loss, (4) user asks to backup or restore OpenClaw state."
---

# OpenClaw Backup

Backup and restore the `.openclaw` state directory to prevent data loss.

## When to Use

- Before modifying `openclaw.json` or agent configs
- Before bulk skill installs
- Periodically (daily/weekly) as insurance
- When user says "backup", "save state", or "snapshot"

## Commands

### Create backup

```bash
BACKUP_DIR="/Users/blackdj/Desktop/OpenClaw Bot/backups"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
mkdir -p "$BACKUP_DIR"
tar czf "$BACKUP_DIR/openclaw-$TIMESTAMP.tar.gz" \
  -C "/Users/blackdj/Desktop/OpenClaw Bot" \
  .openclaw/openclaw.json \
  .openclaw/agents \
  .openclaw/credentials \
  .openclaw/identity \
  .openclaw/cron \
  .openclaw/devices \
  .openclaw/telegram \
  OpenClaw/AGENTS.md \
  OpenClaw/SOUL.md \
  OpenClaw/IDENTITY.md \
  OpenClaw/USER.md \
  OpenClaw/MEMORY.md \
  OpenClaw/TOOLS.md \
  OpenClaw/memory
echo "Backup saved: $BACKUP_DIR/openclaw-$TIMESTAMP.tar.gz"
```

### List backups

```bash
ls -lhtr "/Users/blackdj/Desktop/OpenClaw Bot/backups/"
```

### Restore from backup

```bash
# Stop services first
launchctl unload ~/Library/LaunchAgents/ai.openclaw.gateway.plist
# Extract backup (overwrites current state)
tar xzf "/Users/blackdj/Desktop/OpenClaw Bot/backups/openclaw-YYYYMMDD-HHMMSS.tar.gz" \
  -C "/Users/blackdj/Desktop/OpenClaw Bot"
# Restart
launchctl load ~/Library/LaunchAgents/ai.openclaw.gateway.plist
```

### Cleanup old backups (keep last 7)

```bash
BACKUP_DIR="/Users/blackdj/Desktop/OpenClaw Bot/backups"
ls -t "$BACKUP_DIR"/openclaw-*.tar.gz | tail -n +8 | xargs rm -f 2>/dev/null
```

## Notes

- Backups exclude logs, browser profiles, and session data to keep size small
- Always stop the gateway before restoring to avoid config conflicts
- Recommended: run backup before any `clawhub install` batch
