#adsb-eval
ADS-B reception evaluation using append-only JSONL logs

Most ADS-B reception tuning relies on instantaneous snapshot metrics
provided by decoders such as readsb.

While useful for monitoring, snapshot-based metrics are unstable
and unsuitable for objectively comparing changes such as:

・Antenna replacement
・Gain adjustment
・Decoder parameter tuning

As a result, many tuning decisions are made based on intuition
or isolated observations rather than reproducible evidence.

adsb-eval addresses this limitation by treating ADS-B reception
as a time-accumulated statistical problem.

Reception data is persisted as append-only JSONL logs
and evaluated using distribution-based metrics
(avg, p95, max) instead of momentary values.

The goal of this project is to support reproducible,
data-driven tuning decisions for ADS-B receivers.

This repository focuses on evaluation methodology and data integrity,
not visualization or automation.

For full design rationale, evaluation model,
and real-world application results,
see README.txt.