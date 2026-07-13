from __future__ import annotations

import csv
import json
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
COMMENTS_DIR = ROOT / "comments"
MESSAGES_DIR = ROOT / "messages"
OUTPUT_DIR = ROOT / "output"

MASTER_FEEDBACK_CSV = OUTPUT_DIR / "master_feedback.csv"
PENDING_FEEDBACK_CSV = OUTPUT_DIR / "pending_feedback.csv"
PENDING_CODEX_INPUT_TXT = OUTPUT_DIR / "pending_codex_input.txt"
CATEGORIZED_FEEDBACK_CSV = OUTPUT_DIR / "categorized_feedback.csv"
CODEX_LABELS_TXT = OUTPUT_DIR / "codex_labels.txt"
MASTER_WITH_CATEGORIES_CSV = OUTPUT_DIR / "master_feedback_with_categories.csv"

SELF_USERNAMES = {"evan.builds.tether"}
SELF_DM_NAMES = {"evan larsen", "evan.builds.tether"}

PRIORITY_FIELDS = [
    "source_type",
    "platform",
    "video_id",
    "conversation_title",
    "thread_path",
    "source_file",
    "item_timestamp",
    "item_date",
    "actor_username",
    "actor_display_name",
    "full_text",
    "ai_input_text",
    "lookup_key",
    "comment",
    "comment_full",
    "content",
    "is_message_request",
    "thread_participants",
    "raw_record_json",
]


def ensure_output_dir() -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)


def maybe_fix_text(value: Any) -> str:
    if value is None:
        return ""

    if not isinstance(value, str):
        value = str(value)

    try:
        repaired = value.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        repaired = value

    return repaired.strip()


def normalize_for_ai(value: Any) -> str:
    return " ".join(maybe_fix_text(value).split())


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def is_comment_noise(value: str) -> bool:
    text = normalize_for_ai(value)
    if not text:
        return True

    lowered = text.lower()
    noise_patterns = (
        "reply",
        "like",
        "likes",
    )
    if any(token in lowered for token in noise_patterns) and not any(
        char.isalpha() for char in text.replace("Reply", "").replace("like", "")
    ):
        return True

    if lowered in {"reply", "replies", "like", "likes"}:
        return True

    if lowered.endswith("reply") and len(text.split()) <= 2 and text[0].isdigit():
        return True

    return False


def make_lookup_key(row: dict[str, Any]) -> str:
    parts = [
        row.get("source_type", ""),
        row.get("video_id", ""),
        row.get("thread_path", ""),
        row.get("actor_username", ""),
        row.get("actor_display_name", ""),
        row.get("item_timestamp", ""),
        row.get("full_text", ""),
    ]
    return "||".join(normalize_for_ai(part) for part in parts)


def parse_comment_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    if not COMMENTS_DIR.exists():
        return rows

    for csv_path in sorted(COMMENTS_DIR.glob("*.csv")):
        with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for record in reader:
                username = normalize_for_ai(record.get("username", "")).lower()
                if username in SELF_USERNAMES:
                    continue

                comment_text = maybe_fix_text(record.get("comment", ""))
                if is_comment_noise(comment_text):
                    continue

                row: dict[str, str] = {
                    "source_type": "comment",
                    "platform": "instagram",
                    "video_id": maybe_fix_text(record.get("post_id", "")),
                    "conversation_title": "",
                    "thread_path": "",
                    "source_file": str(csv_path.relative_to(ROOT)),
                    "item_timestamp": maybe_fix_text(record.get("timestamp", "")),
                    "item_date": maybe_fix_text(record.get("timestamp", ""))[:10],
                    "actor_username": maybe_fix_text(record.get("username", "")),
                    "actor_display_name": maybe_fix_text(record.get("username", "")),
                    "full_text": comment_text,
                    "ai_input_text": normalize_for_ai(comment_text),
                    "comment": comment_text,
                    "comment_full": maybe_fix_text(record.get("comment_full", "")),
                    "content": "",
                    "is_message_request": "",
                    "thread_participants": "",
                }

                for key, value in record.items():
                    row[key] = maybe_fix_text(value)

                row["raw_record_json"] = json_dumps(record)
                row["lookup_key"] = make_lookup_key(row)
                rows.append(row)

    return rows


