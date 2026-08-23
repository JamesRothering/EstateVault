"""Poll HTTP URLs until they answer. Acceptance uses this so the runner keeps a heartbeat."""

from __future__ import annotations

import argparse
import sys
import time
import urllib.error
import urllib.request


def http_answered(url: str, timeout: float = 5.0) -> bool:
    """True if the TCP/HTTP stack returns any HTTP status (including 4xx/5xx)."""
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout):
            return True
    except urllib.error.HTTPError:
        return True
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def wait_http(url: str, *, name: str, timeout_sec: int, interval_sec: int = 10) -> bool:
    deadline = time.monotonic() + timeout_sec
    attempt = 0
    while time.monotonic() < deadline:
        attempt += 1
        if http_answered(url):
            print(f"{name} is up: {url}")
            return True
        left = max(0, int(deadline - time.monotonic()))
        print(f"waiting for {name} ({attempt}) {url} ~{left}s left")
        time.sleep(interval_sec)
    print(f"ERROR: {name} never answered at {url}", file=sys.stderr)
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--interval", type=int, default=10)
    args = parser.parse_args(argv)
    return 0 if wait_http(args.url, name=args.name, timeout_sec=args.timeout, interval_sec=args.interval) else 1


if __name__ == "__main__":
    raise SystemExit(main())
