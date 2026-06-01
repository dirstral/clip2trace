#!/usr/bin/env bash
# Create clip2trace labels, milestones and the full issue set via the GitHub CLI.
# Re-runnable: labels use --force; issues are created fresh each run (gh has no
# upsert), so run once. Requires: gh auth login with `repo` scope.
#
#   bash scripts/create_issues.sh            # auto-detect repo from git remote
#   REPO=owner/name bash scripts/create_issues.sh

set -uo pipefail
REPO="${REPO:-$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null)}"
if [ -z "${REPO:-}" ]; then echo "Cannot determine repo; set REPO=owner/name"; exit 1; fi
echo "Target repo: $REPO"

# --- labels ---
label() { gh label create "$1" --color "$2" --description "$3" --force --repo "$REPO" >/dev/null 2>&1 || true; }
label "area:sinas"       "1d76db" "Sinas package/platform"
label "area:telegram"    "0e8a16" "Telegram retrieval"
label "area:video"       "5319e7" "Video pipeline"
label "area:matching"    "b60205" "Matching/scoring"
label "area:agents"      "fbca04" "Agents"
label "area:ui"          "c5def5" "Dashboard/UI"
label "area:docs"        "0052cc" "Documentation"
label "area:demo"        "d4c5f9" "Demo"
label "risk"             "e11d21" "Risky / needs mitigation"
label "stretch"          "bfdadc" "Stretch goal"
label "mvp"              "0e8a16" "MVP scope"
label "blocked"          "000000" "Blocked"
label "good-first-task"  "7057ff" "Good first task"

# --- milestones (best-effort) ---
ms() { gh api "repos/$REPO/milestones" -f title="$1" -f state=open >/dev/null 2>&1 || true; }
M0="M0 Investigation & setup"; M1="M1 Sinas package base"; M2="M2 Core video pipeline"
M3="M3 Telegram retrieval"; M4="M4 Matching & ranking"; M5="M5 Agents & UI"
M6="M6 Demo & polish"; MS="Stretch"
for m in "$M0" "$M1" "$M2" "$M3" "$M4" "$M5" "$M6" "$MS"; do ms "$m"; done

# --- helper: create issue, falling back to no-milestone if needed ---
mk() { # title labels milestone body
  gh issue create --repo "$REPO" --title "$1" --label "$2" --milestone "$3" --body "$4" 2>/dev/null \
    || gh issue create --repo "$REPO" --title "$1" --label "$2" --body "$4"
}

sec() { # owner deps files -> standard footer
  printf '\n**Suggested owner:** %s\n**Dependencies/blockers:** %s\n**Files likely touched:** %s\n' "$1" "$2" "$3"
}

# ============================ Milestone 0 ============================
mk "Configure Sinas access and verify Claude provider/model" "area:sinas,mvp,blocked" "$M0" \
"**Context:** Instance number X and admin token are not yet available to automation; access is a blocker.
**Scope:** Fill .env, log in, confirm the Claude provider + default model.
**Acceptance criteria:**
- .env.example documents SINAS_BASE_URL and SINAS_CONSOLE_URL (done)
- docs/sinas-setup.md explains login/API-key flow (done)
- Configured Claude provider and default model are documented (GET /api/v1/llm-providers/)
- Blocker issue filed if provider/model missing or != claude-sonnet-4-6
$(sec "A" "instance URL + admin token" ".env, docs/sinas-setup.md, docs/research/sinas-investigation.md")"

mk "Install and validate Sinas CLI workflow" "area:sinas,mvp,blocked" "$M0" \
"**Context:** Node/npm are absent in the current dev box, so @sinas/cli could not run.
**Scope:** Install CLI (needs Node), run validate/preview/status; document API fallback.
**Acceptance criteria:**
- @sinas/cli install path documented (done)
- 'sinas validate' result captured in docs/research/sinas-investigation.md
- 'sinas preview'/'status' path documented
- Management API fallback documented if CLI fails
$(sec "A" "#1 access, Node install" "package.json, docs/sinas-setup.md")"

