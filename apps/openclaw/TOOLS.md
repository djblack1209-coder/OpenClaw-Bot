# TOOLS.md - Local Notes

Skills define _how_ tools work. This file is for _your_ specifics — the stuff that's unique to your setup.

## What Goes Here

Things like:

- Camera names and locations
- SSH hosts and aliases
- Preferred voices for TTS
- Speaker/room names
- Device nicknames
- Anything environment-specific

## Examples

```markdown
### Cameras

- living-room → Main area, 180° wide angle
- front-door → Entrance, motion-triggered

### SSH

- home-server → 192.168.1.100, user: admin

### TTS

- Preferred voice: "Nova" (warm, slightly British)
- Default speaker: Kitchen HomePod
```

## Why Separate?

Skills are shared. Your setup is yours. Keeping them apart means you can update skills without losing your notes, and share skills without leaking your infrastructure.

---

Add whatever helps you do your job. This is your cheat sheet.

## Browser automation

- 严总's logged-in Chrome profile usually lives at: `/Users/blackdj/Library/Application Support/Google/Chrome/Profile 1`
- Cookies DB: `/Users/blackdj/Library/Application Support/Google/Chrome/Profile 1/Cookies`
- Default strategy for X / 小红书 / Upwork browser tasks on this machine:
  1. Try local Chrome-profile automation first (Playwright + `browser_cookie3` + Chrome cookies)
  2. Use Browser Relay only if local profile automation cannot reach the required page state
- Do not tell 严总 to manually copy/paste posts if the local Chrome session is already usable.
- If a browser window/tab is opened only to extract video content, close that browser window/tab immediately after extraction completes.
