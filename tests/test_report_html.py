"""#29 — HTML report export: renders, escapes, and never overclaims."""

import importlib.util
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
FUNCS = os.path.join(ROOT, "functions")
for p in (SRC, FUNCS):
    if p not in sys.path:
        sys.path.insert(0, p)

from clip2trace.report import GLOBAL_CAVEATS, build_report, render_html  # noqa: E402


def _load(name):
    path = os.path.join(FUNCS, name + ".py")
    spec = importlib.util.spec_from_file_location("fn_" + name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _sample_report():
    segments = [
        {
            "segment_id": "seg_001",
            "start_sec": 12.0,
            "end_sec": 24.5,
            "source_likelihood": 0.81,
            "reason": "candidate reused footage",
        }
    ]
    ranked = [
        {
            "candidate_id": "cand_demo_1",
            "confidence": 0.9,
            "confidence_label": "very_strong",
            "rejected": False,
            "evidence": {"visual_similarity": 1.0, "ocr_caption_query": 1.0},
            "caveats": ["Telegram post may itself be a repost."],
            "recommended_next_steps": ["Open the Telegram link."],
            "url": "https://t.me/demo_channel/4521",
        }
    ]
    return build_report("job_e2e", segments, ranked, mode="demo")


def test_render_html_contains_key_fields():
    html = render_html(_sample_report())
    assert html.startswith("<!doctype html>")
    assert "job_e2e" in html
    assert "https://t.me/demo_channel/4521" in html
    assert "very_strong" in html
    assert "visual_similarity" in html  # evidence dimension shown
    for caveat in GLOBAL_CAVEATS:
        assert caveat in html  # all global caveats present


def test_render_html_never_says_original():
    assert "original" not in render_html(_sample_report()).lower()


def test_render_html_escapes_user_text():
    segments = []
    ranked = [
        {
            "candidate_id": "c1",
            "confidence": 0.5,
            "confidence_label": "plausible",
            "rejected": False,
            "evidence": {},
            "caveats": ["<script>alert(1)</script>"],
            "url": "https://t.me/x?<b>",
        }
    ]
    html = render_html(build_report("j", segments, ranked))
    assert "<script>alert(1)</script>" not in html  # raw injection escaped
    assert "&lt;script&gt;" in html


def test_render_html_rejects_unsafe_url_scheme():
    ranked = [
        {
            "candidate_id": "c1",
            "confidence": 0.5,
            "confidence_label": "plausible",
            "rejected": False,
            "evidence": {},
            "url": "javascript:alert(1)",
        }
    ]
    html = render_html(build_report("j", [], ranked))
    assert 'href="javascript:' not in html.lower()  # never a clickable js href
    assert "alert(1)" in html  # still shown for transparency (escaped, no href)


def test_render_html_shows_safe_thumbnail():
    ranked = [
        {
            "candidate_id": "c1",
            "confidence": 0.9,
            "confidence_label": "very_strong",
            "rejected": False,
            "evidence": {},
            "url": "https://t.me/x/1",
            "thumbnail_url": "https://media.example/thumb.jpg",
        }
    ]
    html = render_html(build_report("j", [], ranked))
    assert '<img class="thumb"' in html
    assert 'src="https://media.example/thumb.jpg"' in html
    assert "original" not in html.lower()  # guard holds with a thumbnail present


def test_render_html_drops_unsafe_thumbnail_scheme():
    ranked = [
        {
            "candidate_id": "c1",
            "confidence": 0.9,
            "confidence_label": "very_strong",
            "rejected": False,
            "evidence": {},
            "url": "https://t.me/x/1",
            "thumbnail_url": "javascript:alert(1)",
        }
    ]
    html = render_html(build_report("j", [], ranked))
    assert "<img" not in html  # unsafe-scheme thumbnail rendered no image
    assert "alert(1)" not in html  # and the payload never reaches the document


def test_rank_propagates_thumbnail_url():
    out = _load("rank_source_candidates").handler(
        {
            "candidates": [
                {
                    "candidate_id": "c1",
                    "evidence": {"visual_similarity": 0.9},
                    "thumbnail_url": "https://media.example/t.jpg",
                }
            ]
        },
        {},
    )
    assert out["ranked_candidates"][0]["thumbnail_url"] == "https://media.example/t.jpg"


def test_sanitise_replaces_all_occurrences():
    from clip2trace.report import _sanitise

    out = _sanitise("the original and the original again")
    assert "original" not in out.lower()


def test_render_report_output_format_html():
    out = _load("render_report").handler(
        {
            "job_id": "job_x",
            "segments": [],
            "ranked_candidates": [],
            "output_format": "html",
        },
        {},
    )
    assert "report_html" in out and out["report_html"].startswith("<!doctype html>")
    # default (json) keeps the original shape, no html key
    out_json = _load("render_report").handler(
        {"job_id": "job_x", "segments": [], "ranked_candidates": []}, {}
    )
    assert "report_html" not in out_json and "report_json" in out_json