mk "Investigate Sinas function runtime capabilities" "area:sinas,area:video,risk,mvp" "$M0" \
"**Context:** Video/OCR/Telegram depend on runtime libs + tight container limits (512MB/1GB/100MB tmp/300s).
**Scope:** Run diagnose_runtime on the instance; record results; file dep-approval follow-ups.
**Acceptance criteria:**
- diagnose_runtime function/script exists (done)
- ffmpeg, tesseract, OpenCV, Telethon, disk, timeout, secrets access documented
- Blockers converted into follow-up issues
$(sec "Partner" "#1 access" "functions/diagnose_runtime.py, docs/research/runtime-diagnostics.md")"

mk "Research Telegram global search feasibility with Telethon" "area:telegram,risk,mvp" "$M0" \
"**Context:** Need to confirm global public-post search is viable and how.
**Scope:** Document channels.searchPosts, user-session requirement, limits, fallback.
**Acceptance criteria:**
- docs/telegram-global-search.md complete (done)
- User-session requirement documented (done)
- Live search limitations documented (done)
- Fallback/demo mode documented (done)
$(sec "Partner" "none" "docs/telegram-global-search.md, docs/research/telegram-global-search.md")"

# ============================ Milestone 1 ============================
mk "Create clip2trace Sinas package skeleton" "area:sinas,mvp" "$M1" \
"**Context:** The package YAML is authored but unvalidated (no instance/CLI here).
**Scope:** Validate and fix sinas-package.yaml against the live schema.
**Acceptance criteria:**
- sinas-package.yaml exists, package+namespace 'clip2trace' (done)
- collections/stores/functions/agents/skills/component declared (done)
- manifest includes required resources (done)
- 'sinas validate' passes OR blockers documented (inferred collection/store/component fields flagged)
$(sec "A" "#1, #2" "sinas-package.yaml, sinas-config.yaml")"

mk "Add clip2trace Sinas collections and state stores" "area:sinas,mvp" "$M1" \
"**Context:** Storage layer for media + job/segment/result state.
**Scope:** Confirm/refine collection metadata schemas and store declarations.
**Acceptance criteria:**
- input-videos, source-segments, keyframes, telegram-media, reports, demo-fixtures collections declared (done)
- jobs, segments, search-results, candidate-matches, query-cache, runtime-diagnostics stores declared (done)
- Metadata schemas present or follow-up to refine them
$(sec "A" "#5" "sinas-package.yaml")"

mk "Add base function schemas and stubs" "area:sinas,mvp" "$M1" \
"**Context:** All 11 functions exist as inline YAML + dev copies; sandbox can't import src/.
**Scope:** Keep inline YAML authoritative or publish clip2trace as approved dep; add a sync/build step.
**Acceptance criteria:**
- All functions have handler(input_data, context) (done)
- input/output schemas exist in package (done)
- Smoke tests verify each function imports/runs (done: tests/test_functions_smoke.py)
- Stubs return structured JSON (done)
$(sec "Partner" "#5" "functions/*.py, sinas-package.yaml, tests/test_functions_smoke.py")"

# ============================ Milestone 2 ============================
mk "Implement input video job creation and state tracking" "area:sinas,area:video,mvp" "$M2" \
"**Context:** Jobs must persist status/progress/errors across async steps.
**Scope:** Wire create_job to the clip2trace/jobs store; persist status transitions and errors.
**Acceptance criteria:**
- create_job creates job_id (done, stub)
- Job state includes status/progress/input metadata
- Errors are persisted
- README documents how to start a job
$(sec "Partner" "#5, #6" "functions/create_job.py, src/clip2trace/storage.py, src/clip2trace/schemas.py")"

