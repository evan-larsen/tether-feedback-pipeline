from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
MESSAGES_DIR = ROOT / "messages"
OUTPUT_DIR = ROOT / "output"
OUTPUT_FILE = OUTPUT_DIR / "condensed_messages.txt"

IGNORED_MESSAGE_TEXT = {
    "Liked a message",
    "You sent an attachment.",
    "You shared a post.",
    "You shared a reel.",
    "You shared a story.",
    "You sent a voice message.",
    "You unsent a message.",
    "You're now friends. Say hi!",
}


def maybe_fix_text(value: str) -> str:
    """Repair common mojibake from Meta exports when possible."""
    if not value:
        return ""

    try:
        repaired = value.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        repaired = value

    return " ".join(repaired.split())


def format_timestamp(timestamp_ms: Any) -> str:
    if not isinstance(timestamp_ms, (int, float)):
        return "unknown-time"

    dt = datetime.fromtimestamp(timestamp_ms / 1000)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def extract_message_text(message: dict[str, Any]) -> list[str]:
    parts: list[str] = []

    content = maybe_fix_text(message.get("content", ""))
    if content and content not in IGNORED_MESSAGE_TEXT:
        parts.append(content)

    share = message.get("share") or {}
    share_text = maybe_fix_text(share.get("share_text", ""))
    if share_text and share_text != content:
        parts.append(f"[shared] {share_text}")

    link = share.get("link")
    if link and link not in content:
        parts.append(f"[link] {link}")

    photos = message.get("photos") or []
    videos = message.get("videos") or []
    audio_files = message.get("audio_files") or []
    if photos:
        parts.append(f"[photos] {len(photos)} attachment(s)")
    if videos:
        parts.append(f"[videos] {len(videos)} attachment(s)")
    if audio_files:
        parts.append(f"[audio] {len(audio_files)} attachment(s)")

    return parts


def thread_header(thread: dict[str, Any], json_path: Path) -> str:
    title = maybe_fix_text(thread.get("title", json_path.parent.name))
    return f"THREAD: {title}"


def render_thread(json_path: Path) -> str | None:
    with json_path.open("r", encoding="utf-8") as handle:
        thread = json.load(handle)

    messages = thread.get("messages")
    if not isinstance(messages, list):
        return None

    lines = [thread_header(thread, json_path)]
    kept_messages = 0

    for message in reversed(messages):
        sender = maybe_fix_text(message.get("sender_name", "Unknown"))
        timestamp = format_timestamp(message.get("timestamp_ms"))
        text_parts = extract_message_text(message)
        if not text_parts:
            continue

        kept_messages += 1
        text = " | ".join(text_parts)
        lines.append(f"{timestamp} | {sender}: {text}")

    if kept_messages == 0:
        return None

    lines.append("")
    return "\n".join(lines)


def main() -> None:
    if not MESSAGES_DIR.exists():
        raise SystemExit(f"Missing messages directory: {MESSAGES_DIR}")

    OUTPUT_DIR.mkdir(exist_ok=True)

    sections: list[str] = []
    thread_files = sorted(MESSAGES_DIR.rglob("message_*.json"))

    for json_path in thread_files:
        rendered = render_thread(json_path)
        if rendered:
            sections.append(rendered)

    header = [
        "Instagram DMs Condensed Export",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Threads included: {len(sections)}",
        "",
    ]

    OUTPUT_FILE.write_text("\n".join(header + sections), encoding="utf-8")
    print(f"Wrote {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
