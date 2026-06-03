#!/usr/bin/env python3
"""Trace an input video INTO a Telegram channel corpus (channel-scoped visual
source-tracing) — the "found it" counterpart to global text search.

Builds the channel corpus once (enumerate + segment + phash every channel video,
via `enumerate_channel.py`), then for each input video segments + phashes it and
matches it against every channel video using the SAME rubric the Sinas package
uses (`clip2trace.matching` + `clip2trace.scoring` + `clip2trace.report`). For
each input it reports the ranked channel candidates — `t.me` URL, visual
similarity, honest confidence label — and localizes each input segment to the
best-matching channel post + timestamp.

Honest scoring note: `visual_similarity` is only 40% of the confidence rubric
(`scoring.WEIGHTS`), so a self-match (input == its own channel post) scores
`visual≈1.0` but overall confidence stays modest unless other signals fire. The
headline is therefore *localization* (which post + timestamp), with the rubric
confidence shown beside it — never inflated. We set `channel_relevance=1.0`
because in channel-scoped mode the candidate is, by construction, from the
channel we chose to trace into.

Local dev/inspection tool — premium `.env` session, downloads to a temp dir, no
Sinas-instance changes, $0 (no LLM/OCR).

Usage:
    uv run python scripts/match_into_channel.py --all-samples
    uv run python scripts/match_into_channel.py --video "samples/<name>.mkv"
    uv run python scripts/match_into_channel.py --all-samples --channel clip2trace
"""

from __future__ import annotations

import argparse
import glob
import os
import sys

# Importing enumerate_channel applies the worker-parity shims (cv2/scenedetect
# unavailable) and the importable corpus builder.
SCRIPTS = os.path.dirname(os.path.abspath(__file__))
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

import enumerate_channel as ec  # noqa: E402

from clip2trace.matching import (  # noqa: E402
    best_frame_similarity,
    temporal_alignment_score,
)
from clip2trace.report import build_report  # noqa: E402
from clip2trace.scoring import (  # noqa: E402
    EvidenceScores,
    evidence_from_signals,
    score_candidate,
)

ROOT = os.path.dirname(SCRIPTS)
SAMPLES = os.path.join(ROOT, "samples")
MATCH_THRESHOLD = 0.85  # phash similarity counted as a localized hit


def _flat_phashes(segments: list[dict]) -> list[str]:
    out: list[str] = []
    for s in segments:
        out.extend(s.get("phashes") or [])
    return out


def _duration(segments: list[dict]) -> float:
    return max((float(s.get("end_sec") or 0.0) for s in segments), default=0.0)


def _localize(input_segments: list[dict], cand_segments: list[dict]) -> list[dict]:
    """For each input segment, the best-matching channel segment + similarity."""
    links = []
    for iseg in input_segments:
        best_sim, best_cand = 0.0, None
        for cseg in cand_segments:
            sim, _, _ = best_frame_similarity(
                iseg.get("phashes") or [], cseg.get("phashes") or []
            )
            if sim > best_sim:
                best_sim, best_cand = sim, cseg
        links.append(
            {
                "input_segment": iseg["segment_id"],
                "input_window": (iseg["start_sec"], iseg["end_sec"]),
                "channel_segment": best_cand["segment_id"] if best_cand else None,
                "channel_window": (
                    (best_cand["start_sec"], best_cand["end_sec"])
                    if best_cand
                    else None
                ),
                "similarity": round(best_sim, 4),
            }
        )
    return links


