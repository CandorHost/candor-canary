"""Candor Deploy canary — proves each platform capability by exercising it.

Every route here answers a question the platform's own status pages cannot:
not "did it start" but "can a real client authenticate, write, and read back".
``GET /all`` runs every check and reports one verdict, which is what the
end-to-end runner asserts on.

Deliberately stdlib for the HTTP layer: the only dependencies are the three
database drivers, so a build failure is never this app's own fault.
"""
import json
import os
import socket
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

#: Set at deploy time by the runner so it can prove WHICH build is serving.
STAMP = os.environ.get("CANARY_STAMP", "unset")
#: Echoed back by /env, to prove environment injection reaches the container.
ECHO = os.environ.get("CANARY_ECHO", "unset")
PORT = int(os.environ.get("PORT", "8080"))

#: Printed to stdout by /log, so the runner can find it in the runtime logs.
LOG_MARKER = "canary-log-marker"


def check_postgres() -> dict[str, object]:
    """Write a row through DATABASE_URL and read it back."""
    import psycopg

    with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=8) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "CREATE TABLE IF NOT EXISTS canary ("
                "id serial PRIMARY KEY, note text, at timestamptz DEFAULT now())")
            cur.execute("INSERT INTO canary (note) VALUES (%s) RETURNING id", (STAMP,))
            row_id = cur.fetchone()[0]
            cur.execute("SELECT note FROM canary WHERE id = %s", (row_id,))
            note = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM canary")
            total = cur.fetchone()[0]
        conn.commit()
    return {"wrote_id": row_id, "read_back": note, "rows": total}


def check_mysql() -> dict[str, object]:
    """Write a row through MYSQL_URL and read it back."""
    import pymysql

    url = urlparse(os.environ["MYSQL_URL"])
    conn = pymysql.connect(
        host=url.hostname, port=url.port or 3306,
        user=unquote(url.username or ""), password=unquote(url.password or ""),
        database=url.path.lstrip("/"), connect_timeout=8,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                "CREATE TABLE IF NOT EXISTS canary ("
                "id INT AUTO_INCREMENT PRIMARY KEY, note VARCHAR(255))")
            cur.execute("INSERT INTO canary (note) VALUES (%s)", (STAMP,))
            row_id = cur.lastrowid
            cur.execute("SELECT note FROM canary WHERE id = %s", (row_id,))
            note = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM canary")
            total = cur.fetchone()[0]
        conn.commit()
    finally:
        conn.close()
    return {"wrote_id": row_id, "read_back": note, "rows": total}


def check_redis() -> dict[str, object]:
    """SET then GET a key through REDIS_URL."""
    import redis

    client = redis.from_url(os.environ["REDIS_URL"], socket_timeout=8)
    client.set("canary", STAMP)
    value = client.get("canary")
    return {"wrote": STAMP, "read_back": value.decode() if value else None,
            "keys": client.dbsize()}


CHECKS = {"postgres": check_postgres, "mysql": check_mysql, "redis": check_redis}


def run(name: str) -> dict[str, object]:
    """Run one check, turning any failure into a reportable result."""
    try:
        return {"ok": True, **CHECKS[name]()}
    except KeyError as exc:  # the variable was never injected
        return {"ok": False, "error": f"missing environment variable {exc}"}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}",
                "trace": traceback.format_exc(limit=3)}


def run_all() -> dict[str, object]:
    """Run every check and report a single verdict."""
    results = {name: run(name) for name in CHECKS}
    return {
        "ok": all(r["ok"] for r in results.values()),
        "stamp": STAMP,
        "echo": ECHO,
        "host": socket.gethostname(),
        "checks": results,
    }


class Handler(BaseHTTPRequestHandler):
    """Routes the canary's checks."""

    def _send(self, code: int, body: str, content_type: str = "text/plain") -> None:
        payload = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _json(self, code: int, body: dict[str, object]) -> None:
        self._send(code, json.dumps(body, indent=2), "application/json")

    def do_GET(self) -> None:  # noqa: N802 — BaseHTTPRequestHandler's interface
        """Dispatch a request."""
        path = self.path.split("?")[0].rstrip("/") or "/"
        if path in ("/", "/healthz"):
            return self._send(200, f"candor canary ok\nstamp={STAMP}\n")
        if path == "/env":
            return self._json(200, {"CANARY_ECHO": ECHO, "stamp": STAMP})
        if path == "/log":
            print(f"{LOG_MARKER} stamp={STAMP}", flush=True)
            return self._send(200, "logged\n")
        if path == "/all":
            result = run_all()
            return self._json(200 if result["ok"] else 503, result)
        if path.startswith("/db/"):
            name = path.rsplit("/", 1)[-1]
            if name not in CHECKS:
                return self._send(404, "unknown database\n")
            result = run(name)
            return self._json(200 if result["ok"] else 503, result)
        return self._send(404, "not found\n")

    def log_message(self, fmt: str, *args: object) -> None:
        """Log to stdout so the platform's runtime logs capture it."""
        sys.stdout.write("%s - %s\n" % (self.address_string(), fmt % args))
        sys.stdout.flush()


if __name__ == "__main__":
    print(f"canary listening on :{PORT} stamp={STAMP}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
