# Native manual-export acceptance — v0.5 development

This is the release gate for the manual FL export workflow. It is deliberately separate from simulator tests and Windows CI. A passing record requires an actual Windows + FL Studio live session on a disposable saved project copy.

The validator does **not** control FL, choose an export folder, press Render, or upgrade watched-file evidence into causal proof. It only validates a record of observations made during the native session.

## Native session

1. Copy `evidence/RENDER_ACCEPTANCE_TEMPLATE.json` to a writable evidence file; keep the template unchanged.
2. Start the app in **live** mode against a disposable saved FLP copy and record the exact Windows, FL Studio, Python and PostFader versions.
3. In **Audio lab → Catch your next FL export**, arm one user-selected local folder. Manually export one mix from FL with a new filename, capture it, analyze it, and run **Verify copy** in Bounce library.
4. Arm a new watch and manually export a second bounce using the same range and export settings. Verify that stored copy too, then send both inputs to Audio review and confirm technical A/B readiness.
5. Exercise refusal paths: overwrite a baseline audio name and create multiple new audio names. Both cases must refuse promotion rather than guess.
6. Exercise **Cancel watch**, global **Stop**, and an app restart. Restart must not silently re-arm the previous folder; every later capture requires new consent.
7. Record the two verified captures in `captures`. Copy only the pathless evidence fields: `asset`, `watch_id`, `sha256`, `bytes`, `copied_bytes_verified`, `render_triggered_by_app`, and `causal_provenance_verified`.

A pass requires at least two unique asset IDs from two separately armed watch IDs, current-byte verification for every stored copy, every required test marked `pass`, `app_mode: "live"`, and `saved_project_copy_confirmed: true`.

The two provenance flags must remain false. The present workflow did not trigger FL's render command, and watched-file appearance alone does not prove which exact FL action caused a file to appear.

## Validate and export a safe record

```powershell
.\.venv\Scripts\python.exe scripts\validate_render_acceptance.py `
  .\evidence\my-render-acceptance.json `
  --public-out .\evidence\my-render-acceptance-public.json
```

Exit 0 means the JSON satisfies the acceptance schema. It does not independently inspect FL Studio or listen to audio. Exit 2 means the record is incomplete or invalid.

The public formatter removes `project_label`, `export_folder`, `interface_and_driver`, and `private_notes`. Do not put local paths or secrets in the normal `notes` field. Optional screenshots or reports can be bound through `evidence_sha256`.

## Required observations

- `arm_watch_new_filename`: watch armed before the manual export and accepted one new name.
- `capture_first_export`: first manual export was promoted into the guarded asset store.
- `analyze_first_capture`: actual captured copy decoded and analyzed.
- `capture_second_export`: second separately armed export was captured.
- `same_range_review_ready`: both exports passed existing technical A/B readiness checks after explicit same-range/settings confirmation.
- `overwrite_refusal`: overwriting a baseline audio name was refused.
- `multiple_new_files_refusal`: more than one new audio filename was refused as ambiguous.
- `cancel_watch`: local cancellation stopped intake without authorizing unrelated work.
- `global_stop_watch`: global Stop cancelled intake and remained latched until reset.
- `restart_requires_rearm`: app restart did not restore folder authorization.
- `stored_copy_hash_recheck`: Bounce library verification rehashed the current stored copy.

Only after this native gate passes should controller-triggered rendering be investigated. Any future render mechanism must bind the live session, explicit range/settings, and output identity; blind key presses remain out of scope.
