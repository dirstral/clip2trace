"""Pydantic data models shared across the clip2trace pipeline.

These mirror the JSON contracts in docs/api-contracts.md and docs/data-model.md.
Sinas function handlers validate with their own JSON Schema (inputSchema /
outputSchema); these models are for the reusable core library and tests.
"""

from __future__ import annotations

from typing import List, Literal, Optional

try:
    from pydantic import BaseModel, Field
except Exception:  # pragma: no cover - pydantic is a baseline dep but stay safe
    raise

Mode = Literal["demo", "live", "hybrid"]
JobStatus = Literal[
    "created",
    "analyzing",
    "searching",
    "verifying",
    "ranking",
    "reporting",
    "done",
    "failed",
]


class Job(BaseModel):
    job_id: str
    status: JobStatus = "created"
    mode: Mode = "demo"
    input_video_file_id: Optional[str] = None
    video_context: Optional[str] = None
    date_hint: Optional[str] = None
    language_hint: Optional[str] = None
    topic_hint: Optional[str] = None
    progress: float = 0.0
    error: Optional[str] = None


class SourceSegment(BaseModel):
    segment_id: str
    start_sec: float
    end_sec: float
    source_likelihood: float = 0.0
    reason: str = "candidate reused footage"

    @property
    def duration(self) -> float:
        return max(0.0, self.end_sec - self.start_sec)


class SegmentClues(BaseModel):
    segment_id: str
    keyframe_file_ids: List[str] = Field(default_factory=list)
    phashes: List[str] = Field(default_factory=list)
    ocr_text: str = ""
    visible_handles: List[str] = Field(default_factory=list)
    context_terms: List[str] = Field(default_factory=list)
    ocr_available: bool = False


class TelegramQuery(BaseModel):
    query: str
    query_type: Literal["handle", "ocr_exact", "context", "hashtag"]
    priority: int = 5
    reason: str = ""


class TelegramCandidate(BaseModel):
    candidate_id: str
    channel: Optional[str] = None
    message_id: Optional[int] = None
    url: Optional[str] = None
    posted_at: Optional[str] = None  # ISO 8601
    caption: str = ""
    has_media: bool = False
    media_file_id: Optional[str] = None
    is_forward: bool = False
    forward_origin: Optional[str] = None
    source_query: Optional[str] = None
    accessible: bool = True


class MediaMatch(BaseModel):
    candidate_id: str
    visual_score: float = 0.0
    text_score: float = 0.0
    temporal_score: float = 0.0
    overall_score: float = 0.0
    matched_frames: List[dict] = Field(default_factory=list)


class RankedCandidate(BaseModel):
    candidate_id: str
    confidence: float
    confidence_label: str
    rejected: bool = False
    evidence: dict = Field(default_factory=dict)
    caveats: List[str] = Field(default_factory=list)
    recommended_next_steps: List[str] = Field(default_factory=list)
    url: Optional[str] = None


class ProvenanceReport(BaseModel):
    job_id: str
    summary: str = ""
    segments: List[SourceSegment] = Field(default_factory=list)
    ranked_candidates: List[RankedCandidate] = Field(default_factory=list)
    caveats: List[str] = Field(default_factory=list)
    generated_mode: Mode = "demo"