mk "Implement candidate reused-footage segment detection" "area:video,mvp" "$M2" \
"**Context:** Need timestamped candidate segments from the input video.
**Scope:** Real shot detection (PySceneDetect) + uniform-window fallback; demo fixture path.
**Acceptance criteria:**
- analyze_input_video and detect_source_segments process a video or demo fixture
- Outputs timestamped segments
- Long videos handled via async execution
- No Telegram dependency
$(sec "Partner" "#3 runtime, #8" "functions/detect_source_segments.py, functions/analyze_input_video.py, src/clip2trace/video.py")"

mk "Extract keyframes and visual fingerprints from segments" "area:video,area:matching,mvp" "$M2" \
"**Context:** Visual verification needs keyframes + perceptual hashes.
**Scope:** Frame extraction (OpenCV), phash + center-crop phash to ignore lower-thirds.
**Acceptance criteria:**
- extract_segment_clues stores/returns keyframes
- Perceptual hashes generated
- Center-crop/masked variant planned or implemented (helper exists)
- Test fixture included (done)
$(sec "Partner" "#3, #9" "functions/extract_segment_clues.py, src/clip2trace/video.py, src/clip2trace/matching.py")"

mk "Extract text clues and visible handles from segments" "area:video,area:telegram,mvp" "$M2" \
"**Context:** Handles/OCR text are the strongest retrieval signals.
**Scope:** OCR (if available) + regex handle extraction with graceful fallback.
**Acceptance criteria:**
- OCR availability checked
- Regex handle extraction implemented (done)
- Fallback when OCR unavailable (done)
- Clues feed query generation
$(sec "Partner" "#3" "functions/extract_segment_clues.py, src/clip2trace/telegram_search.py")"

# ============================ Milestone 3 ============================
mk "Implement secure Telegram session bootstrap workflow" "area:telegram,risk,mvp" "$M3" \
"**Context:** channels.searchPosts is user-account only; session string = full account access.
**Scope:** Local interactive StringSession bootstrap; secret-storage instructions.
**Acceptance criteria:**
- scripts/bootstrap_telegram_session.py exists (done)
- Session-string storage instructions documented (done)
- No credentials committed (.gitignore covers sessions)
- Required Sinas secrets documented
$(sec "Partner" "#4" "scripts/bootstrap_telegram_session.py, docs/telegram-global-search.md")"

mk "Implement global Telegram post search function" "area:telegram,mvp" "$M3" \
"**Context:** Live retrieval via Telethon functions.channels.SearchPostsRequest.
**Scope:** Live search (sharedPool, secrets), demo/cached/manual fallbacks, flood handling.
**Acceptance criteria:**
- search_global_telegram_posts supports live mode (Telethon) or documented raw-API path
- Returns structured candidate posts
- Handles missing secrets/session (live_unavailable) (done in stub)
- Handles flood/rate-limit errors gracefully
- Supports demo/cached mode (done)
$(sec "Partner" "#12" "functions/search_global_telegram_posts.py, src/clip2trace/telegram_search.py")"

mk "Implement Telegram candidate media fetcher" "area:telegram,area:matching,mvp" "$M3" \
"**Context:** Need candidate media/metadata for visual verification, bounded by container limits.
**Scope:** Metadata normalise + optional bounded download (dry-run default).
**Acceptance criteria:**
- fetch_telegram_candidate_media retrieves metadata (done, dry-run)
- Media download optional and bounded (<=100MB tmp)
- Dry-run/demo mode supported (done)
- Inaccessible/private/deleted handled cleanly (done)
$(sec "Partner" "#13" "functions/fetch_telegram_candidate_media.py, src/clip2trace/telegram_media.py")"

# ============================ Milestone 4 ============================
mk "Implement visual similarity verification" "area:matching,mvp" "$M4" \
"**Context:** Visual match is 40% of the score — the differentiator.
**Scope:** phash distance + center-crop variant + separate text overlap; matched-frame refs.
**Acceptance criteria:**
- verify_media_similarity compares segment vs candidate keyframes (done)
- Perceptual hash distance used (done)
- Text overlap considered separately (done)
- Score object includes evidence + matched frame references (done)
$(sec "Partner" "#10, #14" "functions/verify_media_similarity.py, src/clip2trace/matching.py")"

