from __future__ import annotations

import os
import secrets
from datetime import datetime, timezone
from urllib.parse import urlsplit

from flask import Flask, abort, flash, redirect, render_template, request, url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Index


db = SQLAlchemy()


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY") or secrets.token_hex(32),
        SQLALCHEMY_DATABASE_URI=os.environ.get("DATABASE_URL", "sqlite:///linklog.db"),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        MAX_CONTENT_LENGTH=16 * 1024,
    )
    if test_config:
        app.config.update(test_config)

    db.init_app(app)

    @app.after_request
    def add_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; style-src 'self'; img-src 'self' data:; base-uri 'self'; form-action 'self'; frame-ancestors 'none'",
        )
        return response

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.post("/links")
    def create_link():
        destination = request.form.get("destination", "").strip()
        if not _valid_destination(destination):
            flash("Enter a complete destination URL that starts with https:// or http://.", "error")
            return render_template("index.html", destination=destination), 400

        link = TrackedLink(
            destination_url=destination,
            tracking_code=secrets.token_urlsafe(9),
            access_key=secrets.token_urlsafe(24),
            created_at=datetime.now(timezone.utc),
        )
        db.session.add(link)
        db.session.commit()
        return render_template("created.html", link=link)

    @app.get("/t/<tracking_code>")
    def track(tracking_code: str):
        link = db.session.execute(
            db.select(TrackedLink).where(TrackedLink.tracking_code == tracking_code)
        ).scalar_one_or_none()
        if link is None:
            abort(404)
        # Only use the direct connection address. Forwarded headers are untrusted
        # unless a separately configured, trusted proxy middleware is installed.
        event = Visit(
            link_id=link.id,
            ip_address=request.remote_addr or "unknown",
            user_agent=request.headers.get("User-Agent", "")[:512],
            visited_at=datetime.now(timezone.utc),
        )
        db.session.add(event)
        db.session.commit()
        return redirect(link.destination_url, code=302)

    @app.get("/results/<access_key>")
    def results(access_key: str):
        link = db.session.execute(
            db.select(TrackedLink).where(TrackedLink.access_key == access_key)
        ).scalar_one_or_none()
        if link is None:
            abort(404)
        visits = db.session.execute(
            db.select(Visit).where(Visit.link_id == link.id).order_by(Visit.visited_at.desc())
        ).scalars().all()
        response = app.make_response(render_template("results.html", link=link, visits=visits))
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.errorhandler(404)
    def not_found(_error):
        return render_template("404.html"), 404

    with app.app_context():
        db.create_all()

    return app


def _valid_destination(value: str) -> bool:
    try:
        parts = urlsplit(value)
        return (
            parts.scheme.lower() in {"http", "https"}
            and bool(parts.hostname)
            and not any(ord(char) < 32 for char in value)
        )
    except ValueError:
        return False


class TrackedLink(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    destination_url = db.Column(db.Text, nullable=False)
    tracking_code = db.Column(db.String(32), nullable=False, unique=True, index=True)
    access_key = db.Column(db.String(64), nullable=False, unique=True, index=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False)
    visits = db.relationship("Visit", backref="link", cascade="all, delete-orphan", lazy="select")


class Visit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    link_id = db.Column(db.Integer, db.ForeignKey("tracked_link.id", ondelete="CASCADE"), nullable=False)
    ip_address = db.Column(db.String(45), nullable=False)
    user_agent = db.Column(db.String(512), nullable=False, default="")
    visited_at = db.Column(db.DateTime(timezone=True), nullable=False)
    __table_args__ = (Index("ix_visit_link_time", "link_id", "visited_at"),)


if __name__ == "__main__":
    create_app().run(debug=os.environ.get("FLASK_DEBUG") == "1")
