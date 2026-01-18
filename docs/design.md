# Design background

## Problem

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

## Approach

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

## Metrics

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
## Practical result

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
## Non-goals

This project intentionally does not provide:

  ・Automatic parameter optimization
  ・Real-time control loops
  ・Visualization or dashboards
  ・Single-aircraft or packet-level judgments

The goal is evaluation, not automation.

-------------------------------------------------------------------------------

## Design principles

  ・Data-driven tuning over intuition
  ・Append-only logs for reliability and auditability
  ・Predictable failure behavior
  ・Explicit statistical confidence awareness
  ・Human-in-the-loop decision making

This project intentionally avoids coupling
to specific databases, dashboards, or visualization tools.

JSONL outputs may be consumed by external systems if desired.