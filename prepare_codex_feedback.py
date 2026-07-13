from __future__ import annotations

from feedback_pipeline import (
    MASTER_FEEDBACK_CSV,
    PENDING_CODEX_INPUT_TXT,
    PENDING_FEEDBACK_CSV,
    MASTER_WITH_CATEGORIES_CSV,
    attach_existing_categories,
    build_master_rows,
    uncategorized_rows,
    write_csv,
    write_pending_codex_input,
)


def main() -> None:
    master_rows = build_master_rows()
    pending_rows = uncategorized_rows(master_rows)

    write_csv(MASTER_FEEDBACK_CSV, master_rows)
    write_csv(PENDING_FEEDBACK_CSV, pending_rows)
    write_pending_codex_input(pending_rows)
    write_csv(MASTER_WITH_CATEGORIES_CSV, attach_existing_categories(master_rows))

    print(f"Wrote {MASTER_FEEDBACK_CSV} with {len(master_rows)} rows.")
    print(f"Wrote {PENDING_FEEDBACK_CSV} with {len(pending_rows)} uncategorized rows.")
    print(f"Wrote {PENDING_CODEX_INPUT_TXT}.")
    print(f"Wrote {MASTER_WITH_CATEGORIES_CSV}.")


if __name__ == "__main__":
    main()