def match_one(input_path: str, corpus: list[dict]) -> dict:
    """Match one input video against the channel corpus; return a report dict."""
    name = os.path.basename(input_path)
    print(f"\n{'=' * 70}\nINPUT: {name}\n{'=' * 70}")
    input_segments = ec._segment_video(input_path)
    in_phashes = _flat_phashes(input_segments)
    in_dur = _duration(input_segments)
    print(f"  segmented into {len(input_segments)} segment(s), {len(in_phashes)} phash")

    ranked: list[dict] = []
    for v in corpus:
        cand_phashes = _flat_phashes(v["segments"])
        cand_dur = _duration(v["segments"])
        visual, _, _ = best_frame_similarity(in_phashes, cand_phashes)
        temporal = temporal_alignment_score(in_dur, cand_dur)
        # channel_relevance=1.0: in channel-scoped mode the candidate is, by
        # construction, from the channel we chose to trace into.
        evidence = evidence_from_signals(visual=visual, temporal=temporal, channel=1.0)
        result = score_candidate(f"{v['message_id']}", EvidenceScores(**evidence))
        ranked.append(
            {
                "candidate_id": result.candidate_id,
                "confidence": round(result.confidence, 4),
                "confidence_label": result.confidence_label,
                "rejected": result.rejected,
                "evidence": result.evidence,
                "caveats": result.caveats,
                "url": v["url"],
                "message_id": v["message_id"],
                "_segments": v["segments"],
                "_visual": round(visual, 4),
            }
        )

    ranked.sort(key=lambda c: (c["_visual"], c["confidence"]), reverse=True)

    print("  ranked channel candidates:")
    for c in ranked[:5]:
        flag = " (rejected)" if c["rejected"] else ""
        print(
            f"    visual={c['_visual']:.3f}  conf={c['confidence']:.3f} "
            f"{c['confidence_label']:>11}{flag}  msg {c['message_id']}  {c['url']}"
        )

    top = ranked[0] if ranked else None
    if top and top["_visual"] >= MATCH_THRESHOLD:
        print(
            f"\n  → traces to {top['url']} (visual {top['_visual']:.3f}). Localization:"
        )
        for link in _localize(input_segments, top["_segments"]):
            if link["similarity"] >= MATCH_THRESHOLD and link["channel_window"]:
                iw = link["input_window"]
                cw = link["channel_window"]
                print(
                    f"      {link['input_segment']} [{iw[0]:.1f}-{iw[1]:.1f}s] "
                    f"== msg {top['message_id']} [{cw[0]:.1f}-{cw[1]:.1f}s] "
                    f"(sim {link['similarity']:.3f})"
                )
    else:
        print("\n  → no confident channel source (best visual below threshold).")

    # Same provenance report the package emits (banned-phrase sanitiser intact).
    report = build_report(
        job_id=f"match_{name}",
        segments=input_segments,
        ranked_candidates=[
            {k: v for k, v in c.items() if not k.startswith("_")} for c in ranked
        ],
        mode="channel",
    )
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--channel", default="clip2trace", help="channel @username")
    ap.add_argument("--video", help="a single input video (else --all-samples)")
    ap.add_argument(
        "--all-samples",
        action="store_true",
        help="match every samples/*.mkv|mp4|mov as input, one by one",
    )
    ap.add_argument("--max", type=int, default=ec.MAX_VIDEOS, help="max channel videos")
    args = ap.parse_args()

    ec._load_dotenv()
    missing = [
        k
        for k in ("TELEGRAM_API_ID", "TELEGRAM_API_HASH", "TELEGRAM_SESSION_STRING")
        if not os.environ.get(k)
    ]
    if missing:
        print(f"ERROR: missing env/.env vars: {', '.join(missing)}", file=sys.stderr)
        return 2

    if args.video:
        inputs = [args.video]
    elif args.all_samples:
        inputs = sorted(
            glob.glob(os.path.join(SAMPLES, "*.mkv"))
            + glob.glob(os.path.join(SAMPLES, "*.mp4"))
            + glob.glob(os.path.join(SAMPLES, "*.mov"))
        )
    else:
        ap.error("pass --video PATH or --all-samples")

    if not inputs:
        print("no input videos found")
        return 1

    import tempfile

    with tempfile.TemporaryDirectory(prefix="clip2trace_corpus_") as tmp:
        print(f"building channel corpus from @{args.channel} ...")
        corpus = ec.enumerate_and_segment(args.channel, args.max, tmp)
        print(f"corpus: {len(corpus)} channel video(s)")
        reports = [match_one(p, corpus) for p in inputs]

    kept = sum(len(r["ranked_candidates"]) for r in reports)
    print(
        f"\n{'=' * 70}\nDONE: matched {len(reports)} input(s) into "
        f"{len(corpus)} channel video(s); {kept} non-rejected candidate(s) total."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
