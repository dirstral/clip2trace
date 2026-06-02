"""Build the provenance report JSON.

Careful language is enforced here: we never emit "original"; the report is for
human verification and always carries caveats. See skills/report-style.md.
"""

from __future__ import annotations

import html as _html
from typing import Dict, List

BANNED_PHRASES = ("the original", "original post", "confirmed original",
                  "we found the original")

GLOBAL_CAVEATS = [
    "Global Telegram search is retrieval, not proof of origin.",
    "A matched Telegram post may itself be a repost, not the first appearance.",
    "Private, deleted, or restricted posts are out of scope and may be missed.",
    "Confidence scores are automated and require human verification.",
]


def _sanitise(text: str) -> str:
    """Replace overclaiming phrasing with cautious provenance language.

    Replaces ALL occurrences of each banned phrase (case-insensitively), so the
    no-"original" guarantee holds even when a phrase appears more than once.
    """
    out = text or ""
    for bad in BANNED_PHRASES:
        lowered = out.lower()
        idx = lowered.find(bad)
        while idx != -1:
            out = out[:idx] + "likely Telegram source candidate" + out[idx + len(bad):]
            lowered = out.lower()
            idx = lowered.find(bad)
    return out


def _safe_url(url) -> str:
    """Return the url only if it uses an http(s) scheme — guards against
    `javascript:`/`data:` hrefs built from untrusted Telegram candidate data."""
    u = str(url or "").strip()
    return u if u.lower().startswith(("http://", "https://")) else ""


def build_report(job_id: str, segments: List[Dict],
                 ranked_candidates: List[Dict], *, mode: str = "demo",
                 summary: str = "") -> Dict:
    """Assemble the report JSON dict (schemas.ProvenanceReport shape)."""
    kept = [c for c in ranked_candidates if not c.get("rejected")]
    label_counts: Dict[str, int] = {}
    for c in kept:
        label_counts[c.get("confidence_label", "unknown")] = \
            label_counts.get(c.get("confidence_label", "unknown"), 0) + 1

    if not summary:
        summary = (
            f"Analysed input video into {len(segments)} candidate source "
            f"segment(s); {len(kept)} Telegram source candidate(s) retained "
            f"after scoring (mode={mode}). "
            "These are likely candidates for human verification, not confirmed origins."
        )

    return {
        "job_id": job_id,
        "summary": _sanitise(summary),
        "generated_mode": mode,
        "segments": segments,
        "ranked_candidates": kept,
        "label_counts": label_counts,
        "caveats": list(GLOBAL_CAVEATS),
    }


_HTML_CSS = """
body{font:15px/1.5 system-ui,sans-serif;max-width:880px;margin:2rem auto;padding:0 1rem;color:#1a1a1a}
h1{margin-bottom:.2rem} .meta,.counts{color:#555} code{background:#f2f2f2;padding:1px 4px;border-radius:3px}
table{border-collapse:collapse;width:100%;margin:.5rem 0} th,td{border:1px solid #ddd;padding:4px 8px;text-align:left;font-size:14px}
.card{border:1px solid #ddd;border-left-width:6px;border-radius:6px;padding:.75rem 1rem;margin:.75rem 0}
.card.very_strong{border-left-color:#1a7f37} .card.strong{border-left-color:#2563eb}
.card.plausible{border-left-color:#b08800} .card.weak{border-left-color:#cf222e} .card.reject{border-left-color:#999}
.thumb{max-width:160px;max-height:120px;border-radius:4px;float:right;margin:0 0 .5rem 1rem;border:1px solid #ddd}
.label{text-transform:uppercase;font-size:12px;letter-spacing:.04em}
footer{margin-top:2rem;color:#555;font-size:13px;border-top:1px solid #eee;padding-top:.75rem}
""".strip()


def render_html(report: Dict) -> str:
    """Render a provenance report dict (build_report shape) to a standalone HTML
    string. All user-controlled text is HTML-escaped, and the whole document is
    passed through `_sanitise` so overclaiming phrasing can never appear."""
    r = report or {}

    def esc(x) -> str:
        return _html.escape(str(x))

    job_id = esc(r.get("job_id", ""))
    mode = esc(r.get("generated_mode", "demo"))
    summary = esc(_sanitise(str(r.get("summary", ""))))

    seg_rows = "".join(
        f"<tr><td>{esc(s.get('segment_id'))}</td>"
        f"<td>{esc(s.get('start_sec'))}–{esc(s.get('end_sec'))}s</td>"
        f"<td>{esc(s.get('source_likelihood'))}</td>"
        f"<td>{esc(s.get('reason', ''))}</td></tr>"
        for s in (r.get("segments") or [])
    ) or '<tr><td colspan="4">no segments</td></tr>'

    cards = []
    for c in (r.get("ranked_candidates") or []):
        label = esc(c.get("confidence_label", "unknown"))
        thumb = _safe_url(c.get("thumbnail_url"))
        img = (f'<img class="thumb" src="{esc(thumb)}" loading="lazy" '
               f'alt="candidate media thumbnail">') if thumb else ""
        url = c.get("url")
        safe = _safe_url(url)
        if safe:
            link = f'<a href="{esc(safe)}" rel="noopener noreferrer">{esc(safe)}</a>'
        elif url:
            link = esc(url)  # shown for transparency, but not clickable
        else:
            link = "(no link)"
        ev_rows = "".join(
            f"<tr><td>{esc(k)}</td><td>{esc(round(float(v), 3))}</td></tr>"
            for k, v in (c.get("evidence") or {}).items())
        notes = "".join(
            f"<li>{esc(x)}</li>" for x in
            ((c.get("caveats") or []) + (c.get("recommended_next_steps") or [])))
        cards.append(
            f'<div class="card {label}">'
            f'{img}'
            f'<h3>{esc(c.get("candidate_id"))} — '
            f'<span class="label">{label}</span> ({esc(c.get("confidence", 0))})</h3>'
            f'<p class="link">{link}</p>'
            f'<table><thead><tr><th>evidence</th><th>score</th></tr></thead>'
            f'<tbody>{ev_rows}</tbody></table>'
            f'<details><summary>Caveats &amp; next steps</summary>'
            f'<ul>{notes}</ul></details></div>')
    cards_html = "\n".join(cards) or "<p>No candidates retained after scoring.</p>"

    counts = ", ".join(f"{esc(k)}: {esc(v)}"
                       for k, v in (r.get("label_counts") or {}).items()) or "none"
    global_cav = "".join(f"<li>{esc(x)}</li>" for x in (r.get("caveats") or []))

    out = (
        "<!doctype html>\n"
        '<html lang="en"><head><meta charset="utf-8">'
        f"<title>clip2trace provenance report — {job_id}</title>"
        f"<style>{_HTML_CSS}</style></head><body>"
        "<h1>clip2trace provenance report</h1>"
        f'<p class="meta">job <code>{job_id}</code> · mode <code>{mode}</code></p>'
        f'<p class="summary">{summary}</p>'
        f'<p class="counts">Confidence labels — {counts}</p>'
        "<h2>Candidate source segments</h2>"
        "<table><thead><tr><th>segment</th><th>window</th>"
        "<th>likelihood</th><th>reason</th></tr></thead>"
        f"<tbody>{seg_rows}</tbody></table>"
        "<h2>Likely Telegram source candidates</h2>"
        f"{cards_html}"
        f"<h2>Caveats</h2><ul>{global_cav}</ul>"
        "<footer>Likely candidates for human verification — not confirmed "
        "sources. Global Telegram search is retrieval, not proof.</footer>"
        "</body></html>")
    return _sanitise(out)
