adsb-eval
ADS-B reception evaluation using append-only JSONL logs

Most ADS-B reception tuning today is evaluated using instantaneous
snapshot metrics provided by decoders such as readsb.

These metrics are easy to observe but difficult to trust.
They fluctuate with transient conditions and cannot be reproduced,
making objective comparison across antennas, gain settings,
or decoder parameters inherently unreliable.

As a result, many tuning decisions are still made based on intuition,
isolated observations, or anecdotal reports.

adsb-eval was created to replace this approach by treating ADS-B reception
as a time-accumulated statistical problem rather than a momentary one.

It enables reception quality to be evaluated using long-term,
distribution-based evidence instead of single-point measurements.
-------------------------------------------------------------------------------

Problem

The stats.json output from readsb represents only the current state
of the receiver at a single moment in time.

While useful for monitoring, snapshot-based metrics cannot reliably
answer questions such as:

  ・Did changing the antenna actually improve reception?
  ・Is a higher gain setting truly better, or just noisier?
  ・How does reception quality change across time and configurations?

Without historical data, tuning decisions lack reproducibility
and are difficult to justify objectively.

-------------------------------------------------------------------------------

Approach

ADS-B reception metrics are logged as append-only JSONL files.

This design enables:

  ・Long-term persistence of reception data
  ・Safe operation under power loss or unexpected termination
  ・Post-hoc statistical analysis and comparison
  ・Deterministic replay using fixed input data
The focus of this project is decision-making metrics, not visualization.

Key characteristics:

  ・No web trigger dependency
  ・Cron / systemd friendly execution
  ・Append-only logging with tail repair
  ・Public-safe output (location masking supported)

-------------------------------------------------------------------------------

Metrics

Reception quality is evaluated using distribution-based statistics.

Typical metrics include:

  ・avg
    Average reception distance
  ・p50 / p90 / p95
    Percentile-based distance metrics indicating long-range performance
  ・max
    Maximum observed distance
  ・n_used
    Sample count used for distance evaluation
    Serves as a confidence indicator
  ・n_total
    Total number of aircraft observed
  ・n_with_pos
    Number of aircraft with valid position data
  ・pos_rate
    Position decode success rate

These metrics allow tuning decisions to be made
with awareness of variance and statistical reliability.

-------------------------------------------------------------------------------
Practical result

This methodology was applied during a transition
from an omnidirectional antenna to a high-gain collinear antenna.

Initial intuition suggested lowering gain
due to increased antenna directivity.

However, analysis of accumulated distance distributions revealed:

  ・Reduced sensitivity directly overhead
  ・Significantly improved horizontal coverage
  ・Better overall reception balance at higher gain settings

By tuning based on statistical distributions rather than snapshots,
the daily aircraft capture count increased by more than 200 percent.

This result demonstrates the importance of data-driven evaluation.

-------------------------------------------------------------------------------

Generated outputs

Primary outputs include:
  ・dist_1m.jsonl
    Distance distribution per evaluation interval

 ・dist_pos_health_1m.jsonl
    Position decode health derived from distance logs

  ・summary.json
    Latest metrics and rolling aggregates

Optional outputs (if enabled):
  ・adsb_perf_dist.jsonl
  ・adsb_perf_stats.jsonl
    Performance metrics derived from tar1090

All JSONL files are append-only and immutable once written.

-------------------------------------------------------------------------------

Execution model

Scripts are designed for periodic execution
using cron or systemd timers.

Typical execution pattern:

  ・adsb_dist_logger.py
  ・dist_pos_health_logger.py
  ・make_summary.py

Each script is intended to be executed independently
and may fail without affecting others.

No script performs automatic tuning or feedback control.

-------------------------------------------------------------------------------

Design principles

  ・Data-driven tuning over intuition
  ・Append-only logs for reliability and auditability
  ・Predictable failure behavior
  ・Explicit statistical confidence awareness
  ・Human-in-the-loop decision making

This project intentionally avoids coupling
to specific databases, dashboards, or visualization tools.

JSONL outputs may be consumed by external systems if desired.

-------------------------------------------------------------------------------

Configuration philosophy

All configuration is provided explicitly via environment variables.

There are:

  ・No config files
  ・No YAML
  ・No hidden defaults

This design is intentional.

It ensures that every evaluation run is reproducible,
auditable, and comparable without relying on implicit state
or undocumented configuration layers.

Repository layout

src/
Executable scripts and shared library code.

tests/fixtures/
Deterministic input JSON files used for testing and replay.
Tracked by git.

data/
Runtime-generated artifacts only.
Ignored by git.

This separation keeps the repository clean
while allowing evaluation data to grow without constraint.

-------------------------------------------------------------------------------

Data lifecycle

  ・JSONL logs are append-only and never modified in place
  ・Incomplete or low-sample records are preserved
  ・Summary outputs are derived views and may be regenerated at any time

Data is retained even when evaluation confidence is low,
allowing post-hoc filtering and re-evaluation.

-------------------------------------------------------------------------------

Quality semantics

Each evaluation record contains a quality section.

eval_ok = true
The record satisfies minimum statistical requirements
and may be used for comparative evaluation.

eval_ok = false
The record is structurally valid but should not be used
for evaluative conclusions.

Typical reasons include:

  ・insufficient_samples (n_used below threshold)
  ・incomplete position data
  ・transient startup conditions

Non-evaluable records are preserved intentionally
to maintain continuity and observability.

-------------------------------------------------------------------------------

Intended usage pattern

This project is expected to be used as follows:

  ・Run continuously with a fixed configuration
  ・Accumulate data for multiple days or weeks
  ・Change exactly one parameter (antenna, gain, decoder option)
  ・Continue logging under the new configuration
  ・Compare distributions across periods

Multiple simultaneous changes will invalidate comparison.

-------------------------------------------------------------------------------

Non-goals

This project intentionally does not provide:

  ・Automatic parameter optimization
  ・Real-time control loops
  ・Visualization or dashboards
  ・Single-aircraft or packet-level judgments

The goal is evaluation, not automation.

-------------------------------------------------------------------------------

License

MIT