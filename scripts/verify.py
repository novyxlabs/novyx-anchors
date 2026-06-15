#!/usr/bin/env python3
"""Independently verify the archived Novyx audit checkpoints.

Two checks an external auditor can run with only public information:

  1. Signature: each checkpoint's RSA-PSS-SHA256 signature over its
     `payload_hash` validates under the published public key
     (keys/sentinel_public.pem).

  2. Forward chain: every checkpoint's `previous_checkpoint_hash` equals the
     `payload_hash` of the numerically preceding archived checkpoint. This
     makes the archive append-only: Novyx cannot alter a past checkpoint
     without breaking either the signature or every later link.

Note: `payload_hash` is computed over per-tenant chain heads, which are NOT
public (tenant identifiers are private). So this script does not recompute
payload_hash from scratch — that check runs inside Novyx Core's authenticated
/v1/audit/* surface. What the public archive proves is authenticity (signed
by Novyx's key) and immutability (git history + the forward chain).

Usage:  python scripts/verify.py
Exit 0 = all good, non-zero = a problem was found.
"""

import base64
import glob
import json
import os
import sys

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

# Must match GENESIS_CHECKPOINT_HASH in Novyx Core's audit_anchor_service.
GENESIS = "0" * 64

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KEY_PATH = os.path.join(ROOT, "keys", "sentinel_public.pem")
CHECKPOINTS_DIR = os.path.join(ROOT, "checkpoints")


def load_public_key():
    with open(KEY_PATH, "rb") as fh:
        return serialization.load_pem_public_key(fh.read())


def verify_signature(pub, payload_hash: str, signature_b64: str) -> bool:
    try:
        pub.verify(
            base64.b64decode(signature_b64),
            payload_hash.encode("utf-8"),
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH,
            ),
            hashes.SHA256(),
        )
        return True
    except InvalidSignature:
        return False


def main() -> int:
    pub = load_public_key()
    files = sorted(glob.glob(os.path.join(CHECKPOINTS_DIR, "[0-9]*.json")))
    if not files:
        print("No checkpoints archived yet.")
        return 0

    errors = []
    warnings = []
    prev = None  # (checkpoint_id, payload_hash) of the previous archived file
    for path in files:
        with open(path) as fh:
            cp = json.load(fh)
        cid = cp["checkpoint_id"]

        if not verify_signature(pub, cp["payload_hash"], cp["signature"]):
            errors.append(f"checkpoint {cid}: signature INVALID under published key")

        if prev is None:
            # First archived checkpoint. Only checkpoint #1 chains to GENESIS;
            # an archive that starts later simply can't be linked backward
            # without the missing predecessors — that's a coverage note.
            if cp["previous_checkpoint_hash"] == GENESIS and cid != 1:
                errors.append(
                    f"checkpoint {cid}: claims GENESIS predecessor but is not #1"
                )
            elif cid != 1:
                warnings.append(
                    f"archive starts at #{cid}; checkpoints before it are not "
                    "covered here (verify them via Novyx Core's audit API)"
                )
        elif cid == prev[0] + 1:
            # Adjacent checkpoints must link by payload_hash.
            if cp["previous_checkpoint_hash"] != prev[1]:
                errors.append(
                    f"checkpoint {cid}: chain break — previous_checkpoint_hash "
                    f"{cp['previous_checkpoint_hash'][:16]}… != #{prev[0]} "
                    f"payload {prev[1][:16]}…"
                )
        else:
            # Gap in coverage (missed captures). Can't link across the gap.
            warnings.append(
                f"gap between #{prev[0]} and #{cid}; intermediate checkpoints "
                "not archived, so the link across the gap is unchecked"
            )
        prev = (cid, cp["payload_hash"])

    print(f"Verified {len(files)} checkpoint(s).")
    if warnings:
        print("\nNotes:")
        for w in warnings:
            print(f"  - {w}")
    if errors:
        print("\nFAILURES:")
        for e in errors:
            print(f"  - {e}")
        return 1
    print("All signatures valid; forward chain intact across archived checkpoints.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
