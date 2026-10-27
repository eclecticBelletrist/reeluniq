"""Local web page: drop a video, get variants back, built on http.server.

By default it listens on 127.0.0.1 only and needs no PIN; requests whose Host or Origin is not this address are refused, so a
web page open in the same browser cannot drive it. With `--host 0.0.0.0` (a phone on the same network) a PIN cookie is required;
the connection is plain http, so the PIN and the cookie are visible to anyone on that network.
"""

from __future__ import annotations

import hmac
import json
import os
import re
import secrets
import shutil
import socket
import threading
import time
import webbrowser
import zipfile
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

from . import paths
from .jobs import Job, JobQueue
from .make import MODES
from .watch import VIDEO_EXT

MAX_UPLOAD = 4 * 1024**3
KEEP_SECONDS = 2 * 24 * 3600
DISK_MARGIN = 2 * 1024**3
MAX_PENDING = 8                  # jobs waiting or running; more uploads are refused until some finish
LOOPBACK = {"127.0.0.1", "localhost", "::1"}
WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}

PAGE = """<!doctype html><html><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>reeluniq</title>
<style>
:root{color-scheme:light dark;--bg:#fff;--fg:#111;--mut:#667;--card:#f2f3f5;--acc:#0a6cff}
@media(prefers-color-scheme:dark){:root{--bg:#111;--fg:#eee;--mut:#99a;--card:#1c1d20;--acc:#4d9bff}}
body{margin:0;padding:16px;background:var(--bg);color:var(--fg);font:16px/1.4 system-ui,sans-serif;max-width:560px;margin-inline:auto}
h1{font-size:1.3rem}.card{background:var(--card);border-radius:12px;padding:12px;margin:10px 0}
button,select,input[type=number]{font:inherit;padding:10px 14px;border-radius:10px;border:0;background:var(--acc);color:#fff}
select,input[type=number]{background:var(--card);color:var(--fg);border:1px solid var(--mut)}
progress{width:100%}small,.mut{color:var(--mut)}a{color:var(--acc)}.row{display:flex;gap:8px;flex-wrap:wrap;margin:8px 0}
.warn{border-left:4px solid var(--acc)}.files div{margin:2px 0}
</style>
<h1 id="t"></h1>
<div class="card warn" id="hint"></div>
<div class="card"><input id="f" type="file" accept="video/*">
<div class="row"><label><span id="lv"></span> <input id="n" type="number" min="1" max="8" value="__N__" style="width:4.5em"></label>
<select id="p">__MODES__</select></div>
<button id="go"></button> <progress id="bar" value="0" max="1" hidden></progress><div id="msg" class="mut"></div></div>
<div id="jobs"></div>
<script>
const $=id=>document.getElementById(id);
const L=(navigator.language||'en').startsWith('ru')?'ru':'en';
const S={en:{t:'Video variants',lv:'Variants',go:'Send',pick:'Choose a video',ok:'Accepted, working',err:'Error: ',net:'No connection',
 queued:'queued',running:'working',done:'done',failed:'failed',light:'light: small crop, speed, tone',dust:'dust: light plus fine pixel changes',
 operator:'operator: slow camera drift',meta:'meta only: picture and sound unchanged',n:'variants: ',all:'Download all (zip)',
 hint:'Choose a video, a mode and the number of variants, then press Send. Finished files can be downloaded one by one or as one zip; your browser saves them to its Downloads folder. Keep the black program window open while videos are being made.'},
 ru:{t:'Варианты видео',lv:'Версий',go:'Отправить',pick:'Выберите видео',ok:'Принято, идёт обработка',err:'Ошибка: ',net:'Нет связи',
 queued:'в очереди',running:'обрабатывается',done:'готово',failed:'ошибка',light:'лёгкий: небольшая обрезка, скорость, тон',dust:'пыль: лёгкий плюс мелкие правки пикселей',
 operator:'оператор: плавное движение кадра',meta:'только метаданные: картинка и звук не меняются',n:'версий: ',all:'Скачать всё одним архивом (zip)',
 hint:'Выберите видео, режим и число версий, нажмите «Отправить». Готовые файлы можно скачать по одному или одним архивом; браузер сохранит их в папку «Загрузки». Чёрное окно программы не закрывайте, пока идёт обработка.'}}[L];
$('t').textContent=S.t;$('lv').textContent=S.lv;$('go').textContent=S.go;$('hint').textContent=S.hint;$('p').value='__P__';
document.querySelectorAll('#p option').forEach(o=>o.textContent=S[o.value]);
$('go').onclick=()=>{const f=$('f').files[0];if(!f){$('msg').textContent=S.pick;return}
 const x=new XMLHttpRequest();x.open('POST','/upload?name='+encodeURIComponent(f.name)+'&n='+$('n').value+'&mode='+$('p').value);
 $('bar').hidden=false;x.upload.onprogress=e=>{$('bar').value=e.loaded/e.total};
 x.onload=()=>{$('bar').hidden=true;$('msg').textContent=x.status==200?S.ok:S.err+x.responseText;poll()};
 x.onerror=()=>{$('msg').textContent=S.net};x.send(f)};
async function poll(){const r=await fetch('/jobs');if(!r.ok)return;const js=await r.json();
 $('jobs').replaceChildren(...js.map(j=>{const c=document.createElement('div');c.className='card';
  const b=document.createElement('b');b.textContent=j.name;c.append(b,' — '+S[j.state]);
  const s=document.createElement('small');s.textContent=j.mode+', '+S.n+j.count;c.append(document.createElement('br'),s);
  const box=document.createElement('div');box.className='files';c.append(box);
  j.files.forEach(f=>{const d=document.createElement('div'),a=document.createElement('a');
   a.href='/dl/'+j.id+'/'+encodeURIComponent(f);a.download='';a.textContent=f;d.append(a);box.append(d)});
  if(j.files.length>1){const d=document.createElement('div'),a=document.createElement('a');
   a.href='/zip/'+j.id;a.download='';a.textContent=S.all;a.style.fontWeight='600';d.append(a);box.append(d)}
  if(j.error){const d=document.createElement('div');d.textContent=j.error;c.append(d)}
  if(j.state=='running'&&j.log.length){const m=document.createElement('small');m.textContent=j.log[j.log.length-1];c.append(m)}
  return c}));
 if(js.some(j=>j.state=='queued'||j.state=='running'))setTimeout(poll,3000)}
poll();
</script></html>"""

