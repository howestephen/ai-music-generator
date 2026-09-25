"""Local HTTP API and the React UI.

The browser is a static React app. This process only queues renders, reads the
library, and serves WAV bytes from ``output/``. It does not copy audio into a
cache, and it does not follow a path out of the library.
"""
from __future__ import annotations

import json
import mimetypes
import tempfile
import threading
import time
import webbrowser
from email import message_from_bytes
from email.policy import default as email_default
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

import app
from synth import backends, core, prompting

WEB_DIST = core.PROJECT_ROOT / "web" / "dist"
MAX_JSON_BYTES = 1_000_000
MAX_UPLOAD_BYTES = 200_000_000


def _control_payload(control) -> dict | None:
    if control is None:
        return None
    return {
        "default": control.default,
        "minimum": control.minimum,
        "maximum": control.maximum,
        "step": control.step,
        "label": control.label,
        "info": control.info,
        "integer": bool(control.integer),
    }


def bootstrap() -> dict:
    models = []
    for name, backend in backends.BACKENDS.items():
        choices, info = app._voice_choice_labels(name)
        models.append({
            "name": name,
            "model_id": backend.model_id,
            "licence": backend.licence,
            "notes": backend.notes,
            "available": backend.available,
            "max_duration": backend.max_duration,
            "prompt_style": backend.prompt_style,
            "prompt_hint": app._prompt_hint(backend),
            "supports_lyrics": backend.supports_lyrics,
            "supports_editing": backend.supports_editing,
            "voice_choices": choices,
            "voice_info": info,
            "duration": _control_payload(backend.duration),
            "steps": _control_payload(backend.steps),
            "guidance": _control_payload(backend.guidance),
        })
    return {
        "default_model": core.DEFAULT_MODEL,
        "models": models,
        "genres": prompting.genre_names(),
        "characters": prompting.character_options(),
        "mood_default": prompting.RANDOM_CHOICE,
    }


def genre_options(genre: str | None) -> dict:
    bpm = None
    if genre and genre in prompting.GENRES:
        bpm = prompting.GENRES[genre].default_bpm()
    return {
        "moods": [prompting.RANDOM_CHOICE, *prompting.mood_options(genre)],
        "instruments": prompting.instrument_options(genre),
        "bpm": bpm,
        "duration": prompting.suggested_duration(genre),
    }


def compose_prompt(body: dict) -> str:
    genre = str(body.get("genre") or "").strip()
    if not genre:
        raise ValueError("Pick a genre first.")
    model = str(body.get("model") or core.DEFAULT_MODEL)
    backend = backends.get(model)
    vocals = body.get("vocals") in ("With vocals", "Vocal texture")
    instruments = body.get("instruments") or ()
    character = body.get("character") or ()
    if isinstance(instruments, str):
        instruments = (instruments,)
    if isinstance(character, str):
        character = (character,)
    mood = body.get("mood")
    return prompting.build_prompt(
        genre,
        style=backend.prompt_style,
        bpm=int(body["bpm"]) if body.get("bpm") else None,
        mood=None if not mood or mood == prompting.RANDOM_CHOICE else str(mood),
        instruments=tuple(instruments),
        character=tuple(character),
        vocals=vocals,
        extra=str(body.get("keywords") or ""),
    )


def library_wav(name: str) -> Path:
    """A WAV that lives directly in the library. Nothing else."""
    root = core.OUTPUT_DIR.resolve()
    if (
        not isinstance(name, str)
        or not name
        or "/" in name
        or "\\" in name
        or name.startswith(".")
        or "\x00" in name
    ):
        raise ValueError("that audio is not in the library")
    resolved = (root / name).resolve()
    if resolved.parent != root or resolved.suffix.lower() != ".wav":
        raise ValueError("that audio is not in the library")
    return resolved


def public_track(track: dict) -> dict:
    peaks = app._waveform_peaks(track["path"], int(track["modified_ns"]))
    return {
        "name": track["name"],
        "title": track["display_title"],
        "genre": app.genre_for_track(track),
        "duration": track.get("duration"),
        "requested_duration": track.get("requested_duration"),
        "audit_status": track.get("audit_status"),
        "audit_error": track.get("audit_error"),
        "backend": track.get("backend"),
        "seed": track.get("seed"),
        "prompt": track.get("prompt"),
        "generated_at": track.get("generated_at"),
        "rating": track.get("rating"),
        "sample_rate": track.get("sample_rate"),
        "elapsed_seconds": track.get("elapsed_seconds"),
        "audio": f"/audio/{quote(track['name'])}",
        "peaks": list(peaks),
    }


