// Proxy Hearts: demo data (public/data/demo.json, produced by pipeline.py) + a live run for pasted links.
const S = { people: [], dates: [], byId: {} };
const app = document.getElementById("app");
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const item = (x) => (typeof x === "string" ? x : x?.item ?? x?.need ?? "");
const initials = (n) => esc((n || "?").split(/\s+/).map((w) => w[0]).slice(0, 2).join(""));
const avatar = (p, size = 12) => p?.photo
  ? `<img src="${esc(p.photo)}" alt="" class="avatar rounded-full w-${size} h-${size}">`
  : `<div class="avatar rounded-full w-${size} h-${size} grid place-items-center text-[#8a2846] font-semibold">${initials(p?.profile?.name)}</div>`;
const name = (id) => S.byId[id]?.profile?.name || id;
const dateKey = (d) => `${d.a}__${d.b}`;

function index() { S.byId = Object.fromEntries(S.people.map((p) => [p.id, p])); }

async function boot() {
  try { const r = await fetch("data/demo.json", { cache: "no-store" }); Object.assign(S, await r.json()); } catch { /* no demo yet */ }
  try { const live = JSON.parse(localStorage.getItem("ph-live") || "null"); if (live) { S.people.push(live.person); S.dates.push(...live.dates); } } catch {}
  index(); route();
}
window.addEventListener("hashchange", route);

function route() {
  const [, view, arg] = location.hash.split("/");
  window.scrollTo(0, 0);
  if (view === "p" && S.byId[arg]) return personView(S.byId[arg]);
  if (view === "d") return dateView(S.dates.find((d) => dateKey(d) === arg));
  if (view === "dates") return datesView();
  if (view === "rankings") return rankingsView();
  if (view === "try") return tryView();
  homeView();
}

