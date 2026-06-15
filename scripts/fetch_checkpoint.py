#!/usr/bin/env python3
"""Fetch the current public audit checkpoint and archive it if it's new.

Writes two files when the live checkpoint_id is not yet archived:
  checkpoints/<id zero-padded to 6>.json   immutable per-checkpoint record
  checkpoints/latest.json                   convenience pointer to the newest

Stdlib only — no third-party deps — so the archiving job stays trivial.
Prints "changed=true" / "changed=false" to $GITHUB_OUTPUT so the workflow
knows whether to commit.
"""

import json
import os
import sys
import urllib.request

ENDPOINT = os.environ.get(
    "NOVYX_CHECKPOINT_URL",
    "https://novyx-ram-api.fly.dev/v1/public/audit-checkpoint",
)
CHECKPOINTS_DIR = os.path.join(os.path.dirname(__file__), "..", "checkpoints")


def _set_output(changed: bool, checkpoint_id) -> None:
    out = os.environ.get("GITHUB_OUTPUT")
    line_changed = "true" if changed else "false"
    if out:
        with open(out, "a") as fh:
            fh.write(f"changed={line_changed}\n")
            fh.write(f"checkpoint_id={checkpoint_id}\n")
    print(f"changed={line_changed} checkpoint_id={checkpoint_id}")


def main() -> int:
    req = urllib.request.Request(ENDPOINT, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read().decode("utf-8"))

    cid = payload["checkpoint_id"]
    canonical = json.dumps(payload, indent=2, sort_keys=True) + "\n"

    os.makedirs(CHECKPOINTS_DIR, exist_ok=True)
    numbered = os.path.join(CHECKPOINTS_DIR, f"{cid:06d}.json")

    if os.path.exists(numbered):
        with open(numbered) as fh:
            existing = fh.read()
        if existing == canonical:
            _set_output(False, cid)
            return 0
        # Same id, different bytes: the server changed an already-published
        # checkpoint. That must never happen — fail loudly, do not overwrite.
        sys.stderr.write(
            f"FATAL: checkpoint {cid} already archived with different content. "
            "A published checkpoint was mutated upstream.\n"
        )
        return 2

    with open(numbered, "w") as fh:
        fh.write(canonical)
    with open(os.path.join(CHECKPOINTS_DIR, "latest.json"), "w") as fh:
        fh.write(canonical)

    _set_output(True, cid)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
