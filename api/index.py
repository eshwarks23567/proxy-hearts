"""Agentic dating: scrape (LinkedIn + Instagram) -> analyze -> screen -> date -> rank.

One file, stdlib only, so the same code runs as the Vercel function (GET/POST /api/index?op=...) and in the
local batch pipeline (pipeline.py imports it). Every person is described ONLY by their LinkedIn + Instagram.
"""
import base64, json, os, re, time, urllib.error, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler

APIFY = "https://api.apify.com/v2/acts/{actor}/run-sync-get-dataset-items?token={token}&timeout=110"
UA = "proxy-hearts/1.0 (+https://github.com/eshwarks23567/proxy-hearts)"
IG_ACTOR = os.environ.get("IG_ACTOR", "apify~instagram-profile-scraper")
LI_ACTOR = os.environ.get("LI_ACTOR", "supreme_coder~linkedin-profile-scraper")


# ---------------------------------------------------------------- LLM (OpenAI-compatible, provider pool)

def providers(vision=False):
    """Every configured (url, key, model). Groq limits are per model, so rotating models multiplies throughput."""
    pool = []
    groq, gem = os.environ.get("GROQ_API_KEY"), os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if groq and not vision:  # Groq has no vision model on this account; its text models are fast (8k tokens/min each)
        pool += [("https://api.groq.com/openai/v1/chat/completions", groq, m.strip())
                 for m in os.environ.get("GROQ_MODELS", "openai/gpt-oss-120b,openai/gpt-oss-20b").split(",")]
    if gem:  # Gemini reads photos, and is an extra (slower) lane for text with a much bigger token budget
        pool.append(("https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", gem,
                     os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")))
    if not pool:
        raise RuntimeError("No LLM key configured (GROQ_API_KEY or GEMINI_API_KEY)")
    return pool


_cool = {}  # model -> time it's usable again (from the provider's "try again in Xs")


def chat(messages, vision=False, temperature=0.8, tries=10, timeout=55):
    """JSON-mode chat across a provider pool. A rate-limited model cools down for exactly as long as the
    provider says; the call goes to the model that frees up first."""
    pool = providers(vision)
    last = None
    for _ in range(tries):
        url, key, model = min(pool, key=lambda p: _cool.get(p[2], 0))
        wait = _cool.get(model, 0) - time.time()
        if wait > 0:
            time.sleep(min(wait, 60))
        _cool[model] = time.time() + 1  # light spacing; other threads prefer an idle model
        body = {"model": model, "messages": messages, "temperature": temperature,
                "response_format": {"type": "json_object"}}
        req = urllib.request.Request(url, json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}", "User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                text = json.load(r)["choices"][0]["message"]["content"]
            return parse_json(text)
        except urllib.error.HTTPError as e:
            msg = e.read()[:400].decode(errors="replace")
            last = f"{model}: HTTP {e.code} {msg}"
            m = re.search(r"try again in ([\d.]+)(m?s)", msg)
            delay = (float(m.group(1)) / (1000 if m.group(2) == "ms" else 1)) if m else (5 if e.code in (429, 500, 502, 503, 504) else 120)
            _cool[model] = time.time() + delay + 0.5
        except (TimeoutError, urllib.error.URLError, ValueError, KeyError) as e:
            last = f"{model}: {e}"
            _cool[model] = time.time() + 5
    raise RuntimeError(f"LLM failed: {last}")


def parse_json(text):
    try:
        return json.loads(text)
    except ValueError:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            raise
        return json.loads(m.group(0))


# ---------------------------------------------------------------- scraping (Apify)

def apify(actor, payload):
    token = os.environ.get("APIFY_TOKEN")
    if not token:
        raise RuntimeError("APIFY_TOKEN not configured")
    req = urllib.request.Request(APIFY.format(actor=actor, token=token), json.dumps(payload).encode(),
                                 method="POST", headers={"Content-Type": "application/json", "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def ig_username(url):
    m = re.search(r"instagram\.com/([A-Za-z0-9._]+)", url or "")
    if not m or m.group(1) in ("p", "reel", "explore", "accounts", "stories"):
        raise ValueError(f"Not an Instagram profile link: {url}")
    return m.group(1).lower()


def li_slug(url):
    m = re.search(r"linkedin\.com/in/([^/?#]+)", url or "")
    if not m:
        raise ValueError(f"Not a LinkedIn profile link (needs /in/...): {url}")
    return urllib.parse.unquote(m.group(1)).lower()


def scrape_instagram(usernames):
    items = apify(IG_ACTOR, {"usernames": usernames, "resultsLimit": 12})
    return {(i.get("username") or "").lower(): i for i in items if isinstance(i, dict)}


def scrape_linkedin(urls, retries=2):
    """The actor's account pool sometimes runs dry ({"error": "no available accounts found"}): retry just those."""
    out, todo = {}, list(urls)
    for _ in range(retries + 1):
        if not todo:
            break
        items = apify(LI_ACTOR, {"urls": [{"url": u} for u in todo], "findContacts": False, "scrapeCompany": False})
        for u in list(todo):
            slug = li_slug(u)
            hit = next((i for i in items if slug in json.dumps(i, ensure_ascii=False).lower() and "error" not in i), None)
            if hit:
                out[slug] = hit
                todo.remove(u)
    return out


def slim_instagram(i):
    if not i:
        return None
    if i.get("private") or i.get("isPrivate"):
        return {"private": True}
    posts = [{k: p.get(k) for k in ("caption", "hashtags", "locationName", "timestamp", "type", "alt") if p.get(k)}
             for p in (i.get("latestPosts") or [])[:12]]
    return {"username": i.get("username"), "fullName": i.get("fullName"), "biography": i.get("biography"),
            "followers": i.get("followersCount"), "following": i.get("followsCount"), "posts": i.get("postsCount"),
            "businessCategory": i.get("businessCategoryName"), "latestPosts": posts,
            "_pic": i.get("profilePicUrlHD") or i.get("profilePicUrl"),
            "_images": [p.get("displayUrl") for p in (i.get("latestPosts") or []) if p.get("displayUrl")][:4]}


DROP = re.compile(r"(url|urn|^id$|_id$|Id$|pic|image|logo|thumbnail|token|email|phone|contact)", re.I)


def slim(obj, depth=0):
    """Drop links/ids/contact data and trim lists so the model reads substance, not plumbing."""
    if isinstance(obj, dict):
        return {k: slim(v, depth + 1) for k, v in obj.items() if not DROP.search(k) and v not in (None, "", [], {})}
    if isinstance(obj, list):
        return [slim(v, depth + 1) for v in obj[:8]]
    if isinstance(obj, str):
        return obj[:600]
    return obj


def fetch_image(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = r.read()
        return "data:image/jpeg;base64," + base64.b64encode(data).decode() if len(data) < 3_500_000 else None
    except Exception:
        return None


def scrape_person(linkedin_url, instagram_url):
    u, s = ig_username(instagram_url), li_slug(linkedin_url)
    with ThreadPoolExecutor(2) as ex:
        ig_f, li_f = ex.submit(scrape_instagram, [u]), ex.submit(scrape_linkedin, [linkedin_url])
        ig, li = ig_f.result().get(u), li_f.result().get(s)
    return {"id": u, "linkedin_url": linkedin_url, "instagram_url": instagram_url,
            "instagram": slim_instagram(ig), "linkedin": slim(li) if li else None}


# ---------------------------------------------------------------- the agent reads its person

ANALYZE = """You are a dating agent. You are about to represent ONE real person, and the ONLY things you know about
them are their public LinkedIn and public Instagram (below, plus some of their recent Instagram photos).
Read both carefully, cross-reference them, and write the dossier you'll date with.

Rules:
- Every claim must be grounded in the two sources. Put the evidence (a quote, post, job, photo detail) next to it.
- Separate what is stated from what you infer; inferences get "confidence": "low|medium|high".
- NEVER infer or mention sexual orientation, religion, ethnicity, health, politics, or relationship status.
  NEVER include contact details or addresses. Location at city level only if stated.
- If a source is missing, private or thin, say so in data_gaps instead of inventing.

Return JSON:
{"name": str, "headline": str, "location": str|null,
 "summary": "3 sentences: who they are, what drives them, what they'd bring to a relationship",
 "needs": [{"need": "what they need from a partner/relationship", "evidence": str, "confidence": str}],   // 3-5
 "hobbies": [{"item": str, "evidence": str, "source": "instagram|linkedin|both"}],                        // 3-6
 "interests": [{"item": str, "evidence": str, "source": "instagram|linkedin|both"}],                      // 3-6
 "values": [{"item": str, "evidence": str}],                                                             // 2-4
 "personality": {"traits": [str], "communication_style": str, "energy": "introvert-leaning|ambivert|extrovert-leaning"},
 "lifestyle": str, "career": {"stage": str, "drive": str},
 "green_flags_in_a_match": [str], "likely_dealbreakers": [str],
 "ideal_first_date": str, "conversation_starters": [str],
 "visual_read": "what their photos show about how they spend time (no appearance judgements)",
 "data_gaps": [str], "overall_confidence": "low|medium|high"}"""


def analyze(person):
    ig, li = person.get("instagram") or {}, person.get("linkedin")
    # each source trimmed on its own (~3k tokens total) so neither crowds the other out
    text = ("LINKEDIN: " + json.dumps(li or "NOT AVAILABLE", ensure_ascii=False)[:4500] + "\n\nINSTAGRAM: "
            + json.dumps({k: v for k, v in ig.items() if not k.startswith("_")} or "NOT AVAILABLE", ensure_ascii=False)[:4500])
    images = [] if os.environ.get("VISION", "1") == "0" else [d for d in (fetch_image(u) for u in ig.get("_images", [])[:4]) if d]
    content = [{"type": "text", "text": ANALYZE + "\n\nSOURCES:\n" + text}]
    content += [{"type": "image_url", "image_url": {"url": d}} for d in images]
    try:
        if not images:
            raise RuntimeError("no photos")
        prof = chat([{"role": "user", "content": content}], vision=True, temperature=0.4, tries=2,
                    timeout=int(os.environ.get("VISION_TIMEOUT", "30" if os.environ.get("VERCEL") else "90")))
    except RuntimeError:  # no photos, or the vision model is slow/down: read the text sources only
        prof = chat([{"role": "user", "content": content[0]["text"]}], temperature=0.4)
        images = []
    prof["photos_read"] = len(images)
    return prof


def card(pid, p):
    """What other agents see when screening: a short public card, no evidence quotes."""
    pick = lambda xs: [x.get("item", x) if isinstance(x, dict) else x for x in (xs or [])][:5]
    return {"id": pid, "name": p.get("name"), "headline": p.get("headline"), "summary": p.get("summary"),
            "hobbies": pick(p.get("hobbies")), "interests": pick(p.get("interests")), "values": pick(p.get("values")),
            "energy": (p.get("personality") or {}).get("energy"), "ideal_first_date": p.get("ideal_first_date")}


def dossier(p):
    """What the agent carries into screening and dates: the substance of the profile, without the evidence quotes
    (those stay on the profile page) -- about half the tokens, which matters on free-tier rate limits."""
    items = lambda xs, key="item": [x.get(key) if isinstance(x, dict) else x for x in (xs or [])]
    per = p.get("personality") or {}
    return json.dumps({
        "name": p.get("name"), "headline": p.get("headline"), "location": p.get("location"), "summary": p.get("summary"),
        "needs": items(p.get("needs"), "need"), "hobbies": items(p.get("hobbies")), "interests": items(p.get("interests")),
        "values": items(p.get("values")), "traits": per.get("traits"), "communication_style": per.get("communication_style"),
        "energy": per.get("energy"), "lifestyle": p.get("lifestyle"), "career": p.get("career"),
        "green_flags_in_a_match": p.get("green_flags_in_a_match"), "likely_dealbreakers": p.get("likely_dealbreakers"),
        "ideal_first_date": p.get("ideal_first_date"), "conversation_starters": p.get("conversation_starters")}, ensure_ascii=False)


# ---------------------------------------------------------------- screening: who does my agent ask out?

SCREEN = """You are the dating agent for {name}. Here is everything you know about your person:
{dossier}

Below are the profile cards of other people (each represented by their own agent). Score how well each one fits
YOUR person (0-100), based on their needs, values, lifestyle, energy and interests - not just shared hobbies.
Complementary can beat identical. Be discriminating: use the full range.
Return JSON: {{"scores": [{{"id": str, "score": int, "why": "one specific sentence"}}], "ask_out": [ids of your top {k}]}}

CARDS:
{cards}"""


def screen(pid, prof, cards, k=2):
    others = [c for c in cards if c["id"] != pid]
    # compact cards: 28 full cards would blow a free-tier token budget; this keeps the signal
    brief = [{"id": c["id"], "name": c.get("name"), "headline": (c.get("headline") or "")[:90],
              "hobbies": c.get("hobbies", [])[:3], "interests": c.get("interests", [])[:3],
              "values": c.get("values", [])[:2], "energy": c.get("energy")} for c in others]
    out = chat([{"role": "user", "content": SCREEN.format(name=prof.get("name"), dossier=dossier(prof), k=k,
                                                          cards=json.dumps(brief, ensure_ascii=False))}], temperature=0.3)
    valid = {c["id"] for c in others}
    out["scores"] = [s for s in out.get("scores", []) if s.get("id") in valid]
    out["ask_out"] = [i for i in out.get("ask_out", []) if i in valid][:k] or \
        [s["id"] for s in sorted(out["scores"], key=lambda s: -int(s.get("score", 0)))[:k]]
    return out


# ---------------------------------------------------------------- the date

AGENT = """You are {name}'s dating agent, out on a first date on their behalf with {other}'s agent.
You speak AS {name} (first person), but you only know what's in their dossier - never invent facts, jobs, places or
stories that aren't there. If asked something the dossier doesn't cover, say you'd want to find out / it's not
something you've shared publicly. Be warm, curious, specific and a bit playful; no clichés; 1-3 sentences per turn.
Your job: find out whether {other} genuinely fits {name}'s needs and dealbreakers - ask about them naturally.

{name}'s dossier (private to you):
{dossier}

What you know about {other} going in (their public card): {other_card}"""

TURN = """Date so far ({venue}):
{transcript}

Your move ({turn_label}). Return JSON: {{{venue_field}"say": "what {name} says out loud",
"private_note": "your agent's private read of the other person right now (what fits / what doesn't)",
"fit_signal": -2..2{verdict_field}}}"""

VERDICT = """, "verdict": {{"score": 0-100 how well they fit {name} (be calibrated and honest: 50 = pleasant but no
real fit, 70 = promising, 85+ = rare; judge against {name}'s needs and dealbreakers, not politeness), "see_again": true
only if you'd genuinely book a second date for {name} - most first dates don't earn one,
"why": "2 sentences referencing the conversation", "green_flags": [str], "red_flags": [str]}}"""


def go_on_date(a_id, a, b_id, b, rounds=3):
    """Two agents, each with ONLY its own person's dossier, take turns. Each gives a private verdict at the end."""
    sys_a = AGENT.format(name=a["name"], other=b["name"], dossier=dossier(a), other_card=json.dumps(card(b_id, b), ensure_ascii=False))
    sys_b = AGENT.format(name=b["name"], other=a["name"], dossier=dossier(b), other_card=json.dumps(card(a_id, a), ensure_ascii=False))
    turns, venue, verdicts = [], "a first date", {}
    for r in range(rounds):
        for who, sys, name in ((a_id, sys_a, a["name"]), (b_id, sys_b, b["name"])):
            last = r == rounds - 1
            first = r == 0 and who == a_id
            prompt = TURN.format(
                venue=venue, name=name,
                transcript="\n".join(f'{t["name"]}: {t["say"]}' for t in turns) or "(nothing yet - you asked them out, so you open)",
                turn_label="opening: pick a specific first-date venue that suits BOTH people and open the conversation" if first
                else ("last turn: wrap up the date naturally" if last else "keep the conversation going"),
                venue_field='"venue": "where you took them, specific", ' if first else "",
                verdict_field=VERDICT.format(name=name) if last else "")
            out = chat([{"role": "system", "content": sys}, {"role": "user", "content": prompt}])
            if first and out.get("venue"):
                venue = out["venue"]
            turns.append({"id": who, "name": name, "say": str(out.get("say", "")).strip(),
                          "private_note": out.get("private_note"), "fit_signal": out.get("fit_signal")})
            if last:
                verdicts[who] = out.get("verdict") or {}
    return {"a": a_id, "b": b_id, "venue": venue, "turns": turns, "verdicts": verdicts}


# ---------------------------------------------------------------- ranking

def rank(pid, screen_out, dates):
    """Screening score for everyone; dates override it with the agent's post-date verdict (+ mutual bonus)."""
    rows = {}
    for s in screen_out.get("scores", []):
        rows[s["id"]] = {"id": s["id"], "score": int(s.get("score", 0)), "why": s.get("why"), "dated": False}
    for d in dates:
        if pid not in (d["a"], d["b"]):
            continue
        other = d["b"] if d["a"] == pid else d["a"]
        mine, theirs = d["verdicts"].get(pid, {}), d["verdicts"].get(other, {})
        base = rows.get(other, {"score": 50})["score"]
        score = 0.35 * base + 0.65 * int(mine.get("score", base))
        mutual = bool(mine.get("see_again")) and bool(theirs.get("see_again"))
        rows[other] = {"id": other, "score": round(min(100, score + (5 if mutual else 0))), "why": mine.get("why"),
                       "dated": True, "mutual": mutual, "date": f'{d["a"]}__{d["b"]}'}
    return sorted(rows.values(), key=lambda r: -r["score"])


# ---------------------------------------------------------------- HTTP (Vercel)

def op_scrape(q):
    return scrape_person(q["linkedin"], q["instagram"])


def op_analyze(q):
    return analyze(q["person"])


def op_screen(q):
    return screen(q["id"], q["profile"], q["cards"], int(q.get("k", 2)))


def op_date(q):
    return go_on_date(q["a_id"], q["a"], q["b_id"], q["b"], int(q.get("rounds", 3)))


OPS = {"scrape": op_scrape, "analyze": op_analyze, "screen": op_screen, "date": op_date}


class handler(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._send(200, {"ok": True, "ops": list(OPS), "llm": [m for _, _, m in providers()] if os.environ.get("GROQ_API_KEY") or os.environ.get("GEMINI_API_KEY") else []})

    def do_POST(self):
        op = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get("op", [""])[0]
        try:
            q = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            if op not in OPS:
                return self._send(404, {"error": f"unknown op {op!r}"})
            self._send(200, OPS[op](q))
        except (ValueError, KeyError) as e:
            self._send(400, {"error": str(e)})
        except Exception as e:  # surface upstream failures (Apify / LLM) to the UI
            self._send(502, {"error": str(e)[:500]})
