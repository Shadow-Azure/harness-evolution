"""Shared constants."""

POST_PROCESS_EVENT_INDEX = 2_147_483_647
"""INT_MAX sentinel for a post-process anchor; sorts after every resolvable object."""

ANCHOR_KINDS: tuple[str, ...] = ("event", "node", "post_process", "unknown")
"""Closed anchor-kind vocabulary shared by DTOs, candidates, and the matcher."""
