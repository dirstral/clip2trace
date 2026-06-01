# Skill: telegram-source-tracing

Methodology for tracing reused footage in an edited video to a **likely Telegram
source candidate**.

## Principles
- **Global Telegram search is retrieval, not proof.** A search hit only narrows
  the candidate set; it never establishes origin.
- **Visual verification is required.** Confirm a candidate by comparing keyframes
  (perceptual hash + human review), not by caption text alone.
- **A Telegram post may be a repost.** The earliest *retrievable* appearance is
  not necessarily the first appearance. Check forward/repost metadata.
- **Private/deleted posts are out of scope.** We can only reason about public,
  retrievable posts. Say so when coverage is limited.
- **Do not overclaim.** Use "likely Telegram source candidate", "earlier known
  Telegram appearance", "best candidate found". Never "the original".

## Practical retrieval notes
- `channels.searchPosts` (MTProto, user account only) is the global path.
- Hashtag search is unmetered; free-text search is metered/paid (Telegram Stars).
  Prefer exact handles and hashtags first.
- Expect flood-waits; back off on `FloodWaitError`. See docs/telegram-global-search.md.

## Scope guard
Provenance and source tracing only. No tactical analysis, target identification,
military advice, or conflict geolocation.
