# candor-canary

A working example for [Candor Deploy](https://candorhost.com) — and the probe we
run against our own platform before we tell you it works.

It is one small app that uses **Postgres, MySQL and Redis at once**, gets all
three wired up by a [`.candorfile`](.candorfile), and proves it by writing a row
to each and reading it back. If you want to see what a real Candor Deploy
repository looks like, read [`.candorfile`](.candorfile) and
[`app/main.py`](app/main.py) — that is the whole thing.

We deploy this on every platform change. "It started" is not the same as "a
customer's app can authenticate and write", and only the second one is what you
paid for.

---

## The `.candorfile`

Put it at the root of your repository. Everything in it is also editable in the
portal — the file and the form are two views of one thing. The file wins.

```yaml
services:
  canary:
    root: app
    databases: [postgres, mysql, redis]
    env:
      CANARY_ECHO: injected-by-candorfile
      CANARY_SECRET: {generate: hex32}
```

The file is read at the exact commit being built, so it travels with your code:
a branch that needs a different root or an extra database just says so.

### Options

Every option is optional. Anything you leave out keeps the platform's default,
and anything you set in the portal that the file does not mention stays put.

| Option | What it does |
|---|---|
| `root` | Build from this subdirectory instead of the repository root. For monorepos. |
| `databases` | Provision these databases and inject their connection strings. `postgres`, `mysql`, `redis`; one value or a list. |
| `database` | The same thing, singular, when you only want one. |
| `env` | Environment for your app: literals, or `{generate: …}` for a secret you never have to invent. |
| `port` | The port your process listens on. Only needed for Dockerfile builds — nixpacks-built apps are handed `$PORT` and should use it. |
| `dockerfile` | Build with this Dockerfile instead of nixpacks. Naming one opts you out of nixpacks. |
| `builder` | `nixpacks` or `dockerfile`. Force nixpacks even when a Dockerfile exists. |
| `memory` | Memory in MB, subject to your plan's pool. |
| `kind` | `app` (default), `worker` (no URL, no inbound traffic), or `static`. |

### Databases

Naming a database provisions it as its own service and injects its connection
string once it is ready:

| Engine | Variable |
|---|---|
| `postgres` | `DATABASE_URL` |
| `mysql` | `DATABASE_URL`, or `MYSQL_URL` if Postgres already took it |
| `redis` | `REDIS_URL` |

The first relational engine you name wins `DATABASE_URL`; a second gets an
engine-specific name. **If you set the variable yourself, we never overwrite
it** — point it wherever you like.

A database's credentials do not exist until it has finished starting, which
takes a minute or so. The platform remembers the promise and keeps it as soon
as it can, normally well before your first build finishes.

> **Postgres and SQLAlchemy:** the injected URL uses the standard
> `postgresql://` scheme. If your app is built on psycopg 3 — which SQLAlchemy
> uses by default on new projects — it wants `postgresql+psycopg://`. Rewrite
> the scheme in your app, or set `DATABASE_URL` yourself.

### Generated secrets

```yaml
env:
  JWT_SECRET: {generate: hex32}
```

Minted server-side, stored only in your service's environment, never returned
to a browser and never in your repository. `hex32` is 32 random bytes rendered
as 64 hex characters (256-bit) — the strength a signing key wants. `hex64` is
double that.

Generated once, at creation. Re-deploying does not churn your secrets.

### Mistakes

A `.candorfile` never breaks a deploy. Anything the platform cannot understand —
an unknown option, an unsafe path, a database engine we do not run — is reported
and skipped, and the rest of the file still applies. Your service is always
created.

### Filename

`.candorfile` is the name. `.candorhost` also works if you prefer it.

---

## What this app does

| Route | What it proves |
|---|---|
| `/` `/healthz` | The hostname routes here, over TLS |
| `/env` | Environment from the `.candorfile` reached the process |
| `/db/postgres` | `DATABASE_URL` connects, writes a row, reads it back |
| `/db/mysql` | `MYSQL_URL` connects, writes a row, reads it back |
| `/db/redis` | `REDIS_URL` connects, SETs and GETs |
| `/log` | Prints a marker to stdout, for the portal's log view |
| `/all` | Runs every check; `200` only if all pass, `503` otherwise |

Every check degrades honestly: a missing variable or an unreachable database
returns `ok: false` with the reason, never a hang or a stack trace.

## Deploying it yourself

Fork it, then in the portal: **+ App**, pick your fork, **Create**. The
`.candorfile` does the rest — three databases appear alongside it and their
URLs land in the app's environment. When it goes live, open `/all`.

## Branches

- `main` — builds and runs.
- `broken-build` — fails to resolve its dependencies on purpose, so we can check
  that a failed deployment says *why* in its build log.
