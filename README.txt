adsb-eval
=========

Data-driven evaluation of ADS-B reception tuning using append-only JSONL logs.

This project was created to solve a fundamental limitation of readsb and similar
ADS-B decoders: most available metrics are instantaneous snapshots.

Snapshot-based metrics make it difficult to objectively evaluate changes such as:
- Antenna replacement
- Gain adjustment
- Decoder parameter tuning

As a result, many tuning decisions are made based on intuition rather than evidence.

This repository provides a method to persist reception data over time and evaluate
ADS-B reception quality using statistical distributions instead of momentary values.

--------------------------------------------------------------------

Problem
-------

The stats.json output from readsb represents only the current state of the receiver.

While useful for monitoring, it cannot reliably answer questions like:
- Did changing the antenna actually improve reception?
- Is a higher gain setting truly better, or just noisier?
- How does reception quality change across time and configurations?

Without historical data, tuning decisions lack reproducibility.

--------------------------------------------------------------------

Approach
--------

ADS-B reception metrics are logged as append-only JSONL files.

This design enables:
- Long-term persistence of reception data
- Safe operation under power loss or unexpected termination
- Post-hoc statistical analysis and comparison

The focus of this project is decision-making metrics, not visualization.

Key characteristics:
- No web trigger dependency
- Cron / systemd friendly
- Append-only logging with tail repair
- Public-safe output (location masking supported)

--------------------------------------------------------------------

Metrics
-------

Reception quality is evaluated using distribution-based statistics:

- avg
  Average reception distance

- p50 / p90 / p95
  Percentile-based distance metrics for long-range performance

- max
  Maximum observed distance

- n_used
  Sample count, used as a confidence indicator

- n_total
  Total number of aircraft observed

- n_with_pos
  Aircraft with valid position data

- pos_rate
  Position decode success rate

These metrics allow tuning decisions with awareness of variance and reliability.

--------------------------------------------------------------------

Practical Result
----------------

This methodology was applied when switching from an omnidirectional antenna to a
high-gain collinear antenna.

Initial intuition suggested lowering gain due to increased antenna directivity.
However, analysis of JSONL-based distance distributions revealed:

- Reduced sensitivity directly overhead
- Significantly improved horizontal coverage
- Better overall reception balance at higher gain settings

By tuning based on statistical distributions rather than snapshots,
the aircraft capture count increased by more than 200 percent.

This result demonstrates the importance of data-driven evaluation.

--------------------------------------------------------------------

Generated Outputs
-----------------

- dist_1m.jsonl
  Distance distribution per interval

- dist_pos_health_1m.jsonl
  Position decode health derived from distance logs

- summary.json
  Latest metrics and rolling aggregates

- adsb_perf_dist.jsonl
- adsb_perf_stats.jsonl
  Optional performance logs derived from tar1090

--------------------------------------------------------------------

Execution Model
---------------

Designed for periodic execution using cron or systemd timers.

Typical execution pattern:

- adsb_dist_logger.py
- dist_pos_health_logger.py
- make_summary.py

Each script is intended to be executed periodically and independently.

--------------------------------------------------------------------

Design Principles
-----------------

- Data-driven tuning over intuition
- Append-only logs for reliability
- Predictable failure behavior
- Statistical confidence awareness
- Minimal assumptions about visualization or databases

This project intentionally avoids coupling to specific storage backends or dashboards.
JSONL outputs can be consumed by external tools if desired.

--------------------------------------------------------------------

Sample JSONL files may contain only a few records.
They are provided to illustrate output structure, not statistical significance.
For design rationale and architectural decisions, see docs/architecture.txt.

--------------------------------------------------------------------

License
-------

MIT
