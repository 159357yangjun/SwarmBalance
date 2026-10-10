# P2.1 Low-battery physics audit

Scope: characterise real Drone.update and Environment.step; no production change, no dispatch policy changes and no PR merges.

Three cases: exact-energy reaching a waypoint (control), insufficient power for an active leg followed by a second leg, and explicit out-of-service frozen state (control). Log markers [P2_1_PHYSICAL_GAP] describe violations of **desired physical feasibility**, even when the characterization test exits 0. Thus green CI means **observations gathered and bookkeeping validated**, not that safety/flight feasibility is established.

Desired future flight policy: never advance an impossible leg while merely recording a positive energy shortfall. This is deliberately **not** asserted as a passing control in this diagnostic stage. A later approved P2.2 should pin down reject, land, charging and requeue semantics with failing requirement tests before modifying the executor.

Instrument: real drone/environment methods loaded by the existing test_preflight path; simulator shell excludes map/dispatch to isolate physics. Wh/m configuration set to 0.06, one-second leg of 20m requires 1.2 Wh; initial battery only 0.2 Wh. No default configuration mutation. Results cannot be treated as real-drone feasibility evidence.
