# AI monitor results

Everything here uses synthetic data. Real results need real traffic.

## Behaviour monitor (`app/ai.py`)
Held out check, three seeds: false alarms on normal days 0.1% to 0.6% of events. Four attack patterns (burst at 3 a.m.,
repeated unauthorized attempts, revocation storm, huge off-hours batch) were all flagged, the first within 1 to 12 events.
Run `python scripts/ai_eval.py`.

## Proposal experiment (`app/dataset.py`)
10,000 transactions, 70% train and 30% test, ten random seeds. Two versions of the data:

| data | precision | recall | F1 |
|---|---|---|---|
| spec: strata exactly as defined in the proposal | 0.985 | 0.997 | 0.991 |
| hard: blurred boundaries, stealth insiders, slow scripts | 0.761 | 0.782 | 0.770 |

The spec data is easy because the strata do not overlap. The hard data is closer to what a patient attacker looks like.
Report both, and say which is which.
