#!/usr/bin/env python3

import getpass
import time
import sys
import requests

API = "https://api.github.com"
HEADERS_BASE = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}


def build_headers(token: str) -> dict:
    return {**HEADERS_BASE, "Authorization": f"token {token}"}


def get_variable(headers: dict, repo: str, name: str):
    url = f"{API}/repos/{repo}/actions/variables/{name}"
    r = requests.get(url, headers=headers)
    if r.status_code != 200:
        print(f"\nDebug: API call to {url} failed with status {r.status_code}")
        if r.status_code == 404:
            print("Debug: Not Found. Check repo name and variable name.")
        elif r.status_code == 401:
            print("Debug: Unauthorized. Check PAT token.")
        elif r.status_code == 403:
            print("Debug: Forbidden. Check PAT token permissions.")
        return None
    return r.json().get("value")


def count_csv_rows(headers: dict, repo: str) -> int | None:
    url = f"{API}/repos/{repo}/contents/data.csv"
    r = requests.get(url, headers=headers)
    if r.status_code == 404:
        return None
    if r.status_code != 200:
        return None
    import base64
    raw = base64.b64decode(r.json()["content"]).decode()
    lines = [l for l in raw.strip().splitlines() if l.strip()]
    return max(0, len(lines) - 1)


def request_sync(headers: dict, repo: str, next_row: int) -> bool:
    url = f"{API}/repos/{repo}/dispatches"
    payload = {
        "event_type": "sync-event",
        "client_payload": {"next_row": next_row}
    }
    r = requests.post(url, headers=headers, json=payload)
    return r.status_code == 204


def check_remaining(headers: dict, repo: str, total_rows: int) -> tuple[int, int] | None:
    val = get_variable(headers, repo, "NEXT_ROW")
    if val is None:
        return None
    try:
        next_row = int(val)
    except (ValueError, TypeError):
        return None
    return next_row, total_rows


def fmt_time(seconds: int) -> str:
    m, s = divmod(seconds, 60)
    return f"{m}m {s}s" if m else f"{s}s"


def main():
    print("=" * 50)
    print("  Sync Monitor")
    print("=" * 50)
    print()

    token = getpass.getpass("GitHub PAT token: ").strip()
    if not token:
        print("Token cannot be empty.")
        sys.exit(1)

    repo = input("Repository (OWNER/REPO): ").strip()
    if "/" not in repo:
        print("Invalid format. Use OWNER/REPO.")
        sys.exit(1)

    interval_str = input("Sync interval in seconds [20]: ").strip()
    interval_sec = int(interval_str) if interval_str else 20
    if interval_sec < 5:
        print("Interval must be >= 5 seconds.")
        sys.exit(1)

    headers = build_headers(token)

    print("\nValidating access...", end=" ", flush=True)
    total = count_csv_rows(headers, repo)
    if total is None:
        total_str = input("\nCould not read data.csv (expected if private). Enter total row count: ").strip()
        try:
            total = int(total_str)
        except (ValueError, TypeError):
            print("Invalid row count.")
            sys.exit(1)

    if total is None:
        print("ERROR: Could not fetch total row count.")
        sys.exit(1)

    info = check_remaining(headers, repo, total)
    if info is None:
        print("FAILED")
        print("Could not read NEXT_ROW variable. Ensure it exists in repo Settings → Variables.")
        sys.exit(1)

    next_row, total_r = info
    remaining = max(0, total_r - next_row)
    print("OK")
    print(f"  Rows processed so far : {next_row}")
    print(f"  Total data rows       : {total}")
    print(f"  Remaining             : {remaining}")
    print(f"  Interval              : every {interval_sec} second(s)")
    print()

    if remaining == 0:
        print("Nothing to do — all rows have been processed.")
        sys.exit(0)

    sync_count = 0
    last_dispatched_row = None
    try:
        while True:
            info = check_remaining(headers, repo, total)
            if info is not None:
                next_row, total = info
                remaining = max(0, total - next_row)
                if remaining == 0:
                    print(f"\n All {total} rows processed. Stopping.")
                    break
            
            # Robust row selection: either the next expected variable from GitHub,
            # or the next sequential row in our local run (to handle latency).
            if last_dispatched_row is None:
                dispatch_row = int(next_row)
            else:
                dispatch_row = max(int(next_row), last_dispatched_row + 1)
            
            if dispatch_row >= total:
                 print(f"\n All {total} rows successfully dispatched. Stopping.")
                 break

            sync_count += 1
            ts = time.strftime("%H:%M:%S")
            ok = request_sync(headers, repo, dispatch_row)
            status = "completed" if ok else "FAILED"
            # Show which row index is being sent to verify it increments
            print(f"[{ts}]  Sync #{sync_count} (Row {dispatch_row}) | {status} | items left: {remaining}")
            
            if ok:
                last_dispatched_row = dispatch_row
                # Small sleep after success to prevent massive burst
                time.sleep(2)
            else:
                print("  Sync request failed — check your PAT token permissions.")
            
            wait = interval_sec
            end = time.time() + wait
            while time.time() < end:
                left = int(end - time.time())
                print(f"\r  Next sync in {fmt_time(left)}   ", end="", flush=True)
                time.sleep(1)
            print("\r" + " " * 50 + "\r", end="")

    except KeyboardInterrupt:
        print(f"\n\nStopped by user after {sync_count} sync(s).")
        sys.exit(0)

    print(f"\nDone. Processed {sync_count} transitions total.")


if __name__ == "__main__":
    main()
