from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable, Optional

from bson import ObjectId
from flask import jsonify, request

from .config import config


def parse_pagination() -> tuple[int, int]:
    default = config.PAGINATION_DEFAULT
    page = max(int(request.args.get("page", 1)), 1)
    page_size = int(request.args.get("page_size", default))
    page_size = max(1, min(page_size, config.PAGINATION_MAX))
    return page, page_size


def pagination_envelope(data: Iterable[Any], page: int, page_size: int, total: int):
    total_pages = (total + page_size - 1) // page_size if page_size else 1
    return jsonify(
        {
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "total_items": total,
            "data": list(data),
        }
    )


def parse_sort(default: str = "_id") -> list[tuple[str, int]]:
    sort_param = request.args.get("sort", default)
    sort_fields: list[tuple[str, int]] = []
    for field in sort_param.split(","):
        direction = -1 if field.startswith("-") else 1
        field_name = field[1:] if field.startswith("-") else field
        sort_fields.append((field_name, direction))
    return sort_fields


def error_response(code: str, message: str, status: int, details: Optional[list[dict[str, Any]]] = None):
    payload: dict[str, Any] = {
        "error": {
            "code": code,
            "message": message,
        }
    }
    if details:
        payload["error"]["details"] = details
    return jsonify(payload), status


def iso_to_datetime(value: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def parse_pagination_args(req, default_size=20, max_size=100):
    try:
        page = max(1, int(req.args.get("page", 1)))
    except ValueError:
        page = 1
    try:
        size = int(req.args.get("page_size", default_size))
    except ValueError:
        size = default_size
    size = max(1, min(size, max_size))
    skip = (page - 1) * size
    return page, size, skip


def normalize_id(doc: dict | None):
    """Move Mongo `_id` → `id` (string) for clean JSON responses."""
    if not doc:
        return doc
    _id = doc.get("_id")
    if _id is not None:
        try:
            doc["id"] = str(_id)
        except Exception:
            doc["id"] = _id  # fallback if already a string/uuid
        doc.pop("_id", None)
    return doc


def normalize_many(docs: list[dict]):
    return [normalize_id(d) for d in docs]


def ok_list(items, page, page_size, total):
    return jsonify({
        "items": items,
        "page": page,
        "page_size": page_size,
        "total_items": total,
        "total_pages": (total + page_size - 1) // page_size if page_size else 0,
    }), 200


def looks_like_oid(s: str) -> bool:
    return isinstance(s, str) and len(s) == 24 and all(c in "0123456789abcdefABCDEF" for c in s)


def maybe_object_id(value: Any) -> Any:
    """Coerce ``value`` to :class:`~bson.ObjectId` when appropriate."""
    if isinstance(value, str) and looks_like_oid(value):
        try:
            return ObjectId(value)
        except Exception:
            return value
    return value


def resolve_existing_id(db, coll_name: str, value: str | None):
    """Resolve ``value`` to the stored ``_id`` in ``coll_name`` if it exists."""
    if not value:
        return None

    coll = db[coll_name]

    # 1) ObjectId string?
    if isinstance(value, str) and looks_like_oid(value):
        try:
            oid = ObjectId(value)
            if coll.find_one({"_id": oid}, {"_id": 1}):
                return oid
        except Exception:
            pass

    # 2) Exact string _id?
    if isinstance(value, str):
        doc = coll.find_one({"_id": value}, {"_id": 1})
        if doc:
            return value

    # 3) Numeric legacy ids
    if isinstance(value, str) and value.isdigit():
        n = int(value)
        for f in ("fd_team_id", "legacy_id", "id", "external_id"):
            doc = coll.find_one({f: n}, {"_id": 1})
            if doc:
                return doc["_id"]

    # 4) Common string identifiers (order matters)
    field_order = {
        "competitions": ("code", "slug", "name"),
        "seasons": ("code", "slug", "year"),
        "teams": ("tla", "shortName", "name", "slug", "code"),
    }
    try_fields = field_order.get(coll_name, ("code", "slug", "name"))

    for f in try_fields:
        doc = coll.find_one({f: value}, {"_id": 1})
        if doc:
            return doc["_id"]

    return None
