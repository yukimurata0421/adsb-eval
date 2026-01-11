# adsb-eval

ADS-B reception evaluation using append-only JSONL logs.

This project focuses on statistical evaluation of ADS-B reception tuning.
Instead of relying on instantaneous snapshot metrics, it uses long-term
distribution-based statistics such as avg, p95, and max distance.

The goal is to support data-driven decisions when changing antennas,
gain settings, or decoder parameters.

For full details, design rationale, and evaluation methodology,
see README.txt.
