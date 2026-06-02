"""#21 — the enriched demo fixtures span the confidence bands.

Runs verify + rank over the cached candidates and asserts the strong,
visually-identical, handle-backed candidate outranks the unrelated one, which is
rejected. Keeps the demo honest about weak matches.
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


def test_demo_fixture_spans_confidence_bands():
    verify, rank = _load("verify_media_similarity"), _load("rank_source_candidates")
    seg = _fixture("sample_segment_metadata.json")[0]["clues"]
    cands = _fixture("sample_telegram_results.json")
    assert len(cands) >= 3, "expected the enriched (strong/weak/edge) fixture set"

    ranked_input = []
    for c in cands:
        v = verify.handler({"segment_phashes": seg["phashes"],
                            "candidate_phashes": c.get("phashes", []),
                            "segment_text": seg["ocr_text"],
                            "candidate_text": c.get("caption", "")}, {})
        ranked_input.append({
            "candidate_id": c["candidate_id"], "url": c.get("url"),
            "verification": v,
            "handle_match": 1.0 if str(c.get("source_query", "")).startswith("@")
            else 0.0})

    ranked = rank.handler({"candidates": ranked_input}, {})["ranked_candidates"]
    by_id = {r["candidate_id"]: r for r in ranked}

    # a visually-identical, handle-backed candidate tops the list
    assert ranked[0]["candidate_id"] in ("cand_demo_1", "cand_demo_3")
    assert by_id["cand_demo_1"]["confidence_label"] in ("strong", "very_strong")
    assert not by_id["cand_demo_1"]["rejected"]
    # the unrelated candidate is rejected and ranks below the strong one
    assert by_id["cand_demo_2"]["rejected"]
    assert by_id["cand_demo_2"]["confidence"] < by_id["cand_demo_1"]["confidence"]


def test_demo_segments_match_cached_candidate():
    """Demo must surface a real candidate (not reject everything): seg_001's
    inline phash matches cand_demo_1 → strong, after verify+rank."""
    from clip2trace.video import demo_segments
    verify, rank = _load("verify_media_similarity"), _load("rank_source_candidates")
    seg = demo_segments()[0]
    assert seg.get("phashes"), "demo seg_001 must carry phashes for a real match"
    cand = _fixture("sample_telegram_results.json")[0]
    v = verify.handler({"segment_phashes": seg["phashes"],
                        "candidate_phashes": cand["phashes"],
                        "segment_text": seg.get("ocr_text", ""),
                        "candidate_text": cand.get("caption", "")}, {})
    assert v["visual_score"] == 1.0
    ranked = rank.handler({"candidates": [{
        "candidate_id": cand["candidate_id"], "verification": v,
        "handle_match": 1.0}]}, {})["ranked_candidates"]
    assert not ranked[0]["rejected"]
    assert ranked[0]["confidence_label"] in ("plausible", "strong", "very_strong")

    # seg_002 must NOT confidently match any cached candidate (honest "no source"):
    seg2 = demo_segments()[1]
    cands = _fixture("sample_telegram_results.json")
    worst = []
    for c in cands:
        v2 = verify.handler({"segment_phashes": seg2["phashes"],
                             "candidate_phashes": c.get("phashes", []),
                             "segment_text": seg2.get("ocr_text", ""),
                             "candidate_text": c.get("caption", "")}, {})
        r2 = rank.handler({"candidates": [{"candidate_id": c["candidate_id"],
                                           "verification": v2}]}, {})["ranked_candidates"]
        assert v2["visual_score"] < 0.85, "seg_002 must not exact-match a candidate"
        worst.append(r2[0]["rejected"])
    assert all(worst), "seg_002 should be rejected against every candidate"


def test_make_demo_fixture_check_passes():
    import subprocess
    script = os.path.join(ROOT, "scripts", "make_demo_fixture.py")
    rc = subprocess.run([sys.executable, script, "--check"]).returncode
    assert rc == 0
