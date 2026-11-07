
import os
import secrets
import hmac
from datetime import datetime, timezone
from urllib.parse import urlparse

from flask import Flask, request, jsonify, redirect
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "development-only")
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
    "DATABASE_URL", "sqlite:///tracker.db"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


# DATABASE MODELS

class TrackingLink(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(32), unique=True, nullable=False)
    destination = db.Column(db.Text, nullable=False)
    campaign = db.Column(db.String(150))
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )


class ClickEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    link_id = db.Column(
        db.Integer,
        db.ForeignKey("tracking_link.id"),
        nullable=False
    )
    clicked_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )
    referrer = db.Column(db.String(255))


# AUTHENTICATION

def authorized():
    expected = os.getenv("API_KEY", "")
    supplied = request.headers.get("X-API-Key", "")

    return bool(expected) and hmac.compare_digest(
        expected.encode(), supplied.encode()
    )


# URL VALIDATION

def valid_url(url):
    try:
        parsed = urlparse(url)
        return (
            parsed.scheme in ("http", "https")
            and bool(parsed.hostname)
            and not parsed.username
            and not parsed.password
        )
    except ValueError:
        return False


# HEALTH CHECK

@app.get("/health")
def health():
    return jsonify({
        "status": "online",
        "service": "IP-Logger"
    })


# CREATE TRACKING LINK

@app.post("/api/v1/links")
def create_link():
    if not authorized():
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json(silent=True) or {}
    destination = data.get("url", "").strip()

    if not valid_url(destination):
        return jsonify({"error": "Invalid URL"}), 400

    code = secrets.token_urlsafe(7)

    while TrackingLink.query.filter_by(code=code).first():
        code = secrets.token_urlsafe(7)

    link = TrackingLink(
        code=code,
        destination=destination,
        campaign=data.get("campaign")
    )

    db.session.add(link)
    db.session.commit()

    return jsonify({
        "code": code,
        "tracking_url": request.host_url + "t/" + code
    }), 201


# TRACK CLICK AND REDIRECT

@app.get("/t/<code>")
def track(code):
    link = TrackingLink.query.filter_by(code=code).first()

    if not link:
        return jsonify({"error": "Link not found"}), 404

    event = ClickEvent(
        link_id=link.id,
        referrer=request.referrer[:255] if request.referrer else None
    )

    db.session.add(event)
    db.session.commit()

    response = redirect(link.destination, code=302)
    response.headers["Cache-Control"] = "no-store"

    return response


# GET ALL LINKS

@app.get("/api/v1/links")
def list_links():
    if not authorized():
        return jsonify({"error": "Unauthorized"}), 401

    links = TrackingLink.query.order_by(
        TrackingLink.id.desc()
    ).limit(100).all()

    result = []

    for link in links:
        clicks = ClickEvent.query.filter_by(
            link_id=link.id
        ).count()

        result.append({
            "code": link.code,
            "destination": link.destination,
            "campaign": link.campaign,
            "clicks": clicks
        })

    return jsonify(result)


# GET ANALYTICS

@app.get("/api/v1/analytics/<code>")
def analytics(code):
    if not authorized():
        return jsonify({"error": "Unauthorized"}), 401

    link = TrackingLink.query.filter_by(code=code).first()

    if not link:
        return jsonify({"error": "Not found"}), 404

    events = ClickEvent.query.filter_by(
        link_id=link.id
    ).order_by(
        ClickEvent.clicked_at.desc()
    ).limit(100).all()

    return jsonify({
        "code": link.code,
        "destination": link.destination,
        "total_clicks": ClickEvent.query.filter_by(
            link_id=link.id
        ).count(),
        "recent_clicks": [
            {
                "time": event.clicked_at.isoformat(),
                "referrer": event.referrer
            }
            for event in events
        ]
    })


# DELETE LINK

@app.delete("/api/v1/links/<code>")
def delete_link(code):
    if not authorized():
        return jsonify({"error": "Unauthorized"}), 401

    link = TrackingLink.query.filter_by(code=code).first()

    if not link:
        return jsonify({"error": "Not found"}), 404

    ClickEvent.query.filter_by(link_id=link.id).delete()
    db.session.delete(link)
    db.session.commit()

    return jsonify({"message": "Link deleted"})


# INITIALIZE DATABASE

with app.app_context():
    db.create_all()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
