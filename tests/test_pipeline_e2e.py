"""End-to-end: the full Ali pipeline on demo fixtures (no live Telegram).

create_job -> detect -> clues -> queries -> search(cached) -> fetch -> verify
-> rank -> render_report. Asserts a non-empty report with a ranked candidate,
evidence, caveats, and no overclaiming ("original").
"""

import importlib.util
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
FUNCS = os.path.join(ROOT, "functions")
FIX = os.path.join(ROOT, "tests", "fixtures")
for p in (SRC, FUNCS):
    if p not in sys.path:
        sys.path.insert(0, p)


def _load(name):
    path = os.path.join(FUNCS, name + ".py")
    spec = importlib.util.spec_from_file_location("fn_" + name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _fixture(name):
    with open(os.path.join(FIX, name)) as f:
        return json.load(f)


def test_full_pipeline_demo():
    create, detect, clues = (_load("create_job"), _load("detect_source_segments"),
                             _load("extract_segment_clues"))
    genq, search, fetch = (_load("generate_telegram_queries"),
                           _load("search_global_telegram_posts"),
                           _load("fetch_telegram_candidate_media"))
    verify, rank, report = (_load("verify_media_similarity"),
                            _load("rank_source_candidates"),
                            _load("render_report"))

    job = create.handler({"mode": "demo"}, {"execution_id": "e2e"})
    assert job["status"] == "created" and job["progress"] == 0.0
    job_id = job["job_id"]

    segments = detect.handler({"job_id": job_id}, {})["segments"]
    assert segments

    seg_meta = _fixture("sample_segment_metadata.json")[0]
    seg = segments[0]
    c = clues.handler({"job_id": job_id, "segment_id": seg["segment_id"],
                       "ocr_text": seg_meta["clues"]["ocr_text"],
                       "text_hint": " ".join(seg_meta["clues"]["visible_handles"]),
                       "phashes": seg_meta["clues"]["phashes"]}, {})
    assert "demo_channel" in c["visible_handles"]

    queries = genq.handler({"visible_handles": c["visible_handles"],
                            "ocr_text": c["ocr_text"],
                            "context_terms": c["context_terms"]}, {})["queries"]
    assert queries and queries[0]["query_type"] == "handle"

    cached = _fixture("sample_telegram_results.json")
    found = search.handler({"queries": queries, "mode": "demo",
                            "cached_results": cached}, {})
    assert found["status"] == "ok" and found["candidates"]

    fetched = fetch.handler({"candidates": found["candidates"]}, {})["candidates"]
    cand = fetched[0]
    seg_dur = seg["end_sec"] - seg["start_sec"]

    v = verify.handler({"segment_phashes": c["phashes"],
                        "candidate_phashes": cached[0]["phashes"],
                        "segment_text": c["ocr_text"],
                        "candidate_text": cand.get("caption", ""),
                        "segment_duration": seg_dur,
                        "candidate_duration": seg_dur}, {})
    assert v["visual_score"] == 1.0  # identical demo phash
    assert v["temporal_score"] == 1.0

    ranked = rank.handler({"candidates": [{
        "candidate_id": cand["candidate_id"], "url": cand.get("url"),
        "verification": v, "handle_match": 1.0, "predates_input": 1.0}]},
        {})["ranked_candidates"]
    assert ranked and ranked[0]["confidence"] > 0.5
    assert ranked[0]["confidence_label"] in ("strong", "very_strong")
    assert ranked[0]["recommended_next_steps"]

    rep = report.handler({"job_id": job_id, "segments": segments,
                          "ranked_candidates": ranked, "mode": "demo"}, {})
    rj = rep["report_json"]
    assert rj["ranked_candidates"] and rj["caveats"]
    assert "original" not in json.dumps(rj).lower()
