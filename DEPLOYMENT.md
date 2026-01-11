## Hackathon Deployment Note

This project is designed as a continuously running ADS-B ground station
and evaluation system.

Due to its nature:
- It runs on physical SDR hardware and antennas
- It depends on local radio environment and air traffic
- It is designed for long-term statistical evaluation, not interactive UI

there is no single public Web endpoint that represents the core value of the project.

Instead, this repository contains:
- Append-only JSONL logs used for evaluation
- Statistical analysis scripts (P50/P90/P95/max)
- Design rationale for purpose-driven evaluation
- Example outputs and diagrams used for interpretation

During the judging period, the system continues to run and generate logs,
and all evaluation logic can be verified from this repository.
