"""#25 — clustering wired into the pipeline: the cluster_segments function groups
repeated footage and links one candidate to many timestamps, and render_report
surfaces it as `repeated_footage`.
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

from clip2trace.report import build_report, render_html  # noqa: E402

_SAME = "c3e1c3e1c3e1c3e1"
_OTHER = "5a5a5a5a5a5a5a5a"


def _load(modname):
    path = os.path.join(FUNCS, modname + ".py")
    spec = importlib.util.spec_from_file_location("fn_" + modname, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_cluster_segments_function_groups_repeated_footage():
    mod = _load("cluster_segments")
    out = mod.handler({"segments": [
        {"segment_id": "seg_001", "phashes": [_SAME]},
        {"segment_id": "seg_002", "phashes": [_OTHER]},
        {"segment_id": "seg_003", "phashes": [_SAME]},
    ]}, {})
    # seg_001 and seg_003 (same phash) collapse into one cluster; seg_002 alone.
    multi = [c for c in out["clusters"] if len(c["segment_ids"]) > 1]
    assert len(multi) == 1
    assert set(multi[0]["segment_ids"]) == {"seg_001", "seg_003"}


def test_cluster_segments_links_candidate_to_multiple_timestamps():
    mod = _load("cluster_segments")
    out = mod.handler({
        "segments": [
            {"segment_id": "seg_001", "phashes": [_SAME]},
            {"segment_id": "seg_002", "phashes": [_OTHER]},
            {"segment_id": "seg_003", "phashes": [_SAME]},
        ],
        "candidate_phashes": [_SAME],
    }, {})
    # one Telegram candidate links to every matching input-video timestamp
    assert set(out["linked_segment_ids"]) == {"seg_001", "seg_003"}


def test_report_surfaces_repeated_footage():
    clusters = [{"cluster_id": "cluster_001",
                 "segment_ids": ["seg_001", "seg_003"]},
                {"cluster_id": "cluster_002", "segment_ids": ["seg_002"]}]
    report = build_report("job_x", segments=[], ranked_candidates=[],
                          clusters=clusters)
    # only the >1-segment cluster is notable
    assert len(report["repeated_footage"]) == 1
    assert report["repeated_footage"][0]["cluster_id"] == "cluster_001"
    html = render_html(report)
    assert "Repeated footage" in html
    assert "seg_001" in html and "seg_003" in html
