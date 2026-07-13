from __future__ import annotations

from feedback_pipeline import MASTER_FEEDBACK_CSV, build_master_rows, write_csv


def main() -> None:
    rows = build_master_rows()
    write_csv(MASTER_FEEDBACK_CSV, rows)
    print(f"Wrote {MASTER_FEEDBACK_CSV} with {len(rows)} feedback rows.")


if __name__ == "__main__":
    main()
