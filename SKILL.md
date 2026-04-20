---
name: examtopics-pipeline
description: "ExamTopics extraction pipeline skill — use whenever the user mentions ExamTopics topics, discussion links, exam code counts, topic statistics, fetching discussion HTML, or getting questions for a specific topic and exam code. This skill should trigger for requests that need `fetch_discussion_pages.py`, `fetch_question_response_bodies.py`, or `extract_question_answers.py`, even if the user does not name those scripts."
version: "1.0"
author: "GitHub Copilot"
---

# ExamTopics Pipeline

Use this skill for ExamTopics scraping and extraction workflows. Prefer this skill whenever the user asks for topic-wide statistics, discussion links, question extraction, or a full pipeline run for a specific exam code.

## 0. Skill Folder Structure

This skill bundles the executable helpers under `scripts/`:
Use these bundled scripts from the skill directory:

```text
examtopics-pipeline/
├── SKILL.md                          This file
└── scripts/
    ├── fetch_discussion_pages.py        Script to fetch discussion page links for a topic.
    ├── fetch_question_response_bodies.py Script to fetch HTML bodies for a specific exam code.
    └── extract_question_answers.py       Script to extract question-answer pairs from saved HTML bodies, with support for image placeholders.
```

Keep new helper code in `scripts/` so the skill remains self-contained and portable.

## 1. Decide the mode first

1. **Topic statistics mode** — when the user asks how many exam codes exist in a topic, or wants a topic-wide summary.
2. **Exam extraction mode** — when the user asks for questions from a specific topic and exam code.

The guiding rule is:
- If the request is **topic-wide statistics**, start from `fetch_discussion_pages.py`.
- If the request is **questions for a specific exam code**, run the full pipeline:
  `fetch_discussion_pages.py` → `fetch_question_response_bodies.py` → `extract_question_answers.py`.

---

## 2. Output Formats

Known output conventions:
- `fetch_discussion_pages.py` writes a CSV with a single `link` column.
- `fetch_question_response_bodies.py` saves HTML into `<output>/<exam_code>/question-response-bodies/` and writes an `index.csv`.
- `extract_question_answers.py` accepts `*.body`, `*.html`, and `*.txt` files and can output CSV + JSON.

Use these outputs as the canonical artifacts:
- topic statistics: `discussion_links.csv` plus a per-exam-code count summary
- exam extraction: `question-response-bodies/`, `*_questions.csv`, and `*_questions_detailed.json`
**Save location:** A per-topic folder under the current working directory, named after the topic, for example `./<topic>/scan_<YYYYMMDD-HHMMSS-ffffff>/`. Create it if it does not already exist.

## 3. Output Logic

Use a stable output contract so responses are predictable and easy to scan.

### 3.1 Decision rule

- If the user asks for counts, coverage, or topic inventory, answer in statistics mode.
- If the user asks for questions, answers, or a specific exam code, answer in extraction mode.
- If the request mixes both, lead with the extraction result and append the statistics summary only if it clarifies scope.

### 3.2 Statistics output shape

Keep the response order as:
1. Direct answer first: unique exam-code count.
2. Scope line: topic name and total discussion links collected.
3. Breakdown: top exam codes by link count.
4. Artifacts: CSV path and any summary file.
5. Limits: pagination gaps, detection uncertainty, or partial coverage.

Recommended fields:
- `topic`
- `mode: statistics`
- `total_links`
- `unique_exam_codes`
- `top_exam_codes`
- `artifact_paths`
- `notes`

### 3.3 Extraction output shape

Keep the response order as:
1. Direct answer first: whether matching content was found.
2. Scope line: topic name, exam code, and match count.
3. Artifacts: HTML directory, CSV path, JSON path.
4. Sample size or record count if available.
5. Limits: any fetch or parsing issues.

Recommended fields:
- `topic`
- `exam_code`
- `mode: extraction`
- `matched_links`
- `html_dir`
- `csv_path`
- `json_path`
- `record_count`
- `notes`

### 3.4 Naming rules

- Create a topic folder in the working directory before writing any outputs.
- Create a timestamped scan folder inside the topic folder before writing any outputs, using `scan_<YYYYMMDD-HHMMSS-ffffff>`.
- Use `discussion_links.csv` for collected topic links.
- Use `<exam_code>_questions.csv` for the extracted summary table.
- Use `<exam_code>_questions_detailed.json` for the detailed structured output.
- Keep all outputs for the same topic inside `./<topic>/scan_<YYYYMMDD-HHMMSS-ffffff>/`.

---

## 4. Decision Rules

### A. User asks: “topic này có bao nhiêu exam code?”

Interpret this as a topic statistics task.

Recommended flow:

1. Run `fetch_discussion_pages.py` for the topic to collect all discussion links.
2. Derive exam code counts from the link set.
3. Report:
   - total unique links
   - total unique exam codes
   - top exam codes by link count
   - optionally the raw CSV path

Use a lightweight analysis step after link collection. Extract exam codes from the link pattern `-exam-<CODE>-topic-`, normalize to uppercase, and group by exam code before reporting totals.

If the user only wants statistics, do **not** fetch HTML bodies unless explicitly requested.

### B. User asks: “lấy câu hỏi trong topic A, exam code B”

Interpret this as an exam extraction task.

Recommended flow:

