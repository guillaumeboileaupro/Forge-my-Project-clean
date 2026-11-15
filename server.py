"""Serveur web local uniquement, sans dependance externe."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from generator import generate, validate
from forge import web
import json
import re

ROOT = Path(__file__).parent
STATIC = {
    "/": (ROOT / "ui" / "index.html", "text/html; charset=utf-8"),
    "/legacy": (ROOT / "ui" / "legacy.html", "text/html; charset=utf-8"),
    "/css/app.css": (ROOT / "ui" / "css" / "app.css", "text/css; charset=utf-8"),
    "/js/app.js": (ROOT / "ui" / "js" / "app.js", "text/javascript; charset=utf-8"),
    "/js/legacy.js": (ROOT / "ui" / "js" / "legacy.js", "text/javascript; charset=utf-8"),
}
LOCAL_HOST = re.compile(r"^(?:127\.0\.0\.1|localhost)(?::[0-9]{1,5})?$")
LOCAL_ORIGIN = re.compile(r"^http://(?:127\.0\.0\.1|localhost)(?::[0-9]{1,5})?$")
LEGACY_LIMIT = 16384
API_LIMIT = 65536
FILES_API_LIMIT = 2500000
API_POST = {
    "/api/plan": (web.plan_payload, API_LIMIT),
    "/api/archive": (web.archive_payload, FILES_API_LIMIT),
    "/api/files/validate": (web.preview_validate_payload, FILES_API_LIMIT),
    "/api/answers/validate": (web.answers_validate_payload, API_LIMIT),
    "/api/profiles": (web.profile_create_payload, API_LIMIT),
    "/api/skills/search": (web.skills_search_payload, API_LIMIT),
    "/api/skills/verify": (web.skills_verify_payload, API_LIMIT),
}
PROFILE_PATH = re.compile(r"^/api/profiles/([a-z0-9][a-z0-9-]{0,47})$")


class Handler(BaseHTTPRequestHandler):
    def reply(self, code, content, media="text/plain; charset=utf-8", download=None):
        self.send_response(code)
        self.send_header("Content-Type", media)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'; style-src 'self'; script-src 'self'; connect-src 'self'")
        if download:
            self.send_header("Content-Disposition", 'attachment; filename="' + download + '"')
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self):
        if self.path == "/api/catalog":
            return self.reply(*web.catalog_payload())
        if self.path == "/api/profiles":  # donnees locales : controle Host contre le rebinding DNS
            return self.safe_reply(web.profiles_payload) if self.local_request() else None
        resource = STATIC.get(self.path)
        if resource is None:
            return self.reply(404, b"Not found")
        path, media = resource
        self.reply(200, path.read_bytes(), media)

    def safe_reply(self, handler, *args):
        """Execute un cas d'usage ; une erreur imprevue donne un 500 sans detail."""
        try:
            response = handler(*args)
        except Exception:  # erreur imprevue : journal local, reponse sans detail
            self.log_error("Erreur interne sur %s", self.path)
            return self.reply(500, b"Erreur interne")
        return self.reply(*response)

    def local_request(self):
        """Hote et origine loopback obligatoires pour toute modification."""
        if not LOCAL_HOST.fullmatch(self.headers.get("Host", "")):
            self.reply(403, b"Hote interdit")
            return False
        origin = self.headers.get("Origin")
        if origin is not None and not LOCAL_ORIGIN.fullmatch(origin):
            self.reply(403, b"Origine interdite")
            return False
        return True

    def read_json_body(self, limit):
        """Controles communs : requete locale, JSON, taille bornee. Retourne le corps ou None."""
        if not self.local_request():
            return None
        if self.headers.get_content_type() != "application/json":
            self.reply(415, b"Content-Type application/json requis")
            return None
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            size = 0
        if not 0 < size <= limit:
            self.reply(400, b"Taille de requete invalide")
            return None
        return self.rfile.read(size)

    def do_POST(self):
        if self.path in API_POST:
            handler, limit = API_POST[self.path]
            raw = self.read_json_body(limit)
            return None if raw is None else self.safe_reply(handler, raw)
        if self.path != "/generate":
            return self.reply(404, b"Not found")
        raw = self.read_json_body(LEGACY_LIMIT)
        if raw is None:
            return None
        try:
            config = validate(json.loads(raw))
            result = generate(config)
        except (ValueError, TypeError, UnicodeError, json.JSONDecodeError) as exc:
            return self.reply(400, str(exc).encode("utf-8"))
        self.reply(200, result, "application/zip", config["name"] + ".zip")

    def do_PUT(self):
        match = PROFILE_PATH.fullmatch(self.path)
        if not match:
            return self.reply(404, b"Not found")
        raw = self.read_json_body(API_LIMIT)
        return None if raw is None else self.safe_reply(web.profile_update_payload, match.group(1), raw)

    def do_DELETE(self):
        match = PROFILE_PATH.fullmatch(self.path)
        if not match:
            return self.reply(404, b"Not found")
        if self.local_request():
            self.safe_reply(web.profile_delete_payload, match.group(1))


if __name__ == "__main__":
    print("http://127.0.0.1:8765")
    ThreadingHTTPServer(("127.0.0.1", 8765), Handler).serve_forever()
