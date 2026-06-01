"""render_report — build the provenance report JSON (cautious language, caveats)."""

from __future__ import annotations


def handler(input_data, context):
    input_data = input_data or {}
    job_id = input_data.get("job_id")
    if not job_id:
        return {"error": "job_id is required"}

    segments = input_data.get("segments") or []
    ranked = input_data.get("ranked_candidates") or []
    mode = input_data.get("mode", "demo")
    output_format = input_data.get("output_format", "json")

    try:
        from clip2trace.report import build_report
        report = build_report(job_id, segments, ranked, mode=mode)
    except Exception:
        kept = [c for c in ranked if not c.get("rejected")]
        report = {
            "job_id": job_id,
            "summary": ("Likely Telegram source candidates for human "
                        "verification; not confirmed sources."),
            "generated_mode": mode,
            "segments": segments,
            "ranked_candidates": kept,
            "caveats": [
                "Global Telegram search is retrieval, not proof of origin.",
                "A matched post may itself be a repost.",
                "Private/deleted posts are out of scope.",
                "Confidence scores are automated; verify manually."],
        }

    result = {"report_json": report, "report_file_id": None,
              "summary": report.get("summary", "")}

    if output_format in ("html", "both"):
        try:
            from clip2trace.report import render_html
            result["report_html"] = render_html(report)
        except Exception:
            result["report_html"] = (
                "<!doctype html><html><body><h1>clip2trace provenance report</h1>"
                "<p>Likely Telegram source candidates for human verification; "
                "not confirmed sources.</p></body></html>")

    return result
