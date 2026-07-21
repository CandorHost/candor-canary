# candor-canary

The end-to-end test workload for [Candor Deploy](https://candorhost.com). Not a
product — a probe. It exists so we can answer "does the platform actually work"
with evidence instead of confidence.

The platform's own status is not proof. A pod reaching `Ready` says nothing
about whether a client can authenticate against the database it was given, and
a green build says nothing about whether the URL we handed the customer serves
anything. Every route here closes one of those gaps by *doing* the thing.

## Routes

| Route | Proves |
|---|---|
| `/` `/healthz` | The generated hostname routes to this container, over TLS |
| `/env` | Environment variables set in the portal reach the process |
| `/db/postgres` | `DATABASE_URL` connects, writes a row, reads it back |
| `/db/mysql` | `MYSQL_URL` connects, writes a row, reads it back |
| `/db/redis` | `REDIS_URL` connects, SETs and GETs |
| `/log` | Prints `canary-log-marker` to stdout, for the runtime-log view |
| `/all` | Runs every check; `200` only if all pass, `503` otherwise |

`/all` is the one the runner asserts on: one request, one verdict.

## Environment

| Variable | Set by |
|---|---|
| `PORT` | The platform |
| `DATABASE_URL` | Attaching a Postgres database |
| `MYSQL_URL` | Attaching a MySQL database (with the variable name overridden — two databases cannot both be `DATABASE_URL`) |
| `REDIS_URL` | Attaching a Redis database |
| `CANARY_STAMP` | The runner, so it can prove *which* build is serving |
| `CANARY_ECHO` | The runner, to verify env injection end to end |

Every check degrades honestly: a missing variable or an unreachable database
returns `ok: false` with the reason, rather than a stack trace or a hang.

## Branches

- `main` — builds and runs.
- `broken-build` — deliberately fails to build, so we can verify that a failed
  deployment is reported as failed *and* that its build log explains why.
