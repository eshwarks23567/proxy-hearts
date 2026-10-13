"""Batch run for the demo: people.txt -> public/data/demo.json (+ profile photos).

people.txt: one person per line, "<linkedin url> , <instagram url>". Every step caches to data/, so re-running
resumes where it stopped (rate limits, network). Keys come from .env (APIFY_TOKEN, GROQ_API_KEY, GEMINI_API_KEY).
usage: python pipeline.py [--only scrape|analyze|screen|date|build]
"""
import json, os, re, sys, urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).parent
for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines() if (ROOT / ".env").exists() else []:
    k, _, v = line.partition("=")
    if k.strip() and v.strip():
        os.environ.setdefault(k.strip(), v.strip().strip('"'))
sys.path.insert(0, str(ROOT / "api"))
import index as core  # noqa: E402

DATA, PUB = ROOT / "data", ROOT / "public"
for d in ("raw", "profiles", "screens", "dates"):
    (DATA / d).mkdir(parents=True, exist_ok=True)
(PUB / "img").mkdir(parents=True, exist_ok=True)


def guard(fn):
    def run(x):
        try:
            return fn(x)
        except Exception as e:  # one failure must not stop the batch; re-running fills the gap
            print(f"  ! {x}: {str(e)[:160]}")
    return run


def load(p):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def save(p, obj):
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


def people():
    out = []
    for line in (ROOT / "people.txt").read_text(encoding="utf-8").splitlines():
        urls = re.findall(r"https?://\S+?(?=[\s,]|$)", line)
        li = next((u for u in urls if "linkedin.com/in/" in u), None)
        ig = next((u for u in urls if "instagram.com/" in u), None)
        if li and ig:
            out.append((core.ig_username(ig), li, ig))
    return out


def step_scrape(ppl):
    todo = [p for p in ppl if not (DATA / "raw" / f"{p[0]}.json").exists()]
    if not todo:
        return
    print(f"scraping {len(todo)} people (Apify, one batch per site)...")
    with ThreadPoolExecutor(2) as ex:
        igf = ex.submit(core.scrape_instagram, [p[0] for p in todo])
        lif = ex.submit(core.scrape_linkedin, [p[1] for p in todo])
        ig, li = igf.result(), lif.result()
    for pid, li_url, ig_url in todo:
        raw_li = li.get(core.li_slug(li_url))
        person = {"id": pid, "linkedin_url": li_url, "instagram_url": ig_url,
                  "instagram": core.slim_instagram(ig.get(pid)), "linkedin": core.slim(raw_li) if raw_li else None}
        save(DATA / "raw" / f"{pid}.json", person)
        pic = (person["instagram"] or {}).get("_pic")
        if pic:
            try:
                req = urllib.request.Request(pic, headers={"User-Agent": "Mozilla/5.0"})
                (PUB / "img" / f"{pid}.jpg").write_bytes(urllib.request.urlopen(req, timeout=20).read())
            except Exception as e:
                print("  no photo for", pid, e)
        print(f"  {pid}: instagram={'ok' if person['instagram'] else 'MISSING'} linkedin={'ok' if raw_li else 'MISSING'}")


def step_analyze(ppl):
    def one(pid):
        out = DATA / "profiles" / f"{pid}.json"
        if out.exists():
            return
        prof = core.analyze(load(DATA / "raw" / f"{pid}.json"))
        save(out, prof)
        print(f"  analyzed {pid}: {prof.get('name')} ({prof.get('photos_read')} photos)")
    with ThreadPoolExecutor(3) as ex:
        list(ex.map(guard(one), [p[0] for p in ppl]))


def profiles(ppl):
    out = {p[0]: load(DATA / "profiles" / f"{p[0]}.json") for p in ppl}
    return {k: v for k, v in out.items() if v}  # only people the agent has read


def step_screen(ppl):
    profs = profiles(ppl)
    cards = [core.card(pid, p) for pid, p in profs.items()]

    def one(pid):
        out = DATA / "screens" / f"{pid}.json"
        if not out.exists():
            save(out, core.screen(pid, profs[pid], cards))
            print(f"  {pid} asks out {load(out)['ask_out']}")
    with ThreadPoolExecutor(3) as ex:
        list(ex.map(guard(one), list(profs)))


