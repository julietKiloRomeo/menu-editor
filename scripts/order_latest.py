#!/usr/bin/env python3
"""Run the newest kitchen walk through the local nemlig browser bridge.

The live database belongs on valhalla, while Chrome and its logged-in session
must stay on this machine. This command joins those two facts safely:

1. take a SQLite backup of the live database over SSH (never copy a WAL file),
2. run the app locally against that snapshot,
3. resume/start the newest run and perform fresh nemlig searches,
4. open the in-app picker, and
5. after a clean basket fill records the order, append that order to the live
   database and open the nemlig basket.

No cookies or bearer tokens leave Chrome. The live database is never replaced.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sqlite3
import subprocess
import sys
import time
import webbrowser

import httpx


ROOT = pathlib.Path(__file__).resolve().parents[1]
WORK = pathlib.Path("/tmp/opencode/menu-editor")
STATE = WORK / "nemlig-order-state.json"
DEFAULT_HOST = "valhalla"
DEFAULT_REMOTE_DB = "/home/jikr/projects/kastaniebakken-automation/menu/data/recipes.db"

REMOTE_BACKUP = r"""
import pathlib, sqlite3, sys
source, target = sys.argv[1:3]
pathlib.Path(target).unlink(missing_ok=True)
src = sqlite3.connect(source, timeout=30)
dst = sqlite3.connect(target, timeout=30)
src.backup(dst)
dst.close()
src.close()
"""

REMOTE_SYNC = r"""
import json, sqlite3, sys

live_path, snapshot_path, requested_id = sys.argv[1], sys.argv[2], int(sys.argv[3])
live = sqlite3.connect(live_path, timeout=30)
snapshot = sqlite3.connect(snapshot_path, timeout=30)
snapshot.row_factory = sqlite3.Row
source = snapshot.execute('select * from nemligorder where id=?', (requested_id,)).fetchone()
if source is None or source['recorded_at'] is None:
    raise SystemExit('completed order missing from local snapshot')

with live:
    existing = live.execute(
        'select id from nemligorder where id=? and run_id=? and source=?',
        (source['id'], source['run_id'], source['source']),
    ).fetchone()
    if existing is None:
        existing = live.execute(
            'select id from nemligorder where run_id=? and source=? and recorded_at is null '
            'order by id desc limit 1',
            (source['run_id'], source['source']),
        ).fetchone()

    if existing is None:
        cursor = live.execute(
            'insert into nemligorder(run_id,created_at,source,recorded_at) values(?,?,?,?)',
            (source['run_id'], source['created_at'], source['source'], source['recorded_at']),
        )
        order_id = cursor.lastrowid
    else:
        order_id = existing[0]
        live.execute(
            'update nemligorder set recorded_at=? where id=?',
            (source['recorded_at'], order_id),
        )
        live.execute('delete from nemligorderitem where order_id=?', (order_id,))

    columns = [
        row[1] for row in live.execute('pragma table_info(nemligorderitem)')
        if row[1] not in ('id', 'order_id')
    ]
    placeholders = ','.join('?' for _ in columns)
    quoted = ','.join(f'[{column}]' for column in columns)
    rows = snapshot.execute(
        'select * from nemligorderitem where order_id=? order by position',
        (source['id'],),
    ).fetchall()
    for row in rows:
        live.execute(
            f'insert into nemligorderitem(order_id,{quoted}) values(?,{placeholders})',
            (order_id, *(row[column] for column in columns)),
        )

    # Recording "Have it" updates this table locally. Keep the live kitchen
    # walk in sync without deleting any remote-only staple.
    for row in snapshot.execute('select name from stockeditem'):
        live.execute('insert or ignore into stockeditem(name) values(?)', (row['name'],))

