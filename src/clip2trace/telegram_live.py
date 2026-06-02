"""Live global Telegram search via Telethon (MTProto `channels.searchPosts`).

`channels.searchPosts` is **user-account only** (bots cannot call it). Hashtag
search is unmetered; free-text search consumes free daily slots and then costs
Telegram Stars — we never spend Stars unless explicitly authorised. See
docs/telegram-global-search.md and docs/research/telegram-global-search.md.

The pure logic here (query routing, message normalisation, result accumulation)
is unit-tested without Telethon installed. The thin Telethon glue
(`TelethonSearchClient`, `build_client_from_secrets`) lazily imports Telethon so
this module imports cleanly in minimal/sandbox environments.

`TelethonSearchClient.search(queries)` matches the `live_client` contract used by
`telegram_search.search_posts`: it takes a ranked query list and returns a list
of candidate dicts (the `TelegramCandidate` shape in docs/data-model.md).
"""

from __future__ import annotations

import os
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

# Conservative defaults — we are a courteous client on a risky API.
MAX_RESULTS_PER_QUERY = 50
MAX_PAGES_PER_QUERY = 5
PAGE_LIMIT = 100

# Media download bounds (Sinas containers: 100 MB /tmp, 512 MB RAM, 300 s).
MAX_MEDIA = 5
MAX_MEDIA_BYTES = 8_000_000          # per-file cap
MAX_TMP_BUDGET = 80_000_000          # total bytes across a fetch (under 100 MB /tmp)

# Telethon error class names that mean "this media is inaccessible — skip it".
# Matched by class name so we don't hard-import telethon here.
INACCESSIBLE_ERROR_NAMES = frozenset({
    "ChannelPrivateError", "ChannelInvalidError", "MsgIdInvalidError",
    "MediaEmptyError", "FileIdInvalidError", "LocationInvalidError",
    "UsernameInvalidError", "UsernameNotOccupiedError",
})


def media_within_cap(size, max_bytes: int = MAX_MEDIA_BYTES) -> bool:
    """Pre-download size gate. Unknown size (None, common for photos) is allowed
    through — the per-file cap can't pre-judge it, so we let the download proceed
    and rely on the total-/tmp budget. A known size over the cap is rejected."""
    return size is None or size <= max_bytes


def route_query(query: Dict) -> Tuple[Optional[str], Optional[str]]:
    """Map a query dict to `(hashtag, free_text)` — exactly one is non-None.

    `channels.searchPosts` requires exactly one of `hashtag`/`query`. Hashtag
    queries (unmetered) take the hashtag slot; everything else (handle,
    ocr_exact, context) is a free-text query.
    """
    text = (query.get("query") or "").strip()
    if not text:
        return None, None
    if query.get("query_type") == "hashtag" or text.startswith("#"):
        return text.lstrip("#"), None
    return None, text


def is_free_text(hashtag: Optional[str], free_text: Optional[str]) -> bool:
    """Free-text searches are the metered ones; hashtag searches are free."""
    return free_text is not None and hashtag is None


def _index_chats(chats: Iterable) -> Dict[int, object]:
    """Index a result's `chats` by id for peer resolution."""
    out: Dict[int, object] = {}
    for c in chats or []:
        cid = getattr(c, "id", None)
        if cid is not None:
            out[cid] = c
    return out


def _peer_channel_id(peer_id) -> Optional[int]:
    """Extract a channel id from a message's `peer_id` (PeerChannel)."""
    if peer_id is None:
        return None
    return getattr(peer_id, "channel_id", None) or getattr(peer_id, "chat_id", None)


def normalize_message(
    msg, chats_by_id: Dict[int, object], source_query: Optional[str] = None
) -> Dict:
    """Normalise a raw Telethon message + chat index into a candidate dict.

    Tolerant of missing attributes; never raises on a malformed message.
    """
    mid = getattr(msg, "id", None)
    cid = _peer_channel_id(getattr(msg, "peer_id", None))
    chan = chats_by_id.get(cid) if cid is not None else None
    username = getattr(chan, "username", None) if chan is not None else None
    title = getattr(chan, "title", None) if chan is not None else None

    url = f"https://t.me/{username}/{mid}" if username and mid else None
    date = getattr(msg, "date", None)
    isoformat = getattr(date, "isoformat", None)
    posted = isoformat() if callable(isoformat) else (str(date) if date else None)

    return {
        "candidate_id": f"{username or title or 'unknown'}_{mid}",
        "channel": username or title,
        "message_id": mid,
        "url": url,
        "posted_at": posted,
        "caption": getattr(msg, "message", "") or "",
        "has_media": getattr(msg, "media", None) is not None,
        "is_forward": getattr(msg, "fwd_from", None) is not None,
        "accessible": True,
        "source_query": source_query,
    }


