"""Proxy Hearts as an MCP server (stdio, JSON-RPC 2.0, stdlib only).

Lets any MCP client (Claude Code, Hermes Agent, Claude Desktop, ...) drive the dating agents:
read a person from their LinkedIn + Instagram, list people, open a dossier, send two agents on a date,
read an agent's memory, and rank who fits someone best.

  Claude Code:  claude mcp add proxy-hearts -- python /path/to/mcp_server.py
  Hermes:       mcp_servers: {proxy-hearts: {command: python, args: [/path/to/mcp_server.py]}}   (config.yaml)

State = the demo (public/data/demo.json) + anything added through MCP (data/mcp_store.json). Keys come from .env.
"""
import json, os, sys
from pathlib import Path

ROOT = Path(__file__).parent
for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines() if (ROOT / ".env").exists() else []:
    k, _, v = line.partition("=")
    if k.strip() and v.strip() and not k.startswith("#"):
        os.environ.setdefault(k.strip(), v.strip().strip('"'))
sys.path.insert(0, str(ROOT / "api"))
import index as core  # noqa: E402

STORE = ROOT / "data" / "mcp_store.json"
PROTOCOL = "2025-06-18"


def state():
    demo = json.loads((ROOT / "public" / "data" / "demo.json").read_text(encoding="utf-8"))
    extra = json.loads(STORE.read_text(encoding="utf-8")) if STORE.exists() else {"people": [], "dates": []}
    people = {p["id"]: p for p in demo["people"] + extra["people"]}
    return people, demo["dates"] + extra["dates"], extra


def save(extra):
    STORE.parent.mkdir(exist_ok=True)
    STORE.write_text(json.dumps(extra, ensure_ascii=False, indent=1), encoding="utf-8")


def person(people, pid):
    if pid not in people:
        raise ValueError(f"unknown person {pid!r}; call list_people")
    return people[pid]


# ---------------------------------------------------------------- tools

def t_list_people(_):
    people, dates, _ = state()
    return [{"id": p["id"], "name": p["profile"].get("name"), "headline": p["profile"].get("headline"),
             "dates": sum(pid in (d["a"], d["b"]) for d in dates for pid in [p["id"]])} for p in people.values()]


def t_get_profile(a):
    people, dates, _ = state()
    p = person(people, a["person_id"])
    return {"profile": p["profile"], "memory": core.memory_for(p["id"], dates), "sources": {"linkedin": p["linkedin_url"], "instagram": p["instagram_url"]}}


def t_read_person(a):
    raw = core.scrape_person(a["linkedin_url"], a["instagram_url"])
    if not raw["instagram"] or raw["instagram"].get("private"):
        raise ValueError("Instagram is private or not found; only public profiles can be read")
    prof = core.analyze(raw)
    people, dates, extra = state()
    p = {"id": raw["id"], "linkedin_url": a["linkedin_url"], "instagram_url": a["instagram_url"], "profile": prof,
         "card": core.card(raw["id"], prof), "photo": None, "sources": {"linkedin": raw["linkedin"],
         "instagram": {k: v for k, v in (raw["instagram"] or {}).items() if not k.startswith("_")}}}
    extra["people"] = [x for x in extra["people"] if x["id"] != p["id"]] + [p]
    save(extra)
    return {"id": p["id"], "profile": prof}


def t_go_on_date(a):
    people, dates, extra = state()
    A, B = person(people, a["a_id"]), person(people, a["b_id"])
    d = core.go_on_date(A["id"], A["profile"], B["id"], B["profile"], core.clamp(a.get("rounds", 3), 1, 3),
                        core.memory_for(A["id"], dates), core.memory_for(B["id"], dates))  # agents remember past dates
    extra["dates"].append(d)
    save(extra)
    return d


def t_agent_memory(a):
    people, dates, _ = state()
    return core.memory_for(person(people, a["person_id"])["id"], dates)


def t_rank(a):
    people, dates, _ = state()
    p = person(people, a["person_id"])
    scr = p.get("screen") or core.screen(p["id"], p["profile"], [x["card"] for x in people.values()])
    return core.rank(p["id"], scr, dates)[: int(a.get("top", 10))]


S = lambda props, req: {"type": "object", "properties": props, "required": req}
ID = {"type": "string", "description": "person id (from list_people), e.g. 'melrobbins'"}
TOOLS = {
    "list_people": (t_list_people, "List everyone with a dating agent (id, name, headline, number of dates).", S({}, [])),
    "get_profile": (t_get_profile, "A person's agent dossier: needs, hobbies, interests, values, personality - each with evidence - plus the agent's memory.", S({"person_id": ID}, ["person_id"])),
    "read_person": (t_read_person, "Scrape a public LinkedIn + public Instagram and have a new agent read the person. Only for yourself or with permission.",
                    S({"linkedin_url": {"type": "string"}, "instagram_url": {"type": "string"}}, ["linkedin_url", "instagram_url"])),
    "go_on_date": (t_go_on_date, "Send two agents on a date on their people's behalf. Each knows only its own person (and its memory of past dates). Returns venue, transcript, private notes, verdicts.",
                   S({"a_id": ID, "b_id": ID, "rounds": {"type": "integer", "minimum": 1, "maximum": 3}}, ["a_id", "b_id"])),
    "agent_memory": (t_agent_memory, "What a person's agent has learned from its dates (what worked, what didn't).", S({"person_id": ID}, ["person_id"])),
    "rank": (t_rank, "Who fits this person best: screening scores, overridden by the agent's post-date verdicts.",
             S({"person_id": ID, "top": {"type": "integer"}}, ["person_id"])),
}


# ---------------------------------------------------------------- JSON-RPC over stdio

def handle(msg):
    method, mid, params = msg.get("method"), msg.get("id"), msg.get("params") or {}
    if mid is None:  # notification (e.g. notifications/initialized): no reply
        return None
    if method == "initialize":
        return {"protocolVersion": params.get("protocolVersion", PROTOCOL), "capabilities": {"tools": {}},
                "serverInfo": {"name": "proxy-hearts", "version": "1.0.0"}}
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": [{"name": n, "description": d, "inputSchema": s} for n, (_, d, s) in TOOLS.items()]}
    if method == "tools/call":
        fn = TOOLS.get(params.get("name"), (None,))[0]
        if not fn:
            raise KeyError(f"unknown tool {params.get('name')!r}")
        try:
            out = fn(params.get("arguments") or {})
            return {"content": [{"type": "text", "text": json.dumps(out, ensure_ascii=False, indent=1)}]}
        except Exception as e:  # tool errors go back to the model, not as protocol errors
            return {"content": [{"type": "text", "text": f"Error: {e}"}], "isError": True}
    raise KeyError(f"method not found: {method}")


def main():
    out = sys.stdout
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        try:
            result = handle(msg)
            if result is None:
                continue
            reply = {"jsonrpc": "2.0", "id": msg.get("id"), "result": result}
        except KeyError as e:
            reply = {"jsonrpc": "2.0", "id": msg.get("id"), "error": {"code": -32601, "message": str(e)}}
        out.write(json.dumps(reply, ensure_ascii=False) + "\n")
        out.flush()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
