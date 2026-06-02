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
    # No segment_id and no segments list -> single mode still demands segment_id.
    assert "error" in mod.handler({"job_id": "j"}, {})
    assert "error" in mod.handler({"segment_id": "s"}, {})


def test_batch_mode_returns_clues_per_segment():
    mod = _load("extract_segment_clues")
    out = mod.handler(
        {
            "job_id": "j",
            "segments": [
                {"segment_id": "seg_001", "text_hint": "follow @one_channel"},
                {
                    "segment_id": "seg_002",
                    "caption": "crowd in city square",
                    "phashes": ["c3e1c3e1c3e1c3e1"],
                },
            ],
        },
        {},
    )
    assert out["implemented"] is True
    assert [c["segment_id"] for c in out["segments"]] == ["seg_001", "seg_002"]
    assert "one_channel" in out["segments"][0]["visible_handles"]
    assert "c3e1c3e1c3e1c3e1" in out["segments"][1]["phashes"]
    assert "square" in [t.lower() for t in out["segments"][1]["context_terms"]]
    # each batched segment validates against the SegmentClues seam contract
    for clues in out["segments"]:
        SegmentClues(
            **{
                k: clues[k]
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


def test_batch_mode_flags_invalid_segment_without_id():
    mod = _load("extract_segment_clues")
    out = mod.handler(
        {
            "job_id": "j",
            "segments": [
                {"segment_id": "seg_001", "caption": "city square"},
                {"caption": "no id here"},  # missing segment_id
                "not-a-dict",  # not an object
            ],
        },
        {},
    )
    assert out["segments"][0]["implemented"] is True
    # invalid entries are marked implemented=False, never a clues dict with id None
    assert out["segments"][1]["implemented"] is False
    assert out["segments"][1]["segment_id"] is None
    assert out["segments"][2]["implemented"] is False


def test_batch_mode_skips_staging_when_no_segment_needs_video(monkeypatch):
    # A clues-only batch (no keyframe windows) must not download the video.
    mod = _load("extract_segment_clues")
    import clip2trace.storage as storage

    def _boom(*a, **k):
        raise AssertionError("should not stage when no segment has a keyframe window")

    monkeypatch.setattr(storage, "stage_input_file", _boom)
    out = mod.handler(
        {
            "job_id": "j",
            "input_video_file_id": "vid.mp4",
            "segments": [
                {"segment_id": "seg_001", "phashes": ["c3e1c3e1c3e1c3e1"]},
                {"segment_id": "seg_002", "caption": "city square"},
            ],
        },
        {"access_token": "t", "user_id": "u1"},
    )
    assert [c["segment_id"] for c in out["segments"]] == ["seg_001", "seg_002"]


def test_batch_mode_stages_input_video_only_once(monkeypatch):
    # The whole point of batch mode: one download serves every segment, instead
    # of one staging call per segment.
    mod = _load("extract_segment_clues")
    import clip2trace.storage as storage

    calls = {"n": 0}

    def _fake_stage(file_id, context, **kwargs):
        calls["n"] += 1
        return None  # no real decode; we only count staging attempts

    monkeypatch.setattr(storage, "stage_input_file", _fake_stage)
    out = mod.handler(
        {
            "job_id": "j",
            "input_video_file_id": "vid.mp4",
            "segments": [
                {"segment_id": "seg_001", "start_sec": 0, "end_sec": 1},
                {"segment_id": "seg_002", "start_sec": 1, "end_sec": 2},
                {"segment_id": "seg_003", "start_sec": 2, "end_sec": 3},
            ],
        },
        {"access_token": "t", "user_id": "u1"},
    )
    assert calls["n"] == 1
    assert len(out["segments"]) == 3
