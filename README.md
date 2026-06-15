# Novyx Audit Anchors

A public, append-only archive of **Novyx Core's signed audit chain-head checkpoints**.

Novyx Core maintains a per-tenant hash-linked audit chain. On a schedule it
snapshots every tenant's current chain head, signs the snapshot with its
RSA-4096 signing key, and chains each checkpoint to the previous one. The
result is a single signed value that commits to the state of the entire audit
log at a point in time.

This repository captures those checkpoints into git history. Each commit is an
**independent, timestamped anchor** held outside Novyx's own infrastructure:
once a checkpoint is committed here, Novyx cannot quietly rewrite a past audit
entry without contradicting a signature that is already public and a git
history that is already distributed.

## What's here

| Path | Description |
| --- | --- |
| `checkpoints/NNNNNN.json` | One immutable record per checkpoint (zero-padded id) |
| `checkpoints/latest.json` | Pointer to the most recently archived checkpoint |
| `keys/sentinel_public.pem` | The RSA-4096 public key the checkpoints are signed with |
| `scripts/fetch_checkpoint.py` | Fetches the live checkpoint and archives it if new (stdlib only) |
| `scripts/verify.py` | Independently verifies signatures + the forward chain |
| `.github/workflows/anchor.yml` | Runs the fetch every 6 hours and commits new checkpoints |

Source endpoint (public, unauthenticated, metadata only):
`https://novyx-ram-api.fly.dev/v1/public/audit-checkpoint`

## Checkpoint shape

```json
{
  "checkpoint_id": 6,
  "created_at": "2026-06-15T13:41:28.051328+00:00",
  "tenant_count": 43,
  "total_entries": 170460,
  "previous_checkpoint_hash": "29ad18b…",
  "payload_hash": "7506a5f…",
  "signature": "oNbatjAYZ3M…",
  "key_fingerprint": "8888b9fb…"
}
```

Per-tenant chain heads are **not** included — tenant identifiers are private.
The `payload_hash` commits to them; tenants verify their own slice through
Novyx Core's authenticated `/v1/audit/*` API.

## Verify it yourself

```bash
pip install cryptography
python scripts/verify.py
```

This checks two things using only public data:

1. **Authenticity** — each checkpoint's `signature` is a valid RSA-PSS-SHA256
   signature over its `payload_hash` under `keys/sentinel_public.pem`.
2. **Immutability** — for consecutively archived checkpoints, each
   `previous_checkpoint_hash` equals the prior checkpoint's `payload_hash`, so
   the sequence is append-only.

`payload_hash` itself is computed over the private chain heads and is therefore
verified inside Novyx Core, not here. What this archive proves is that the
checkpoints are genuinely Novyx-signed and have not been reordered or rewritten
since they were published.

## Key

- Algorithm: `RSA-PSS-SHA256`, 4096-bit
- Fingerprint (SHA-256 of the SubjectPublicKeyInfo PEM):
  `8888b9fb0e8f5089be2d027364f96bcaeb1204f814ea174283124932d2faf1bf`

If the signing key is ever rotated, checkpoints signed by the new key will
carry a new `key_fingerprint`; the old public key stays in git history so
historical checkpoints remain verifiable.
