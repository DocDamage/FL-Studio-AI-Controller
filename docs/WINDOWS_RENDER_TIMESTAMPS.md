# Windows export timestamp correction

Development continuation on September 19, 2026, based on commit
`1d8db25cc492af1bf0d2d914b45d912b5d791f78` of `dev/v0.5-render-workflow`.
The existing Audio lab workflow, tests, and separate saved-render branch are preserved.

## Observed failure and correction

Windows Actions run `35461464006`, job `105945975449`, rejected both actual
FLOAT and PCM_24 WAV exports in the native-codec preflight. File size, modification
time, device and inode agreed, but pathname and descriptor `st_ctime_ns` differed.
The export was not shown to be corrupt; the identity comparison used inconsistent
timestamp semantics.

`FileStamp.read` now uses explicit `st_birthtime_ns` on Windows where available,
falling back to the older creation-time `st_ctime_ns` on Python 3.11. POSIX retains
metadata-change `st_ctime_ns`, including systems that also expose birth time.
The legacy internal `ctime_ns` field holds this platform-normalized timestamp.

Size, modification time, file identity, link checks, second-pass source hashing,
late folder verification and staged publication remain enforced. No timestamp
tolerance, assertion deletion, native-codec test bypass or automatic FL command
was introduced.

Python reference: https://docs.python.org/3.13/library/os.html#os.stat_result

## Executed local validation

- 447 tests passed with warnings treated as errors.
- 12 focused timestamp/metadata/native-codec cases passed, including eight new
  timestamp regressions. The existing native-codec preflight assertions are unchanged.
- Actual companion, diagnostics, MCP and synthetic WAV intake/review subprocess
  checks passed. Simulator diagnostics still report not qualified for live FL.

Evidence: `evidence/windows_timestamp_tests.txt` and
`evidence/windows_timestamp_runtime.json`.

These local results are Linux results, including emulated Windows timestamp cases.
Final native Windows/Linux Actions results belong to their exact commit checks
in PR #3. Neither the local suite nor Actions constitutes live FL Studio acceptance.
