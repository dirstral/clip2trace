"""Guard: the authoritative inline `code:` blocks in sinas-package.yaml run.

The sandbox can't import clip2trace, so the inline blocks are the real deployed
code. This execs each block and runs its handler with minimal inputs, ensuring
the deployable code stays runnable and in sync with the functions/ dev copies.
"""

import os

import pytest

yaml = pytest.importorskip("yaml")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = os.path.join(ROOT, "sinas-package.yaml")

MINIMAL_INPUT = {
    "create_job": {"mode": "demo"},
    "analyze_input_video": {"job_id": "job_x"},
    "detect_source_segments": {"job_id": "job_x"},
    "extract_segment_clues": {
        "job_id": "job_x",
        "segment_id": "seg_001",
        "text_hint": "follow @demo_channel",
    },
    "generate_telegram_queries": {"visible_handles": ["demo_channel"]},
    "search_global_telegram_posts": {"mode": "demo"},
    "fetch_telegram_candidate_media": {"candidates": []},
    "verify_media_similarity": {
        "segment_phashes": ["c3e1"],
        "candidate_phashes": ["c3e1"],
    },
    "rank_source_candidates": {
        "candidates": [{"candidate_id": "c1", "evidence": {"visual_similarity": 0.9}}]
    },
    "render_report": {"job_id": "job_x", "segments": [], "ranked_candidates": []},
    "diagnose_runtime": {},
}

# Dev-copy files that must each have a matching inline block (and vice versa).
DEV_COPY_FUNCTIONS = set(MINIMAL_INPUT)


def _inline_functions():
    with open(PKG) as f:
        data = yaml.safe_load(f)
    funcs = data["spec"]["functions"]
    return {fn["name"]: fn["code"] for fn in funcs}


def test_inline_blocks_match_dev_copies():
    names = set(_inline_functions())
    assert names == DEV_COPY_FUNCTIONS, (
        f"inline/dev-copy drift: only inline={names - DEV_COPY_FUNCTIONS}, "
        f"only dev={DEV_COPY_FUNCTIONS - names}"
    )


@pytest.mark.parametrize("name,code", sorted(_inline_functions().items()))
def test_inline_handler_runs(name, code):
    ns = {}
    exec(compile(code, f"<inline:{name}>", "exec"), ns)
    assert "handler" in ns, f"{name} inline block defines no handler"
    out = ns["handler"](MINIMAL_INPUT.get(name, {}), {"execution_id": "test"})
    assert isinstance(out, dict), f"{name} inline handler did not return a dict"
    assert not out.get("error"), f"{name} inline returned error: {out.get('error')}"
