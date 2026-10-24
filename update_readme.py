#!/usr/bin/env python3
"""Scans a GitHub user's public repos and rewrites marked sections of README.md.
No third-party dependencies."""
import json, os, re, sys, urllib.request
from collections import Counter
from datetime import datetime, timezone

USER = os.environ.get("GH_USER", "Volzez")
TOKEN = os.environ.get("GH_TOKEN", "")
README = os.path.join(os.path.dirname(__file__), "..", "README.md")

# interest -> keywords searched in repo name, description, topics, language
INTERESTS = {
    "⚙️ Automation & Workflows": ["automation", "automate", "workflow", "bot", "cli", "script", "pipeline", "actions"],
    "🌐 Web Development": ["react", "next", "nextjs", "web", "frontend", "website", "vue", "svelte", "tailwind", "html", "css"],
    "🔌 Backend & APIs": ["api", "backend", "server", "express", "fastapi", "flask", "graphql", "database", "sql", "node"],
    "🤖 AI & Machine Learning": ["ai", "ml", "llm", "machine-learning", "gpt", "neural", "openai", "claude", "model"],
    "🦀 Systems & Low-Latency": ["rust", "systems", "latency", "kernel", "compiler", "performance", "embedded", "cpp", "c"],
    "🐳 DevOps & Infrastructure": ["docker", "kubernetes", "ci", "devops", "linux", "terraform", "deploy", "shell", "bash"],
    "🎮 Games & Graphics": ["game", "unity", "godot", "graphics", "three", "opengl"],
    "🛡️ Security": ["security", "pentest", "ctf", "crypto", "hacking", "exploit"],
    "📱 Mobile": ["android", "ios", "flutter", "swift", "kotlin"],
}

def api(path):
    req = urllib.request.Request(path if path.startswith("http") else f"https://api.github.com{path}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "readme-updater")
    if TOKEN:
        req.add_header("Authorization", f"Bearer {TOKEN}")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)

def get_repos():
    repos, page = [], 1
    while True:
        batch = api(f"/users/{USER}/repos?per_page=100&page={page}&type=owner&sort=pushed")
        repos += batch
        if len(batch) < 100:
            break
        page += 1
    # skip forks, archived, and the profile repo itself
    return [r for r in repos if not r["fork"] and not r["archived"] and r["name"].lower() != USER.lower()]

def tokens(repo):
    text = " ".join([repo["name"], repo.get("description") or "", repo.get("language") or "", " ".join(repo.get("topics", []))]).lower()
    t = set(re.findall(r"[a-z0-9\+\#]+", text))
    t |= set(re.findall(r"[a-z0-9\-]+", text))
    return {"cpp" if x == "c++" else x for x in t}

def lang_bytes(repos):
    total = Counter()
    for r in repos[:40]:
        try:
            total.update(api(r["languages_url"]))
        except Exception as e:
            print(f"warn: languages for {r['name']}: {e}", file=sys.stderr)
    return total

def bar(pct, width=20):
    filled = round(pct / 100 * width)
    return "█" * filled + "░" * (width - filled)

def section_languages(langs):
    if not langs:
        return "_No language data yet — push some code!_"
    total = sum(langs.values())
    rows = ["| Language | Share | |", "|:--|--:|:--|"]
    for name, b in langs.most_common(8):
        p = b / total * 100
        rows.append(f"| `{name}` | {p:.1f}% | `{bar(p)}` |")
    return "\n".join(rows)

def section_topics(repos):
    c = Counter(t for r in repos for t in r.get("topics", []))
    if not c:
        return "<sub>Tip: add topics to your repos (Settings → About ⚙️) and they'll show up here.</sub>"
    return "**Topics:** " + " ".join(f"`{t}`" for t, _ in c.most_common(15))

def section_interests(repos):
    score = Counter()
    for r in repos:
        toks = tokens(r)
        for label, kws in INTERESTS.items():
            hits = sum(1 for k in kws if k in toks)
            if hits:
                score[label] += hits
    if not score:
        return "_Not enough data yet — add descriptions and topics to your repos._"
    top = score.most_common(5)
    return "\n".join(f"- **{label}** — matched across {n} signal{'s' if n != 1 else ''}" for label, n in top)

def ago(iso):
    d = datetime.now(timezone.utc) - datetime.fromisoformat(iso.replace("Z", "+00:00"))
    if d.days >= 1: return f"{d.days}d ago"
    h = d.seconds // 3600
    return f"{h}h ago" if h else f"{d.seconds // 60}m ago"

def section_recent(repos):
    rows = ["| Repo | What it is | Lang | Updated |", "|:--|:--|:--|:--|"]
    for r in sorted(repos, key=lambda x: x["pushed_at"], reverse=True)[:6]:
        desc = (r.get("description") or "—").replace("|", "\\|")
        lang = f"`{r['language']}`" if r.get("language") else "—"
        stars = f" ⭐{r['stargazers_count']}" if r["stargazers_count"] else ""
        rows.append(f"| [**{r['name']}**]({r['html_url']}){stars} | {desc} | {lang} | {ago(r['pushed_at'])} |")
    return "\n".join(rows) if len(rows) > 2 else "_No public repos yet._"

def section_stats(repos, profile):
    stars = sum(r["stargazers_count"] for r in repos)
    return "\n".join([
        f"- 💻 **Host:** `{USER}`",
        f"- 📦 **Public repos scanned:** `{len(repos)}`",
        f"- ⭐ **Stars earned:** `{stars}`",
        f"- 👥 **Followers:** `{profile.get('followers', 0)}`",
        f"- 🌍 **Location:** `{profile.get('location') or 'LOCALHOST // GRID_COORD'}`",
        "- 🛠️ **Environment Status:** Active deployment tracking enabled.",
    ])

def replace(text, name, body):
    pat = re.compile(rf"(<!--START_SECTION:{name}-->)(.*?)(<!--END_SECTION:{name}-->)", re.S)
    if not pat.search(text):
        print(f"warn: marker '{name}' not found", file=sys.stderr)
        return text
    inline = name == "updated"
    return pat.sub(lambda m: f"{m.group(1)}{body}{m.group(3)}" if inline else f"{m.group(1)}\n{body}\n{m.group(3)}", text)

def main():
    repos = get_repos()
    profile = api(f"/users/{USER}")
    sections = {
        "interests": section_interests(repos),
        "languages": section_languages(lang_bytes(repos)),
        "topics": section_topics(repos),
        "recent": section_recent(repos),
        "stats": section_stats(repos, profile),
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    }
    with open(README, encoding="utf-8") as f:
        text = f.read()
    for k, v in sections.items():
        text = replace(text, k, v)
    with open(README, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"Updated README for {USER}: {len(repos)} repos")

if __name__ == "__main__":
    main()