def accumulate(
    pages: Iterable[List[Dict]], max_results: int = MAX_RESULTS_PER_QUERY
) -> List[Dict]:
    """Flatten paginated candidate lists, de-dupe by candidate_id, cap at
    `max_results`. `pages` is any iterable of candidate-dict lists."""
    seen, out = set(), []
    for page in pages:
        for cand in page:
            cid = cand.get("candidate_id")
            if cid in seen:
                continue
            seen.add(cid)
            out.append(cand)
            if len(out) >= max_results:
                return out
    return out


class TelethonSearchClient:
    """Thin wrapper over a Telethon user client for global post search.

    `connector` is a zero-arg callable returning a *connected, sync* Telethon
    client usable as a context manager (so the client lives only for the call).
    Injectable for testing. `allow_paid` authorises spending Telegram Stars on
    free-text search once free slots are exhausted (default False).
    """

    def __init__(
        self,
        connector: Callable[[], Any],
        *,
        allow_paid: bool = False,
        max_results_per_query: int = MAX_RESULTS_PER_QUERY,
        max_pages: int = MAX_PAGES_PER_QUERY,
        page_limit: int = PAGE_LIMIT,
    ):
        self._connector = connector
        self.allow_paid = allow_paid
        self.max_results_per_query = max_results_per_query
        self.max_pages = max_pages
        self.page_limit = page_limit
        self.diagnostics: List[str] = []

    def search(self, queries: List[Dict]) -> List[Dict]:
        """Run each query via `channels.searchPosts`; return candidate dicts."""
        from telethon import functions, types  # lazy
        from telethon.errors import FloodWaitError

        results: List[Dict] = []
        seen = set()
        with self._connector() as client:
            for q in queries or []:
                hashtag, free_text = route_query(q)
                if hashtag is None and free_text is None:
                    continue
                if is_free_text(hashtag, free_text) and not self._free_text_ok(client):
                    self.diagnostics.append(
                        f"skipped metered free-text query {free_text!r}: "
                        "no free slots and paid search not authorised"
                    )
                    continue
                try:
                    # Materialise inside the try so pagination errors (the
                    # generator raises while iterating) are caught here.
                    pages = list(
                        self._paginate(
                            client, functions, types, hashtag, free_text, q.get("query")
                        )
                    )
                    candidates = accumulate(pages, self.max_results_per_query)
                except FloodWaitError as exc:
                    self.diagnostics.append(
                        f"flood wait {getattr(exc, 'seconds', '?')}s; "
                        "stopping live search"
                    )
                    break
                except Exception as exc:  # never crash the pipeline
                    self.diagnostics.append(f"query failed {q.get('query')!r}: {exc!r}")
                    continue
                for cand in candidates:
                    if cand["candidate_id"] in seen:
                        continue
                    seen.add(cand["candidate_id"])
                    results.append(cand)
        return results

    def download_candidates(self, candidates: List[Dict], *,
                            max_media: int = MAX_MEDIA,
                            max_bytes: int = MAX_MEDIA_BYTES,
                            total_budget: int = MAX_TMP_BUDGET,
                            dest_dir: str = "/tmp") -> Dict:
        """Download bounded media for candidates over a single connection.

        Caps per-file size (`max_bytes`), item count (`max_media`) and the total
        bytes written (`total_budget`, to respect the 100 MB /tmp limit). Sets
        `media_file_id` on success; marks `accessible = False` on inaccessible/
        deleted/private media. Returns
        {"candidates", "downloaded", "diagnostics"}. Never raises.
        """
        updated = [dict(c) for c in candidates]
        downloaded, spent, diags = 0, 0, []
        try:
            from telethon.errors import FloodWaitError  # lazy
        except Exception as exc:  # telethon missing — don't raise, report
            diags.append(f"telethon unavailable: {exc!r}")
            self.diagnostics.extend(diags)
            return {"candidates": updated, "downloaded": 0, "diagnostics": diags}

        try:
            with self._connector() as client:  # connect can fail (bad secrets)
                for cand in updated:
                    if downloaded >= max_media:
                        break
                    if not cand.get("has_media") or not cand.get("accessible"):
                        continue
                    channel, mid = cand.get("channel"), cand.get("message_id")
                    if not channel or not mid:
                        continue
                    try:
                        msg = client.get_messages(channel, ids=mid)
                        if msg is None:
                            cand["accessible"] = False
                            diags.append(f"{channel}/{mid}: not found or deleted")
                            continue
                        size = getattr(getattr(msg, "file", None), "size", None)
                        if not media_within_cap(size, max_bytes):
                            diags.append(f"{channel}/{mid}: {size} bytes over per-file cap")
                            continue
                        if size and spent + size > total_budget:
                            diags.append("tmp byte budget reached; stopping downloads")
                            break
                        path = client.download_media(msg, file=dest_dir)
                        if path is None:
                            cand["accessible"] = False
                            diags.append(f"{channel}/{mid}: no downloadable media")
                            continue
                        # Enforce caps against the ACTUAL bytes written:
                        # msg.file.size is an estimate for photos and None for
                        # some media, so an unknown/under-reported size must not
                        # be allowed to blow the per-file cap or /tmp budget.
                        actual = size
                        if actual is None:
                            try:
                                actual = os.path.getsize(path)
                            except OSError:
                                actual = 0
                        if actual > max_bytes or spent + actual > total_budget:
                            try:
                                os.remove(path)
                            except OSError:
                                pass
                            if actual > max_bytes:
                                diags.append(f"{channel}/{mid}: {actual} bytes over per-file cap")
                                continue
                            diags.append("tmp byte budget reached; stopping downloads")
                            break
                        cand["media_file_id"] = path
                        downloaded += 1
                        spent += actual
                    except FloodWaitError as exc:
                        diags.append(f"flood wait {getattr(exc, 'seconds', '?')}s; "
                                     "stopping downloads")
                        break
                    except Exception as exc:
                        cand["accessible"] = False
                        name = type(exc).__name__
                        reason = "inaccessible" if name in INACCESSIBLE_ERROR_NAMES else name
                        diags.append(f"{channel}/{mid}: download failed ({reason})")
        except Exception as exc:  # connector / connection setup failure
            diags.append(f"download session failed: {exc!r}")
        self.diagnostics.extend(diags)
        return {"candidates": updated, "downloaded": downloaded, "diagnostics": diags}

    def _free_text_ok(self, client) -> bool:
        """Best-effort check of remaining free-text search slots."""
        if self.allow_paid:
            return True
        try:
            from telethon import functions

            flood = client(functions.channels.CheckSearchPostsFloodRequest())
            remaining = getattr(flood, "remaining", None)
            # If we can't read it, be conservative and allow one attempt.
            return remaining is None or remaining > 0
        except Exception:
            return True

    def _paginate(self, client, functions, types, hashtag, free_text, source_query):
        """Yield candidate-dict pages, following `next_rate`."""
        offset_rate, offset_id = 0, 0
        offset_peer = types.InputPeerEmpty()
        for _ in range(self.max_pages):
            req = functions.channels.SearchPostsRequest(
                hashtag=hashtag,
                query=free_text,
                offset_rate=offset_rate,
                offset_peer=offset_peer,
                offset_id=offset_id,
                limit=self.page_limit,
            )
            res = client(req)
            msgs = list(getattr(res, "messages", []) or [])
            if not msgs:
                break
            chats_by_id = _index_chats(getattr(res, "chats", []) or [])
            yield [normalize_message(m, chats_by_id, source_query) for m in msgs]
            next_rate = getattr(res, "next_rate", None)
            if not next_rate:
                break
            offset_rate = next_rate
            offset_id = getattr(msgs[-1], "id", 0) or 0


def build_client_from_secrets(
    secrets: Optional[Dict], *, allow_paid: bool = False
) -> Optional["TelethonSearchClient"]:
    """Build a live client from Sinas secrets, or return None if unavailable.

    Returns None (never raises) when Telethon is missing or any of
    TELEGRAM_API_ID / TELEGRAM_API_HASH / TELEGRAM_SESSION_STRING is absent — the
    caller then reports `live_unavailable` rather than faking a live search.
    """
    secrets = secrets or {}
    api_id = secrets.get("TELEGRAM_API_ID")
    api_hash = secrets.get("TELEGRAM_API_HASH")
    session = secrets.get("TELEGRAM_SESSION_STRING")
    if not (api_id and api_hash and session):
        return None
    try:
        from telethon.sync import TelegramClient  # noqa: F401  (sync wrapper)
    except Exception:
        return None

    def connector():
        from telethon.sessions import StringSession
        from telethon.sync import TelegramClient

        return TelegramClient(StringSession(session), int(api_id), api_hash)

    return TelethonSearchClient(connector, allow_paid=allow_paid)
