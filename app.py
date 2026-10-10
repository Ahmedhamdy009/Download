from __future__ import annotations

import json
import base64
import hmac
import os
import re
import shutil
import subprocess
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse


ROOT = Path(__file__).resolve().parent
WEB = ROOT / "website"
DOWNLOADS = ROOT / "downloads"
YTDLP = Path(shutil.which("yt-dlp") or ROOT / "yt-dlp.exe")
FFMPEG = Path(shutil.which("ffmpeg") or ROOT / "ffmpeg.exe")
HOST = "0.0.0.0"  # Reachable by other devices on the same private Wi-Fi.
PORT = int(os.environ.get("PORT", "8765"))
APP_PASSWORD = os.environ.get("APP_PASSWORD", "")
REQUIRE_APP_PASSWORD = os.environ.get("REQUIRE_APP_PASSWORD", "false").lower() == "true"
JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()

STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/manifest.webmanifest": ("manifest.webmanifest", "application/manifest+json; charset=utf-8"),
    "/service-worker.js": ("service-worker.js", "text/javascript; charset=utf-8"),
    "/icon.svg": ("icon.svg", "image/svg+xml; charset=utf-8"),
}
QUALITIES = {"144", "360", "480", "720", "1080", "1440", "2160"}


def run_download(job_id: str, url: str, kind: str, quality: str) -> None:
    folder = DOWNLOADS / job_id
    folder.mkdir(parents=True, exist_ok=True)
    output = str(folder / "%(title).150s.%(ext)s")
    args = [
        str(YTDLP), "--ffmpeg-location", str(FFMPEG.parent), "--js-runtimes", "node",
        "--newline", "--no-playlist",
        "--no-overwrites", "--no-warnings", "-o", output,
    ]

    if kind == "audio":
        args += ["-x", "--audio-format", "mp3", url]
    elif kind == "thumbnail":
        args += ["--write-thumbnail", "--convert-thumbnails", "jpg", "--skip-download", url]
    else:
        format_choice = f"bestvideo[height<={quality}]+bestaudio/best[height<={quality}]/best"
        args += ["--merge-output-format", "mp4", "-f", format_choice, url]

    last_line = ""
    try:
        process = subprocess.Popen(
            args,
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert process.stdout is not None
        for raw_line in process.stdout:
            line = raw_line.strip()
            if not line:
                continue
            last_line = line[-240:]
            percent = re.search(r"(\d+(?:\.\d+)?)%", line)
            with JOBS_LOCK:
                if job_id in JOBS:
                    JOBS[job_id]["message"] = "جارٍ التنزيل…"
                    if percent:
                        JOBS[job_id]["progress"] = min(99, max(0, int(float(percent.group(1)))))

        return_code = process.wait()
        files = [p for p in folder.iterdir() if p.is_file() and not p.name.endswith((".part", ".ytdl"))]
        with JOBS_LOCK:
            if return_code == 0 and files:
                result = max(files, key=lambda item: item.stat().st_mtime)
                JOBS[job_id].update(state="done", progress=100, message="اكتمل التحميل", file=str(result))
            else:
                JOBS[job_id].update(
                    state="error",
                    message="ما قدرناش نكمل التحميل. راجع الرابط وحاول مرة تانية.",
                    details=last_line,
                )
    except Exception as error:
        with JOBS_LOCK:
            if job_id in JOBS:
                JOBS[job_id].update(state="error", message="حصلت مشكلة أثناء التحميل.", details=str(error))


class AppHandler(BaseHTTPRequestHandler):
    server_version = "Nazzelha/1.0"

    def is_authorized(self) -> bool:
        if not APP_PASSWORD or urlparse(self.path).path == "/health":
            return True
        header = self.headers.get("Authorization", "")
        if not header.startswith("Basic "):
            return False
        try:
            credentials = base64.b64decode(header[6:], validate=True).decode("utf-8")
            username, password = credentials.split(":", 1)
        except (ValueError, UnicodeDecodeError):
            return False
        return username == "nazzelha" and hmac.compare_digest(password, APP_PASSWORD)

    def request_auth(self) -> bool:
        if self.is_authorized():
            return True
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="Nazzelha", charset="UTF-8"')
        self.send_header("Content-Length", "0")
        self.end_headers()
        return False

    def send_bytes(self, status: int, data: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, status: int, data: dict) -> None:
        self.send_bytes(status, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            return self.send_bytes(200, b"ok", "text/plain; charset=utf-8")
        if not self.request_auth():
            return
        if parsed.path in STATIC_FILES:
            filename, content_type = STATIC_FILES[parsed.path]
            try:
                self.send_bytes(200, (WEB / filename).read_bytes(), content_type)
            except OSError:
                self.send_error(500, "Website file is missing")
            return

        if parsed.path == "/api/status":
            job_id = parse_qs(parsed.query).get("id", [""])[0]
            with JOBS_LOCK:
                job = JOBS.get(job_id)
                if not job:
                    return self.send_json(404, {"error": "الطلب غير موجود"})
                public_job = {key: value for key, value in job.items() if key not in ("file", "details")}
            self.send_json(200, public_job)
            return

        if parsed.path == "/api/file":
            job_id = parse_qs(parsed.query).get("id", [""])[0]
            with JOBS_LOCK:
                job = JOBS.get(job_id)
                file_path = Path(job["file"]) if job and job.get("state") == "done" else None
            expected_parent = DOWNLOADS / job_id
            if not file_path or not file_path.is_file() or file_path.parent != expected_parent:
                return self.send_json(404, {"error": "الملف مش موجود"})
            safe_name = file_path.name.replace('"', "")
            fallback = re.sub(r"[^A-Za-z0-9._ -]", "_", safe_name) or "download"
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(file_path.stat().st_size))
            self.send_header(
                "Content-Disposition",
                f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(safe_name, safe='')}",
            )
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            with file_path.open("rb") as stream:
                while chunk := stream.read(1024 * 1024):
                    self.wfile.write(chunk)
            return

        self.send_error(404)

    def do_POST(self) -> None:
        if not self.request_auth():
            return
        if self.path != "/api/download":
            return self.send_json(404, {"error": "المسار غير موجود"})
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size <= 0 or size > 16_384:
                return self.send_json(400, {"error": "البيانات غير صحيحة"})
            data = json.loads(self.rfile.read(size))
            url = str(data.get("url", "")).strip()
            kind = str(data.get("kind", "video"))
            quality = str(data.get("quality", "720"))
        except (ValueError, TypeError, json.JSONDecodeError):
            return self.send_json(400, {"error": "البيانات غير صحيحة"})

        parsed_url = urlparse(url)
        if parsed_url.scheme not in ("http", "https") or not parsed_url.hostname or any(ch.isspace() for ch in url):
            return self.send_json(400, {"error": "اكتب رابطًا صحيحًا يبدأ بـ https:// أو http://"})
        if kind not in ("video", "audio", "thumbnail") or quality not in QUALITIES:
            return self.send_json(400, {"error": "اختيار التحميل غير صحيح"})
        if not YTDLP.is_file() or not FFMPEG.is_file():
            return self.send_json(500, {"error": "ملفات أداة التنزيل غير موجودة بجانب التطبيق"})

        job_id = uuid.uuid4().hex
        with JOBS_LOCK:
            JOBS[job_id] = {"state": "running", "progress": 0, "message": "بنجهّز التحميل…"}
        threading.Thread(target=run_download, args=(job_id, url, kind, quality), daemon=True).start()
        self.send_json(202, {"id": job_id})

    def log_message(self, format: str, *args) -> None:
        print("[%s] %s" % (self.log_date_time_string(), format % args), flush=True)


if __name__ == "__main__":
    if REQUIRE_APP_PASSWORD and not APP_PASSWORD:
        raise SystemExit("Set the APP_PASSWORD environment variable before starting this public deployment.")
    if not WEB.is_dir():
        raise SystemExit("Website folder not found. Keep the website folder beside app.py.")
    DOWNLOADS.mkdir(exist_ok=True)
    server = ThreadingHTTPServer((HOST, PORT), AppHandler)
    print(f"Nazzelha is running at http://127.0.0.1:{PORT}/", flush=True)
    print(f"For your phone on the same Wi-Fi, open http://<computer-ip>:{PORT}/", flush=True)
    print("Keep this window open while using the app. Press Ctrl+C to stop.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Nazzelha stopped.", flush=True)
    finally:
        server.server_close()
