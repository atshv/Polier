# Authentication and safety

The dashboard is a local operator tool. Its protection is layered: loopback by default, an optional token, an action header for writes and a same-origin check.

## Tokens

Start the server with a token to require it on every request:

```bash
POLIER_DASHBOARD_TOKEN=$(openssl rand -hex 24) python3 tools/serve.py . --port 8765
```

Send it in one of three ways:

| Where | Example |
|---|---|
| `Authorization` header | `Authorization: Bearer <token>` |
| query parameter | `/api/snapshot?token=<token>` |
| cookie | `polier_token=<token>` |

A missing or wrong token answers `401`.

```bash
curl -s -H "Authorization: Bearer $POLIER_DASHBOARD_TOKEN" http://127.0.0.1:8765/api/snapshot
```

## The action header

Every request that changes something (`POST`, `PUT`, `PATCH`, `DELETE`) must carry:

```text
X-Polier-Action: 1
```

Browsers cannot add it in a cross-site form post, so a malicious page cannot trigger writes. The one exception is `POST /api/automations/run`, which is a read.

## Same origin

When a request carries an `Origin` header, its host must match the server's `Host`; otherwise the write is refused with `403`.

## Read-only mode

`--read-only` (or `--role viewer`) refuses every write with `403`. Use it for a shared status screen.

## Network exposure

A bind to anything but `127.0.0.1`, `localhost` or `::1` only answers API calls with a token. Even then, put a TLS reverse proxy in front.

> [!WARNING]
> Sessions and gate jobs run commands in your project. Anyone who can call the API with a valid token can run them. Treat the token like an SSH key.
