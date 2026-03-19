# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog, and this project follows Semantic Versioning.

## [2.0.10] - 2026-03-20

### Added
- Added `examples/systemd/adsb-eval-failure-notify@.service` for OnFailure notifications.
- Added `src/systemd_failure_notify.py` to send webhook notifications for failed systemd units with cooldown.

### Changed
- Updated systemd examples to be portable across environments (removed `/home/yuki/...` assumptions).
- Updated `examples/systemd/adsb-eval-dist.service` and `adsb-eval-summary.service` to use:
  - `StartLimitIntervalSec=0`
  - `OnFailure=adsb-eval-failure-notify@%n.service`
  - `ADSB_BASE_DIR` / `ADSB_LOG_DIR` / `ADSB_STATE_DIR` based execution
- Updated default base directory behavior in:
  - `src/adsb_jsonl_logger.py`
  - `src/readsb/readsb_dist_signal_stats_logger.py`
  - `src/decoder/airspy_adsb_decoder_metrics_logger.py`
  to infer from script location when `ADSB_BASE_DIR` is not set.
- Updated `examples/systemd/adsb-eval.env.example` with portable path placeholders and failure notify variables.

## [2.0.9] - 2026-01-18

### Docs
- Added design background document.

## [2.0.8] - 2026-01-18

### Docs
- Fixed directory structure rendering in README.

## [2.0.7] - 2026-01-18

### Docs
- Clarified directory structure and responsibilities.

## [2.0.6] - 2026-01-18

### Docs
- Clarified `fsutil` helpers are stdlib-only.

## [2.0.5] - 2026-01-18

### Docs
- Declared `requests` dependency.

## [2.0.4] - 2026-01-18

### Docs
- Declared `requests` dependency.

## [2.0.3] - 2026-01-18

### Docs
- Declared `requests` dependency.

## [2.0.2] - 2026-01-18

### Docs
- Added systemd examples and quickstart guidance.

## [2.0.1] - 2026-01-18

### Docs
- Added systemd examples and quickstart guidance.

## [2.0.0] - 2026-01-18

### Changed
- Prepared v2 documentation and evaluation model.

## [0.1.1] - 2026-01-11

### Docs
- Linked architecture document from README.

## [0.1.0] - 2026-01-11

### Added
- Initial commit: JSONL-based ADS-B evaluation framework.
