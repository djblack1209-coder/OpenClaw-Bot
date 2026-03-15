# Automated Meeting Notes & Action Items

You just finished a 45-minute team call. Now you need to write up the summary, pull out action items, and distribute them to Jira, Linear, or Todoist — manually. By the time you're done, the next meeting is starting. What if your agent handled all of that the moment the transcript lands?

This use case turns any meeting transcript into structured notes and automatically creates tasks in your project management tool.

## Pain Point

Meeting notes are tedious but critical. Most people either skip them (and lose context) or spend 20+ minutes writing them up. Action items get forgotten because they live in someone's head or buried in a chat thread. This agent eliminates the gap between "we discussed it" and "it's tracked and assigned."

## What It Does

- **Watches** for new meeting transcripts (via Otter.ai export, Google Meet transcript, Zoom recording summary, or a simple paste into chat)
- **Extracts** key decisions, discussion topics, and action items with owners and deadlines
- **Creates tasks** in Jira, Linear, Todoist, or Notion — assigned to the right person with context from the meeting
- **Posts a summary** to Slack or Discord so the whole team has a record
- **Follows up** — optionally pings assignees before deadlines via scheduled reminders

## Skills You Need

- Jira, Linear, Todoist, or Notion integration (for task creation)
- Slack or Discord integration (for posting summaries)
- File system access (for reading transcript files)
- Scheduling / cron (for follow-up reminders)
- Optional: Otter.ai, Fireflies.ai, or Google Meet API for automatic transcript retrieval

## How to Set It Up

1. Choose your transcript source. The simplest approach is pasting the transcript directly into chat. For automation, set up a folder watch or API integration.

2. Prompt OpenClaw:
```text
I just finished a meeting. Here's the transcript:

[paste transcript or point to file]

Please:
1. Write a concise summary (max 5 bullet points) covering key decisions and topics.
2. Extract ALL action items. For each one, identify:
   - What needs to be done
   - Who is responsible (match names to my team)
   - Deadline (if mentioned, otherwise mark as "TBD")
3. Create a Jira ticket for each action item, assigned to the right person.
4. Post the full summary to #meeting-notes in Slack.
```

3. For fully automated pipeline (transcript folder watch):
```text
Set up a recurring task: every 30 minutes, check ~/meeting-transcripts/ for
new .txt or .vtt files. When you find one:

1. Parse the transcript into a structured summary with action items.
2. Create tasks in Linear for each action item.
3. Post the summary to #team-updates in Slack.
4. Move the processed file to ~/meeting-transcripts/processed/.

For each action item with a deadline, set a reminder to ping the assignee
in Slack one day before it's due.
```

4. Customize the output format:
```text
When writing meeting summaries, always use this structure:
- **Date & Attendees** at the top
- **Key Decisions** — numbered list of what was decided
- **Action Items** — table with columns: Task, Owner, Deadline, Status
- **Open Questions** — anything unresolved that needs follow-up
```

## Key Insights

- The real value isn't in the summary — it's in the **automatic task creation**. Meeting notes that don't become tracked tasks are just documentation theater.
- Pair this with the [Todoist Task Manager](todoist-task-manager.md) use case for full visibility into agent-created tasks.
- VTT/SRT subtitle files from Zoom or Google Meet work great as input — they include timestamps which help the agent attribute statements to speakers.
- Start simple (paste transcript, get summary) and automate incrementally. Don't over-engineer the pipeline before validating the output quality.

## Related Links

- [Otter.ai API](https://otter.ai/)
- [Jira REST API](https://developer.atlassian.com/cloud/jira/platform/rest/v3/)
- [Linear API](https://developers.linear.app/)
- [Slack API](https://api.slack.com/)
