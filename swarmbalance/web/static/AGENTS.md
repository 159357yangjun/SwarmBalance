# Browser interface scope

These instructions apply to `swarmbalance/web/static/` only.

The application uses `index.html` (Vue 3 global build with embedded styles/logic, Canvas 2D, Three.js and ECharts), `spec.html`, and the separate GIS preview `map_lab.html` / `map_lab.js`. Browser dependencies are vendored in `vendor/`; preserve their original bytes and recorded hashes.

Navigation in the main console uses `showMap`, `tab`, and `view`, without Vue Router. Browser requests use inline `api()` / `fetch`; state lives in the Vue instance. There is no Vite build, Pinia store or standalone Vue component tree. API endpoints reside in `swarmbalance/web/routes/`. `swarmbalance/simulation/` contains the Python simulation kernel.

Preserve the distinct lifecycles of live SimSession snapshots, persistent scene/config files, in-memory checkpoints and historical comparison CSVs. UI-only changes must preserve scheduling, energy accounting, lifecycle semantics and server API contracts.

For interface changes, check actual browser task paths, loading/error feedback, keyboard/focus behavior and target viewport layouts. GIS preview packages are not validated simulation maps.

The historical TaskUI rule pack and its validation tools have been removed from this repository; they are not prerequisites for current maintenance.
