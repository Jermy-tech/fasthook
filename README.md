# fasthook 🪝

A dead-simple local webhook receiver for testing and development.
Because sometimes you just need to see what’s being sent to your endpoint.

[![PyPI Version](https://img.shields.io/pypi/v/fasthook)](https://pypi.org/project/fasthook/)
[![PyPI Downloads](https://img.shields.io/pypi/dm/fasthook)](https://pypi.org/project/fasthook/)
[![License](https://img.shields.io/github/license/Jermy-tech/fasthook)](https://github.com/Jermy-tech/fasthook/blob/main/LICENSE)
[![GitHub Repo](https://img.shields.io/badge/GitHub-fasthook-blue?logo=github)](https://github.com/Jermy-tech/fasthook)

```bash
pip install fasthook
fasthook listen 3000
```

Just like that, you're catching webhooks at:
👉 **[http://localhost:3000](http://localhost:3000)**

---

# Why fasthook?

When you’re integrating Stripe, PayPal, Clerk, GitHub, or any service that fires webhooks, you hit the same problem:

**You can’t see what they’re sending without tunnels, accounts, dashboards, or annoying setup.**

fasthook fixes that:
✅ No ngrok
✅ No cloud dashboard
✅ No signup
❗ Just a lightweight local server that captures everything.

---

# 🚀 What's New in v2.0.0

fasthook 2.0 is a complete upgrade, built to move from “dev toy” → **production-ready tooling**.

### **⚡ Performance & Reliability**

* Fully async architecture (FastAPI + Uvicorn)
* Connection pooling for forwarding
* Bounded queues prevent memory bloat
* Configurable concurrency & rate limits
* Graceful shutdown + full cleanup
* Structured logging with optional log rotation

### **🎭 Mock Server Mode**

* Scripted responses for any endpoint
* Dynamic sequences (return different responses per call)
* Per-route delays, status codes, and bodies
* Built-in health & stats endpoints
* Wildcard paths (`/api/*`) supported

### **🔄 Event Replay**

* Replay saved events with original timing
* Adjustable playback speed (`0.5x → 10x`)
* Rate limiting to avoid flooding targets
* Replays to *any* URL
* Great for load testing or staging environments

### **🧰 Developer Quality-of-Life**

* Pretty printed JSON
* Quiet mode for CI
* Save-event output as newline-delimited JSON
* Automatic retry logic (exponential backoff)
* Debug mode for introspecting requests

---

# Installation

```bash
pip install fasthook
```

Requires **Python 3.8+**.

---

# Quick Start

Start listening on port 3000:

```bash
fasthook listen 3000
```

Now any request to `http://localhost:3000/*` is logged with full details.

---

# Features

### 🔍 Inspect Everything

* Method, path, headers, IP, query params
* JSON body or raw body
* Pretty JSON display

### 💾 Save Webhooks

* Save all events to newline-delimited JSON
* Works great with `jq`, pandas, or custom scripts

### 🔁 Forward Webhooks

* Forward to another endpoint
* Retry with exponential backoff
* Connection pooling
* Concurrency controls

### 🎭 Mock Server

* Script dynamic responses
* Wildcards supported
* Per-call sequences
* Built-in status, logs, delays

### 🔄 Event Replay

* Replay saved events exactly as received
* Preserve timing or speed up
* Target any URL
* Limit RPS to avoid overload

### ⚙️ Production-Ready

* Logging (stdout/file)
* Log rotation
* Resource cleanup
* Rate limiting
* Graceful shutdown

---

# Usage Examples

### Listen on port 3000

```bash
fasthook listen 3000
```

### Save events

```bash
fasthook listen 3000 --save events.json
```

### Forward with retries

```bash
fasthook listen 3000 --forward http://example.com/webhook --forward-retries 3
```

### Mock server

```bash
fasthook listen 3000 --mock responses.json
```

### Replay events (2× faster)

```bash
fasthook replay events.json --target http://localhost:8000 --rate 2.0
```

### Full setup

```bash
fasthook listen 3000 --save events.json --forward http://example.com/webhook --pretty --exit-after 100
```

---

# Mock Server Example (`responses.json`)

```json
{
  "defaults": {
    "status": 200,
    "delay": 0,
    "body": {"status": "ok"}
  },
  "routes": {
    "/webhook": {
      "POST": {
        "status": 201,
        "body": {"success": true, "id": "123"},
        "delay": 0.5
      },
      "GET": {
        "status": 200,
        "body": {"message": "Hello World"}
      }
    },
    "/api/*": {
      "ANY": {
        "status": 404,
        "body": {"error": "Not found"}
      }
    }
  }
}
```

Run it:

```bash
fasthook mock 3000 --spec responses.json
```

---

# What It Looks Like

```
============================================================
[2025-01-15T10:30:45.123Z] POST /webhook/stripe
IP: 192.168.1.100
Query: {'test': 'true'}
Headers:
  content-type: application/json
  stripe-signature: t=123456,v1=abcdef...
JSON Body:
{
  "id": "evt_123",
  "type": "payment_intent.succeeded",
  ...
}
============================================================
```

---

# Command Reference

### `fasthook listen`

```
PORT

--save PATH
--forward URL
--forward-retries N
--forward-concurrency N
--pretty
--quiet
--log-file PATH
--log-level LEVEL
--log-rotate
--exit-after N
--mock SPEC
--debug
--host HOST
```

### `fasthook replay`

```
EVENTS_FILE

--rate MULTIPLIER
--once
--target URL
--delay SECONDS
--max-rps RATE
```

### `fasthook mock`

```
PORT

--spec PATH
--host HOST
--quiet
```

---

# Saved Events Format

Events saved with `--save` are newline-delimited JSON:

```json
{"timestamp": "...", "method": "POST", "path": "...", "headers": {...}, "json": {...}}
```

Perfect for use with:

```bash
jq
pandas
grep
custom scripts
```

---

# Common Use Cases

**Local Stripe testing**

```bash
fasthook listen 3000 --save stripe.json --pretty
```

**Forward to your API**

```bash
fasthook listen 8080 --forward http://localhost:5000/webhook
```

**Mock endpoints in CI**

```bash
fasthook mock 9000 --spec test-responses.json --quiet
```

**Load testing with replay**

```bash
fasthook replay events.json --target http://staging.example.com --rate 5 --max-rps 80
```

---

# Testing

fasthook uses pytest with async support.

```
pytest
```

Coverage is ~74%.

---

# Development

```bash
git clone https://github.com/Jermy-tech/fasthook
cd fasthook
pip install -e .
pytest
fasthook listen 3000
```

---

# How It Works (High-Level)

* Built on **FastAPI + Uvicorn**
* Single catch-all route accepts *any* HTTP method on *any* path
* Logs the request, optionally saves, forwards, or mocks responses
* Forwarding uses an async connection pool
* Replay uses timestamped events + async dispatch
* Engine is fully asynchronous for high concurrency

---

# License

MIT License — see LICENSE.

---

# Author

Built by **Jermy Peña**

---

# Links

* GitHub: [https://github.com/Jermy-tech/fasthook](https://github.com/Jermy-tech/fasthook)
* Issues: [https://github.com/Jermy-tech/fasthook/issues](https://github.com/Jermy-tech/fasthook/issues)
* PyPI: [https://pypi.org/project/fasthook/](https://pypi.org/project/fasthook/)