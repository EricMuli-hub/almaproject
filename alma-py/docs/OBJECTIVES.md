# Objectives, research questions and what the code does

## 1. Role based access control (RQ1)
`AlmaRegistry.sol` has five roles. Only the platform owner can register institutions, employers and regulators.
Only an active university administrator can register its own students, issue, anchor and revoke, and only for its own
institution. Students grant and withdraw access to their own records. Regulators and the owner can suspend an
institution. Every refusal is a typed error (`NotAllowed`, `WrongInstitution`, `InstitutionInactive`), and tests call
the contract directly to show it refuses even when the API is skipped.

## 2. AI anomaly detection (RQ2)
Two detectors share the same event stream (`ledger_events`):
- `app/ai.py`: nine behaviour features per actor (burst rate, hourly and daily volume, off hours, failure ratio,
  revocation ratio, batch size, unauthorized attempts, minimum gap), an Isolation Forest, z-score deviation and a
  small rule engine. Each action is scored the moment it happens. A critical score puts the institution on hold, on
  chain, until a regulator reviews it.
- `app/watcher.py`: reads every block from the node and scores transactions that never passed through the API,
  which is how a stolen admin key used directly against the node shows up.
- `app/dataset.py`: the 10,000 transaction experiment (9,500 normal, 250 insider, 250 script, 70/30 split) with
  features temporal fraction, invocation velocity and payload entropy.

All training data is synthetic. See `docs/AI.md` for the numbers and their limits.

## 3. Decentralized storage and hashing (RQ3)
Each record is encrypted with its own key (AES-256-GCM) and stored by content id. Only a salted SHA-256 hash goes
on chain, either alone or as a leaf of a Merkle tree whose root is one transaction. Tampering with a stored blob
changes its id and fails. If the database is lost, `recover_index` rebuilds the index from chain events and the
manifests on the content store, and a holder's own package verifies with the chain alone.

## 4. Privacy and data sovereignty (RQ4)
No names, emails or marks are on chain, and a test scans every log the contract ever wrote. Disclosure to an employer
needs an on-chain grant from the student with an expiry, and the student can withdraw it. Erasure destroys the record's
key (crypto-shredding), data export gives the student everything, the audit trail is hash chained, and the storage
region is a setting. `docs/COMPLIANCE.md` lists what this does and does not do. It is not legal advice.

## 5. Performance, scalability, latency, cost (RQ5)
Batch anchoring makes the cost per record small. Measured gas: one record on its own 85,957, a batch of 1,000 costs
56,042 in total, 56 per record. Verification and tree numbers are in `docs/BENCHMARK_testchain.md`. The conventional
centralized lookup is faster per request (0.35 ms against 13 ms here), because it does no proof and no chain read; the
comparison is about what each answer is worth, not raw speed. `docs/SCALABILITY.md` explains the design and the limits.
