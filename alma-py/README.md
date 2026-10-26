# Alma backend (Python)

Backend for the blockchain and AI academic credential verification system. FastAPI, SQLAlchemy, web3.py,
a Solidity contract, an Isolation Forest monitor, and an IPFS style content store.

## Run it

```
pip install -r requirements.txt
npm install            # only to compile the contract
node scripts/compile.js
(cd frontend && npm install && npm run build)    # the interface
python scripts/serve.py          # interface at http://localhost:8000, API docs at /docs
python scripts/seed_demo.py --owner-password change-me-now-please   # demo data (optional)
python -m pytest -q tests        # 28 backend tests
./scripts/e2e.sh                 # 26 interface tests on a real Hardhat node (needs hardhat installed in /tmp/hh)
```

With no settings it uses a built in test chain and a local content store. That is good for the demo and the
tests. The test chain forgets everything when the process stops, so for anything you want to keep, point it at a
real node (Hardhat, Anvil, Ganache or a testnet):

```
CHAIN_RPC=http://127.0.0.1:8545 FUNDER_KEY=0x... python scripts/deploy.py   # prints CONTRACT_ADDRESS and PLATFORM_KEY
cp .env.example .env     # fill in the values, then
python scripts/serve.py
```

Set `IPFS_API` to use a real IPFS node, and `DATABASE_URL` for PostgreSQL. `WATCHER=1` turns on the ledger
watcher. First start creates the platform owner: `owner@alma.local`, password from `ADMIN_PASSWORD`. Change it.

## Where each objective lives

| objective | code | proof |
|---|---|---|
| 1. Role based access control in a smart contract | `contracts/AlmaRegistry.sol`, `app/service.py` | `tests/test_objectives.py` O1 |
| 2. AI anomaly detection in real time | `app/ai.py`, `app/watcher.py`, `app/dataset.py` | O2 tests, `test_extra.py`, `docs/AI.md` |
| 3. IPFS storage plus hashing | `app/core.py` (store, Merkle), `app/service.py` | O3 tests |
| 4. Immutable verification that respects privacy law | consent in the contract, `erase`, `export_student`, audit chain | O4 tests, `docs/COMPLIANCE.md` |
| 5. Performance, scalability, latency, cost | `app/bench.py`, `scripts/benchmark.py` | O5 tests, `docs/BENCHMARK_testchain.md`, `docs/SCALABILITY.md` |

`docs/OBJECTIVES.md` answers the five research questions one by one and says what is and is not proven.

## Roles

Platform owner, university administrator, student, employer, regulator. The API checks the role, and the contract
checks it again from the sender address, so a stolen API token still cannot issue, revoke or change roles.

## Interface

`frontend/` is the React.js, Tailwind and Ethers.js interface the proposal describes. See `frontend/README.md` and `docs/FRONTEND.md`.
