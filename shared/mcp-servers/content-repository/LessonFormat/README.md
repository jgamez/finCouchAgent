# Lesson format documents (shared storage)

This folder holds **authoring references** for lesson flows (for example `MoneyLingoLessonTemplate-v1.pdf`).

- **Purpose:** One place in the monorepo so **project-1-vanilla** and **project-2-orchestrated** can share the same spec files. This is **not** part of the MCP stdio protocol; the content-repository server does not need to read these files for normal MCP operation.
- **Runtime behavior:** Lesson flows are implemented **in application code** from these specs (step order, UI hints, MCP usage). The app does **not** parse the PDF when a student starts a lesson; developers update code (e.g. `project-1-vanilla/agent/lesson_flows/moneylingo_*.py`) when the template changes.
- **MoneyLingo v1:** Keep `MoneyLingoLessonTemplate-v1.pdf` here as the human-readable source of truth while coding; the live flow uses `moneylingo_outline.py` + `moneylingo_prompts.py` + `moneylingo_v1.py`.
- **New versions:** Add a new PDF (e.g. `MoneyLingoLessonTemplate-v2.pdf`), implement a new flow module + registry entry + any UI labels.

Commit the PDF only if licensing allows; otherwise keep it local and document the expected filename here.
