---
name: feedback-classifier
description: Classify ordered product feedback from output/pending_codex_input.txt into compact category|subcategory labels, preserve exact input order, and support the local prepare/merge workflow for Instagram comments and DMs. Use when the task is to triage feedback, write output/codex_labels.txt, or operate the feedback classification pipeline without adding prose.
---

# Feedback Classifier

Use this skill when the repository contains feedback prepared for low-token classification and the job is to label each feedback item in order.

## Goal

Convert each line in `output/pending_codex_input.txt` into exactly one line in `output/codex_labels.txt` using this format:

```text
category|subcategory
```

The output line count must exactly match the input line count. Preserve order exactly.

## Workflow

1. Run `python prepare_codex_feedback.py` to refresh the master dataset and pending batch.
2. Read `output/pending_codex_input.txt`.
3. Classify every line using the taxonomy in `references/taxonomy.md`.
4. Write only ordered labels to `output/codex_labels.txt`.
5. Run `python merge_codex_feedback.py` immediately after writing `output/codex_labels.txt`.
6. Run `python prepare_codex_feedback.py` again after the merge so `output/pending_feedback.csv` and `output/pending_codex_input.txt` reflect the new categorized state.
7. In the final response, confirm that the merge command was run, that `output/master_feedback_with_categories.csv` was updated, and that the post-merge prepare step left `output/pending_feedback.csv` with the expected remaining count.

## Output Rules

- Write one label per input line.
- Do not include numbering.
- Do not include explanations in `output/codex_labels.txt`.
- Use lowercase slugs only.
- If a line contains praise plus a clear request, bug, or confusion signal, classify by the stronger product signal.
- If uncertain, prefer `other|unclear` over inventing intent.
- Do not stop after writing labels; always complete the merge step in the same turn unless the user explicitly says not to.

## Decision Rules

- `feature_request`: The user wants a new capability, new content, or a product enhancement.
- `bug_report`: The user says something is broken, missing unexpectedly, not working, or behaving incorrectly.
- `confusion`: The user is unsure how to use, access, find, or understand something. Use this when the issue may be discoverability rather than a missing feature.
- `praise`: Positive sentiment without a concrete request or problem.
- `tester_interest`: The user wants access, an Android build, a beta link, or to help test.
- `growth_signal`: The user offers distribution help, influencer access, partnerships, promotion, or referrals.
- `non_product`: Social chatter, off-topic replies, jokes, or messages that do not provide meaningful product feedback.
- `other`: Product-relevant but not clearly covered above.

## Notes

- For comment rows, the input is already stripped down to the main comment text.
- For DM rows, the input may be longer and can include more direct feature language.
- The merge step depends on exact line order, so never reorder, skip, or combine lines.
- `python merge_codex_feedback.py` does not clear `output/pending_feedback.csv` by itself; that file is only refreshed by `python prepare_codex_feedback.py`.
- If `pending_feedback.csv` still shows old rows after labeling, treat it as stale until the post-merge prepare step has been run and verified.
- If the user wants summaries or prioritization, do that after writing `output/codex_labels.txt`, not inside it.

## Taxonomy

Read `references/taxonomy.md` before classifying if you need the allowed subcategories or examples.
