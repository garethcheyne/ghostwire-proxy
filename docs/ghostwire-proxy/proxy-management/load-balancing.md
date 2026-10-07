---
title: Load Balancing
excerpt: Spread a proxy host's traffic across several backend servers, with health checks and a live config preview
---

A proxy host normally forwards every request to one backend (its **forward host** and **port**). Switch it to **Load balanced** and Ghostwire builds an nginx `upstream` group instead, spreading requests across as many backend servers as you list: several Node or Python processes on one machine, several machines, or both.

## Turning it on

1. Open the proxy host (**Edit**) and find **Backends** on the Details tab.
2. Switch from **Single backend** to **Load balanced**. The current forward host is added as the first server, so nothing changes until you add more.
3. Add servers:
   - **Add server** — one host and port.
   - **Add a port range** — a host, a first port and a count. `10.0.0.5`, `8050`, `4` adds `10.0.0.5:8050` to `10.0.0.5:8053`. Ports already listed are skipped.
   - **Copy from forward host** — adds the single-backend forward host as a server.
4. Pick a **balancing method** (below), check the **Generated config** preview, and **Save Changes**.

Saving runs `nginx -t` on the new config first. If nginx rejects it, nothing is saved and the running config is untouched.

Switching back to **Single backend** removes the servers and the host goes straight to its forward host again, with exactly the config it had before.

## Balancing methods

| Method | What it does | Use it when |
|--------|--------------|-------------|
| **Round robin** (default) | Takes turns, in proportion to each server's weight | Requests all cost roughly the same |
| **Least connections** | Sends each request to the server with the fewest requests in flight | Some pages are much slower than others (recommended for most apps) |
| **IP hash** | The same visitor IP always reaches the same server | The app keeps sessions in process memory (sticky sessions) |
| **URI hash** | The same URL always reaches the same server (consistent hashing) | Each server keeps its own cache |
| **Random, two choices** | Picks two servers at random and uses the less busy one | Many servers, several Ghostwire workers |

nginx only allows **backup** servers with round robin and least connections, so the editor and the API refuse backups with the hash and random methods.

## Server settings

| Setting | Meaning | Default |
|---------|---------|---------|
| **Weight** | Relative share of traffic, 1–100 | 1 |
| **Max connections** | Cap on simultaneous connections to this server; empty = unlimited | unlimited |
| **Max fails** / **Fail timeout** | After this many failed requests within the timeout, nginx skips the server for the timeout (0 = never) | 3 / 30 s |
| **Backup** | Only receives traffic when every primary server is unavailable | off |
| **Maintenance (down)** | Kept in the group (hash methods keep their mapping) but sent no traffic — use it while deploying to that server | off |
| **Enabled** | Disabled servers are left out of the config | on |

## What nginx gets

For four Node processes with least connections:

```nginx
upstream upstream_<host id> {
    # Load balancing: Least connections
    zone upstream_<host id> 64k;
    least_conn;
    server 10.0.0.5:8050;
    server 10.0.0.5:8051;
    server 10.0.0.5:8052;
    server 10.0.0.5:8053;
    keepalive 32;
}

location / {
    proxy_pass http://upstream_<host id>;
    proxy_http_version 1.1;
    proxy_set_header Connection "";
    proxy_next_upstream error timeout http_502 http_503 http_504;
    proxy_next_upstream_tries 3;
    ...
}
```

- **zone** shares connection counts between nginx workers, so least connections, random and max connections see the whole picture.
- **keepalive** keeps idle connections open to the servers (default 32 per worker; 0 turns it off). HTTP/1.1 and an empty `Connection` header are set for you; with WebSockets on, a per-host map keeps upgrades working without breaking keepalive.
- **proxy_next_upstream** retries a request on the next server when one fails to connect, times out or answers 502/503/504, at most three tries. nginx never retries a POST or other non-idempotent request once it has been sent.

The **Generated config** box in the editor shows this block live for whatever is on screen, rendered by the same code that writes the real config.

## Health checks

Every minute, Ghostwire probes each enabled server of every monitored host directly at its own host and port:

- **HTTP GET** on a path you choose (default `/`, e.g. `/healthz`). Any status below 500 counts as up; a 5xx counts as down.
- **TCP connect** if the app has no HTTP endpoint.
- A timeout (1–30 s, default 5).

Each server's status, response time and last error show as a dot in the editor's server table, and the proxy hosts list shows **Load balanced · N backends · M healthy**. **Check now** in the editor probes immediately.

The host as a whole counts as up while any server outside maintenance answers, so a host-down alert means every backend is unreachable.

### Taking failed servers out automatically

nginx already skips a server that fails real requests (**max fails**). If you also want health checks to remove a server, turn on **Take failed servers out automatically**: after two failed checks in a row the server is rendered `down` (marked **Auto-down** in the editor), and it goes back in as soon as it answers. The last server standing is never taken out. Each change goes through `nginx -t` before nginx reloads.

### Safety

Probes only ever contact the configured host and port of each server, never follow redirects, and ignore proxy settings in the environment; the path can't point the probe anywhere else.

## Which backend served a request

With **Traffic Logging** on, every logged request records the backend that answered it: the address nginx used, that backend's status and response time, the matching server from this host's list, how many servers were tried, and whether nginx failed over (with each attempt's address, status and time when it did). Single-backend hosts record their forward host as before.

## API

All endpoints are under `/api/proxy-hosts` and need an admin, except reads and the preview.

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/` | Create a host; include `lb_method` and `upstream_servers` to create it load balanced |
| `PUT` | `/{id}` | Update a host; `upstream_servers` (when sent) replaces the whole list in one validated apply — rows with an `id` are updated and keep their health history, rows without one are added, missing rows are removed; `[]` returns to a single backend |
| `GET` | `/{id}/upstreams` | The servers with their latest health |
| `POST` | `/{id}/upstreams` | Add one server |
| `PUT` / `PATCH` | `/{id}/upstreams/{server_id}` | Change one server (only the fields sent) |
| `DELETE` | `/{id}/upstreams/{server_id}` | Remove one server |
| `POST` | `/{id}/upstreams/check` | Probe the servers now |
| `POST` | `/upstream-preview` | Render the upstream block for unsaved settings; returns `upstream_block`, `location_directives`, `errors`, `warnings` |

Host fields: `lb_method` (`round_robin`, `least_conn`, `ip_hash`, `hash_uri`, `random_two`), `upstream_keepalive` (0–1024), `health_check_type` (`http`, `tcp`), `health_check_path`, `health_check_timeout` (1–30), `lb_auto_down`.

Server fields: `host`, `port`, `weight` (1–100), `max_fails` (0–100), `fail_timeout` (1–3600 s), `max_conns` (1–100000 or null), `backup`, `down`, `enabled`; read-only `last_status` (`unknown`, `up`, `down`), `last_latency_ms`, `last_error`, `last_check_at`, `auto_down`.

Example — four Node processes behind least connections:

```bash
curl -X PUT https://proxy.example.com/api/proxy-hosts/<id> \
  -H "Content-Type: application/json" -b <session cookie> \
  -d '{
    "lb_method": "least_conn",
    "health_check_path": "/healthz",
    "upstream_servers": [
      {"host": "10.0.0.5", "port": 8050},
      {"host": "10.0.0.5", "port": 8051},
      {"host": "10.0.0.5", "port": 8052},
      {"host": "10.0.0.5", "port": 8053}
    ]
  }'
```

A group nginx would reject (no primary server, a backup with a hash method, the same server twice, an invalid host) is refused with `422` and a message saying why.