1. Run `fetch_discussion_pages.py` for the topic to collect links.
2. Run `fetch_question_response_bodies.py` to filter those links by the requested exam code and download HTML.
3. Run `extract_question_answers.py` on the downloaded HTML directory.
4. Return the CSV/JSON output locations and, if useful, a brief sample count.

---

## 5. Standard Workflows

### 5.1 Topic statistics workflow

Use this when the user wants counts, coverage, or exam-code inventory for a topic.

```bash
python3 scripts/fetch_discussion_pages.py <topic> \
  -o ./<topic>/scan_<timestamp>/discussion_links.csv \
  --batch-size 5 \
  --batch-delay 2 \
  --sleep 0.2 \
  --max-pages 800
```

Example only. This command writes to `./<topic>/scan_<timestamp>/discussion_links.csv`.

Then summarize the links by exam code.

Suggested reporting fields:
- topic name
- number of discussion links
- number of unique exam codes
- top N exam codes by link count
- any notable gaps or pagination issues
If the user asks only for a count, return the unique exam-code count first and keep the rest brief.

### 5.2 Exam extraction workflow

Use this when the user wants actual questions for one exam code.

```bash
python3 ~/.claude/skills/examtopics-pipeline/scripts/fetch_discussion_pages.py <topic> \
  -o ./<topic>/scan_<timestamp>/discussion_links.csv \
  --batch-size 5 \
  --batch-delay 2 \
  --sleep 0.2 \
  --max-pages 800

python3 ~/.claude/skills/examtopics-pipeline/scripts/fetch_question_response_bodies.py ./<topic>/scan_<timestamp>/discussion_links.csv <exam_code> \
  -o ./<topic>/scan_<timestamp>/<exam_code> \
  --limit 2000 \
  --sleep 0.5

python3 ~/.claude/skills/examtopics-pipeline/scripts/extract_question_answers.py ./<topic>/scan_<timestamp>/<exam_code>/question-response-bodies \
  -o ./<topic>/scan_<timestamp>/<exam_code>_questions.csv \
  -j
```

## 6. Exam Code Statistics Rules

When counting exam codes from discussion links:

- Extract the exam code from the discussion URL, not from page titles.
- Treat the exam code as case-insensitive, but normalize output to uppercase.
- Count unique exam codes and also count total links per exam code.
- If the user asks “how many exam codes are in this topic?”, report the unique exam-code count.
- If the user asks “how many questions / links for each exam code?”, report the per-code distribution.

Suggested regex pattern for the link format:

```text
-exam-([a-z0-9-]+)-topic-
```

Normalize captured values to uppercase before grouping.

---

## 7. Fetcher Behavior Notes

### `fetch_discussion_pages.py`

Use this script to gather topic-wide discussion links.

Important flags:
- `--start` / `--end` for page ranges
- `--max-pages` for safety limiting
- `--batch-size` for consecutive page requests before a pause
- `--batch-delay` for pause between batches
- `--sleep` for delay between individual requests
- `--retry-count` for the maximum number of retry attempts on transient network errors
- `--retry-delay` for the base backoff delay between retry attempts
- `--limit` for limiting total collected links

Preferred usage for large topics:
- Keep `--sleep` small but non-zero.
- Use `--batch-size` greater than 1 when you want to reduce pause frequency.
- Use `--batch-delay` to avoid hammering the site.

### `fetch_question_response_bodies.py`

Use this script to fetch individual discussion pages for a specific exam code.

Expected output layout:

```text
<output>/<exam_code>/question-response-bodies/*.html
<output>/<exam_code>/index.csv
```

### `extract_question_answers.py`

Use this script to parse the saved HTML files.

Important notes:
- It accepts `.html`, `.body`.
- It can emit a CSV summary and a detailed JSON file.
- It already handles image placeholders and richer question text.

---

## 8. Response Style

When answering the user:

- Give the final number first when they ask for statistics.
- For topic statistics, include the topic, the unique exam-code count, and the link count.
- For exam extraction, include the output files and the next command if more processing is needed.
- Avoid overexplaining unless the user asks for the pipeline details.
- If detection or pagination looks suspicious, mention the limitation briefly and continue with the safest working path.
- If the user asks for a direct answer like “bao nhiêu exam code”, do not narrate the pipeline unless they ask for it.

---

## 9. Examples of Proper Interpretation

### Example 1
User: “topic <topic> có bao nhiêu exam code?”

Example only.

Interpret as:
- fetch topic links
- count unique exam codes
- report topic summary

### Example 2
User: “thu thập câu hỏi trong topic <topic>, exam code <exam_code>”

Example only.

Interpret as:
- fetch topic links
- filter by <exam_code>
- download HTML bodies
- extract questions and answers
- return CSV/JSON paths

---

## 10. Safety and Reliability

- Use conservative request delays.
- Do not assume pagination detection is perfect.
- Prefer explicit limits during testing.
- If the topic listing does not expose all pages cleanly, continue with the available pages and mention the limitation.
- Do not download images unless the user explicitly wants that feature.

---

## 11. Minimal Deliverables

For topic statistics, the deliverable is usually:
- `discussion_links.csv`
- a short count summary

For exam extraction, the deliverable is usually:
- `question-response-bodies/`
- `*_questions.csv`
- `*_questions_detailed.json`

---

## 12. Workspace Assumptions

This skill assumes the repository has the `scripts/` directory structure described in the current workspace and that the scripts are present there.

If the user asks for a variant workflow, prefer adapting these scripts rather than inventing a new pipeline.
