// clip2trace dashboard — Sinas component (#19, #20).
//
// Runs / inspects a source-tracing job and renders the provenance report:
// candidate source segments + likely Telegram source candidates with evidence,
// confidence, and caveats. Provenance language is non-negotiable — this UI shows
// "likely Telegram source candidate" / "best candidate found", never
// "the original" / "confirmed original".
//
// Wiring (see docs/dashboard-wireframe.md):
//   - demo mode runs fully offline against a bundled fixture, so the component
//     always renders something even without a live instance.
//   - live/hybrid mode calls the package functions through the injected `sinas`
//     client (create_job -> render_report) and, for the long analysis step, polls
//     an async execution (execute/async -> GET /executions/{id}) — #20.
//   - the exact `sinas` client method surface differs across embed contexts, so
//     calls go through small adapters (callFunction / enqueueFunction /
//     getExecution) that feature-detect the available method and otherwise
//     surface a clear error. Adjust the adapters if the live SDK differs.

import React, { useCallback, useEffect, useRef, useState } from "react";

const STATES = ["configure", "select-video", "start", "progress", "report"];

// Bundled demo fixture so the dashboard renders end-to-end with no live instance.
// Mirrors the shape render_report returns (docs/api-contracts.md). Cautious
// language only — these are candidates, not "originals".
const DEMO_REPORT = {
  job_id: "job_demo",
  mode: "demo",
  segments: [
    {
      segment_id: "seg_001",
      start_sec: 12.0,
      end_sec: 24.5,
      source_likelihood: 0.81,
      reason: "static establishing shot, no edit overlays",
      visible_handles: ["demo_channel"],
      context_terms: ["square", "crowd", "city"],
    },
  ],
  ranked_candidates: [
    {
      candidate_id: "c1",
      url: "https://t.me/demo_channel/4521",
      channel: "@demo_channel",
      post_time: "2026-05-30T09:12:00Z",
      caption: "crowd gathers in the city square",
      confidence: 0.78,
      confidence_label: "strong candidate",
      rejected: false,
      segment_ids: ["seg_001"],
      evidence: {
        visual_similarity: 0.95,
        text_score: 0.6,
        predates_input: true,
        temporal_alignment: 0.7,
      },
      caveats: [
        "Global search is retrieval, not proof.",
        "Earliest known appearance, not necessarily the source.",
      ],
      recommended_next_steps: [
        "Inspect the channel's own forwards for an earlier copy.",
      ],
    },
  ],
  summary: "1 likely Telegram source candidate found for 1 reused segment.",
};

// --- sinas client adapters (feature-detect; never invent a single method) -----

async function callFunction(sinas, name, input) {
  const fns = (sinas && sinas.functions) || {};
  if (typeof fns.run === "function") return fns.run(name, input);
  if (typeof fns.execute === "function") return fns.execute(name, input);
  if (sinas && typeof sinas.run === "function") return sinas.run(name, input);
  throw new Error("sinas client exposes no functions.run/execute");
}

async function enqueueFunction(sinas, name, input) {
  const fns = (sinas && sinas.functions) || {};
  if (typeof fns.runAsync === "function") return fns.runAsync(name, input);
  if (typeof fns.executeAsync === "function") return fns.executeAsync(name, input);
  // Fall back to a synchronous call wrapped to look async (small jobs / demo).
  const result = await callFunction(sinas, name, input);
  return { execution_id: null, result };
}

async function getExecution(sinas, executionId) {
  const ex = (sinas && sinas.executions) || {};
  if (typeof ex.get === "function") return ex.get(executionId);
  throw new Error("sinas client exposes no executions.get");
}

// --- presentational pieces ----------------------------------------------------

function Pill({ children, tone = "neutral" }) {
  const bg = {
    strong: "#1b5e20",
    medium: "#8d6e00",
    weak: "#7a2e2e",
    neutral: "#444",
  }[tone];
  return (
    <span
      style={{
        background: bg,
        color: "#fff",
        borderRadius: 10,
        padding: "1px 8px",
        fontSize: 12,
        marginLeft: 6,
      }}
    >
      {children}
    </span>
  );
}

function toneForConfidence(c) {
  if (c >= 0.7) return "strong";
  if (c >= 0.4) return "medium";
  return "weak";
}

function fmtRange(s, e) {
  const f = (n) => (n == null ? "?" : Number(n).toFixed(1) + "s");
  return `${f(s)}–${f(e)}`;
}

