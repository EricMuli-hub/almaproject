# Data protection design

Built around the usual principles in the Kenya Data Protection Act, 2019 and the GDPR. This is a technical design, not legal advice.

| principle | what the system does |
|---|---|
| data minimisation | only a salted hash is on chain, no personal fields |
| consent and purpose | the student grants a verifier access to one record, with a purpose and an expiry, recorded on chain |
| access and portability | `GET /student/export` returns the student's records, proofs and consents |
| erasure | `DELETE /student/credentials/{id}` destroys the record key; the encrypted copy can never be read again |
| integrity | Merkle proofs, content ids, hash chained audit log |
| storage location | `DATA_REGION` records the region; run the database and content store there |
| accountability | audit log of issuing, consent, disclosure and erasure, checked at `GET /system/audit/verify` |

Known limits: encrypted data on IPFS cannot be deleted, only made unreadable. A salted hash on a public chain is still
personal data under some readings, so get legal review before going live. The platform holds users' chain keys
(custodial, encrypted with the master key); a real deployment should use a key management service or hardware module.