LOGIN = """<!doctype html><html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>PIN</title><body style="font:18px system-ui;padding:24px;max-width:360px;margin:auto">
<form method="post" action="/login"><p>PIN:</p><input name="pin" inputmode="numeric" autofocus style="font:inherit;width:100%;padding:10px">
<p><button style="font:inherit;padding:10px 20px">OK</button></p></form></body></html>"""


def _safe_name(name: str) -> str:
    stem = re.sub(r"[^\w.\- ]", "_", Path(name).stem, flags=re.UNICODE).strip(" .")[:60] or "video"
    if stem.split(".")[0].upper() in WINDOWS_RESERVED:     # CON.mp4 cannot be created on Windows
        stem = "_" + stem
    ext = Path(name).suffix.lower()
    return stem + (ext if ext in VIDEO_EXT else ".mp4")


def _cleanup_old(data: Path) -> None:
    for d in data.iterdir():
        if d.is_dir() and time.time() - d.stat().st_mtime > KEEP_SECONDS:
            shutil.rmtree(d, ignore_errors=True)


def make_handler(pin: str | None, queue: JobQueue, data: Path, default_count: int, default_mode: str, port: int):
    """`pin=None` means local-only: no login, but Host and Origin must be this machine."""
    token = secrets.token_hex(16)   # cookie value; the PIN itself never goes back to the browser
    local_hosts = {f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"}
    pin_gate = threading.Lock()     # one PIN attempt at a time, half a second each

    class H(BaseHTTPRequestHandler):
        server_version = "reeluniq"
        timeout = 120               # a stalled client must not hold a thread for ever

        def log_message(self, *a):   # no request log noise in the terminal
            pass

        def _authed(self) -> bool:
            if pin is None:
                host = self.headers.get("Host", "").lower()
                origin = self.headers.get("Origin")
                return host in local_hosts and (origin is None or origin.lower() == f"http://{host}")
            c = SimpleCookie(self.headers.get("Cookie", ""))
            return "t" in c and hmac.compare_digest(c["t"].value, token)

        def _send(self, code, body: bytes, ctype="text/html; charset=utf-8", headers=()):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            for k, v in headers:
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _send_zip(self, job: Job) -> None:
            """All variants of one job in one stored (uncompressed) zip, built on first request."""
            archive = job.out_dir / "all.zip"
            names = [n for n in job.files if (job.out_dir / n).is_file()]
            if not names:
                return self._send(404, b"not found", "text/plain")
            if not archive.is_file():
                tmp = archive.with_name("all.zip.part")
                with zipfile.ZipFile(tmp, "w", zipfile.ZIP_STORED) as zf:
                    for n in names:
                        zf.write(job.out_dir / n, n)
                os.replace(tmp, archive)
            label = (job.source.stem or "variants").encode("ascii", "replace").decode().replace('"', "_")
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Length", str(archive.stat().st_size))
            self.send_header("Content-Disposition", f'attachment; filename="{label}_variants.zip"')
            self.end_headers()
            with archive.open("rb") as fh:
                shutil.copyfileobj(fh, self.wfile, 1 << 20)

        def do_GET(self):
            path = urlparse(self.path).path
            if not self._authed():
                return self._send(200, LOGIN.encode()) if pin else self._send(403, b"forbidden", "text/plain")
            if path == "/":
                options = "".join(f'<option value="{m}"></option>' for m in MODES)
                html = PAGE.replace("__N__", str(default_count)).replace("__P__", default_mode).replace("__MODES__", options)
                return self._send(200, html.encode())
            if path == "/jobs":
                js = sorted(queue.jobs.values(), key=lambda j: j.created, reverse=True)
                return self._send(200, json.dumps([j.public() for j in js]).encode(), "application/json")
            z = re.fullmatch(r"/zip/([0-9a-f]{12})", path)
            zjob = queue.jobs.get(z.group(1)) if z else None
            if zjob and zjob.state == "done" and zjob.files:
                return self._send_zip(zjob)
            m = re.fullmatch(r"/dl/([0-9a-f]{12})/([^/]+)", unquote(path))
            job = queue.jobs.get(m.group(1)) if m else None
            f = job.out_dir / m.group(2) if job and m.group(2) in job.files else None
            if f and f.is_file():
                ascii_name = f.name.encode("ascii", "replace").decode().replace('"', "_")
                self.send_response(200)
                self.send_header("Content-Type", "video/mp4")
                self.send_header("Content-Length", str(f.stat().st_size))
                self.send_header("Content-Disposition", f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(f.name)}")
                self.end_headers()
                with f.open("rb") as fh:
                    shutil.copyfileobj(fh, self.wfile, 1 << 20)
                return
            self._send(404, b"not found", "text/plain")

        def do_POST(self):
            url = urlparse(self.path)
            if url.path == "/login" and pin:
                try:
                    length = int(self.headers.get("Content-Length", 0))
                except ValueError:
                    return self._send(400, b"bad request", "text/plain")
                body = self.rfile.read(max(0, min(length, 1024))).decode(errors="replace")
                given = parse_qs(body).get("pin", [""])[0]
                with pin_gate:
                    time.sleep(0.5)   # slows down PIN guessing: parallel requests queue up here
                    ok = hmac.compare_digest(given.encode(), pin.encode())
                if ok:
                    return self._send(303, b"", headers=[("Location", "/"), ("Set-Cookie", f"t={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=2592000")])
                return self._send(403, LOGIN.encode())
            if url.path != "/upload" or not self._authed():
                return self._send(403, b"forbidden", "text/plain")
            q = parse_qs(url.query)
            try:
                size = int(self.headers.get("Content-Length", 0))
            except ValueError:
                return self._send(400, b"bad request", "text/plain")
            if not 0 < size <= MAX_UPLOAD:
                return self._send(413, b"file is empty or larger than 4 GB", "text/plain")
            queue.prune(KEEP_SECONDS)
            _cleanup_old(data)
            if queue.pending() >= MAX_PENDING:
                return self._send(429, b"too many videos in the queue, wait for some to finish", "text/plain")
            if shutil.disk_usage(data).free < size * 2 + DISK_MARGIN:
                return self._send(507, b"not enough disk space", "text/plain")
            try:
                count = max(1, min(8, int(q.get("n", [default_count])[0])))
            except ValueError:
                count = default_count
            mode = q.get("mode", [default_mode])[0]
            if mode not in MODES:
                mode = default_mode
            jid = secrets.token_hex(6)
            jdir = data / jid
            jdir.mkdir()
            src = jdir / _safe_name(q.get("name", ["video.mp4"])[0])
            left = size
            try:
                with src.open("wb") as out:
                    while left > 0:
                        chunk = self.rfile.read(min(1 << 20, left))
                        if not chunk:
                            break
                        out.write(chunk)
                        left -= len(chunk)
            except OSError:   # disk full, client gone, read timeout
                left = size
            if left:
                shutil.rmtree(jdir, ignore_errors=True)
                return self._send(400, b"upload interrupted", "text/plain")
            queue.submit(Job(id=jid, source=src, out_dir=jdir / "out", count=count, mode=mode))
            self._send(200, json.dumps({"id": jid}).encode(), "application/json")

    return H


class _Server6(ThreadingHTTPServer):
    address_family = socket.AF_INET6


def _lan_address() -> str | None:
    """The address other machines on the network can reach this one by. A UDP connect sends no packet."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("10.255.255.255", 9))
            return sock.getsockname()[0]
    except OSError:
        return None


def serve(host: str, port: int, pin: str | None, count: int, mode: str, open_browser: bool = True) -> int:
    local = host in LOOPBACK
    pin = None if local else (pin or f"{secrets.randbelow(10**6):06d}")
    data = paths.data_dir() / "web"
    data.mkdir(parents=True, exist_ok=True)
    _cleanup_old(data)

    def drop_source(job: Job) -> None:   # the uploaded original is only needed while variants are made
        job.source.unlink(missing_ok=True)

    queue = JobQueue(on_done=drop_source)
    httpd = (_Server6 if ":" in host else ThreadingHTTPServer)((host, port), None)
    port = httpd.server_address[1]       # the real one when 0 was asked for
    httpd.RequestHandlerClass = make_handler(pin, queue, data, max(1, min(8, count)), mode, port)
    where = ("[::1]" if host == "::1" else "127.0.0.1") if local else (_lan_address() or "<this computer address>")
    url = f"http://{where}:{port}"
    print(f"open {url}" + ("" if local else f"   PIN: {pin}") + "\nCtrl+C to stop", flush=True)
    if local and open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("stopped")
    finally:
        httpd.server_close()
    return 0
