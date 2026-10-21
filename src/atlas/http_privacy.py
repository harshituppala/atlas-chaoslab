"""Browser response policy; never cache tenant documents or decisions."""

import re

from starlette.datastructures import MutableHeaders


class ResponsePrivacy:
    def __init__(self, app, form_origin=None):
        if form_origin is not None and not re.fullmatch(
            r"https://[A-Za-z0-9][A-Za-z0-9.-]*(?::443)?", form_origin
        ):
            raise ValueError("Form origin must be a pinned HTTPS hostname")
        self.app = app
        self.form_target = " 'self'" + (" " + form_origin if form_origin else "")

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def private_send(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["X-Content-Type-Options"] = "nosniff"
                headers["X-Frame-Options"] = "DENY"
                headers["Referrer-Policy"] = "no-referrer"
                headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
                if scope["path"].startswith(("/api/", "/auth/")):
                    headers["Cache-Control"] = "no-store"
                    headers.add_vary_header("Authorization")
                    headers.add_vary_header("Cookie")
                if "text/html" in headers.get("Content-Type", ""):
                    headers["Content-Security-Policy"] = (
                        "default-src 'self'; script-src 'self'; style-src 'self'; "
                        "connect-src 'self'; img-src 'self' data:; font-src 'self'; "
                        "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action"
                        + self.form_target
                    )
            await send(message)

        return await self.app(scope, receive, private_send)
