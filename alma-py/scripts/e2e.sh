#!/usr/bin/env bash
# Starts a local Hardhat node and the API on it, then runs the interface tests. Needs: npm i hardhat in HH_DIR (default /tmp/hh).
set -e
HH_DIR=${HH_DIR:-/tmp/hh}
cd "$(dirname "$0")/.."
( cd "$HH_DIR" && npx hardhat node --hostname 127.0.0.1 --port 8545 > node.log 2>&1 & echo $! > /tmp/alma-node.pid )
sleep 8
KEY=$(grep -m1 "Private Key" "$HH_DIR/node.log" | awk '{print $3}')
export CHAIN_RPC=http://127.0.0.1:8545 FUNDER_KEY=$KEY ADMIN_PASSWORD=owner-password-1 ALMA_DATA=$(mktemp -d) PORT=8000
python3 scripts/serve.py > /tmp/alma-api.log 2>&1 & echo $! > /tmp/alma-api.pid
for i in $(seq 1 60); do curl -sf http://127.0.0.1:8000/system/health >/dev/null && break; sleep 1; done
( cd frontend && ALMA_TEST_API=http://127.0.0.1:8000 npx vitest run ) ; RC=$?
kill $(cat /tmp/alma-api.pid) $(cat /tmp/alma-node.pid) 2>/dev/null || true
exit $RC
