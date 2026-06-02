# samples/

Demo input videos for clip2trace — short public news clips used as **edited
videos** to trace back to likely Telegram source candidates. Unlike the rest of
the repo's media (gitignored), these are tracked on purpose because they're the
demo inputs (see the `!samples/` override in `.gitignore`).

## Provenance
Downloaded with `yt-dlp` as separate adaptive streams (video-only `f399`, AV1 /
audio-only `f251`, Opus) and **muxed locally** into a single `.mkv` per clip
(lossless stream copy, no re-encode). The YouTube id is in the filename
(`… [<id>].mkv`).

## Use
- Visual pipeline (`src/clip2trace/video.py`, `extract_segment_clues`) decodes
  frames via PyAV; the audio track is only used if the ASR/transcript stretch
  (#26) lands.
- AV1 decode needs `libdav1d` (bundled in PyAV's ffmpeg locally); confirm the
  managed Sinas worker's PyAV build supports AV1 before relying on the
  on-instance path, otherwise transcode to H.264 for that environment.

## Scope / caveats
Third-party news footage, used only as **provenance / source-tracing** test
inputs — not for tactical analysis, identification, or any use outside the
product's stated scope. They are demo fixtures, not redistributable datasets.
