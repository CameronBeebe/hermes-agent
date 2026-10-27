"""Private one-request worker. Credentials arrive on stdin, never argv or logs."""
import json
import sys

from scripts.context_map import post


def main():
    try:
        raw = sys.stdin.buffer.read(100001)
        if len(raw) > 100000:
            return 1
        envelope = json.loads(raw)
        payload = envelope["payload"].encode()
        if len(payload) > 65536:
            return 1
        body = post(payload, envelope["key"])
        sys.stdout.buffer.write(body)
        return 0
    except Exception:  # health: allow BLE001 -- no credential-bearing exception or remote body logs
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
