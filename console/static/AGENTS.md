# SwarmBalance browser workbench — TaskUI v1.0.0 scope

These instructions apply to `console/static/` only. Read `../../TaskUI/AGENTS.md`, `../../TaskUI/core/`, and `../../TaskUI/adapters/web.md` before planning UI changes. Evaluate the upstream `monitoring-analysis` and `object-management` patterns based on task demands; do not treat either pattern as a mandatory page layout.

This project uses one browser workbench `index.html` (Vue 3 global build with embedded styles/logic, Canvas 2D, Three.js and ECharts) and `spec.html`. Navigation is represented by `showMap`, `tab`, and `view` rather than Vue Router; browser calls use inline `api()`/`fetch`, and state is inside the Vue instance. No Vite, Pinia or standalone Vue components are present in the audited baseline. API endpoints reside in `console/server.py`; `frontend/` is predominantly the Python simulation core, *not* browser UI source.

For design tasks: G0 identify role, task, manipulated object, frequency, risk and successful outcome. G1 map the existing five navigation areas, global run toolbar, 2D/3D workbench, inspector, dialogs/forms, experiment actions and backend provenance to task paths. Keep task entry points near the user's object/context, and record placement decisions and failure/recovery/confirmation handling. Use `../../TaskUI/tools/taskui_check.py` on a genuine approved project manifest with traceable G0/G1 evidence—never pass upstream example data off as application coverage.

G2 can modify the actual UI only in a separately approved change. Preserve the three distinct data sources: live `SimSession` snapshot, persistent scene/config/checkpoints with their distinct lifecycles, and historical CSV comparison with comparability gates. Do not alter frozen simulation baselines, scheduling, energy accounting, lifecycle semantics or server API contracts under UI rule integration.

G3 requires actual browser task walk-through, focus/keyboard checks, failure and loading feedback, and layout at target viewports. A green manifest validator alone cannot claim G3 success. UI-01 itself must not change `index.html`, `spec.html`, `console/server.py`, `frontend/` or algorithms.
