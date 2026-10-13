# Proxy Hearts: agents that date on your behalf

**Live:** https://agentic-dating-lovat.vercel.app · paste a LinkedIn + public Instagram and watch your agent date.

Each person is represented by an AI agent. The agent reads exactly two sources about its person, their public
**LinkedIn** and public **Instagram**, writes an evidence-backed dossier (needs, hobbies, interests, values,
personality), then screens everyone else, asks people out, and goes on multi-turn dates with *other agents*.
Every person ends with a ranking of who fits them best.

## How it works

```
LinkedIn URL + Instagram URL
   │  Apify actors: supreme_coder/linkedin-profile-scraper (no cookies) + apify/instagram-profile-scraper
   ▼
Raw sources ── slimmed: links, ids, contact data and @mentions dropped; 12 latest posts (caption, hashtags,
   │           location, Instagram's own photo description "alt")
   ▼
1. READ      The agent writes a dossier. Every claim carries evidence (quote/post/job) and a confidence level;
             data gaps are admitted, never invented. Hard rule: no inference of orientation, religion, ethnicity,
             health, politics or relationship status.
2. SCREEN    Each agent sees everyone else's public card and scores all of them 0-100 for *its* person's needs,
             then picks who to ask out.
3. DATE      Two separate agents, each with ONLY its own person's dossier (plus the other's public card).
             The asker picks a venue that suits both, then they talk for 3 rounds, speaking as their person.
             After every message each agent writes a private note + fit signal the other never sees, and at
             the end each gives a private verdict (score, see-again, green/red flags).
4. RANK      For every person: screening score for everyone, replaced by the agent's post-date verdict for the
             people it dated (35% paper fit, 65% date), +5 when both agents want a second date (mutual).
```

## Code
| File | What |
|---|---|
| `api/index.py` | Everything: scraping, the agent prompts, screening, the date loop, ranking. Runs as one Vercel Python function (`POST /api/index?op=scrape\|analyze\|screen\|date`), stdlib only. |
| `pipeline.py` | Batch run for the demo: `people.txt` → `public/data/demo.json`. Every step is cached to `data/` and resumable. |
| `public/` | The site (no build step): people, profile pages, date transcripts with private notes, rankings, live "Try yours". |

LLMs: Groq (`openai/gpt-oss-120b`, `qwen/qwen3.8-27b`, `openai/gpt-oss-20b`, rotated, since limits are per model)
with Gemini as the fallback. Everything goes through the OpenAI-compatible chat API in JSON mode.

## Run it
```
# .env: APIFY_TOKEN=..., GROQ_API_KEY=..., GEMINI_API_KEY=... (optional)
python pipeline.py          # scrape -> analyze -> screen -> date -> build
vercel deploy --prod        # site + API; set the same env vars on Vercel
```

## Ethics
The demo uses public figures' public profiles. The dates are between AI agents, a simulation, and say nothing
about anyone's real relationships. Live submissions require confirming it's you or you have permission, and are
kept only in the visitor's browser. To be removed, open an issue.
