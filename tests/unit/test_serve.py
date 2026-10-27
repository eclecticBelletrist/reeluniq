from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


def test_upload_name_is_sanitised():
    from reeluniq.serve import _safe_name

    assert _safe_name("../../etc/passwd") == "passwd.mp4"
    assert _safe_name("my reel (1).MOV") == "my reel _1_.mov"
    assert _safe_name("...") == "video.mp4"
    assert _safe_name("CON.mov") == "_CON.mov" and _safe_name("nul.mp4") == "_nul.mp4"

def test_upload_page_refuses_foreign_host(tmp_path):
    from http.client import HTTPConnection
    from http.server import ThreadingHTTPServer
    import threading

    from reeluniq.jobs import JobQueue
    from reeluniq.serve import make_handler

    data = tmp_path
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), None)
    port = httpd.server_address[1]
    httpd.RequestHandlerClass = make_handler(None, JobQueue(), data, 3, "light", port)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        for headers, code in (({}, 200), ({"Host": "evil.example"}, 403), ({"Origin": "http://evil.example"}, 403)):
            c = HTTPConnection("127.0.0.1", port)
            c.request("GET", "/", headers=headers)
            assert c.getresponse().status == code
    finally:
        httpd.shutdown()
        httpd.server_close()

def test_pin_mode_needs_the_cookie(tmp_path):
    import threading
    from http.client import HTTPConnection
    from http.server import ThreadingHTTPServer

    from reeluniq.jobs import JobQueue
    from reeluniq.serve import make_handler

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), None)
    port = httpd.server_address[1]
    httpd.RequestHandlerClass = make_handler("123456", JobQueue(), tmp_path, 3, "light", port)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    def call(method, path, body=None, headers=None):
        c = HTTPConnection("127.0.0.1", port)
        c.request(method, path, body=body, headers=headers or {})
        r = c.getresponse()
        return r.status, r.getheader("Set-Cookie"), r.read()

    try:
        assert b"PIN" in call("GET", "/")[2] and call("GET", "/jobs")[2].startswith(b"<!doctype")      # login page, not data
        assert call("POST", "/upload?name=a.mp4", b"x")[0] == 403
        assert call("POST", "/login", b"pin=000000", {"Content-Length": "10"})[1] is None
        status, cookie, _ = call("POST", "/login", b"pin=123456", {"Content-Length": "10"})
        assert status == 303 and cookie
        assert call("GET", "/jobs", headers={"Cookie": cookie.split(";")[0]})[0] == 200
    finally:
        httpd.shutdown()
        httpd.server_close()

def test_zip_download_holds_every_variant(tmp_path):
    import threading
    import zipfile
    from http.client import HTTPConnection
    from http.server import ThreadingHTTPServer
    from io import BytesIO

    from reeluniq.jobs import Job, JobQueue
    from reeluniq.serve import make_handler

    out = tmp_path / "out"
    out.mkdir()
    for name in ("a_light_01.mp4", "a_light_02.mp4"):
        (out / name).write_bytes(name.encode() * 50)
    queue = JobQueue()
    queue.jobs["abcdef012345"] = Job(id="abcdef012345", source=tmp_path / "клип.mp4", out_dir=out, count=2, mode="light",
                                     state="done", files=["a_light_01.mp4", "a_light_02.mp4"])
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), None)
    port = httpd.server_address[1]
    httpd.RequestHandlerClass = make_handler(None, queue, tmp_path, 3, "light", port)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        c = HTTPConnection("127.0.0.1", port)
        c.request("GET", "/zip/abcdef012345")
        r = c.getresponse()
        body = r.read()
        assert r.status == 200 and r.getheader("Content-Type") == "application/zip"
        assert sorted(zipfile.ZipFile(BytesIO(body)).namelist()) == ["a_light_01.mp4", "a_light_02.mp4"]
        c = HTTPConnection("127.0.0.1", port)
        c.request("GET", "/zip/ffffffffffff")
        assert c.getresponse().status == 404
    finally:
        httpd.shutdown()
        httpd.server_close()
