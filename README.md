# IP-Logger
Linklog

A small Flask + SQLite application for link click logging. It creates an unguessable public tracking URL and a separate private results URL for each destination. Visiting the tracking URL records the request's direct peer IP address, User-Agent, and UTC timestamp, then immediately responds with HTTP 302.

## Setup

Requires Python 3.10 or newer.

```powershell
cd path\to\linklog
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$env:SECRET_KEY = python -c "import secrets; print(secrets.token_hex(32))"
python app.py
```

Open http://127.0.0.1:5000. The SQLite database (`instance/linklog.db`) is created automatically. For local development, the app uses a random secret if `SECRET_KEY` is unset; set a stable secret for deployments. Set `DATABASE_URL` to use another SQLAlchemy database URL. Set `FLASK_DEBUG=1` only for local development.

## How to use

1. Enter an absolute `http://` or `https://` destination URL and submit.
2. Share the public `/t/<tracking-code>` link.
3. Keep the private `/results/<access-key>` URL secret. Anyone with that URL can view its logs.

## Privacy and deployment

This app records personal data (IP address and User-Agent). Tell visitors what you collect and why, use it only with appropriate authorization, restrict access to the results URL, and set a retention policy before public deployment. The link creation page reminds creators to disclose tracking to visitors. Use HTTPS in deployment. The app deliberately ignores `X-Forwarded-For` because clients can spoof it; if deployed behind a proxy, configure trusted proxy handling at the server boundary before relying on forwarded client IPs. No cookies or external assets are used.

There is no authentication beyond the private access key, so treat it as a password. This starter app does not include link deletion, log expiration, rate limiting, or user accounts. Use a production WSGI server and add those controls as appropriate before exposing it publicly.
