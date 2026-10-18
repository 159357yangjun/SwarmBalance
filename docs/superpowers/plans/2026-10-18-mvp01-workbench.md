# MVP-01 Workbench Implementation Plan

**Goal:** Build a usable four-workspace client for the real persisted MVP API.

**Architecture:** Native HTML/CSS/JS served by explicit allowlisted routes. The editor clones complete saved configurations and mutates only visible fields. Request epochs isolate project/run changes; polling reads persisted status, results read only completed run snapshots.

**Tech Stack:** Existing FastAPI, native browser APIs, Python unittest, Node editor checks. No added runtime dependency.

- [x] Write and run failing editor and actual HTTP route tests in `console/test_mvp_workbench.py`.
- [x] Implement immutable config editor and request epochs in `console/static/workbench-core.js`.
- [x] Add four semantic workspaces in `workbench.html`, industrial responsive styling in `workbench.css`, API/state orchestration in `workbench.js`.
- [x] Add only `/workbench` and allowlisted `/workbench/assets/{name}` routes to `console/server.py`.
- [x] Run workbench checks and existing backend regression suite. Record actual commands/output in `docs/mvp01-workbench.md`.
- [x] Commit bounded changes for independent browser acceptance and main-controller PR creation.

Acceptance is the actual saved-project → real run → persisted result flow, followed by independent AI-R browser operation. Automated checks here do not claim overall MVP acceptance.
