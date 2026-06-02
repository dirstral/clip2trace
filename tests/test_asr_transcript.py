"""ASR transcript extraction + its feed into the query planner.

These tests run WITHOUT any heavy ASR model: the backend is injected as a fake
callable. The real faster-whisper path lives behind the optional `asr` extra and
is not exercised in CI.
"""

from clip2trace.asr import extract_transcript
from clip2trace.telegram_search import derive_context_terms, generate_queries


def test_no_backend_returns_empty_transcript():
    # No injected transcriber and (in CI) no faster-whisper installed -> "".
    # Even if the dep were present, this path must degrade gracefully.
    assert extract_transcript("/nonexistent/clip.mp4", transcriber=None) in ("", None)


def test_injected_transcriber_returns_its_text():
    fake = lambda path: "  protesters gathered in the square  "  # noqa: E731
    assert extract_transcript("/clip.mp4", transcriber=fake) == (
        "protesters gathered in the square"
    )


def test_failing_backend_degrades_to_empty():
    def boom(_path: str) -> str:
        raise RuntimeError("model load failed")

    assert extract_transcript("/clip.mp4", transcriber=boom) == ""


def test_transcript_adds_context_terms_without_breaking_baseline():
    clues = {"context_terms": ["protest"]}
    baseline = generate_queries(clues)
    with_transcript = generate_queries(
        clues, transcript="protesters gathered at the riverside bridge"
    )

    base_terms = {q["query"].lower() for q in baseline}
    new_terms = {q["query"].lower() for q in with_transcript}

    # Baseline is preserved...
    assert base_terms <= new_terms
    # ...and spoken context contributes new context queries.
    assert {"protesters", "riverside", "bridge"} <= new_terms
    assert any(
        q["query_type"] == "context" and q["query"].lower() == "riverside"
        for q in with_transcript
    )


def test_transcript_handles_and_hashtags_are_picked_up():
    qs = generate_queries({}, transcript="follow @riverside_news and #flood updates")
    types = {q["query"]: q["query_type"] for q in qs}
    assert types.get("@riverside_news") == "handle"
    assert types.get("#flood") == "hashtag"


def test_empty_transcript_is_a_noop():
    clues = {"ocr_text": "overlay", "context_terms": ["square"]}
    assert generate_queries(clues) == generate_queries(clues, transcript="")


def test_derive_context_terms_folds_transcript():
    terms = derive_context_terms("alpha", transcript="bravo charlie")
    assert terms[0] == "alpha"
    assert "bravo" in terms and "charlie" in terms