def public_job(job: dict) -> dict:
    safe = {key: value for key, value in job.items() if key != "output_path"}
    safe["status_text"] = app._queue_status_text(job)
    return safe


def pending_public() -> list[dict]:
    now = time.time()
    rows = []
    for entry in app._pending_entries():
        rows.append({
            "stem": entry["stem"],
            "title": entry["title"],
            "name": entry["name"],
            "seconds_left": max(0, int(entry["expires_at"] - now)),
        })
    return rows


def library_state(signature: str | None) -> dict:
    app.purge_expired_deletions()
    current = app._history_signature()
    token = ",".join(f"{name}:{stamp}" for name, stamp in current)
    payload = {
        "queue": [public_job(job) for job in app._queue_items_for_render(None)],
        "signature": token,
        "pending": pending_public(),
    }
    if signature != token:
        tracks = app.filter_history(
            app._history_items_for_render(None),
        )
        payload["tracks"] = [public_track(track) for track in tracks]
    return payload


def _json_body(handler: BaseHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length") or 0)
    if length < 0 or length > MAX_JSON_BYTES:
        raise ValueError("request is too large")
    raw = handler.rfile.read(length) if length else b""
    if not raw:
        return {}
    try:
        body = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("request was not JSON") from exc
    if not isinstance(body, dict):
        raise ValueError("request was not a JSON object")
    return body


def _parse_upload(handler: BaseHTTPRequestHandler) -> tuple[dict, Path | None]:
    length = int(handler.headers.get("Content-Length") or 0)
    if length < 0 or length > MAX_UPLOAD_BYTES:
        raise ValueError("that file is too large")
    content_type = handler.headers.get("Content-Type") or ""
    raw = handler.rfile.read(length)
    header = (
        f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n"
    ).encode("utf-8")
    message = message_from_bytes(header + raw, policy=email_default)
    if not message.is_multipart():
        raise ValueError("upload required")
    fields: dict[str, str] = {}
    upload: Path | None = None
    for part in message.iter_parts():
        name = part.get_param("name", header="content-disposition")
        if not name:
            continue
        payload = part.get_payload(decode=True) or b""
        filename = part.get_filename()
        if filename:
            suffix = Path(filename).suffix.lower() or ".bin"
            if suffix not in {".wav", ".mp3", ".flac", ".aiff", ".aif", ".ogg"}:
                raise ValueError("upload a wav, mp3, flac, aiff or ogg file")
            target = Path(tempfile.gettempdir()) / f"ui-upload-{time.time_ns()}{suffix}"
            target.write_bytes(payload)
            upload = target
        else:
            fields[name] = payload.decode("utf-8", errors="replace")
    return fields, upload


def _static_file(url_path: str) -> Path | None:
    dist = WEB_DIST.resolve()
    rel = unquote(url_path).lstrip("/")
    if not rel or rel.endswith("/"):
        candidate = dist / "index.html"
    else:
        candidate = (dist / rel).resolve()
        try:
            candidate.relative_to(dist)
        except ValueError:
            return None
        if not candidate.is_file():
            candidate = dist / "index.html"
    if candidate.is_file():
        return candidate
    return None


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args) -> None:
        del fmt, args

    def do_GET(self) -> None:
        self._handle()

    def do_POST(self) -> None:
        self._handle()

    def _handle(self) -> None:
        try:
            parsed = urlparse(self.path)
            path = parsed.path
            query = parse_qs(parsed.query)
            if path == "/api/bootstrap" and self.command == "GET":
                self._send_json(bootstrap())
            elif path == "/api/options" and self.command == "GET":
                genre = (query.get("genre") or [None])[0]
                self._send_json(genre_options(genre))
            elif path == "/api/prompt" and self.command == "POST":
                self._send_json({"prompt": compose_prompt(_json_body(self))})
            elif path == "/api/generate" and self.command == "POST":
                self._generate(_json_body(self))
            elif path == "/api/remix" and self.command == "POST":
                self._remix()
            elif path == "/api/state" and self.command == "GET":
                signature = (query.get("signature") or [None])[0]
                self._send_json(library_state(signature))
            elif path == "/api/queue/move" and self.command == "POST":
                body = _json_body(self)
                self._send_json({
                    "queue": [
                        public_job(job)
                        for job in app._move_job(str(body.get("id") or ""), int(body.get("direction") or 0))
                    ],
                })
            elif path == "/api/queue/remove" and self.command == "POST":
                body = _json_body(self)
                self._send_json({
                    "queue": [
                        public_job(job)
                        for job in app._remove_job(str(body.get("id") or ""))
                    ],
                })
            elif path == "/api/tracks/rating" and self.command == "POST":
                self._rate(_json_body(self))
            elif path == "/api/tracks/delete" and self.command == "POST":
                self._delete(_json_body(self))
            elif path == "/api/tracks/undo" and self.command == "POST":
                body = _json_body(self)
                app.undo_delete(str(body.get("stem") or ""))
                self._send_json(library_state(None))
            elif path.startswith("/audio/") and self.command == "GET":
                self._audio(unquote(path[len("/audio/"):]))
            elif self.command == "GET":
                self._file(_static_file(path))
            else:
                self._send_json({"error": "not found"}, status=404)
        except (app.gr.Error, ValueError, FileNotFoundError, FileExistsError, OSError) as exc:
            self._send_json({"error": str(exc)}, status=400)

    def _generate(self, body: dict) -> None:
        status, seed, snapshot = app._enqueue_generation(
            body.get("model") or core.DEFAULT_MODEL,
            body.get("prompt"),
            body.get("duration"),
            body.get("steps"),
            body.get("guidance"),
            body.get("seed"),
            bool(body.get("use_seed")),
            body.get("lyrics"),
            body.get("genre"),
        )
        self._send_json({
            "status": status,
            "seed": seed,
            "queue": [public_job(job) for job in snapshot],
        })

    def _remix(self) -> None:
        content_type = self.headers.get("Content-Type") or ""
        upload = None
        if content_type.startswith("multipart/"):
            fields, upload = _parse_upload(self)
        else:
            fields = {key: "" if value is None else str(value) for key, value in _json_body(self).items()}
        track_name = fields.get("track") or ""
        track_path = str(library_wav(track_name)) if track_name else None
        try:
            noise = float(fields.get("noise") or 0.6)
        except (TypeError, ValueError) as exc:
            raise ValueError("amount of change must be a number") from exc
        headline, snapshot = app._enqueue_edit(
            fields.get("model") or core.DEFAULT_MODEL,
            track_path,
            str(upload) if upload else None,
            fields.get("prompt") or fields.get("become") or "",
            120,
            1,
            8,
            fields.get("steps") or None,
            fields.get("guidance") or None,
            app.REMIX_MODE,
            noise,
        )
        self._send_json({
            "status": headline,
            "queue": [public_job(job) for job in snapshot],
        })

    def _rate(self, body: dict) -> None:
        wav = library_wav(str(body.get("name") or ""))
        if not wav.is_file():
            raise FileNotFoundError("track not found")
        app.set_track_rating(str(wav), body.get("rating"))
        self._send_json(library_state(None))

    def _delete(self, body: dict) -> None:
        wav = library_wav(str(body.get("name") or ""))
        app.delete_track(str(wav))
        self._send_json(library_state(None))

    def _audio(self, name: str) -> None:
        path = library_wav(name)
        if not path.is_file():
            self._send_json({"error": "track not found"}, status=404)
            return
        size = path.stat().st_size
        range_header = self.headers.get("Range")
        start, end = 0, size - 1
        status = 200
        if range_header:
            if not range_header.startswith("bytes="):
                self._send_json({"error": "bad range"}, status=416)
                return
            spec = range_header[6:]
            start_text, _, end_text = spec.partition("-")
            try:
                start = int(start_text) if start_text else 0
                end = int(end_text) if end_text else size - 1
            except ValueError:
                self._send_json({"error": "bad range"}, status=416)
                return
            if start < 0 or end >= size or start > end:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            status = 206
        length = end - start + 1
        self.send_response(status)
        self.send_header("Content-Type", "audio/wav")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        with path.open("rb") as handle:
            handle.seek(start)
            remaining = length
            while remaining:
                chunk = handle.read(min(remaining, 1024 * 256))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)

    def _file(self, path: Path | None) -> None:
        if path is None:
            message = (
                "The UI has not been built. From web/, run npm install and npm run build."
            ).encode("utf-8")
            self.send_response(503)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(message)))
            self.end_headers()
            self.wfile.write(message)
            return
        body = path.read_bytes()
        mime, _ = mimetypes.guess_type(path.name)
        self.send_response(200)
        self.send_header("Content-Type", mime or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def serve(port: int = 7860) -> None:
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}"
    print(f"Running on {url}", flush=True)
    webbrowser.open(url)
    server.serve_forever()


def serve_in_thread(port: int = 0) -> tuple[ThreadingHTTPServer, int]:
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    thread = threading.Thread(target=server.serve_forever, name="ui-http", daemon=True)
    thread.start()
    bound = server.server_address[1]
    return server, bound
