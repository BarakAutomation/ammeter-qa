# Design Decisions

## Fixes to the supplied code

Fixes 1-5 and 8 are marked in the code with a one-line `# Fix #N` comment; 6 and 7 are whole-file rewrites.

| # | What was broken | Fix | File |
|---|---|---|---|
| 1 | Requests sent only a command prefix; an emulator answers only its exact command, so it closed silently ("No data received."). | Send each emulator's full command. | `main.py` |
| 2 | README and config said ports 5000-5002; `main.py` uses 5001-5003. | Config and README follow the running code. | `config/config.yaml`, `README.md` |
| 3 | README gave the CIRCUTOR command without `-current`. | Aligned to the emulator. | `config/config.yaml`, `README.md` |
| 4 | A quick restart failed with `Address already in use` (errno 98 Linux, 48 macOS) while the port was in TIME_WAIT. | `SO_REUSEADDR` before `bind()`; skipped on Windows, where it lets another process take the port. | `Ammeters/base_ammeter.py` |
| 5 | The logger attached no handler, so nothing was logged. | File and console handlers, a fresh file per run. | `src/utils/logger.py` |
| 6 | `run_test()` was `pass` and used `Dict` without importing it. | Implemented the framework. | `src/testing/test_framework.py` |
| 7 | The example called `run_test()` without `ammeter_type`. | Rewritten as an end-to-end run. | `examples/run_tests.py` |
| 8 | `python examples/run_tests.py` failed: `No module named 'src'`. | Add the project root to the import path. | `examples/run_tests.py` |

Fix #4 is the only change to the emulator code. `config.yaml` (shipped with `NULL` values) was also filled in, and the README rewritten to match the code.

## Design decisions

- **One client for every ammeter.** `AmmeterClient` is the unified API; devices differ only by config (port, command), so a new device is one config entry.
- **Replies are read until the server closes.** One `recv()` can return part of a TCP reply; the emulator closes after sending, so the close marks the end.
- **Timing is measured, not assumed.** Sample *k* is due at `start + k/f` on the monotonic clock, so nothing drifts; each run reports lateness, jitter, achieved frequency and overruns.
- **Any two of count, duration and frequency.** The third is derived; an invalid config fails fast with a `ConfigError` naming the key.
- **A failed sample does not fail the run.** Timeouts and retries per attempt; a failed sample is recorded with its error. A run is `failed` only if every sample fails, and it is still archived.
- **Statistics from the standard library.** Mean, median, sample stdev, min and max via `statistics`. With one value the stdev is undefined, so it is reported as `null`, not 0.
- **One JSON file per run.** Unique id (UTC timestamp + short uuid), times, resolved config, report and raw samples. `ResultsStore` lists, loads and compares runs; no database needed.
- **Configuration-driven.** Every setting lives in `config/config.yaml`.
- **Readiness check, not a fixed sleep.** `main.py` and the tests wait until each emulator port accepts connections (`wait_for_port`, 5 s timeout) instead of sleeping a guessed time.

## Bonus features

**Visualization.** A time-series plot per run and a log-scale boxplot across devices, whose ranges differ by orders of magnitude.

**Error simulation.** Client-side fault injection (wrong command, refused connection, dropped reply) with a configured probability.

**Accuracy assessment: what it does and does not claim.** Each emulator generates its own random inputs, so there is no shared reference current and no way to rank devices by accuracy. Instead, each device's measured mean is compared with the expected mean of its own formula (Greenlee ≈ 0.380 A, ENTES 68.75 A, CIRCUTOR ≈ 0.030 A). It is descriptive only, with no ranking, because the distributions are skewed and the samples small.

**Performance consistency.** Covered by the timing report and the per-sample durations in the archive.

## Tests

11 focused tests with the standard-library `unittest` (they also run under `pytest`), one or more per requirement: the real emulators answer their commands and reject a wrong one; the client handles a timeout, a refused connection and retries; the sampler keeps its schedule and records a failed sample without stopping; the statistics on known values; archive save, load and compare; and a new device added with config only. Fake TCP servers and a fake clock keep them fast and deterministic.

## Libraries installed

- `pyyaml`: configuration.
- `matplotlib`: plots (it installs `numpy` as a dependency).

scipy, seaborn and pandas from the supplied `requirements.txt` are not used and were removed. `pytest` is optional.

## Requirement to code

| Requirement | Where |
|---|---|
| Unified API, consistent reporting | `src/client/ammeter_client.py`, `AmmeterTestFramework.run_test` |
| Count, duration, frequency, precise timing | `src/testing/sampler.py` |
| Mean, median, stdev, min, max | `src/testing/stats.py` |
| Unique id, metadata, retrieval, comparison | `src/testing/results_store.py` |
| Visualization, accuracy assessment | `src/testing/visualization.py`, `src/testing/accuracy.py` |
| Error simulation, configuration-driven | `config/config.yaml`, `AmmeterClient` |

## Limitations

- One device is sampled at a time; parallel sampling (one thread per device) is the next step.
- The reply read is capped at 4096 bytes; larger payloads would need length-prefixed messages.
- The supplied emulators reseed the global random generator per instance; left unchanged, as the infrastructure was to be reused.
- Tested on macOS with Python 3.9 and 3.13. Only standard, cross-platform APIs are used, but it has not been run on Linux or Windows.