mk "Implement evidence scoring and candidate ranking" "area:matching,area:agents,mvp" "$M4" \
"**Context:** Rank candidates with the rubric; never claim 'original'.
**Scope:** Apply weights/labels; penalties; caveats; next steps.
**Acceptance criteria:**
- rank_source_candidates applies scoring rubric (done)
- Confidence labels implemented (done)
- Caveats included (done)
- No automated output says 'original post' (enforced + tested)
$(sec "A" "#15" "functions/rank_source_candidates.py, src/clip2trace/scoring.py, skills/evidence-scoring-rubric.md")"

mk "Implement provenance report renderer" "area:docs,area:sinas,mvp" "$M4" \
"**Context:** Final artifact for human verification.
**Scope:** JSON report (HTML stretch); cautious language; save to reports collection.
**Acceptance criteria:**
- render_report returns JSON report (done)
- Report includes segments, candidates, confidence, evidence, caveats, next steps (done)
- Report can be saved to reports collection or documented if not yet wired
$(sec "A" "#16" "functions/render_report.py, src/clip2trace/report.py")"

# ============================ Milestone 5 ============================
mk "Add coordinator and specialist agents" "area:agents,mvp" "$M5" \
"**Context:** Agents orchestrate the pipeline with cautious provenance language.
**Scope:** Validate agent YAML (systemPrompt/enabledFunctions/enabledSkills/enabledStores) against the instance.
**Acceptance criteria:**
- coordinator + 4 specialists defined (done)
- enabled functions/skills/stores declared explicitly (done)
- Prompts use cautious provenance language (done)
- Agent workflow documented (done: architecture.md, agents/*.md)
$(sec "A" "#5" "agents/*.md, sinas-package.yaml")"

mk "Add clip2trace dashboard skeleton" "area:ui,mvp" "$M5" \
"**Context:** A Sinas component to run/inspect jobs.
**Scope:** Wire create_job + report view via @sinas/sdk; segment/candidate cards.
**Acceptance criteria:**
- Dashboard component exists (skeleton done)
- Can start or display a job in demo mode
- Shows segment cards and candidate cards
- Limitations documented if full wiring blocked (done: dashboard-wireframe.md)
$(sec "A" "#5, #18" "components/dashboard.jsx, docs/dashboard-wireframe.md")"

mk "Wire async execution and progress polling" "area:sinas,area:ui,mvp" "$M5" \
"**Context:** Long analysis exceeds 300s; must run async with visible progress.
**Scope:** Use execute/async + poll executions/{id}; surface failures in UI/docs.
**Acceptance criteria:**
- Long video analysis uses async function execution
- execution_id/job_id shown
- UI or docs explain polling status
- Failures visible to the user
$(sec "Both" "#8, #19" "components/dashboard.jsx, functions/analyze_input_video.py, docs/architecture.md")"

# ============================ Milestone 6 ============================
mk "Build controlled demo fixture" "area:demo,mvp" "$M6" \
"**Context:** The demo must not depend on live Telegram.
**Scope:** Edited-video-like fixture + cached candidate path.
**Acceptance criteria:**
- make_demo_fixture.py exists or manual instructions exist (done)
- Fixture simulates edited video with reused Telegram-like footage (done: JSON fixtures)
- Cached candidate result path works (done)
- Demo does not depend fully on live Telegram search (done)
$(sec "Both" "#9, #13" "scripts/make_demo_fixture.py, tests/fixtures/*.json")"

mk "Write final hackathon demo script" "area:demo,area:docs,mvp" "$M6" \
"**Context:** Judges need a crisp narrative + fallback.
**Scope:** 3-min and 5-min scripts, fallback flow, product explanation, limitations.
**Acceptance criteria:**
- docs/demo-plan.md includes 3-minute and 5-minute scripts (done)
- Includes fallback flow (done)
- Includes judge-facing product explanation (done)
- Includes known limitations (done)
$(sec "Both" "#21" "docs/demo-plan.md")"

mk "Add README with setup and first-run instructions" "area:docs,mvp,good-first-task" "$M6" \
"**Context:** Onboarding for teammates + judges.
**Scope:** Overview, Sinas setup, env, CLI, validation/install, demo, live caveats.
**Acceptance criteria:**
- Project overview, Sinas setup, env setup, CLI commands (done)
- Package validation/install, demo mode, live Telegram caveats (done)
$(sec "A" "none" "README.md")"

mk "Add safety, privacy, and compliance notes" "area:docs,risk" "$M6" \
"**Context:** Provenance scope + Telegram ToS + data handling must be explicit.
**Scope:** Document privacy/ToS, scope guard, retention, session risk.
**Acceptance criteria:**
- docs/risks.md includes privacy and ToS considerations (done)
- No military/tactical analysis in product wording (enforced)
- Data retention and media storage caveats documented (done)
- Telegram account/session risk documented (done)
$(sec "A" "none" "docs/risks.md")"

# ============================ Stretch ============================
mk "Add repeated segment clustering across an input video" "area:matching,stretch" "$MS" \
"**Context:** The same footage may recur at multiple timestamps.
**Scope:** Cluster repeated appearances; one candidate links to many timestamps.
**Acceptance criteria:**
- Repeated footage appearances clustered
- One Telegram candidate can link to multiple input-video timestamps
$(sec "Partner" "#10" "src/clip2trace/matching.py")"

mk "Add ASR/transcript context extraction" "area:video,stretch" "$MS" \
"**Context:** Spoken context improves query planning.
**Scope:** Extract transcript; feed query planner; document heavy-dep cost.
**Acceptance criteria:**
- Transcript extracted or integrated
- Query planner uses transcript context
- Heavy dependency/runtime impact documented
$(sec "Partner" "#11" "src/clip2trace/telegram_search.py, docs/risks.md")"

mk "Add OCR upgrade path" "area:video,stretch" "$MS" \
"**Context:** pytesseract may be insufficient.
**Scope:** Compare pytesseract vs EasyOCR vs vision-model; choose per runtime constraints.
**Acceptance criteria:**
- Compare options; choose based on Sinas runtime constraints
- Document dependency/runtime cost
$(sec "Partner" "#3, #11" "functions/extract_segment_clues.py, docs/risks.md")"

mk "Add third-party Telegram search fallback adapter" "area:telegram,stretch" "$MS" \
"**Context:** A managed search API could de-risk live search.
**Scope:** Adapter interface; optional provider impl; API key via Sinas secret.
**Acceptance criteria:**
- Adapter interface designed
- Provider-specific implementation optional
- API key handled via Sinas secrets
$(sec "Partner" "#13" "src/clip2trace/telegram_search.py")"

mk "Add HTML report export" "area:ui,area:docs,stretch" "$MS" \
"**Context:** Human-readable report with thumbnails.
**Scope:** HTML version with thumbnails + Telegram links + caveats.
**Acceptance criteria:**
- Report has human-readable HTML version
- Thumbnails and Telegram links included
- Caveats visible
$(sec "A" "#17" "src/clip2trace/report.py, functions/render_report.py")"

mk "Add visual embedding similarity" "area:matching,stretch" "$MS" \
"**Context:** Embeddings may beat phash for re-encoded/cropped footage.
**Scope:** Evaluate CLIP/lightweight embeddings; keep phash fallback.
**Acceptance criteria:**
- Evaluate CLIP or lightweight embedding model
- Document runtime/dependency impact
- Fallback to phash remains available
$(sec "Partner" "#15" "src/clip2trace/matching.py, docs/risks.md")"

echo "Done. Issues created in $REPO."
