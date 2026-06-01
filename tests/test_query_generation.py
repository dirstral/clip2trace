from clip2trace.telegram_search import (
    generate_queries, extract_handles, extract_hashtags,
)


def test_handles_extracted_and_prioritised_first():
    clues = {"visible_handles": ["demo_channel"], "ocr_text": "Some overlay text",
             "context_terms": ["protest"]}
    qs = generate_queries(clues)
    assert qs[0]["query_type"] == "handle"
    assert qs[0]["query"] == "@demo_channel"
    assert qs[0]["priority"] == 1


def test_priority_ordering_is_sorted():
    clues = {"visible_handles": ["a_channel"], "ocr_text": "live overlay",
             "context_terms": ["square"], "caption": "see #breaking now"}
    qs = generate_queries(clues)
    priorities = [q["priority"] for q in qs]
    assert priorities == sorted(priorities)
    types = {q["query_type"] for q in qs}
    assert "handle" in types and "hashtag" in types


def test_dedup_case_insensitive():
    clues = {"visible_handles": ["Dup"], "context_terms": ["@dup"]}
    qs = generate_queries(clues)
    handle_qs = [q for q in qs if q["query"].lower() == "@dup"]
    assert len(handle_qs) == 1


def test_long_ocr_not_used_as_exact_query():
    clues = {"ocr_text": "x" * 200}
    qs = generate_queries(clues)
    assert not any(q["query_type"] == "ocr_exact" for q in qs)


def test_extract_helpers():
    # Telegram handles are >=5 chars; the regex requires >=4 after the leading char.
    assert extract_handles("hi @alpha and @alpha and @two_x") == ["alpha", "two_x"]
    assert extract_hashtags("a #foo b #foo #bar") == ["foo", "bar"]