def pairs(ppl):
    """Round 1: everyone's first choice. Round 2: a wildcard, someone screening rated a middling fit (~55), so the
    dates test the paper scores instead of only confirming them. First choices go first so a partial run still
    gives every person a date."""
    screens = {pid: load(DATA / "screens" / f"{pid}.json") or {} for pid, *_ in ppl}
    seen, out = set(), []

    def add(a, b):
        key = tuple(sorted((a, b)))
        if b and key not in seen:
            seen.add(key)
            out.append((a, b))  # the asker opens the date
    for pid, s in screens.items():
        add(pid, (s.get("ask_out") or [None])[0])
    for pid, s in screens.items():
        cands = [x for x in s.get("scores", []) if tuple(sorted((pid, x["id"]))) not in seen]
        if cands:
            add(pid, min(cands, key=lambda x: abs(int(x.get("score", 0)) - 55))["id"])
    return out


def step_date(ppl):
    profs = profiles(ppl)
    todo = pairs(ppl)
    print(f"{len(todo)} dates scheduled")

    def one(pair):
        a, b = pair
        out = DATA / "dates" / f"{a}__{b}.json"
        if out.exists():
            return
        d = core.go_on_date(a, profs[a], b, profs[b])
        save(out, d)
        va, vb = d["verdicts"].get(a, {}), d["verdicts"].get(b, {})
        print(f"  {a} x {b} @ {d['venue']}: {va.get('score')}/{vb.get('score')}")
    with ThreadPoolExecutor(3) as ex:
        list(ex.map(guard(one), todo))


def step_build(ppl):
    profs = profiles(ppl)
    dates = [load(p) for p in sorted((DATA / "dates").glob("*.json"))]
    dates = [d for d in dates if d["a"] in profs and d["b"] in profs]
    people_out = []
    for pid, li, ig in ppl:
        if pid not in profs or not (DATA / "screens" / f"{pid}.json").exists():
            continue
        raw = load(DATA / "raw" / f"{pid}.json")
        igd = raw.get("instagram") or {}
        people_out.append({
            "id": pid, "linkedin_url": li, "instagram_url": ig,
            "photo": f"img/{pid}.jpg" if (PUB / "img" / f"{pid}.jpg").exists() else None,
            "sources": {"instagram": {k: v for k, v in igd.items() if not k.startswith("_")},
                        "linkedin": raw.get("linkedin")},
            "profile": profs[pid], "card": core.card(pid, profs[pid]),
            "screen": load(DATA / "screens" / f"{pid}.json"),
            "ranking": core.rank(pid, load(DATA / "screens" / f"{pid}.json"), dates)})
    save(PUB / "data" / "demo.json", {"people": people_out, "dates": dates})
    print(f"built public/data/demo.json: {len(people_out)} people, {len(dates)} dates")


STEPS = {"scrape": step_scrape, "analyze": step_analyze, "screen": step_screen, "date": step_date, "build": step_build}

if __name__ == "__main__":
    (PUB / "data").mkdir(exist_ok=True)
    ppl = people()
    print(f"{len(ppl)} people in people.txt")
    only = sys.argv[2] if len(sys.argv) > 2 and sys.argv[1] == "--only" else None
    for name, fn in STEPS.items():
        if only in (None, name):
            print(f"== {name}")
            fn(ppl)
        if name == "scrape":  # the brief: exactly two sources per person, public Instagram only
            def usable(p):
                raw = load(DATA / "raw" / f"{p[0]}.json") or {}
                ig = raw.get("instagram") or {}
                return bool(raw.get("linkedin")) and bool(ig) and not ig.get("private")
            dropped = [p[0] for p in ppl if not usable(p)]
            ppl = [p for p in ppl if usable(p)]
            print(f"{len(ppl)} people have both sources" + (f"; skipped: {', '.join(dropped)}" if dropped else ""))
