# fasthook 🪝

A dead-simple local webhook receiver for testing and development. Because sometimes you just need to see what's being sent to your endpoint.

```bash
pip install fasthook
fasthook listen 3000
```

That's it. You're now catching webhooks on `http://localhost:3000`.

## Why?

You know that moment when you're integrating a third-party service and you need to see what they're actually sending to your webhook? Or when you're testing a payment provider's IPN callbacks locally? Yeah, that's what this is for.

No tunnels, no forwarding services, no accounts. Just a local server that shows you everything that hits it.

## Installation

```bash
pip install fasthook
```

Requires Python 3.8 or higher.

## Quick Start

Start listening on port 3000:

```bash
fasthook listen 3000
```

Now any request to `http://localhost:3000/*` will be captured and displayed in your terminal.

## Features

**See everything**: Method, path, headers, query params, body (JSON or raw)

**Save to file**: Log all events to a JSON file for later analysis

**Forward requests**: Relay incoming webhooks to another URL (like your actual endpoint)

**Pretty output**: Optional pretty-printed JSON for easier reading

**Quiet mode**: Suppress output when you just want to save/forward

## Usage Examples

Basic listening:
```bash
fasthook listen 3000
```

Save all events to a file:
```bash
fasthook listen 3000 --save events.json
```

Forward to your actual endpoint:
```bash
fasthook listen 3000 --forward http://example.com/webhook
```

Do everything at once:
```bash
fasthook listen 3000 --save events.json --forward http://example.com/webhook --pretty
```

Bind to a different host:
```bash
fasthook listen 3000 --host 0.0.0.0
```

Run quietly (only show errors):
```bash
fasthook listen 3000 --save events.json --quiet
```

## What You'll See

When a webhook hits your endpoint, you'll see something like this:

```
============================================================
[2025-01-15T10:30:45.123Z] POST /webhook/stripe
IP: 192.168.1.100
Query: {'test': 'true'}
Headers:
  content-type: application/json
  user-agent: Stripe/1.0
  stripe-signature: t=123456,v1=abcdef...
JSON Body:
{
  "id": "evt_123",
  "type": "payment_intent.succeeded",
  "data": {
    "object": {
      "id": "pi_123",
      "amount": 2000,
      "currency": "usd"
    }
  }
}
============================================================
```

## Command Options

```
fasthook listen PORT [OPTIONS]

Arguments:
  PORT                  Port number to listen on (required)

Options:
  --save PATH          Save events to a JSON file (newline-delimited)
  --forward URL        Forward all requests to this URL
  --pretty             Pretty-print JSON output to console
  --quiet              Suppress console output (except errors)
  --host HOST          Host to bind to (default: 127.0.0.1)
  --debug              Run in debug mode
  --help               Show help message
```

## Saved Events Format

When using `--save`, events are saved as newline-delimited JSON. Each line is a complete event:

```json
{"timestamp": "2025-01-15T10:30:45.123Z", "method": "POST", "path": "/webhook", "headers": {...}, "query": {...}, "json": {...}, "raw": "", "ip": "192.168.1.100"}
```

This format is easy to parse and works great with tools like `jq`:

```bash
# Pretty print all events
cat events.json | jq '.'

# Filter POST requests only
cat events.json | jq 'select(.method == "POST")'

# Count events by path
cat events.json | jq -r '.path' | sort | uniq -c
```

## Testing

We use pytest with full async support. The test suite has 100% success rate with 98% code coverage.

Run tests:
```bash
pytest
```

## Development

```bash
# Clone the repo
git clone https://github.com/Jermy-tech/fasthook.git
cd fasthook

# Install in development mode
pip install -e .

# Run fasthook
fasthook listen 3000
```

## Common Use Cases

**Testing Stripe webhooks locally**: 
```bash
fasthook listen 3000 --save stripe-events.json --pretty
```

**Debugging third-party API callbacks**:
```bash
fasthook listen 8080 --forward http://localhost:5000/api/callback
```

**Recording webhook payloads for documentation**:
```bash
fasthook listen 3000 --save examples.json --pretty
```

**Running a mock webhook endpoint in CI/CD**:
```bash
fasthook listen 9000 --quiet --save test-webhooks.json
```

## How It Works

fasthook is built on FastAPI and Uvicorn. It creates a catch-all route that accepts any HTTP method on any path, logs the request details, and optionally saves or forwards the data.

The server runs asynchronously, so it can handle multiple concurrent requests without blocking. When forwarding is enabled, requests are relayed with the same method, headers, and body (minus the `host` header).

## License

MIT License - see LICENSE file for details.

## Contributing

Found a bug? Want a feature? Pull requests are welcome!

## Author

Built by Jermy Pena

## Links

- GitHub: https://github.com/Jermy-tech/fasthook
- Issues: https://github.com/Jermy-tech/fasthook/issues