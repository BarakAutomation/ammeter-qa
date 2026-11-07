# Ammeter Emulators - QA Testing Framework

Testing framework for current measurement systems over three ammeter
emulators (Greenlee, ENTES, CIRCUTOR). Each emulator is a small TCP server;
the framework is a unified client that samples measurements on a precise
schedule, analyses them statistically, and archives every run.

See `DESIGN_DECISIONS.md` for the issues found in the supplied code, how
each was fixed, and the reasoning behind the design.

## Project Structure

- `DESIGN_DECISIONS.md` - fixes to the supplied code, design decisions,
  libraries installed.
- `main.py` - starts the three emulators; `--serve` keeps them running.
- `Ammeters/` - supplied emulator infrastructure (base class, the three
  emulators, raw socket client). Only one change here (SO_REUSEADDR,
  see DESIGN_DECISIONS.md).
- `config/config.yaml` - sampling, client policy, error simulation,
  analysis and storage settings.
- `src/client/ammeter_client.py` - unified defensive client (timeouts,
  retries, EOF-framed reply reading, error simulation hook).
- `src/testing/` - the framework:
  - `test_framework.py` - orchestration entry point (`AmmeterTestFramework`)
  - `sampler.py` - scheduled sampling engine with measured-lateness reporting
  - `stats.py` - statistical analysis (standard library only)
  - `results_store.py` - JSON archive: unique run IDs, metadata, retrieval,
    comparison
  - `accuracy.py` - bonus: model-agreement assessment + its limitation
  - `visualization.py` - bonus: plots
- `src/utils/` - config loader, logger (fixed), random helper, `wait_for_port` readiness check.
- `examples/run_tests.py` - end-to-end example over all ammeters.
- `tests/` - automated test suite (11 tests; unit + integration against the
  real emulators).
- `results/` - archived runs (`runs/`), plots (`plots/`), logs (`logs/`) and captured
  console output (`sample_run_output.txt`) from a real run.

## Ammeters

Each emulator answers only its exact command; anything else closes the
connection without a reply.

| Ammeter | Port | Command | Measurement method |
|---|---|---|---|
| Greenlee | 5001 | `MEASURE_GREENLEE -get_measurement` | Ohm's law: I = V / R (V 1-10 V, R 0.1-100 Ω) |
| ENTES | 5002 | `MEASURE_ENTES -get_data` | Hall effect: I = B × K (B 0.01-0.1 T, K 500-2000) |
| CIRCUTOR | 5003 | `MEASURE_CIRCUTOR -get_measurement -current` | Rogowski coil: I = ∫V dt (V 0.1-1.0 V, dt 0.001-0.01 s) |

## Usage

Requires Python 3.9+ (tested with Python 3.9 and 3.13 on macOS). Install dependencies (minimal set):

```sh
pip install -r requirements.txt
```

1. Start the emulators and verify they answer (also prints one sample
   measurement from each):

```sh
python main.py            # demo: one measurement per ammeter, then exits
python main.py --serve    # keep emulators running for the framework
```

2. With `--serve` running in one terminal, run the full test cycle in
   another (from the project root):

```sh
python examples/run_tests.py                       # default config
python examples/run_tests.py --config my.yaml      # another config file
```

A device that fails on every sample is reported as `FAILED` and archived
with `status: failed`; the other devices still run and are compared.

3. Run the automated test suite (standard library only, no extra install;
   also runs under pytest if installed: `pip install pytest`):

```sh
python -m unittest discover -s tests
# or: pytest            (pytest.ini points it at tests/)
```

## Retrieving archived runs

```python
from src.testing.results_store import ResultsStore
store = ResultsStore("results/runs")
store.list_runs()                    # id, ammeter, start time, status
store.load_run("<run_id>")           # full record: config used, stats, raw samples
store.compare_runs(["<id1>", "<id2>"])  # side-by-side statistics
```

## Configuration

`config/config.yaml` controls:

- `testing.sampling` - `measurements_count`, `total_duration_seconds`,
  `sampling_frequency_hz`. Any two determine the third; if all three are
  set they must be consistent, otherwise the run fails fast with a clear
  configuration error. Timing convention: with n samples at frequency f,
  sample k is due at offset k/f (k = 0..n-1), so the samples occupy the
  window [0, n/f) and the last sample is due at (n-1)/f.
- `testing.timing.overrun_tolerance_ratio` - how late a sample may start
  (as a fraction of its slot) before it counts as an overrun.
- `testing.client` - connect/read timeouts, retries, backoff per attempt.
- `testing.error_simulation` - bonus fault injection (`wrong_command`,
  `connection_refused`, `drop_response`) to exercise error handling.
- `ammeters` - port and exact command per ammeter type.
- `analysis` - accuracy assessment and visualization on/off, plot types.
- `result_management` - where runs, plots and logs are stored (`results_dir`, `plots_dir`, `logs_dir`).

Not configurable: the emulators and
client talk on localhost, and the reply read is bounded at 4096 bytes.
