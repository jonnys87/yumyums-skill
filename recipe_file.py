"""Writes a `.yumyums` file that the YumYums iOS app will open.

The format is read by RecipeFile.read in the app, and FORMAT.md beside this file
is the written specification. It is a zip holding:

    manifest.json   format "yumyums-recipe", version 1, plus app_version,
                    created_at, title, and photo when there is one
    recipe.json     one recipe, in the same JSON the backup archive writes
    photo.<ext>     the picture, when one is embedded

What the reader insists on, and therefore what this writer honours: the whole
file is at most twelve megabytes, manifest.json exists and its format field is
exactly "yumyums-recipe", its version is not greater than 1, recipe.json exists
and decodes, and the recipe has a title or an ingredient or a step in it. The
photo entry has to be a single path component starting with "photo." and the
app sniffs its bytes rather than trusting the extension, so only the five image
types it knows are worth embedding.

Entries are stored rather than deflated, which is what the app's own test
fixture does, and JSON is written sorted and indented by two the way Swift's
JSONEncoder writes it with .prettyPrinted and .sortedKeys.
"""

from __future__ import annotations

import json
import re
import uuid
import zipfile
from datetime import datetime, timezone
from io import BytesIO
from typing import Any

TOOL_VERSION = "1.0.0"
FORMAT_IDENTIFIER = "yumyums-recipe"
CURRENT_VERSION = 1
FILE_EXTENSION = "yumyums"
MANIFEST_NAME = "manifest.json"
RECIPE_NAME = "recipe.json"
PHOTO_PREFIX = "photo."
MAXIMUM_BYTES = 12 * 1024 * 1024
MAXIMUM_FILENAME_LENGTH = 60

RECIPE_FIELDS = (
    "id", "title", "source_url", "image_url", "servings", "prep_time",
    "cook_time", "total_time", "ingredients", "steps", "tags", "notes",
    "created_at", "updated_at",
)

AI_READ_TAG = "AI read"


class RecipeFileError(Exception):
    pass


def photo_extension(data: bytes) -> str | None:
    """The same sniff the app does in RecipeImageStore.fileExtension."""
    head = data[:12]
    if len(head) < 12:
        return None
    if head[0] == 0xFF and head[1] == 0xD8:
        return "jpg"
    if head[0:4] == b"\x89PNG":
        return "png"
    if head[0:3] == b"GIF":
        return "gif"
    if head[0:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    if head[4:8] == b"ftyp":
        return "heic"
    return None


def recipe_payload(recipe: dict[str, Any]) -> dict[str, Any]:
    """The recipe as the app's decoder expects it: every field, all strings."""
    payload: dict[str, Any] = {}
    for field in RECIPE_FIELDS:
        value = recipe.get(field, "")
        if field == "ingredients":
            payload[field] = [
                {
                    "amount": str(item.get("amount", "")),
                    "unit": str(item.get("unit", "")),
                    "item": str(item.get("item", "")),
                }
                for item in (value or [])
                if str(item.get("item", "")).strip()
            ]
        elif field in {"steps", "tags"}:
            payload[field] = [str(entry) for entry in (value or []) if str(entry).strip()]
        else:
            payload[field] = str(value or "")
    if not payload["id"]:
        payload["id"] = str(uuid.uuid4())
    return payload


def filename(title: str) -> str:
    """The app's own naming, so a file sent from here looks like one sent from it."""
    stem = re.sub(r"\s+", " ", title)
    stem = "".join(char for char in stem if ord(char) >= 32 and ord(char) != 127)
    stem = re.sub(r'[/\\:*?"<>|]', " ", stem)
    stem = " ".join(stem.split())
    stem = stem[:MAXIMUM_FILENAME_LENGTH].strip()
    while stem.startswith(".") or stem.startswith(" "):
        stem = stem[1:]
    stem = stem.strip()
    if not stem:
        stem = "Recipe"
    return f"{stem}.{FILE_EXTENSION}"


def make(
    recipe: dict[str, Any],
    photo: bytes | None = None,
    app_version: str = f"yumyums-send {TOOL_VERSION}",
    created_at: datetime | None = None,
    extras: dict[str, Any] | None = None,
) -> bytes:
    """The file, as bytes.

    `extras` goes into the manifest beside the fields the app reads, which
    ignores what it does not know. It is where this tool says how the recipe was
    got and whether anybody has looked at it yet.
    """
    payload = recipe_payload(recipe)
    if not payload["title"].strip() and not payload["ingredients"] and not payload["steps"]:
        raise RecipeFileError("There is nothing in that recipe for the app to open")

    photo_name = None
    if photo:
        extension = photo_extension(photo)
        if extension is None:
            raise RecipeFileError("That photo is not a JPEG, PNG, GIF, WebP or HEIC")
        photo_name = PHOTO_PREFIX + extension

    stamp = created_at or datetime.now(timezone.utc)
    manifest: dict[str, Any] = {
        "format": FORMAT_IDENTIFIER,
        "version": CURRENT_VERSION,
        "app_version": app_version,
        "created_at": stamp.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "title": payload["title"],
    }
    if photo_name:
        manifest["photo"] = photo_name
    manifest.update(extras or {})

    buffer = BytesIO()
    date_time = (stamp.year, stamp.month, stamp.day, stamp.hour, stamp.minute, stamp.second)
    with zipfile.ZipFile(buffer, "w") as archive:
        _write(archive, MANIFEST_NAME, _json_bytes(manifest), date_time)
        _write(archive, RECIPE_NAME, _json_bytes(payload), date_time)
        if photo and photo_name:
            _write(archive, photo_name, photo, date_time)

    data = buffer.getvalue()
    if len(data) > MAXIMUM_BYTES:
        raise RecipeFileError(
            f"That file is {len(data) // (1024 * 1024)} MB and the app will not open "
            f"anything over {MAXIMUM_BYTES // (1024 * 1024)} MB"
        )
    return data


def _json_bytes(value: dict[str, Any]) -> bytes:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False).encode("utf-8")


def _write(archive: zipfile.ZipFile, name: str, data: bytes, date_time: tuple) -> None:
    info = zipfile.ZipInfo(name, date_time=date_time)
    info.compress_type = zipfile.ZIP_STORED
    info.create_system = 3
    info.external_attr = 0o644 << 16
    archive.writestr(info, data)
