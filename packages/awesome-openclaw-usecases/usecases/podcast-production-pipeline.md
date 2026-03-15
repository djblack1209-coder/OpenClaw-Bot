# Podcast Production Pipeline

You have a podcast idea, maybe even a backlog of episode topics. But between researching guests, writing outlines, drafting intros, generating show notes, and writing social media posts for promotion — the production overhead kills your momentum. What if you handed off a topic and got back a full production package?

This use case chains agents together to handle the entire podcast production workflow from topic to publish-ready assets.

## Pain Point

Solo podcasters and small teams spend more time on production than on actually recording. Research takes hours, show notes are an afterthought, and social media promotion is the first thing that gets skipped. The creative part — the conversation — is maybe 30% of the total effort. This agent handles the other 70%.

## What It Does

- **Episode Research** — given a topic or guest name, compiles background research, talking points, and suggested questions
- **Outline & Script** — generates a structured episode outline with intro script, segment transitions, and closing remarks
- **Show Notes** — after recording, processes the transcript into timestamped show notes with links to everything mentioned
- **Social Media Kit** — creates promotional posts for X, LinkedIn, and Instagram with episode highlights and pull quotes
- **Episode Description** — writes SEO-optimized episode descriptions for Spotify, Apple Podcasts, and YouTube

## Skills You Need

- Web search / research skill (for guest research and topic deep-dives)
- File system access (for reading transcripts and writing output files)
- Slack, Discord, or Telegram integration (for delivering assets)
- Optional: `sessions_spawn` for running research and writing agents in parallel
- Optional: RSS feed skill (for monitoring competitor podcasts)

## How to Set It Up

1. Pre-recording — generate research and outline:
```text
I'm recording a podcast episode about [TOPIC]. My guest is [NAME].

Please:
1. Research the guest — their background, recent work, hot takes, and
   anything controversial or interesting they've said publicly.
2. Research the topic — key trends, recent news, common misconceptions,
   and what the audience likely already knows vs. what would surprise them.
3. Generate an episode outline:
   - Cold open hook (1-2 sentences to grab attention)
   - Intro script (30 seconds, casual tone)
   - 5-7 interview questions, ordered from easy/rapport-building to deep/provocative
   - 2-3 "back pocket" questions in case the conversation stalls
   - Closing segment with call-to-action

Save everything to ~/podcast/episodes/[episode-number]/prep/
```

2. Post-recording — generate show notes and promo:
```text
Here's the transcript for Episode [NUMBER]: [paste or point to file]

Please:
1. Write timestamped show notes — every major topic shift gets a timestamp
   and one-line summary. Include links to anything mentioned (tools, books,
   articles, people).
2. Write an episode description (max 200 words) optimized for podcast
   search. Include 3-5 relevant keywords naturally.
3. Create social media posts:
   - X/Twitter: 3 tweets — one pull quote, one key insight, one question
     to spark discussion. Each under 280 chars.
   - LinkedIn: 1 post, professional tone, 100-150 words.
   - Instagram caption: 1 post with emoji, casual tone, include relevant hashtags.
4. Extract a "highlights" list — the 3 most interesting/surprising moments
   with timestamps.

Save everything to ~/podcast/episodes/[episode-number]/publish/
```

3. Optional — competitor monitoring:
```text
Monitor these podcast RSS feeds daily:
- [feed URL 1]
- [feed URL 2]

When a new episode drops that covers a topic relevant to my podcast,
send me a Telegram message with:
- Episode title and link
- One-sentence summary
- Whether this is something I should respond to or cover from my angle
```

## Key Insights

- The **pre-recording research** is where most value is. Walking into an interview with deep guest research makes the conversation dramatically better — and that's something you can't fake in post-production.
- Show notes with timestamps are a huge listener retention tool. Most podcasters skip them because they're tedious. This agent makes them effortless.
- The social media kit saves the most *recurring* time. You need promo for every single episode, and it's always the same structure — perfect for automation.
- Pairs well with the [Multi-Agent Content Factory](content-factory.md) if you want to repurpose podcast content into blog posts, newsletters, or video clips.

## Related Links

- [Podcast RSS Feed Spec](https://podcasters.apple.com/support/823-podcast-requirements)
- [Spotify for Podcasters](https://podcasters.spotify.com/)
- [Whisper (OpenAI)](https://github.com/openai/whisper) — for local transcript generation
