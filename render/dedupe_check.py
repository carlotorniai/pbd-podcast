#!/usr/bin/env python3
"""Podcast repeat guard (cloud side, shared by OWITH.ai Daily and Pharma and Biotech Daily). Stops a story from being told again within N days.

Compares the candidate stories for the next episode against the story ledger of past
episodes (stories.json files on the `episodes` branch). Deterministic, no network.

Usage:
  python3 -I dedupe_check.py <candidates.json> <episodes_dir> <target_date> [--days 7] [--report out.json]

candidates.json / stories.json schema (a list, 5 to 7 items):
  {"headline": str, "keywords": [str, ...], "urls": [str, ...],
   "follow_up_of": "YYYY-MM-DD#n" (optional), "new_fact": str (optional), "review_note": str (optional)}
  keywords = 4 to 10 distinctive proper names: companies, people, products, places, deal names.

Verdicts per candidate:
  BLOCK   same article URL, or same event (keyword or headline overlap) inside the window
  REVIEW  partial overlap; the writer must reread the earlier story and either drop this one or
          add "review_note" explaining why it is a different event (then REVIEWED)
  FOLLOWUP accepted repeat of a topic: declared follow_up_of with a new_fact and only new URLs
  OK      new story
Exit codes: 0 clean, 3 at least one BLOCK or unresolved REVIEW, 1 bad input.
"""
import argparse, json, re, sys
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlsplit

STOP = set("""a an the and or of to in on for with at by from as is are was were be been it its this that
these those new says said after over into about than more most up down out amid via vs will would could
has have had not no yes report reports according today week year billion million percent""".split())
INDEX_PATTERNS = re.compile(r"/(section|sections|tag|tags|category|categories|topics?|newsletters?)(/|$)")


def norm_url(u: str):
    """Article identity: host without www, path without trailing slash, no query or fragment.
    Index and section pages return None because they legitimately recur."""
    try:
        s = urlsplit(u.strip())
    except ValueError:
        return None
    host = s.netloc.lower().removeprefix("www.")
    path = re.sub(r"/+$", "", s.path.lower())
    segments = [p for p in path.split("/") if p]
    if not host or len(segments) < 1 or INDEX_PATTERNS.search(path + "/"):
        return None
    if len(segments) == 1 and segments[0] in {"the-batch", "blog", "news", "archive", "p"}:
        return None
    return f"{host}/{path.lstrip('/')}"


def norm_kw(k: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", "", k.lower()).strip()


def words(text: str) -> set:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOP and len(w) > 2}


def jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def load_ledger(episodes_dir: Path, target: date, days: int):
    ledger = []
    for d in range(1, days + 1):
        day = (target - timedelta(days=d)).isoformat()
        folder = episodes_dir / day
        meta_p, stories_p = folder / "episode.json", folder / "stories.json"
        if not stories_p.exists():
            continue
        if meta_p.exists() and json.loads(meta_p.read_text()).get("kind") == "saturday":
            continue  # the Saturday story reuses the week's headlines by design
        for i, s in enumerate(json.loads(stories_p.read_text()), 1):
            ledger.append({"id": f"{day}#{i}", "date": day, **s})
    return ledger


def validate(stories) -> None:
    if not isinstance(stories, list) or not 1 <= len(stories) <= 10:
        raise ValueError("candidates must be a list of 1 to 10 stories")
    for s in stories:
        if not s.get("headline") or not isinstance(s.get("keywords"), list) or len(s["keywords"]) < 3:
            raise ValueError(f"story needs a headline and at least 3 keywords: {s.get('headline')!r}")
        if not isinstance(s.get("urls"), list) or not s["urls"]:
            raise ValueError(f"story needs at least one source url: {s['headline']!r}")


def check(cands, ledger):
    results, followups = [], 0
    for n, c in enumerate(cands, 1):
        ck = {norm_kw(k) for k in c["keywords"] if norm_kw(k)}
        cu = {u for u in map(norm_url, c["urls"]) if u}
        cw = words(c["headline"])
        verdict, hits = "OK", []
        for p in ledger:
            pk = {norm_kw(k) for k in p.get("keywords", []) if norm_kw(k)}
            pu = {u for u in map(norm_url, p.get("urls", [])) if u}
            shared_kw, shared_url = ck & pk, cu & pu
            jk, jh = jaccard(ck, pk), jaccard(cw, words(p.get("headline", "")))
            if shared_url:
                level = "BLOCK"
                why = f"same article already used on {p['date']}: {sorted(shared_url)[0]}"
            elif jk >= 0.4 or len(shared_kw) >= 3 or jh >= 0.5:
                level = "BLOCK"
                why = f"same event as {p['id']} ({p['headline']!r}); shared keywords {sorted(shared_kw)}"
            elif len(shared_kw) == 2 or jh >= 0.3:
                level = "REVIEW"
                why = f"partial overlap with {p['id']} ({p['headline']!r}); shared {sorted(shared_kw)}"
            else:
                continue
            if not shared_url and c.get("follow_up_of") == p["id"] and c.get("new_fact"):
                level, why = "FOLLOWUP", f"declared follow up of {p['id']} with new fact"
            hits.append({"level": level, "why": why})
        rank = {"OK": 0, "FOLLOWUP": 1, "REVIEW": 2, "BLOCK": 3}  # REVIEWED is set after ranking
        if hits:
            verdict = max((h["level"] for h in hits), key=rank.get)
        if verdict == "FOLLOWUP":
            followups += 1
            if followups > 1:
                verdict = "BLOCK"
                hits.append({"level": "BLOCK", "why": "only one follow up story per episode"})
        if verdict == "REVIEW" and c.get("review_note"):
            verdict = "REVIEWED"
        results.append({"n": n, "headline": c["headline"], "verdict": verdict, "hits": hits})
    return results


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("candidates")
    ap.add_argument("episodes_dir")
    ap.add_argument("target_date")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--report")
    a = ap.parse_args()
    try:
        cands = json.loads(Path(a.candidates).read_text(encoding="utf-8"))
        validate(cands)
        target = date.fromisoformat(a.target_date)
    except (ValueError, OSError) as e:
        print(f"bad input: {e}", file=sys.stderr)
        return 1
    ledger = load_ledger(Path(a.episodes_dir), target, a.days)
    results = check(cands, ledger)
    report = {"target_date": a.target_date, "window_days": a.days,
              "ledger_stories": len(ledger), "results": results}
    if a.report:
        Path(a.report).write_text(json.dumps(report, indent=2))
    for r in results:
        print(f"[{r['verdict']:8}] {r['n']}. {r['headline']}")
        for h in r["hits"]:
            print(f"           {h['level']}: {h['why']}")
    print(f"ledger: {len(ledger)} past stories in {a.days} days")
    return 3 if any(r["verdict"] in ("BLOCK", "REVIEW") for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