def parse_dm_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    if not MESSAGES_DIR.exists():
        return rows

    for json_path in sorted(MESSAGES_DIR.rglob("message_*.json")):
        with json_path.open("r", encoding="utf-8") as handle:
            thread = json.load(handle)

        messages = thread.get("messages")
        if not isinstance(messages, list):
            continue

        thread_title = maybe_fix_text(thread.get("title", json_path.parent.name))
        thread_path = maybe_fix_text(thread.get("thread_path", str(json_path.relative_to(ROOT))))
        participants = [
            maybe_fix_text(person.get("name", ""))
            for person in thread.get("participants", [])
            if maybe_fix_text(person.get("name", ""))
        ]
        participants_text = " | ".join(participants)
        is_message_request = "yes" if thread.get("is_pending") else "no"

        for message in reversed(messages):
            sender_name = maybe_fix_text(message.get("sender_name", ""))
            if sender_name.lower() in SELF_DM_NAMES:
                continue

            raw_content = maybe_fix_text(message.get("content", ""))
            share = message.get("share") or {}
            share_text = maybe_fix_text(share.get("share_text", ""))

            full_text_parts = [
                part
                for part in [
                    raw_content,
                    f"[shared] {share_text}" if share_text else "",
                    f"[link] {maybe_fix_text(share.get('link', ''))}"
                    if share.get("link")
                    else "",
                ]
                if part
            ]

            if not full_text_parts:
                continue

            timestamp_ms = message.get("timestamp_ms")
            iso_timestamp = ""
            item_date = ""
            if isinstance(timestamp_ms, (int, float)):
                dt = datetime.fromtimestamp(timestamp_ms / 1000)
                iso_timestamp = dt.isoformat(timespec="seconds")
                item_date = dt.date().isoformat()

            row = {
                "source_type": "dm",
                "platform": "instagram",
                "video_id": "",
                "conversation_title": thread_title,
                "thread_path": thread_path,
                "source_file": str(json_path.relative_to(ROOT)),
                "item_timestamp": iso_timestamp,
                "item_date": item_date,
                "actor_username": sender_name,
                "actor_display_name": sender_name,
                "full_text": " | ".join(full_text_parts),
                "ai_input_text": normalize_for_ai(" | ".join(full_text_parts)),
                "comment": "",
                "comment_full": "",
                "content": raw_content,
                "is_message_request": is_message_request,
                "thread_participants": participants_text,
                "dm_sender_name": sender_name,
                "dm_timestamp_ms": maybe_fix_text(timestamp_ms),
                "dm_share_link": maybe_fix_text(share.get("link", "")),
                "dm_share_text": share_text,
                "dm_share_original_content_owner": maybe_fix_text(
                    share.get("original_content_owner", "")
                ),
                "dm_reactions_json": json_dumps(message.get("reactions", [])),
                "dm_photos_json": json_dumps(message.get("photos", [])),
                "dm_videos_json": json_dumps(message.get("videos", [])),
                "dm_audio_files_json": json_dumps(message.get("audio_files", [])),
                "dm_is_geoblocked_for_viewer": maybe_fix_text(
                    message.get("is_geoblocked_for_viewer", "")
                ),
                "dm_is_unsent_image_by_messenger_kid_parent": maybe_fix_text(
                    message.get("is_unsent_image_by_messenger_kid_parent", "")
                ),
            }

            row["raw_record_json"] = json_dumps(message)
            row["lookup_key"] = make_lookup_key(row)
            rows.append(row)

    return rows


def build_master_rows() -> list[dict[str, str]]:
    rows = parse_comment_rows() + parse_dm_rows()
    rows.sort(
        key=lambda row: (
            row.get("source_type", ""),
            row.get("video_id", ""),
            row.get("thread_path", ""),
            row.get("item_timestamp", ""),
            row.get("actor_username", ""),
            row.get("full_text", ""),
        )
    )
    return rows


def collect_fieldnames(rows: list[dict[str, Any]]) -> list[str]:
    ordered = OrderedDict((field, None) for field in PRIORITY_FIELDS)
    for row in rows:
        for key in row:
            ordered.setdefault(key, None)
    return list(ordered.keys())


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    ensure_output_dir()
    if not rows:
        fieldnames = PRIORITY_FIELDS[:]
    else:
        fieldnames = collect_fieldnames(rows)

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def categorized_lookup() -> dict[str, dict[str, str]]:
    rows = read_csv_rows(CATEGORIZED_FEEDBACK_CSV)
    return {row.get("lookup_key", ""): row for row in rows if row.get("lookup_key")}


def uncategorized_rows(master_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    existing = categorized_lookup()
    return [row for row in master_rows if row.get("lookup_key", "") not in existing]


def write_pending_codex_input(rows: list[dict[str, str]]) -> None:
    ensure_output_dir()
    lines = [row.get("ai_input_text", "") for row in rows]
    PENDING_CODEX_INPUT_TXT.write_text("\n".join(lines), encoding="utf-8")


def read_label_lines(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    return text.splitlines()


def attach_existing_categories(master_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    existing = categorized_lookup()
    merged: list[dict[str, str]] = []

    for row in master_rows:
        combined = dict(row)
        match = existing.get(row.get("lookup_key", ""))
        if match:
            combined["category_line"] = match.get("category_line", "")
            combined["category"] = match.get("category", "")
            combined["subcategory"] = match.get("subcategory", "")
            combined["categorized_at"] = match.get("categorized_at", "")
        else:
            combined["category_line"] = ""
            combined["category"] = ""
            combined["subcategory"] = ""
            combined["categorized_at"] = ""
        merged.append(combined)

    return merged
