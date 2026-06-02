"""Smoke test: every Sinas function dev-copy imports and its handler runs.

Adds repo dirs to sys.path so `functions/*.py` (which import clip2trace.*) load.
"""

import importlib.util
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
FUNCS = os.path.join(ROOT, "functions")
for p in (SRC, FUNCS):
    if p not in sys.path:
        sys.path.insert(0, p)

FUNCTION_FILES = [
    "create_job", "diagnose_runtime", "analyze_input_video",
    "detect_source_segments", "extract_segment_clues",
    "generate_telegram_queries", "search_global_telegram_posts",
    "fetch_telegram_candidate_media", "verify_media_similarity",
    "rank_source_candidates", "render_report",
]

MINIMAL_INPUT = {
    "create_job": {"mode": "demo"},
    "analyze_input_video": {"job_id": "job_x"},
    "detect_source_segments": {"job_id": "job_x"},
    "extract_segment_clues": {"job_id": "job_x", "segment_id": "seg_001",
                              "text_hint": "follow @demo_channel"},
    "generate_telegram_queries": {"visible_handles": ["demo_channel"]},
    "search_global_telegram_posts": {"mode": "demo"},
    "fetch_telegram_candidate_media": {"candidates": []},
    "verify_media_similarity": {"segment_phashes": ["c3e1"], "candidate_phashes": ["c3e1"]},
    "rank_source_candidates": {"candidates": [{"candidate_id": "c1",
                                               "evidence": {"visual_similarity": 0.9}}]},
    "render_report": {"job_id": "job_x", "segments": [], "ranked_candidates": []},
    "diagnose_runtime": {},
}


def _load(modname):
    path = os.path.join(FUNCS, modname + ".py")
    spec = importlib.util.spec_from_file_location("fn_" + modname, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_all_functions_import_and_run():
    for name in FUNCTION_FILES:
        mod = _load(name)
        assert hasattr(mod, "handler"), f"{name} missing handler"
        out = mod.handler(MINIMAL_INPUT.get(name, {}), {"execution_id": "test"})
        assert isinstance(out, dict), f"{name} did not return a dict"
        # A truthy `error` signals failure; a nullable `error: None` field
        # (e.g. in create_job's job-state shape) is fine.
        assert not out.get("error"), f"{name} returned error: {out.get('error')}"


def test_handle_extraction_in_clues():
    mod = _load("extract_segment_clues")
    out = mod.handler({"job_id": "j", "segment_id": "s",
                       "text_hint": "watch @demo_channel"}, {})
    assert "demo_channel" in out["visible_handles"]


def test_rank_never_emits_original():
    mod = _load("rank_source_candidates")
    out = mod.handler({"candidates": [{"candidate_id": "c1",
                                       "evidence": {"visual_similarity": 1.0}}]}, {})
    blob = str(out).lower()
    assert "original" not in blob