print(json.dumps({'order_id': order_id, 'items': len(rows)}))
snapshot.close()
live.close()
"""


def ssh(host: str, *command: str, input_text: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", host, *command],
        input=input_text,
        text=True,
        check=True,
        capture_output=True,
    )


def scp(source: str, destination: str) -> None:
    subprocess.run(
        [
            "scp",
            "-q",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=5",
            source,
            destination,
        ],
        check=True,
    )


def snapshot_live_database(host: str, remote_db: str, local_db: pathlib.Path) -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    remote_copy = f"/tmp/menu-editor-order-{os.getpid()}.db"
    try:
        ssh(host, "python3", "-", remote_db, remote_copy, input_text=REMOTE_BACKUP)
        local_db.unlink(missing_ok=True)
        scp(f"{host}:{remote_copy}", str(local_db))
    finally:
        try:
            ssh(host, "rm", "-f", remote_copy)
        except subprocess.CalledProcessError:
            pass


def sqlite_backup(source: pathlib.Path, target: pathlib.Path) -> None:
    target.unlink(missing_ok=True)
    src = sqlite3.connect(source, timeout=30)
    dst = sqlite3.connect(target, timeout=30)
    src.backup(dst)
    dst.close()
    src.close()


def sync_completed_order(
    host: str, remote_db: str, local_db: pathlib.Path, order_id: int
) -> dict:
    transfer = WORK / "nemlig-order-completed.db"
    remote_copy = f"/tmp/menu-editor-order-completed-{os.getpid()}.db"
    sqlite_backup(local_db, transfer)
    try:
        scp(str(transfer), f"{host}:{remote_copy}")
        result = ssh(
            host,
            "python3",
            "-",
            remote_db,
            remote_copy,
            str(order_id),
            input_text=REMOTE_SYNC,
        )
        return json.loads(result.stdout)
    finally:
        transfer.unlink(missing_ok=True)
        try:
            ssh(host, "rm", "-f", remote_copy)
        except subprocess.CalledProcessError:
            pass


def wait_for_app(base: str, server: subprocess.Popen, timeout: float = 30) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if server.poll() is not None:
            raise RuntimeError("The local app stopped during startup")
        try:
            response = httpx.get(f"{base}/api/status", timeout=1)
            if response.is_success:
                return response.json()
        except httpx.HTTPError:
            pass
        time.sleep(0.25)
    raise RuntimeError("The local app did not become ready")


def api(method: str, url: str, **kwargs) -> dict:
    response = httpx.request(method, url, timeout=180, **kwargs)
    body = response.json()
    if not response.is_success:
        raise RuntimeError(body.get("error") or f"HTTP {response.status_code}")
    return body


def write_state(*, host: str, remote_db: str, order: dict) -> None:
    """Remember enough to resume after closing the terminal or a sync failure."""
    payload = {
        "host": host,
        "remote_db": remote_db,
        "order_id": int(order["id"]),
        "run_id": int(order["run_id"]),
    }
    temporary = STATE.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload), encoding="utf-8")
    temporary.replace(STATE)


def read_state() -> dict | None:
    try:
        payload = json.loads(STATE.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else None
    except (OSError, ValueError):
        return None


def local_order_state(local_db: pathlib.Path, order_id: int) -> dict | None:
    if not local_db.is_file():
        return None
    try:
        connection = sqlite3.connect(local_db, timeout=5)
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "select id, run_id, recorded_at from nemligorder where id=?",
            (order_id,),
        ).fetchone()
        connection.close()
    except sqlite3.Error:
        return None
    return dict(row) if row else None


def latest_run_id(database: pathlib.Path) -> int | None:
    connection = sqlite3.connect(database, timeout=5)
    row = connection.execute(
        "select id from shoppingrun order by created_at desc, id desc limit 1"
    ).fetchone()
    connection.close()
    return int(row[0]) if row else None


def ensure_frontend_build() -> None:
    """Build the picker when its checked-in source is newer than local output."""
    frontend = ROOT / "frontend"
    output = frontend / "dist" / "index.html"
    inputs = list((frontend / "src").rglob("*"))
    inputs.extend(
        frontend / name
        for name in (
            "package.json",
            "bun.lock",
            "vite.config.ts",
            "tailwind.config.js",
            "tsconfig.json",
        )
    )
    source_times = [path.stat().st_mtime for path in inputs if path.is_file()]
    if output.is_file() and source_times and output.stat().st_mtime >= max(source_times):
        return
    print("Building the local picker…", flush=True)
    subprocess.run(["bun", "run", "build"], cwd=frontend, check=True)


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--remote-db", default=DEFAULT_REMOTE_DB)
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument(
        "--allow-recorded",
        action="store_true",
        help="deliberately start another order for an already completed latest run",
    )
    parser.add_argument("--no-open", action="store_true", help="do not open browser tabs")
    parser.add_argument(
        "--discard-unfinished",
        action="store_true",
        help="discard a saved unfinished picker when a newer kitchen run exists",
    )
    return parser.parse_args()


def run(args: argparse.Namespace) -> int:
    local_db = WORK / "nemlig-order-live.db"
    incoming_db = WORK / "nemlig-order-incoming.db"
    log_path = WORK / "nemlig-order-app.log"
    ensure_frontend_build()
    print("Loading the live kitchen run…", flush=True)

    # A clean fill may have happened just before the terminal closed or the
    # network failed. Complete that idempotent sync before replacing anything.
    state = read_state()
    if (
        state
        and state.get("host") == args.host
        and state.get("remote_db") == args.remote_db
    ):
        saved = local_order_state(local_db, int(state.get("order_id") or 0))
        if saved and saved.get("recorded_at"):
            synced = sync_completed_order(
                args.host, args.remote_db, local_db, int(state["order_id"])
            )
            STATE.unlink(missing_ok=True)
            print(
                f"Recovered and synced order {synced['order_id']} ({synced['items']} rows).",
                flush=True,
            )
            if not args.no_open:
                webbrowser.open("https://www.nemlig.com/basket")
            return 0

        if saved:
            snapshot_live_database(args.host, args.remote_db, incoming_db)
            if latest_run_id(incoming_db) == int(state.get("run_id") or 0):
                incoming_db.unlink(missing_ok=True)
                print("Resuming the unfinished local picker…", flush=True)
            elif not args.discard_unfinished:
                incoming_db.unlink(missing_ok=True)
                raise RuntimeError(
                    "A picker for an older kitchen run is unfinished. Finish it first, "
                    "or rerun with --discard-unfinished."
                )
            else:
                incoming_db.replace(local_db)
                STATE.unlink(missing_ok=True)
        else:
            STATE.unlink(missing_ok=True)
            snapshot_live_database(args.host, args.remote_db, local_db)
    else:
        snapshot_live_database(args.host, args.remote_db, local_db)

    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{local_db}"
    env["NEMLIG_MAP_PATH"] = str(ROOT / "data" / "nemlig_product_map.json")
    command = [
        sys.executable,
        "-c",
        (
            "from app import app; "
            f"app.run(host='127.0.0.1', port={args.port}, debug=False, use_reloader=False)"
        ),
    ]
    log = log_path.open("w", encoding="utf-8")
    server: subprocess.Popen | None = None
    base = f"http://127.0.0.1:{args.port}"

    try:
        server = subprocess.Popen(
            command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT
        )
        status = wait_for_app(base, server)
        if pathlib.Path(status.get("database_path", "")) != local_db:
            raise RuntimeError(f"Local app opened the wrong database: {status.get('database_path')}")

        order = api(
            "POST",
            f"{base}/api/orders/latest",
            json={"allow_recorded": args.allow_recorded},
        )
        write_state(host=args.host, remote_db=args.remote_db, order=order)
        browser = api("GET", f"{base}/api/browser/status")
        if not (browser.get("reachable") and browser.get("tab")):
            if not args.no_open:
                webbrowser.open("https://www.nemlig.com/")
            print(browser.get("detail") or "Open nemlig.com in logged-in Chrome.", flush=True)
            input("Log in yourself, then press Enter to continue: ")

        pending = api("GET", f"{base}/api/orders/{order['id']}/queries")["queries"]
        if pending:
            print(f"Searching live products for {order['total']} unticked rows…", flush=True)
            searched = api("POST", f"{base}/api/orders/{order['id']}/run-search", json={})
            ready = searched["order"]
        else:
            ready = order
        print(
            f"Ready: {ready['decided']}/{ready['total']} reused safely; "
            f"{ready['total'] - ready['decided']} choices need attention.",
            flush=True,
        )
        picker_url = f"{base}/order?order={order['id']}"
        print(picker_url, flush=True)
        if not args.no_open:
            webbrowser.open(picker_url)

        # A clean fill records automatically. Once that marker appears, append
        # only this order to the live database and leave the user at checkout.
        while server.poll() is None:
            current = api("GET", f"{base}/api/orders/{order['id']}")
            if current.get("recorded_at"):
                synced = sync_completed_order(
                    args.host, args.remote_db, local_db, order["id"]
                )
                STATE.unlink(missing_ok=True)
                print(
                    f"Done: synced order {synced['order_id']} ({synced['items']} rows) "
                    "to the live database.",
                    flush=True,
                )
                if not args.no_open:
                    webbrowser.open("https://www.nemlig.com/basket")
                return 0
            time.sleep(1)
        raise RuntimeError(f"The local app stopped. See {log_path}")
    finally:
        if server is not None and server.poll() is None:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
        log.close()


def main() -> int:
    try:
        return run(arguments())
    except KeyboardInterrupt:
        print("Stopped; rerun the same command to resume your saved choices.", flush=True)
        return 130
    except (
        RuntimeError,
        OSError,
        sqlite3.Error,
        subprocess.CalledProcessError,
        httpx.HTTPError,
    ) as exc:
        print(f"Order stopped safely: {exc}", file=sys.stderr, flush=True)
        print(f"App log: {WORK / 'nemlig-order-app.log'}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
