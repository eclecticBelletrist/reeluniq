import pytest

pytestmark = pytest.mark.unit


@pytest.fixture
def serve(tmp_path):
    """serve(pin=None, queue=None, lang="auto") starts a server on a free port and returns the port; the fixture stops it."""
    import threading
    from http.server import ThreadingHTTPServer

    from reeluniq.jobs import JobQueue
    from reeluniq.serve import make_handler

    servers = []

    def start(pin=None, queue=None, lang="auto"):
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), None)
        port = httpd.server_address[1]
        httpd.RequestHandlerClass = make_handler(pin, queue or JobQueue(), tmp_path, 3, "light", port, lang)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        servers.append(httpd)
        return port

    yield start
    for httpd in servers:
        httpd.shutdown()
        httpd.server_close()


def request(port, method, path, body=None, headers=None):
    from http.client import HTTPConnection

    c = HTTPConnection("127.0.0.1", port)
    c.request(method, path, body=body, headers=headers or {})
    r = c.getresponse()
    return r.status, r, r.read()


def test_upload_name_is_sanitised():
    from reeluniq.serve import _safe_name

    assert _safe_name("../../etc/passwd") == "passwd.mp4"
    assert _safe_name("my reel (1).MOV") == "my reel _1_.mov"
    assert _safe_name("...") == "video.mp4"
    assert _safe_name("CON.mov") == "_CON.mov" and _safe_name("nul.mp4") == "_nul.mp4"


def test_upload_page_refuses_foreign_host(serve):
    port = serve()
    for headers, code in (({}, 200), ({"Host": "evil.example"}, 403), ({"Origin": "http://evil.example"}, 403)):
        assert request(port, "GET", "/", headers=headers)[0] == code


def test_pin_mode_needs_the_cookie(serve):
    port = serve("123456")
    assert b"PIN" in request(port, "GET", "/")[2] and request(port, "GET", "/jobs")[2].startswith(b"<!doctype")
    assert request(port, "POST", "/upload?name=a.mp4", b"x")[0] == 403
    assert request(port, "POST", "/login", b"pin=000000", {"Content-Length": "10"})[1].getheader("Set-Cookie") is None
    status, response, _ = request(port, "POST", "/login", b"pin=123456", {"Content-Length": "10"})
    cookie = response.getheader("Set-Cookie")
    assert status == 303 and cookie
    assert request(port, "GET", "/jobs", headers={"Cookie": cookie.split(";")[0]})[0] == 200


def test_zip_download_holds_every_variant(tmp_path, serve):
    import zipfile
    from io import BytesIO

    from reeluniq.jobs import Job, JobQueue

    out = tmp_path / "out"
    out.mkdir()
    for name in ("a_light_01.mp4", "a_light_02.mp4"):
        (out / name).write_bytes(name.encode() * 50)
    queue = JobQueue()
    queue.jobs["abcdef012345"] = Job(id="abcdef012345", source=tmp_path / "клип.mp4", out_dir=out, count=2, mode="light",
                                     state="done", files=["a_light_01.mp4", "a_light_02.mp4"])
    port = serve(queue=queue)
    status, response, body = request(port, "GET", "/zip/abcdef012345")
    assert status == 200 and response.getheader("Content-Type") == "application/zip"
    assert sorted(zipfile.ZipFile(BytesIO(body)).namelist()) == ["a_light_01.mp4", "a_light_02.mp4"]
    assert request(port, "GET", "/zip/ffffffffffff")[0] == 404


def test_page_language_comes_from_the_setting(serve):
    for lang, marker in (("ru", "const L='ru'=='auto'"), ("auto", "const L='auto'=='auto'")):
        assert marker in request(serve(lang=lang), "GET", "/")[2].decode()


def test_upload_is_accepted_and_the_limits_answer(serve, tmp_path, monkeypatch):
    import json
    import shutil
    from types import SimpleNamespace

    from reeluniq.jobs import Job, JobQueue

    port = serve()
    status, _, body = request(port, "POST", "/upload?name=a.mp4&n=1&mode=meta", b"not a video", {"Content-Length": "11"})
    assert status == 200 and len(json.loads(body)["id"]) == 12
    assert request(port, "POST", "/upload?name=a.mp4", b"", {"Content-Length": "0"})[0] == 413

    queue = JobQueue()
    for i in range(8):
        queue.jobs[f"{i:012x}"] = Job(id=f"{i:012x}", source=tmp_path / "x.mp4", out_dir=tmp_path, count=1, mode="light", state="queued")
    assert request(serve(queue=queue), "POST", "/upload?name=a.mp4", b"x", {"Content-Length": "1"})[0] == 429

    monkeypatch.setattr(shutil, "disk_usage", lambda _: SimpleNamespace(free=0))
    assert request(serve(), "POST", "/upload?name=a.mp4", b"x", {"Content-Length": "1"})[0] == 507


def test_parallel_zip_requests_all_succeed_and_the_name_survives_cyrillic(tmp_path, serve):
    import threading
    from urllib.parse import quote

    from reeluniq.jobs import Job, JobQueue

    out = tmp_path / "out"
    out.mkdir()
    for name in ("a_light_01.mp4", "a_light_02.mp4"):
        (out / name).write_bytes(b"x" * 4_000_000)
    queue = JobQueue()
    queue.jobs["abcdef012345"] = Job(id="abcdef012345", source=tmp_path / "клип.mp4", out_dir=out, count=2, mode="light",
                                     state="done", files=["a_light_01.mp4", "a_light_02.mp4"])
    port = serve(queue=queue)
    results = []
    threads = [threading.Thread(target=lambda: results.append(request(port, "GET", "/zip/abcdef012345"))) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert [r[0] for r in results] == [200] * 4
    assert f"filename*=UTF-8''{quote('клип_variants.zip')}" in results[0][1].getheader("Content-Disposition")
