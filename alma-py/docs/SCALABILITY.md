# Scalability

What makes it scale:
- one chain transaction per batch of up to `MAX_BATCH` records (default 5,000) instead of one per record;
  verification needs a proof of about log2(n) hashes (13 for 5,000 records, 17 for 100,000, 20 for a million);
- API servers keep no state, so run as many copies as needed behind a load balancer (`docker-compose.yml`);
  all state is in PostgreSQL, the chain and the content store;
- the issuing queue (`/institution/credentials/queue`, then flush) separates taking requests from anchoring;
- chain reads can be cached for a few seconds (`READ_CACHE_TTL`); revocations then show up within that time;
- indexed ledger table, so the AI features are computed from short queries per actor.

What is measured here: see `BENCHMARK_testchain.md`. The test chain is a Python EVM simulator that runs one call at a time,
so its numbers (about 50 verifications a second, 160 with the cache, slow at 500 to 1,000 simultaneous requests) are the
simulator and a single process, not the limit of the design. They are not a claim that it handles a university's peak load.
To measure the real thing, run the benchmark against a real node with several API copies.

Real networks add block time (seconds to minutes) to issuing and revoking, and gas cost to every anchor. Reads stay fast.
