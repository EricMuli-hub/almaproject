# Benchmark results (objective 5)

Measured on: in-process test chain. Chain latency here is near zero, so the latency numbers show the cost of the software around the chain, not network or block time. Point CHAIN_RPC at a real node and run `python scripts/benchmark.py` to measure those.

## Transaction cost (gas, exact for this contract)

| | gas |
|---|---|
| issue one record on its own | 85,957 |
| anchor a batch of 1,000 | 56,042 |
| per record in that batch | 56.0 |

## Cost for 10,000 records (assumed coin price $3,000; gas prices are assumptions)

| network | gas price (gwei) | one transaction each | batches of 1,000 |
|---|---|---|---|
| mainnet-like (assumed) | 20.0 | $51,574.2 | $33.63 |
| layer-2-like (assumed) | 0.05 | $128.94 | $0.08 |

## Gas by contract method (Table 3.3 layout)

Standard = compiled without the optimizer, optimized = optimizer on (200 runs). Measured, not estimated.

| method | gas (standard) | gas (optimized) |
|---|---|---|
| constructor | 3,804,522 | 1,963,108 |
| grantRole (employer) | 49,285 | 48,819 |
| registerStudent | 75,838 | 75,181 |
| mintCredential | 86,687 | 85,938 |
| revokeCredential | 55,823 | 55,225 |
| anchorBatch (any size) | 56,869 | 55,220 |
| verifyCredential | 0 | 0 |
| verifyCredential (view) latency | 5.633 ms | 6.03 ms |

## Concurrent verification, every request reads the chain

A burst of N simultaneous GET /verify calls against a running server, 2 rounds per level.

| concurrent | ok | min ms | median ms | mean ms | p95 ms | max ms | requests/s |
|---|---|---|---|---|---|---|---|
| 10 | 20/20 | 89.7 | 134.4 | 135.2 | 160.5 | 160.5 | 59.2 |
| 50 | 100/100 | 106.7 | 877.9 | 827.2 | 934.9 | 936.5 | 53.7 |
| 100 | 200/200 | 256.4 | 1553.9 | 1396.0 | 1835.8 | 1848.8 | 54.9 |
| 500 | 1000/1000 | 1464.0 | 9418.0 | 8434.3 | 10293.8 | 10535.0 | 47.6 |
| 1000 | 2000/2000 | 2273.8 | 17734.6 | 15661.5 | 18728.4 | 19779.3 | 51.1 |

Process memory: 270.0 MB before, 325.9 MB after.

## Concurrent verification, chain reads cached for 5 s

A burst of N simultaneous GET /verify calls against a running server, 2 rounds per level.

| concurrent | ok | min ms | median ms | mean ms | p95 ms | max ms | requests/s |
|---|---|---|---|---|---|---|---|
| 10 | 20/20 | 33.3 | 86.7 | 87.6 | 149.2 | 149.2 | 105.4 |
| 50 | 100/100 | 49.1 | 178.1 | 279.2 | 428.1 | 429.3 | 156.4 |
| 100 | 200/200 | 87.3 | 356.8 | 475.0 | 786.0 | 796.8 | 162.7 |
| 500 | 1000/1000 | 1010.6 | 5392.2 | 5385.1 | 8077.8 | 8380.4 | 62.3 |
| 1000 | 2000/2000 | 2914.6 | 9995.8 | 9266.4 | 10935.8 | 11245.0 | 89.2 |

Process memory: 331.4 MB before, 339.3 MB after.

## Verification latency

| | median (ms) | 95th percentile (ms) |
|---|---|---|
| hybrid, every check reads the chain | 13.248 | 18.11 |
| hybrid with the 5 second chain-status cache | 1.87 | 2.484 |
| centralized lookup only (no integrity proof) | 0.3493 | 0.5521 |

Verification throughput with 8 concurrent clients: 69.6 per second.

## Scalability of the Merkle tree

| records | build (s) | proof hashes | proof bytes | verify (ms) |
|---|---|---|---|---|
| 1,000 | 0.001 | 10 | 320 | 0.0087 |
| 10,000 | 0.006 | 14 | 448 | 0.0142 |
| 100,000 | 0.067 | 17 | 544 | 0.0278 |

Issuing 1,000 records in one batch took 0.34 s end to end (encryption, storage, anchoring).
