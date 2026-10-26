# The interface and the five objectives

The proposal asks for a React.js, HTML5, CSS3 interface that hides Web3 behind ordinary login portals. This is
how each objective shows up on screen. Every row below is exercised by the interface tests.

| objective | where to see it | what you can do there |
|---|---|---|
| 1. Role based access control | Institution, "Access rules" | Asks the smart contract what your account may do (nothing is sent). Refusals show the contract's own error. Reads your role from the node with Ethers.js. |
| | Every portal | A page that is not part of your role is refused in the app, and the contract refuses the action even if the app were skipped. |
| 2. AI anomaly detection | Regulator, "AI alerts" | Live list with score, reasons, automatic hold, confirm or dismiss. |
| | "Ledger events" | Every action scored, with its source: `api` or `ledger` (found by the watcher on the node). |
| | "AI model" | Four attack patterns, false alarm rate, and the 10,000 transaction experiment as specified and as a harder variant, with the confusion matrix. |
| 3. IPFS storage plus hashing | Institution, "Issue records" | One record, a spreadsheet, or a queue. Shows the content ID, fingerprint, Merkle root and transaction. |
| | Check a record, "From a package file" | Rebuilds the Merkle proof step by step in the browser and reads the ledger through Ethers.js, beside the server's own answer. An edit to any field fails. |
| | System, "Rebuild index" | Rebuilds the database index from the chain and the content store. |
| 4. Immutable verification that respects privacy law | Student, "Sharing" | Consent per record and per employer, with a purpose and an expiry, recorded on the chain. Withdraw any time. |
| | Student, "My data" | Full export, and erasure behind a typed confirmation (the record key is destroyed). The check page then says it was erased. |
| | Check a record | Public answer shows issuer, type and date only. No names or marks. |
| | Regulator, "Audit and privacy" | Verifies the hash-chained audit trail and scans every log on the chain for stored names and emails. |
| 5. Performance, scalability, cost | Regulator, "Performance" | Gas per record one by one against batched, proof size against record count, latency and throughput with and without the status cache, cost for 10,000 records. |
| | Institution, "Anchors" | Gas per record of each batch next to the one-by-one cost. |
| | Landing page | Live figures from the benchmark file. |

## Abstraction

Nobody needs a wallet. Accounts are email and password, each account gets a chain key held by the platform (encrypted),
and every action is a plain button. "Technical view" and the "Under the hood" boxes show what really happened: content
IDs, transaction hashes, gas, roots and proofs. The check page can also prove a record without trusting the server.

## Things the interface does not do

- It does not talk to a wallet such as MetaMask. The proposal's abstraction means the platform signs for people. Wallet
  signing would be a separate sign-in option.
- The performance charts show what was measured on the simulated chain, with the caveat printed on the page.
- The AI figures come from synthetic data and are labelled that way.
