from __future__ import annotations

from typing import Tuple
from flask import current_app, Request

def _to_int(value: str | None, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except Exception:
        return default

def parse_pagination_args(
    req: Request,
    default: int | None = None,
    max_: int | None = None
) -> Tuple[int, int]:
    """
    Reads ?page= and ?page_size= from the query string with sane bounds.
    Falls back to Flask config:
      - PAGINATION_DEFAULT
      - PAGINATION_MAX
    Returns (page, page_size).
    """
    # Use caller overrides when available, otherwise lean on Flask configuration.
    cfg_default = default if default is not None else int(current_app.config.get("PAGINATION_DEFAULT", 20))
    cfg_max = max_ if max_ is not None else int(current_app.config.get("PAGINATION_MAX", 100))

    page = _to_int(req.args.get("page"), 1)
    if page < 1:
        page = 1

    page_size = _to_int(req.args.get("page_size"), cfg_default)
    if page_size < 1:
        page_size = cfg_default
    if page_size > cfg_max:
        page_size = cfg_max

    return page, page_size
