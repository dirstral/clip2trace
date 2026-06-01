// clip2trace dashboard — Sinas component skeleton.
//
// This is a minimal skeleton. Full wiring (calling functions via @sinas/sdk,
// async job polling, evidence views) is tracked in the "Add clip2trace dashboard
// skeleton" and "Wire async execution and progress polling" issues.
//
// UI states (see docs/dashboard-wireframe.md):
//   1. configure instance/status   2. upload/select input video
//   3. start job                    4. job progress (async)
//   5. candidate source segments    6. Telegram query plan
//   7. candidate Telegram posts     8. visual match / evidence
//   9. final provenance report

import React, { useState } from "react";

const STATES = [
  "configure", "select-video", "start", "progress",
  "segments", "queries", "candidates", "evidence", "report",
];

export default function Dashboard({ sinas }) {
  const [stage, setStage] = useState("configure");
  const [job, setJob] = useState(null);
  const [mode, setMode] = useState("demo");

  async function startJob() {
    // In a fully wired build, call the create_job function via the SDK:
    //   const res = await sinas.functions.run("clip2trace/create_job", { mode });
    // then poll GET /executions/{execution_id} for async steps.
    setJob({ job_id: "job_demo", status: "created", mode });
    setStage("progress");
  }

  return (
    <div style={{ fontFamily: "system-ui", padding: 16 }}>
      <h1>clip2trace</h1>
      <p>Telegram source tracing for reused footage in edited videos.</p>

      <nav style={{ display: "flex", gap: 8, flexWrap: "wrap", margin: "12px 0" }}>
        {STATES.map((s) => (
          <button key={s} disabled={s === stage} onClick={() => setStage(s)}>
            {s}
          </button>
        ))}
      </nav>

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
          <p>Instance status: (wire to GET /info or /auth/me)</p>
        </section>
      )}

      {stage === "start" && (
        <section>
          <h2>3. Start job</h2>
          <button onClick={startJob}>Start source-tracing job</button>
        </section>
      )}

      {stage === "progress" && job && (
        <section>
          <h2>4. Job progress</h2>
          <pre>{JSON.stringify(job, null, 2)}</pre>
          <p>(Poll execution_id for async analyze/search/verify steps.)</p>
        </section>
      )}

      {stage === "report" && (
        <section>
          <h2>9. Provenance report</h2>
          <p>Renders render_report output: segments, ranked candidates,
             confidence, evidence, caveats. Likely candidates only — never
             "confirmed original".</p>
        </section>
      )}
    </div>
  );
}