function SegmentCard({ seg }) {
  return (
    <div
      style={{
        border: "1px solid #ccc",
        borderRadius: 8,
        padding: 12,
        marginBottom: 8,
      }}
    >
      <strong>{seg.segment_id}</strong>
      <Pill>{fmtRange(seg.start_sec, seg.end_sec)}</Pill>
      {seg.source_likelihood != null && (
        <Pill tone={toneForConfidence(seg.source_likelihood)}>
          likelihood {Number(seg.source_likelihood).toFixed(2)}
        </Pill>
      )}
      {seg.reason && <p style={{ margin: "6px 0 0", color: "#555" }}>{seg.reason}</p>}
      {Array.isArray(seg.visible_handles) && seg.visible_handles.length > 0 && (
        <p style={{ margin: "4px 0 0", fontSize: 13 }}>
          handles: {seg.visible_handles.map((h) => "@" + h).join(", ")}
        </p>
      )}
      {Array.isArray(seg.context_terms) && seg.context_terms.length > 0 && (
        <p style={{ margin: "2px 0 0", fontSize: 13, color: "#777" }}>
          terms: {seg.context_terms.join(", ")}
        </p>
      )}
    </div>
  );
}

function CandidateCard({ cand }) {
  const ev = cand.evidence || {};
  return (
    <div
      style={{
        border: "1px solid #ccc",
        borderRadius: 8,
        padding: 12,
        marginBottom: 8,
        opacity: cand.rejected ? 0.55 : 1,
      }}
    >
      <strong>{cand.channel || cand.candidate_id}</strong>
      {cand.confidence != null && (
        <Pill tone={toneForConfidence(cand.confidence)}>
          {cand.confidence_label || "candidate"} {Number(cand.confidence).toFixed(2)}
        </Pill>
      )}
      {cand.rejected && <Pill tone="weak">rejected</Pill>}
      {cand.caption && <p style={{ margin: "6px 0 0", color: "#555" }}>{cand.caption}</p>}
      <p style={{ margin: "4px 0 0", fontSize: 13, color: "#777" }}>
        visual {ev.visual_similarity ?? "–"} · text {ev.text_score ?? "–"} · predates{" "}
        {ev.predates_input ? "yes" : "no"}
      </p>
      {cand.url && (
        <p style={{ margin: "6px 0 0" }}>
          <a href={cand.url} target="_blank" rel="noopener noreferrer">
            open in Telegram
          </a>
        </p>
      )}
      {Array.isArray(cand.caveats) && cand.caveats.length > 0 && (
        <ul style={{ margin: "6px 0 0", paddingLeft: 18, fontSize: 12, color: "#777" }}>
          {cand.caveats.map((c, i) => (
            <li key={i}>{c}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

// --- main component -----------------------------------------------------------

export default function Dashboard({ sinas }) {
  const [stage, setStage] = useState("configure");
  const [mode, setMode] = useState("demo");
  const [job, setJob] = useState(null);
  const [report, setReport] = useState(null);
  const [status, setStatus] = useState("idle");
  const [executionId, setExecutionId] = useState(null);
  const [error, setError] = useState(null);
  const pollRef = useRef(null);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  useEffect(() => stopPolling, [stopPolling]); // clear timer on unmount

  // Demo mode: synthesize a short progression, then show the bundled report —
  // fully offline, no client needed.
  const runDemo = useCallback(() => {
    setError(null);
    setJob({ job_id: DEMO_REPORT.job_id, status: "analyzing", mode: "demo" });
    setExecutionId("exec_demo");
    setStage("progress");
    const steps = ["analyzing", "searching", "verifying", "ranking", "reporting", "done"];
    let i = 0;
    stopPolling();
    pollRef.current = setInterval(() => {
      i += 1;
      const s = steps[Math.min(i, steps.length - 1)];
      setStatus(s);
      setJob((j) => ({ ...(j || {}), status: s }));
      if (s === "done") {
        stopPolling();
        setReport(DEMO_REPORT);
        setStage("report");
      }
    }, 500);
  }, [stopPolling]);

  // Live/hybrid: create the job, then render the report. The long analysis step
  // is async — kick it off, then poll the execution for visible progress (#20).
  const runLive = useCallback(async () => {
    setError(null);
    setStatus("creating");
    try {
      const created = await callFunction(sinas, "clip2trace/create_job", { mode });
      const jobId = created.job_id || (created.result && created.result.job_id);
      setJob({ job_id: jobId, status: "created", mode });
      setStage("progress");

      // Enqueue the report build (stands in for the long async pipeline). When a
      // real execution_id comes back, poll it; otherwise we already have a result.
      setStatus("analyzing");
      const enq = await enqueueFunction(sinas, "clip2trace/render_report", {
        job_id: jobId,
        mode,
      });
      if (enq.execution_id) {
        setExecutionId(enq.execution_id);
        stopPolling();
        pollRef.current = setInterval(async () => {
          try {
            const ex = await getExecution(sinas, enq.execution_id);
            setStatus(ex.status || "running");
            if (ex.status === "completed" || ex.status === "succeeded") {
              stopPolling();
              setReport(ex.result || ex.output);
              setStage("report");
            } else if (ex.status === "failed" || ex.status === "error") {
              stopPolling();
              setError(ex.error || "execution failed");
            }
          } catch (e) {
            stopPolling();
            setError(String((e && e.message) || e));
          }
        }, 2000);
      } else {
        setStatus("done");
        setReport(enq.result);
        setStage("report");
      }
    } catch (e) {
      setError(String((e && e.message) || e));
      setStatus("failed");
    }
  }, [sinas, mode, stopPolling]);

  function startJob() {
    if (mode === "demo" || !sinas) {
      runDemo();
    } else {
      runLive();
    }
  }

  const segments = (report && report.segments) || [];
  const candidates = (report && report.ranked_candidates) || [];

  return (
    <div style={{ fontFamily: "system-ui", padding: 16, maxWidth: 920 }}>
      <header style={{ display: "flex", alignItems: "baseline", gap: 12 }}>
        <h1 style={{ margin: 0 }}>clip2trace</h1>
        <span style={{ color: "#777" }}>
          Telegram source tracing for reused footage in edited videos
        </span>
      </header>

      <nav style={{ display: "flex", gap: 8, flexWrap: "wrap", margin: "12px 0" }}>
        {STATES.map((s) => (
          <button key={s} disabled={s === stage} onClick={() => setStage(s)}>
            {s}
          </button>
        ))}
      </nav>

      {error && (
        <div style={{ background: "#7a2e2e", color: "#fff", padding: 10, borderRadius: 6 }}>
          Error: {error}
        </div>
      )}

      {stage === "configure" && (
        <section>
          <h2>1. Configure</h2>
          <label>
            Mode:{" "}
            <select value={mode} onChange={(e) => setMode(e.target.value)}>
              <option value="demo">demo</option>
              <option value="hybrid">hybrid</option>
              <option value="live">live</option>
            </select>
          </label>
          <p style={{ color: "#777" }}>
            Instance: {sinas ? "connected" : "not connected — demo mode only"}
          </p>
          <button onClick={() => setStage("start")}>Next</button>
        </section>
      )}

      {stage === "select-video" && (
        <section>
          <h2>2. Select input video</h2>
          <p style={{ color: "#777" }}>
            Live/hybrid runs upload to the <code>clip2trace/input-videos</code> collection;
            demo mode needs no file.
          </p>
        </section>
      )}

      {stage === "start" && (
        <section>
          <h2>3. Start job</h2>
          <p style={{ color: "#777" }}>Mode: {mode}</p>
          <button onClick={startJob}>Start source-tracing job</button>
        </section>
      )}

      {stage === "progress" && (
        <section>
          <h2>4. Job progress</h2>
          <p>
            job_id: <code>{(job && job.job_id) || "—"}</code>
            {executionId && (
              <>
                {"  ·  execution_id: "}
                <code>{executionId}</code>
              </>
            )}
          </p>
          <p>
            status: <strong>{status}</strong> {pollRef.current ? "(polling…)" : ""}
          </p>
          <p style={{ color: "#777", fontSize: 13 }}>
            Long analysis runs async (execute/async → poll /executions/&#123;id&#125;); failures
            surface above.
          </p>
        </section>
      )}

      {stage === "report" && (
        <section>
          <h2>9. Provenance report</h2>
          {!report && <p style={{ color: "#777" }}>No report yet — start a job.</p>}
          {report && (
            <>
              <p>
                {report.summary} <em style={{ color: "#777" }}>({report.mode} mode)</em>
              </p>
              <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
                <div style={{ flex: "1 1 360px" }}>
                  <h3>Candidate source segments</h3>
                  {segments.length === 0 && <p style={{ color: "#777" }}>none</p>}
                  {segments.map((seg) => (
                    <SegmentCard key={seg.segment_id} seg={seg} />
                  ))}
                </div>
                <div style={{ flex: "1 1 360px" }}>
                  <h3>Likely Telegram source candidates</h3>
                  {candidates.length === 0 && <p style={{ color: "#777" }}>none</p>}
                  {candidates.map((c) => (
                    <CandidateCard key={c.candidate_id} cand={c} />
                  ))}
                </div>
              </div>
              <p style={{ color: "#777", fontSize: 12, marginTop: 12 }}>
                Likely candidates only — global search is retrieval, not proof. clip2trace never
                claims to have found "the original".
              </p>
            </>
          )}
        </section>
      )}
    </div>
  );
}
