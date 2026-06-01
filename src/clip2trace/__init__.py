"""clip2trace — Telegram source tracing for reused footage in edited videos.

This package holds the reusable, testable core logic (scoring, matching, query
generation, schemas, report building). Sinas functions in ../functions are thin
handlers; in production they must be self-contained or depend on admin-approved
packages, so they embed the logic they need rather than importing this package
at runtime. See docs/architecture.md.
"""

__version__ = "0.1.0"
