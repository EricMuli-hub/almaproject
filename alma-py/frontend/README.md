# Alma interface

React.js, HTML5 and CSS3 with Tailwind, and Ethers.js for talking to the ledger. It is the presentation layer
of the proposal: people sign in with an email and a password, and the keys, hashes and transactions stay behind
the screen. Tick "Technical view" in the sidebar to see them.

## Run it

The API serves the built interface itself, so for a normal run you only need the backend:

```
cd frontend && npm install && npm run build      # once, writes frontend/dist
cd .. && python scripts/serve.py                  # http://localhost:8000
python scripts/seed_demo.py --owner-password change-me-now-please   # optional demo data
```

For development with hot reload: `npm run dev` (port 5173) with `VITE_API=http://localhost:8000`.

## Tests

`npm test` drives the real screens (React Testing Library) against a running API and a JSON-RPC node.
`scripts/e2e.sh` in the parent folder starts a Hardhat node and the API, then runs all 26 tests.

## Pages

| who | pages |
|---|---|
| anyone | landing, check a record (by ID or QR link, or from a package file) |
| platform owner | system, directory, plus every regulator page |
| institution | overview, students, issue records, records, anchors, access rules |
| student | my records, sharing, my data |
| employer | check a record |
| regulator | dashboard, AI alerts, ledger events, AI model, audit and privacy, performance |
