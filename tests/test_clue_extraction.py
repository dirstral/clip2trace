"""#10/#11 — extract_segment_clues: handles, context terms, phash passthrough."""

import importlib.util
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
FUNCS = os.path.join(ROOT, "functions")
for p in (SRC, FUNCS):
    if p not in sys.path:
        sys.path.insert(0, p)

from clip2trace.schemas import SegmentClues  # noqa: E402


def _load(name):
    path = os.path.join(FUNCS, name + ".py")
    spec = importlib.util.spec_from_file_location("fn_" + name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_handles_and_context_terms_and_contract():
    mod = _load("extract_segment_clues")
    out = mod.handler(
        {
            "job_id": "j",
            "segment_id": "seg_001",
            "text_hint": "follow @demo_channel",
            "caption": "crowd gathers in city square #breaking",
            "ocr_text": "LIVE FROM DEMO",
        },
        {},
    )
    assert "demo_channel" in out["visible_handles"]

    terms = [t.lower() for t in out["context_terms"]]
    # real context words survive
    assert "square" in terms and "crowd" in terms and "city" in terms
    # stopwords, handles and hashtags are excluded
    assert "live" not in terms and "breaking" not in terms
    assert "demo_channel" not in terms and "channel" not in terms

    # output validates against the SegmentClues seam contract (docs/data-model.md)
    SegmentClues(
        **{
            k: out[k]
            for k in (
                "segment_id",
                "keyframe_file_ids",
                "phashes",
                "ocr_text",
                "visible_handles",
                "context_terms",
                "ocr_available",
            )
        }
    )
    assert out["implemented"] is True


def test_supplied_phashes_pass_through():
    mod = _load("extract_segment_clues")
    out = mod.handler(
        {"job_id": "j", "segment_id": "s", "phashes": ["c3e1c3e1c3e1c3e1"]}, {}
    )
    assert "c3e1c3e1c3e1c3e1" in out["phashes"]


def test_ocr_available_is_bool():
    mod = _load("extract_segment_clues")
    out = mod.handler({"job_id": "j", "segment_id": "s"}, {})
    assert isinstance(out["ocr_available"], bool)


def test_requires_ids():
    mod = _load("extract_segment_clues")
    assert "error" in mod.handler({"job_id": "j"}, {})
