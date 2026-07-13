from __future__ import annotations

from datetime import datetime

from feedback_pipeline import (
    CATEGORIZED_FEEDBACK_CSV,
    CODEX_LABELS_TXT,
    MASTER_WITH_CATEGORIES_CSV,
    PENDING_FEEDBACK_CSV,
    attach_existing_categories,
    build_master_rows,
    categorized_lookup,
    read_csv_rows,
    read_label_lines,
    write_csv,
)


def main() -> None:
    pending_rows = read_csv_rows(PENDING_FEEDBACK_CSV)
    if not pending_rows:
        raise SystemExit(f"No pending rows found in {PENDING_FEEDBACK_CSV}")

    if not CODEX_LABELS_TXT.exists():
        raise SystemExit(f"Missing labels file: {CODEX_LABELS_TXT}")

    label_lines = read_label_lines(CODEX_LABELS_TXT)
    if len(label_lines) != len(pending_rows):
        raise SystemExit(
            f"Label count mismatch: {len(label_lines)} labels for {len(pending_rows)} pending rows."
        )

    existing = categorized_lookup()
    categorized_rows = list(existing.values())
    categorized_at = datetime.now().isoformat(timespec="seconds")

    for row, label_line in zip(pending_rows, label_lines):
        category_line = label_line.strip()
        if "|" in category_line:
            category, subcategory = [part.strip() for part in category_line.split("|", 1)]
        else:
            category, subcategory = category_line, ""

        merged = dict(row)
        merged["category_line"] = category_line
        merged["category"] = category
        merged["subcategory"] = subcategory
        merged["categorized_at"] = categorized_at
        existing[merged["lookup_key"]] = merged

    categorized_rows = list(existing.values())
    categorized_rows.sort(
        key=lambda row: (
            row.get("source_type", ""),
            row.get("video_id", ""),
            row.get("thread_path", ""),
            row.get("item_timestamp", ""),
            row.get("actor_username", ""),
            row.get("full_text", ""),
        )
    )

    write_csv(CATEGORIZED_FEEDBACK_CSV, categorized_rows)
    write_csv(MASTER_WITH_CATEGORIES_CSV, attach_existing_categories(build_master_rows()))

    print(f"Wrote {CATEGORIZED_FEEDBACK_CSV} with {len(categorized_rows)} categorized rows.")
    print(f"Updated {MASTER_WITH_CATEGORIES_CSV}.")


if __name__ == "__main__":
    main()
