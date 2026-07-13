from __future__ import annotations

import csv
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

from feedback_pipeline import MASTER_WITH_CATEGORIES_CSV, OUTPUT_DIR


CHATGPT_OUTPUT_DIR = OUTPUT_DIR / "chatgpt"
FULL_OUTPUT_FILE = CHATGPT_OUTPUT_DIR / "chatgpt_feedback_last_30_days.txt"
ROADMAP_OUTPUT_FILE = CHATGPT_OUTPUT_DIR / "chatgpt_feedback_roadmap_last_30_days.txt"

ROADMAP_KEEP_PREFIXES = (
    "feature_request|",
    "bug_report|",
    "confusion|",
    "tester_interest|",
    "growth_signal|",
)

ROADMAP_DROP_EXACT = {
    "praise|general",
    "praise|value",
    "non_product|social",
    "non_product|other",
    "non_product|joke",
    "non_product|spam",
    "other|unclear",
}


def parse_date(value: str) -> date | None:
    value = (value or "").strip()
    if not value:
        return None

    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue

    try:
        return datetime.fromisoformat(value).date()
    except ValueError:
        return None


def normalize_text(value: str) -> str:
    return " ".join((value or "").split())


def recent_feedback_rows() -> tuple[list[dict[str, str]], date, date]:
    if not MASTER_WITH_CATEGORIES_CSV.exists():
        raise SystemExit(
            f"Missing categorized master file: {MASTER_WITH_CATEGORIES_CSV}. "
            "Run classification and merge first."
        )

    today = date.today()
    cutoff = today - timedelta(days=30)

    with MASTER_WITH_CATEGORIES_CSV.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    recent_rows: list[dict[str, str]] = []
    for row in rows:
        row_date = parse_date(row.get("item_date", "")) or parse_date(row.get("item_timestamp", ""))
        if not row_date or row_date < cutoff:
            continue

        text = normalize_text(row.get("ai_input_text", "") or row.get("full_text", ""))
        if not text:
            continue

        row["_resolved_date"] = row_date.isoformat()
        row["_resolved_text"] = text
        recent_rows.append(row)

    if not recent_rows:
        raise SystemExit("No feedback rows found in the last 30 days.")

    return recent_rows, cutoff, today


def write_pack(
    rows: list[dict[str, str]],
    output_file: Path,
    cutoff: date,
    today: date,
    title: str,
    dropped_counts: Counter[str] | None = None,
) -> None:
    category_counts = Counter(row.get("category_line", "") or "other|unclear" for row in rows)
    ordered_categories = sorted(
        category_counts,
        key=lambda label: (-category_counts[label], label),
    )
    category_codes = {label: index + 1 for index, label in enumerate(ordered_categories)}

    dm_groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    video_groups: dict[str, dict[str, list[dict[str, str]]]] = defaultdict(lambda: defaultdict(list))

    for row in rows:
        source_type = row.get("source_type", "")
        resolved_date = row["_resolved_date"]
        if source_type == "dm":
            dm_groups[resolved_date].append(row)
        else:
            video_id = row.get("video_id", "") or "unknown_video"
            video_groups[video_id][resolved_date].append(row)

    lines: list[str] = []
    lines.append(title)
    lines.append(f"window={cutoff.isoformat()}..{today.isoformat()}")
    lines.append(f"rows={len(rows)}")
    if dropped_counts:
        lines.append(f"dropped_rows={sum(dropped_counts.values())}")
    lines.append("")
    lines.append("CATEGORY MAP")
    for label in ordered_categories:
        lines.append(f"{category_codes[label]}={label}|count={category_counts[label]}")
    if dropped_counts:
        lines.append("")
        lines.append("DROPPED CATEGORY COUNTS")
        for label, count in dropped_counts.most_common():
            lines.append(f"{label}|count={count}")

    lines.append("")
    lines.append("FORMAT")
    lines.append("code|||feedback")

    if dm_groups:
        lines.append("")
        lines.append("DMS")
        for day in sorted(dm_groups):
            lines.append(f"DATE {day}")
            for row in dm_groups[day]:
                code = category_codes[row.get("category_line", "") or "other|unclear"]
                lines.append(f"{code}|||{row['_resolved_text']}")

    if video_groups:
        lines.append("")
        lines.append("VIDEOS")
        for video_id in sorted(video_groups):
            lines.append(f"VIDEO {video_id}")
            for day in sorted(video_groups[video_id]):
                lines.append(f"DATE {day}")
                for row in video_groups[video_id][day]:
                    code = category_codes[row.get("category_line", "") or "other|unclear"]
                    lines.append(f"{code}|||{row['_resolved_text']}")

    output_file.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {output_file} with {len(rows)} rows across {len(category_codes)} category codes.")


def is_roadmap_row(row: dict[str, str]) -> bool:
    label = row.get("category_line", "") or "other|unclear"
    if label in ROADMAP_DROP_EXACT:
        return False
    return label.startswith(ROADMAP_KEEP_PREFIXES)


def main() -> None:
    recent_rows, cutoff, today = recent_feedback_rows()
    CHATGPT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    write_pack(
        recent_rows,
        FULL_OUTPUT_FILE,
        cutoff,
        today,
        "CHATGPT FEEDBACK PACK",
    )

    roadmap_rows = [row for row in recent_rows if is_roadmap_row(row)]
    dropped_counts = Counter(
        (row.get("category_line", "") or "other|unclear")
        for row in recent_rows
        if not is_roadmap_row(row)
    )
    write_pack(
        roadmap_rows,
        ROADMAP_OUTPUT_FILE,
        cutoff,
        today,
        "CHATGPT ROADMAP FEEDBACK PACK",
        dropped_counts=dropped_counts,
    )


if __name__ == "__main__":
    main()