// ------------------------------------------------------------------ home
function homeView() {
  const demo = S.people.filter((p) => !p.live);
  app.innerHTML = `
  <section class="fade grid md:grid-cols-[1.3fr_1fr] gap-8 items-center mb-10">
    <div>
      <h1 class="serif text-5xl md:text-6xl leading-[1.05] mb-4">Your agent dates.<br><em class="text-[#8a2846]">You just read the results.</em></h1>
      <p class="text-lg text-gray-600 mb-6">Every person here is represented by an AI agent. It reads exactly two things, their public LinkedIn and
      public Instagram, builds a dossier of their needs, hobbies and interests, then goes out on dates with other agents on their behalf.</p>
      <div class="flex gap-3"><a href="#/try" class="px-5 py-2.5 rounded-full bg-[#8a2846] text-white font-semibold">Paste your links</a>
      <a href="#/rankings" class="px-5 py-2.5 rounded-full border border-[#8a2846] text-[#8a2846] font-semibold">See rankings</a></div>
    </div>
    <div class="card p-5 text-sm">
      ${[["LinkedIn + Instagram", "two public links per person, scraped live"], ["The agent reads", "posts, captions, photos, career; every claim cites evidence"],
         ["Profile page", "needs · hobbies · interests · values · personality"], ["Screening", "each agent scores everyone and picks who to ask out"],
         ["The dates", "two agents talk, each knowing only its own person, then each gives a private verdict"], ["Ranking", "who fits each person best"]]
        .map(([t, d], i) => `<div class="flex gap-3 py-2 ${i ? "border-t border-[#f3e8eb]" : ""}"><span class="serif text-2xl text-[#8a2846] w-6">${i + 1}</span><div><b>${t}</b><div class="text-gray-500">${d}</div></div></div>`).join("")}
    </div>
  </section>
  <section class="grid grid-cols-3 gap-4 mb-8 text-center">
    ${[[demo.length, "people, each with an agent"], [S.dates.length, "dates the agents went on"], [S.dates.reduce((n, d) => n + d.turns.length, 0), "messages exchanged"]]
      .map(([n, l]) => `<div class="card p-4"><div class="serif text-4xl text-[#8a2846]">${n}</div><div class="text-sm text-gray-500">${l}</div></div>`).join("")}
  </section>
  <h2 class="serif text-3xl mb-4">The people</h2>
  ${demo.length ? "" : `<p class="text-gray-500">The demo hasn't been run yet. Run <code>python pipeline.py</code>.</p>`}
  <div class="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">${S.people.map(personCard).join("")}</div>`;
}

function personCard(p) {
  const pr = p.profile || {}, top = (p.ranking || [])[0];
  return `<a href="#/p/${esc(p.id)}" class="card p-4 flex gap-4 hover:-translate-y-0.5 transition fade">
    ${avatar(p, 14)}
    <div class="min-w-0"><div class="font-semibold">${esc(pr.name)} ${p.live ? '<span class="chip">you</span>' : ""}</div>
    <div class="text-xs text-gray-500 truncate">${esc(pr.headline)}</div>
    <div class="mt-1">${(pr.hobbies || []).slice(0, 3).map((h) => `<span class="chip">${esc(item(h))}</span>`).join("")}</div>
    ${top ? `<div class="text-xs mt-1 text-gray-600">Best fit: <b>${esc(name(top.id))}</b> · ${top.score}</div>` : ""}</div></a>`;
}

// ------------------------------------------------------------------ profile page
function evidenceList(title, xs, key = "item") {
  if (!xs?.length) return "";
  return `<div class="card p-5 reveal"><h3 class="serif text-2xl mb-2">${title}</h3><ul class="space-y-2">${xs.map((x) => `
    <li class="reveal"><b>${esc(x[key] ?? item(x))}</b>${x.confidence ? ` <span class="text-xs text-gray-400">(${esc(x.confidence)} confidence)</span>` : ""}
    ${x.source ? `<span class="chip">${esc(x.source)}</span>` : ""}
    ${x.evidence ? `<div class="text-sm text-gray-500 italic">“${esc(String(x.evidence).replace(/^["“”']+|["“”']+$/g, ""))}”</div>` : ""}</li>`).join("")}</ul></div>`;
}

function personView(p) {
  const pr = p.profile || {}, per = pr.personality || {}, src = p.sources || {}, ig = src.instagram || {};
  const myDates = S.dates.filter((d) => d.a === p.id || d.b === p.id);
  app.innerHTML = `
  <section class="fade flex flex-col md:flex-row gap-6 items-start mb-6">
    ${avatar(p, 28)}
    <div class="flex-1">
      <h1 class="serif text-5xl">${esc(pr.name)}</h1>
      <div class="text-gray-600">${esc(pr.headline)}${pr.location ? ` · ${esc(pr.location)}` : ""}</div>
      <div class="flex gap-2 mt-2 text-sm"><a class="chip" target="_blank" rel="noopener" href="${esc(p.linkedin_url)}">LinkedIn ↗</a>
      <a class="chip" target="_blank" rel="noopener" href="${esc(p.instagram_url)}">Instagram ↗</a>
      <span class="chip">analysis confidence: ${esc(pr.overall_confidence)}</span>
      <button id="replay" class="chip cursor-pointer hover:bg-[#8a2846] hover:text-white">▶ Replay analysis</button></div>
      <p class="mt-3 text-lg reveal">${esc(pr.summary)}</p>
    </div>
  </section>

  <div id="reading" class="card p-5 mb-6 text-sm">
    <div class="font-semibold mb-2">🤖 ${esc(pr.name?.split(" ")[0])}'s agent is reading them</div>
    <ol id="steps" class="space-y-1"></ol>
    <div id="ticker" class="mt-2 text-xs text-gray-500 italic h-4 overflow-hidden"></div>
  </div>

  <details class="card p-5 mb-6 reveal"><summary class="cursor-pointer font-semibold">How the agent read ${esc(pr.name)}: the two sources it was given</summary>
    <div class="grid md:grid-cols-2 gap-4 mt-3 text-sm">
      <div><h4 class="font-semibold mb-1">Instagram @${esc(ig.username)}</h4><p class="italic text-gray-600">${esc(ig.biography)}</p>
        <p class="text-gray-500">${esc(ig.posts)} posts · ${esc(ig.followers)} followers</p>
        <ul class="list-disc pl-5 mt-2 space-y-1">${(ig.latestPosts || []).slice(0, 6).map((x) => `<li>${esc((x.caption || x.alt || "").slice(0, 160))}</li>`).join("")}</ul></div>
      <div><h4 class="font-semibold mb-1">LinkedIn</h4><pre class="whitespace-pre-wrap text-xs bg-[#faf5f6] p-3 rounded-lg max-h-72 overflow-auto">${esc(JSON.stringify(src.linkedin, null, 1)?.slice(0, 2500) || "not available")}</pre></div>
    </div>
    ${pr.data_gaps?.length ? `<p class="text-sm mt-3"><b>Data gaps the agent admitted:</b> ${pr.data_gaps.map(esc).join(" · ")}</p>` : ""}
  </details>

  <div class="grid md:grid-cols-2 gap-4 mb-6">
    ${evidenceList("Needs", pr.needs, "need")}
    ${evidenceList("Hobbies", pr.hobbies)}
    ${evidenceList("Interests", pr.interests)}
    ${evidenceList("Values", pr.values)}
    <div class="card p-5 reveal"><h3 class="serif text-2xl mb-2">Personality</h3>
      <div>${(per.traits || []).map((t) => `<span class="chip">${esc(t)}</span>`).join("")}</div>
      <p class="text-sm mt-2"><b>Communication:</b> ${esc(per.communication_style)}</p><p class="text-sm"><b>Energy:</b> ${esc(per.energy)}</p>
      <p class="text-sm"><b>Lifestyle:</b> ${esc(pr.lifestyle)}</p><p class="text-sm"><b>Career:</b> ${esc(pr.career?.stage)}, ${esc(pr.career?.drive)}</p>
      ${pr.visual_read ? `<p class="text-sm mt-2"><b>From the photos:</b> ${esc(pr.visual_read)}</p>` : ""}</div>
    <div class="card p-5 reveal"><h3 class="serif text-2xl mb-2">What the agent looks for</h3>
      <p class="text-sm"><b>Green flags in a match:</b> ${(pr.green_flags_in_a_match || []).map(esc).join(" · ")}</p>
      <p class="text-sm mt-1"><b>Likely dealbreakers:</b> ${(pr.likely_dealbreakers || []).map(esc).join(" · ")}</p>
      <p class="text-sm mt-1"><b>Ideal first date:</b> ${esc(pr.ideal_first_date)}</p>
      <p class="text-sm mt-1"><b>Opening lines:</b> ${(pr.conversation_starters || []).map(esc).join(" · ")}</p></div>
  </div>

  <div class="grid md:grid-cols-2 gap-4">
    <div class="card p-5 reveal"><h3 class="serif text-2xl mb-2">Dates ${esc(pr.name?.split(" ")[0])}'s agent went on</h3>
      ${myDates.map((d) => { const o = d.a === p.id ? d.b : d.a, v = d.verdicts?.[p.id] || {};
        return `<a href="#/d/${esc(dateKey(d))}" class="flex items-center gap-3 py-2 border-t border-[#f3e8eb] first:border-0 hover:bg-[#faf5f6] rounded">
          ${avatar(S.byId[o], 10)}<div class="flex-1"><b>${esc(name(o))}</b><div class="text-xs text-gray-500">${esc(d.venue)}</div></div>
          <div class="text-right"><div class="serif text-2xl text-[#8a2846]">${esc(v.score ?? "–")}</div><div class="text-xs">${v.see_again ? "wants a 2nd date" : "no 2nd date"}</div></div></a>`; }).join("") || '<p class="text-gray-500 text-sm">No dates yet.</p>'}
    </div>
    <div class="card p-5 reveal"><h3 class="serif text-2xl mb-2">Ranking: who fits ${esc(pr.name?.split(" ")[0])} best</h3>${rankingList(p, 10)}</div>
  </div>`;
  document.getElementById("replay").onclick = () => personView(p);
  animateReading(p);
}

// The agent "reads" its person on screen, then the dossier reveals card by card, claim by claim.
function animateReading(p) {
  const pr = p.profile || {}, ig = p.sources?.instagram || {}, li = p.sources?.linkedin || {};
  const here = location.hash, alive = () => location.hash === here && document.getElementById("steps");
  const reveal = () => document.querySelectorAll(".reveal").forEach((el, i) => setTimeout(() => alive() && el.classList.add("in"), i * 90));
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) return reveal();
  const posts = ig.latestPosts || [];
  const caps = posts.map((x) => (x.caption || x.alt || "").replace(/\s+/g, " ").slice(0, 90)).filter(Boolean);
  const head = li.headline || li.occupation || pr.headline || "";
  const steps = [
    [`📸 Instagram @${ig.username || ""}: bio and ${posts.length} latest posts`, caps],
    ["💬 Captions, hashtags, locations, photo descriptions", (posts.flatMap((x) => x.hashtags || [])).slice(0, 12).map((h) => "#" + h)],
    [`💼 LinkedIn: ${head}`.slice(0, 110), [li.about || li.summary || ""].map((s) => String(s).slice(0, 90))],
    ["🔗 Cross-referencing both sources: what's stated vs. inferred", []],
    [`🧠 Writing the dossier: ${(pr.needs || []).length} needs, ${(pr.hobbies || []).length} hobbies, ${(pr.interests || []).length} interests, ${(pr.values || []).length} values`, []],
  ];
  const ol = document.getElementById("steps"), ticker = document.getElementById("ticker");
  let t = 0;
  steps.forEach(([label, flashes], i) => {
    setTimeout(() => {
      if (!alive()) return;
      ol.insertAdjacentHTML("beforeend", `<li class="fade" id="st${i}">⏳ ${esc(label)}</li>`);
      flashes.slice(0, 5).forEach((f, j) => setTimeout(() => alive() && (ticker.textContent = f ? `“${f}”` : ""), j * 160));
    }, t);
    t += 250 + Math.min(5, flashes.length) * 160;
    setTimeout(() => { const el = alive() && document.getElementById(`st${i}`); if (el) el.innerHTML = `✅ ${esc(label)}`; }, t);
  });
  setTimeout(() => { if (alive()) { ticker.textContent = ""; reveal(); } }, t + 150);
}

function rankingList(p, n) {
  return `<ol class="space-y-1">${(p.ranking || []).slice(0, n).map((r, i) => `
    <li class="flex items-start gap-3 py-1"><span class="serif text-xl w-6 text-gray-400">${i + 1}</span>${avatar(S.byId[r.id], 8)}
    <div class="flex-1 text-sm"><a href="#/p/${esc(r.id)}" class="font-semibold">${esc(name(r.id))}</a>
      ${r.dated ? `<a href="#/d/${esc(r.date)}" class="chip">dated ↗</a>` : ""}${r.mutual ? '<span class="chip">mutual ♥</span>' : ""}
      <div class="text-xs text-gray-500">${esc(r.why)}</div></div><span class="font-semibold text-[#8a2846]">${r.score}</span></li>`).join("")}</ol>`;
}

// ------------------------------------------------------------------ a date
function dateView(d) {
  if (!d) return (app.innerHTML = "<p>Date not found.</p>");
  const A = S.byId[d.a], B = S.byId[d.b];
  app.innerHTML = `
  <section class="fade text-center mb-6">
    <div class="flex justify-center items-center gap-4 mb-3">${avatar(A, 16)}<span class="serif text-3xl text-[#8a2846]">&amp;</span>${avatar(B, 16)}</div>
    <h1 class="serif text-4xl">${esc(name(d.a))} &amp; ${esc(name(d.b))}</h1>
    <p class="text-gray-600">📍 ${esc(d.venue)} · ${esc(name(d.a))}'s agent asked</p>
    <p class="text-xs text-gray-500 mt-1">Each side is a separate agent that only knows its own person's dossier. The grey notes are each agent's private thoughts; the other agent never sees them.</p>
  </section>
  <div class="max-w-3xl mx-auto space-y-4" id="chat"></div>
  <div class="max-w-3xl mx-auto grid md:grid-cols-2 gap-4 mt-8" id="verdicts"></div>`;
  const chat = document.getElementById("chat");
  d.turns.forEach((t, i) => setTimeout(() => {
    const mine = t.id === d.a;
    chat.insertAdjacentHTML("beforeend", `<div class="fade flex gap-3 ${mine ? "" : "flex-row-reverse"}">
      ${avatar(S.byId[t.id], 10)}<div class="max-w-[80%] ${mine ? "" : "text-right"}">
      <div class="text-xs text-gray-500 mb-1">${esc(t.name)}'s agent ${sig(t.fit_signal)}</div>
      <div class="inline-block text-left rounded-2xl px-4 py-2 ${mine ? "bubble-a" : "bubble-b"}">${esc(t.say)}</div>
      ${t.private_note ? `<div class="text-xs text-gray-400 italic mt-1">🔒 private note: ${esc(t.private_note)}</div>` : ""}</div></div>`);
    if (i === d.turns.length - 1) showVerdicts(d);
  }, i * 350));
}
const sig = (s) => { const n = Number(s); return isNaN(n) ? "" : `<span title="fit signal">${n > 0 ? "▲".repeat(n) : n < 0 ? "▼".repeat(-n) : "•"}</span>`; };

function showVerdicts(d) {
  document.getElementById("verdicts").innerHTML = [d.a, d.b].map((id) => { const v = d.verdicts?.[id] || {};
    return `<div class="card p-5 fade"><div class="text-xs text-gray-500">${esc(name(id))}'s agent, after the date</div>
      <div class="flex items-baseline gap-2"><span class="serif text-5xl text-[#8a2846]">${esc(v.score ?? "–")}</span><span>/100 · ${v.see_again ? "✅ wants a second date" : "❌ no second date"}</span></div>
      <p class="text-sm mt-2">${esc(v.why)}</p>
      <p class="text-xs mt-2"><b>Green flags:</b> ${(v.green_flags || []).map(esc).join(" · ")}</p>
      <p class="text-xs"><b>Red flags:</b> ${(v.red_flags || []).map(esc).join(" · ") || "none"}</p></div>`; }).join("");
}

function datesView() {
  app.innerHTML = `<h1 class="serif text-5xl mb-6 fade">Every date</h1><div class="grid md:grid-cols-2 gap-4">${S.dates.map((d) => {
    const va = d.verdicts?.[d.a] || {}, vb = d.verdicts?.[d.b] || {};
    return `<a href="#/d/${esc(dateKey(d))}" class="card p-4 flex items-center gap-3 fade">${avatar(S.byId[d.a], 10)}${avatar(S.byId[d.b], 10)}
      <div class="flex-1 min-w-0"><b>${esc(name(d.a))} &amp; ${esc(name(d.b))}</b><div class="text-xs text-gray-500 truncate">📍 ${esc(d.venue)}</div></div>
      <div class="text-sm text-right"><b class="text-[#8a2846]">${esc(va.score)} / ${esc(vb.score)}</b><div class="text-xs">${va.see_again && vb.see_again ? "mutual ♥" : ""}</div></div></a>`; }).join("")}</div>`;
}

// ------------------------------------------------------------------ rankings
function rankingsView() {
  const mutual = S.dates.filter((d) => d.verdicts?.[d.a]?.see_again && d.verdicts?.[d.b]?.see_again);
  app.innerHTML = `<h1 class="serif text-5xl mb-2 fade">Rankings</h1>
  <p class="text-gray-600 mb-6">For every person: who fits them best. Each agent first scored all the others from their profiles, then went on dates. A date replaces the paper score with the agent's verdict, plus a bonus when both agents want a second date.</p>
  ${mutual.length ? `<div class="card p-5 mb-6"><h2 class="serif text-3xl mb-2">Mutual matches ♥</h2><div class="flex flex-wrap gap-2">${mutual.map((d) =>
    `<a href="#/d/${esc(dateKey(d))}" class="chip">${esc(name(d.a))} &amp; ${esc(name(d.b))}</a>`).join("")}</div></div>` : ""}
  <div class="grid md:grid-cols-2 lg:grid-cols-3 gap-4">${S.people.map((p) => `
    <div class="card p-4 fade"><a href="#/p/${esc(p.id)}" class="flex items-center gap-3 mb-2">${avatar(p, 10)}<b>${esc(p.profile?.name)}</b></a>${rankingList(p, 5)}</div>`).join("")}</div>`;
}

// ------------------------------------------------------------------ live run
function tryView() {
  app.innerHTML = `<h1 class="serif text-5xl mb-2 fade">Send your agent on dates</h1>
  <p class="text-gray-600 mb-6">Paste a public LinkedIn profile and the public Instagram that belongs to the same person. Their agent reads both,
  builds a profile, screens all ${S.people.filter((p) => !p.live).length} people here, goes on 2 dates, and ranks everyone. It takes about 1–2 minutes.</p>
  <form id="f" class="card p-5 grid gap-3 max-w-2xl">
    <input required name="linkedin" placeholder="https://www.linkedin.com/in/…" class="border rounded-lg px-3 py-2">
    <input required name="instagram" placeholder="https://www.instagram.com/…" class="border rounded-lg px-3 py-2">
    <label class="text-sm text-gray-600"><input type="checkbox" required> This is me, or I have this person's permission.</label>
    <button class="px-5 py-2.5 rounded-full bg-[#8a2846] text-white font-semibold w-fit">Start my agent</button>
  </form>
  <ol id="log" class="mt-6 space-y-2 max-w-2xl"></ol>`;
  document.getElementById("f").onsubmit = (e) => {
    e.preventDefault();
    // accept the two links in either box, with or without https://
    const links = [...new FormData(e.target).values()].filter((v) => typeof v === "string" && v.trim())
      .map((v) => (/^https?:\/\//.test(v.trim()) ? v.trim() : "https://" + v.trim().replace(/^\/+/, "")));
    const li = links.find((u) => /linkedin\.com\/in\//i.test(u)), ig = links.find((u) => /instagram\.com\//i.test(u));
    if (!li || !ig) { document.getElementById("log").innerHTML = `<li class="card p-3 text-sm text-red-700">❌ Please paste one LinkedIn profile link (linkedin.com/in/…) and one Instagram profile link.</li>`; return; }
    run(li, ig);
  };
}

async function api(op, body) {
  const r = await fetch(`/api/index?op=${op}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const j = await r.json().catch(() => ({ error: `HTTP ${r.status}` }));
  if (!r.ok || j.error) throw new Error(j.error || `HTTP ${r.status}`);
  return j;
}

async function run(linkedin, instagram) {
  const log = document.getElementById("log");
  const step = (t) => { log.insertAdjacentHTML("beforeend", `<li class="card p-3 fade text-sm">⏳ ${t}</li>`); return log.lastElementChild; };
  const done = (el, t) => (el.innerHTML = `✅ ${t}`);
  const demo = S.people.filter((p) => !p.live);
  try {
    let s = step("Scraping LinkedIn and Instagram…");
    const raw = await api("scrape", { linkedin, instagram });
    if (!raw.instagram || raw.instagram.private) throw new Error("Instagram profile is private or not found. Only public profiles can be read.");
    done(s, `Scraped: Instagram @${esc(raw.instagram.username)} (${raw.instagram.latestPosts?.length || 0} posts) · LinkedIn ${raw.linkedin ? "found" : "not found"}`);
    s = step("The agent is reading the person: captions, photos, career…");
    const profile = await api("analyze", { person: raw });
    const id = "live-" + raw.id, person = { id, live: true, linkedin_url: linkedin, instagram_url: instagram, photo: null, profile,
      sources: { instagram: Object.fromEntries(Object.entries(raw.instagram).filter(([k]) => !k.startsWith("_"))), linkedin: raw.linkedin } };
    done(s, `Profile built for <b>${esc(profile.name)}</b>: ${(profile.hobbies || []).slice(0, 3).map((h) => esc(item(h))).join(", ")}`);
    s = step(`Screening all ${demo.length} people…`);
    const scr = await api("screen", { id, profile, cards: demo.map((p) => p.card), k: 2 });
    done(s, `Asking out: ${scr.ask_out.map((x) => `<b>${esc(name(x))}</b>`).join(" and ")}`);
    const dates = [];
    for (const other of scr.ask_out) {
      s = step(`On a date with ${esc(name(other))}…`);
      const d = await api("date", { a_id: id, a: profile, b_id: other, b: S.byId[other].profile, rounds: 2 });
      dates.push(d);
      done(s, `Date with <b>${esc(name(other))}</b> at ${esc(d.venue)}: ${esc(d.verdicts?.[id]?.score ?? "?")} / ${esc(d.verdicts?.[other]?.score ?? "?")}`);
    }
    person.ranking = rankJS(id, scr, dates);
    S.people = S.people.filter((p) => !p.live).concat(person);
    S.dates = S.dates.filter((d) => !String(d.a).startsWith("live-")).concat(dates);
    index();
    try { localStorage.setItem("ph-live", JSON.stringify({ person, dates })); } catch {}
    log.insertAdjacentHTML("beforeend", `<li class="fade"><a href="#/p/${esc(id)}" class="px-5 py-2.5 rounded-full bg-[#8a2846] text-white font-semibold inline-block">Open ${esc(profile.name)}'s profile, dates &amp; ranking →</a></li>`);
  } catch (e) {
    log.insertAdjacentHTML("beforeend", `<li class="card p-3 text-sm text-red-700">❌ ${esc(e.message)}</li>`);
  }
}

function rankJS(pid, scr, dates) { // mirrors rank() in api/index.py
  const rows = {};
  for (const s of scr.scores || []) rows[s.id] = { id: s.id, score: +s.score || 0, why: s.why, dated: false };
  for (const d of dates) {
    const other = d.a === pid ? d.b : d.a, mine = d.verdicts?.[pid] || {}, theirs = d.verdicts?.[other] || {};
    const base = rows[other]?.score ?? 50, mutual = !!(mine.see_again && theirs.see_again);
    rows[other] = { id: other, score: Math.round(Math.min(100, 0.35 * base + 0.65 * (+mine.score || base) + (mutual ? 5 : 0))), why: mine.why, dated: true, mutual, date: dateKey(d) };
  }
  return Object.values(rows).sort((x, y) => y.score - x.score);
}

boot();
