"""Sealing, fetching and serving a catalog, mostly by trying to get past them. Everything stays on this machine."""
import hashlib
import http.client
import http.server
import json
import os
import shutil
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]

from srlocations import CatalogError, Material, Registry, SharedCatalog
from srlocations import exchange
from srlocations.exchange import (MANIFEST, SIGNATURE, CatalogServer, Tokens, allowed, encoded, fetch, inventory, main,
                                  manifest_of, seal)
from srlocations.stock.prefabs import Table

pytestmark = pytest.mark.skipif(shutil.which("ssh-keygen") is None, reason="needs ssh-keygen")


def key_pair(folder: Path, name: str) -> tuple[Path, Path]:
    """A key and an allowed-signers file naming it."""
    folder.mkdir(parents=True, exist_ok=True)
    key = folder / name
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", name, "-f", str(key)], check=True)
    signers = folder / f"{name}.signers"
    signers.write_text(f"{name} {Path(str(key) + '.pub').read_text()}")
    return key, signers


@pytest.fixture(scope="module")
def keys(tmp_path_factory):
    folder = tmp_path_factory.mktemp("keys")
    return key_pair(folder, "publisher"), key_pair(folder, "stranger")


@pytest.fixture
def shelf(tmp_path) -> SharedCatalog:
    catalog = SharedCatalog.create(tmp_path / "shelf", "shelf")
    catalog.publish_shader("oak", Material("#8a5a33", 0.5), description="Warm oak")
    catalog.publish_prop("desk", Table(), Registry.default())
    return catalog


def sealed(catalog: SharedCatalog, keys) -> tuple[SharedCatalog, Path]:
    (key, signers), _ = keys
    catalog.seal(key)
    return catalog, signers


def entry_path(catalog: SharedCatalog) -> Path:
    return catalog.root / "shaders/oak/1.0.0.json"


def get(url: str, token: str = "", method: str = "GET"):
    request = urllib.request.Request(url, method=method, headers={"Authorization": f"Bearer {token}"} if token else {})
    try:
        with urllib.request.urlopen(request, timeout=10) as answer:
            return answer.status, answer.read()
    except urllib.error.HTTPError as error:
        return error.code, b""


def raw_get(server: CatalogServer, path: str):
    """A path exactly as written, which a URL library would tidy."""
    connection = http.client.HTTPConnection(*server.httpd.server_address[:2], timeout=10)
    connection.putrequest("GET", path, skip_host=False)
    connection.endheaders()
    answer = connection.getresponse()
    return answer.status, answer.read()


class Static:
    """A plain web server over a folder, or one given canned answers."""

    def __init__(self, root: Path = None, answer=None) -> None:
        class Handler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=str(root or "."), **kwargs)

            def log_message(self, *args):
                pass

            def do_GET(self):
                if answer is None or not answer(self):
                    super().do_GET()
        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.mark.parametrize("path", ["catalog.json", "shaders/oak/1.0.0.json", "props/a.b-c/1.2.3.json", "files/" + "a" * 64 + ".png",
                                  "models/" + "b" * 64 + "/car.glb", "models/" + "b" * 64 + "/maps/Body (1).png",
                                  "browse/index.html", "browse/" + "c" * 64 + ".png"])
def test_paths_a_catalog_holds(path):
    assert allowed(path)


@pytest.mark.parametrize("path", ["", ".", "..", "/etc/passwd", "../catalog.json", "secret.txt", ".git/config", "manifest.json",
                                  "shaders/../../etc/passwd", "shaders/oak/../../../x.json", "shaders/oak/latest.json",
                                  "shaders/.hidden/1.0.0.json", "shaders/a..b/1.0.0.json", "files/x.png", "files/../catalog.json",
                                  "files/" + "a" * 64 + "/x", "models/" + "b" * 64, "models/nothex/car.glb",
                                  "models/" + "b" * 64 + "/../../secret", "models/" + "b" * 64 + "/.ssh", "models/" + "b" * 64 + "/a\\b",
                                  "browse/other.html", "browse/../catalog.json", "shaders//oak/1.0.0.json", "catalog.json/"])
def test_paths_a_catalog_does_not(path):
    assert not allowed(path)


def test_a_sealed_catalog_opens_for_who_trusts_its_signer(shelf, keys):
    catalog, signers = sealed(shelf, keys)
    assert SharedCatalog.open(catalog.root, signers=signers).name == "shelf"
    assert catalog.verify(signers=signers) == []


def test_without_signers_nothing_changes(shelf):
    assert SharedCatalog.open(shelf.root).verify() == []


def test_an_unsealed_catalog_is_refused(shelf, keys):
    with pytest.raises(CatalogError, match="not sealed"):
        SharedCatalog.open(shelf.root, signers=keys[0][1])


def test_someone_elses_seal_is_refused(shelf, keys):
    shelf.seal(keys[1][0])
    with pytest.raises(CatalogError, match="allowed signers"):
        SharedCatalog.open(shelf.root, signers=keys[0][1])


def test_tags_and_descriptions_are_covered_although_a_digest_does_not_cover_them(shelf, keys):
    catalog, signers = sealed(shelf, keys)
    data = json.loads(entry_path(catalog).read_text())
    data["description"] = "Now with a link to somewhere else"
    entry_path(catalog).write_text(json.dumps(data))
    assert SharedCatalog.open(catalog.root).verify() == []  # the digest alone does not see it
    with pytest.raises(CatalogError, match="changed after sealing"):
        SharedCatalog.open(catalog.root, signers=signers)


def test_a_new_entry_with_a_good_digest_is_caught(shelf, keys):
    catalog, signers = sealed(shelf, keys)
    catalog.publish_shader("walnut", Material("#4e2f1c"))
    with pytest.raises(CatalogError, match="added after sealing"):
        SharedCatalog.open(catalog.root, signers=signers)


def test_a_removed_file_is_caught(shelf, keys):
    catalog, signers = sealed(shelf, keys)
    entry_path(catalog).unlink()
    assert any("removed" in issue.message for issue in catalog.verify(signers=signers))


def test_a_link_slipped_in_is_caught(shelf, keys, tmp_path):
    catalog, signers = sealed(shelf, keys)
    (tmp_path / "outside").write_text("secret")
    (catalog.root / "files").mkdir(exist_ok=True)
    os.symlink(tmp_path / "outside", catalog.root / "files" / ("d" * 64 + ".png"))
    assert any("added" in issue.message for issue in catalog.verify(signers=signers))


def test_a_rewritten_manifest_breaks_the_signature(shelf, keys):
    catalog, signers = sealed(shelf, keys)
    entry = entry_path(catalog)
    entry.write_text(entry.read_text().replace("Warm oak", "Other oak"))
    manifest = json.loads((catalog.root / MANIFEST).read_text())
    manifest["files"]["shaders/oak/1.0.0.json"]["sha256"] = hashlib.sha256(entry.read_bytes()).hexdigest()
    (catalog.root / MANIFEST).write_bytes(encoded(manifest))
    with pytest.raises(CatalogError, match="signature"):
        SharedCatalog.open(catalog.root, signers=signers)


def test_a_signature_made_for_something_else_does_not_pass(shelf, keys, tmp_path):
    (key, signers), _ = keys
    catalog, _ = sealed(shelf, keys)
    copy = tmp_path / MANIFEST
    copy.write_bytes((catalog.root / MANIFEST).read_bytes())
    subprocess.run(["ssh-keygen", "-q", "-Y", "sign", "-f", str(key), "-n", "file", str(copy)], check=True)
    (catalog.root / SIGNATURE).write_bytes(Path(str(copy) + ".sig").read_bytes())
    with pytest.raises(CatalogError, match="signature"):
        SharedCatalog.open(catalog.root, signers=signers)


def test_trust_cannot_live_in_the_catalog_it_vouches_for(shelf, keys):
    catalog, signers = sealed(shelf, keys)
    inside = catalog.root / ".signers"
    inside.write_text(signers.read_text())
    with pytest.raises(CatalogError, match="inside the catalog"):
        SharedCatalog.open(catalog.root, signers=inside)


def test_sealing_again_raises_the_sequence_and_covers_new_work(shelf, keys):
    catalog, signers = sealed(shelf, keys)
    catalog.publish_shader("walnut", Material("#4e2f1c"))
    sealed(catalog, keys)
    assert json.loads((catalog.root / MANIFEST).read_text())["sequence"] == 2
    assert catalog.verify(signers=signers) == []


def test_a_catalog_can_be_a_git_repository(shelf, keys):
    (shelf.root / ".git").mkdir()
    (shelf.root / ".git/config").write_text("[core]\n")
    catalog, signers = sealed(shelf, keys)
    assert catalog.verify(signers=signers) == []


def test_something_strange_in_a_catalog_cannot_be_sealed(shelf, keys):
    (shelf.root / "notes.txt").write_text("hello")
    with pytest.raises(CatalogError, match="notes.txt"):
        shelf.seal(keys[0][0])


def test_a_bad_key_says_so(shelf, tmp_path):
    with pytest.raises(CatalogError, match="could not sign"):
        shelf.seal(tmp_path / "nothing")


def test_a_broken_entry_is_an_issue_and_not_a_crash(shelf):
    entry_path(shelf).write_text("{ not json")
    assert [issue.code for issue in shelf.verify()] == ["catalog-digest"]


def test_the_stored_example_can_be_sealed_as_it_stands(tmp_path, keys):
    (key, signers), _ = keys
    copy = tmp_path / "copy"
    shutil.copytree(ROOT / "catalog", copy)
    assert inventory(copy)[1] == []
    seal(copy, key)
    assert SharedCatalog.open(copy, signers=signers).verify(signers=signers) == []


def test_fetching_a_folder_needs_no_seal(shelf, tmp_path):
    copy = fetch(shelf.root, tmp_path / "copy")
    assert copy.name == "shelf" and copy.get("shader", "oak").description == "Warm oak"


def test_fetching_from_a_plain_web_server(shelf, keys, tmp_path):
    catalog, signers = sealed(shelf, keys)
    with Static(catalog.root) as web:
        copy = SharedCatalog.fetch(web.url, tmp_path / "copy", signers=signers)
    assert copy.verify(signers=signers) == []


def test_a_plain_web_server_needs_a_seal(shelf, tmp_path):
    with Static(shelf.root) as web, pytest.raises(CatalogError, match="sealed"):
        fetch(web.url, tmp_path / "copy")


def test_fetching_from_a_server(shelf, tmp_path):
    with CatalogServer([shelf.root]) as server:
        assert fetch(f"{server.url}/shelf", tmp_path / "copy").verify() == []


def test_fetching_again_downloads_only_what_changed(shelf, keys, tmp_path, monkeypatch):
    catalog, signers = sealed(shelf, keys)
    with CatalogServer([catalog.root]) as server:
        fetch(f"{server.url}/shelf", tmp_path / "copy", signers=signers)
        catalog.publish_shader("walnut", Material("#4e2f1c"))
        sealed(catalog, keys)
        asked = []
        real = exchange.Web.open
        monkeypatch.setattr(exchange.Web, "open", lambda self, path: asked.append(path) or real(self, path))
        copy = fetch(f"{server.url}/shelf", tmp_path / "copy", signers=signers)
    assert sorted(asked) == [MANIFEST, SIGNATURE, "shaders/walnut/1.0.0.json"]
    assert copy.get("shader", "walnut")


def assert_untouched(tmp_path, before: list) -> None:
    assert sorted(path.name for path in tmp_path.iterdir()) == before  # no staging folder left behind


def test_a_file_changed_on_the_server_is_refused_and_nothing_lands(shelf, keys, tmp_path):
    catalog, signers = sealed(shelf, keys)
    with CatalogServer([catalog.root]) as server:
        fetch(f"{server.url}/shelf", tmp_path / "copy", signers=signers)
        held = (tmp_path / "copy" / "shaders/oak/1.0.0.json").read_bytes()
        entry_path(catalog).write_text(entry_path(catalog).read_text().replace("Warm oak", "Evil oak"))
        (tmp_path / "copy" / "shaders/oak/1.0.0.json").unlink()  # so it has to come over again
        before = sorted(path.name for path in tmp_path.iterdir())
        with pytest.raises(CatalogError, match="larger|match"):
            fetch(f"{server.url}/shelf", tmp_path / "copy", signers=signers)
    assert_untouched(tmp_path, before)
    assert held


def test_a_server_that_sends_too_much_is_cut_off(shelf, tmp_path):
    manifest = manifest_of(shelf.root)
    data = encoded(manifest)

    def answer(handler):
        body = data if handler.path.endswith(MANIFEST) else b"x" * 10 ** 7
        handler.send_response(200)
        handler.send_header("Content-Length", str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)
        return True
    with Static(answer=answer) as web, pytest.raises((CatalogError, OSError), match="larger"):
        fetch(web.url, tmp_path / "copy")
    assert not (tmp_path / "copy").exists()


@pytest.mark.parametrize("path", ["../escaped.json", "/tmp/escaped.json", "shaders/../../escaped.json", "secret.txt",
                                  "models/" + "b" * 64 + "/../../../escaped"])
def test_a_manifest_cannot_write_outside_the_catalog_even_when_signed(shelf, keys, tmp_path, path):
    (key, signers), _ = keys
    served = tmp_path / "served"
    shutil.copytree(shelf.root, served)
    manifest = manifest_of(served, 1)
    manifest["files"][path] = {"sha256": "a" * 64, "size": 1}
    with_path = encoded(manifest)
    (served / MANIFEST).write_bytes(with_path)
    subprocess.run(["ssh-keygen", "-q", "-Y", "sign", "-f", str(key), "-n", exchange.NAMESPACE, str(served / MANIFEST)], check=True)
    with Static(served) as web, pytest.raises(CatalogError, match="no catalog holds"):
        fetch(web.url, tmp_path / "copy" / "here", signers=signers)
    assert not (tmp_path / "escaped.json").exists() and not (tmp_path / "copy" / "escaped.json").exists()


@pytest.mark.parametrize("bad", [b"{", b"[]", b'{"files": 3}', b'{"name": "x", "sequence": 1, "files": {}}',
                                 b'{"name": "../x", "sequence": 1, "files": {"catalog.json": {"sha256": "' + b"a" * 64 + b'", "size": 1}}}',
                                 b'{"name": "x", "sequence": 1, "files": {"catalog.json": {"sha256": "z", "size": 1}}}',
                                 b'{"name": "x", "sequence": 1, "files": {"catalog.json": {"sha256": "' + b"a" * 64 + b'", "size": -1}}}'])
def test_a_broken_manifest_is_refused(tmp_path, bad):
    with pytest.raises(CatalogError, match="manifest"):
        exchange._manifest(bad, 1000)


def test_a_catalog_past_the_limit_is_refused_before_it_is_downloaded(shelf, tmp_path):
    with pytest.raises(CatalogError, match="limit"):
        fetch(shelf.root, tmp_path / "copy", limit=5)


def test_a_mirror_cannot_wind_a_reader_back(shelf, keys, tmp_path):
    catalog, signers = sealed(shelf, keys)
    old = tmp_path / "old"
    shutil.copytree(catalog.root, old)
    catalog.publish_shader("patched", Material("#4e2f1c"))
    sealed(catalog, keys)
    with CatalogServer([catalog.root]) as server:
        fetch(f"{server.url}/shelf", tmp_path / "copy", signers=signers)
    with Static(old) as mirror, pytest.raises(CatalogError, match="older"):
        fetch(mirror.url, tmp_path / "copy", signers=signers)
    assert SharedCatalog.open(tmp_path / "copy").get("shader", "patched")


def test_a_fetch_needs_the_seal_it_was_told_to_expect(shelf, keys, tmp_path):
    with CatalogServer([shelf.root]) as server, pytest.raises(CatalogError, match="no seal"):
        fetch(f"{server.url}/shelf", tmp_path / "copy", signers=keys[0][1])


def test_a_stranger_cannot_sign_for_a_fetch(shelf, keys, tmp_path):
    shelf.seal(keys[1][0])
    with Static(shelf.root) as web, pytest.raises(CatalogError, match="allowed signers"):
        fetch(web.url, tmp_path / "copy", signers=keys[0][1])
    assert not (tmp_path / "copy").exists()


def test_a_fetched_entry_that_breaks_its_digest_is_refused_without_signers(shelf, tmp_path):
    entry = entry_path(shelf)
    entry.write_text(entry.read_text().replace('"roughness": 0.5', '"roughness": 0.6'))
    with pytest.raises(CatalogError, match="unsound"):
        fetch(shelf.root, tmp_path / "copy")
    assert not (tmp_path / "copy").exists()


def test_a_fetch_leaves_someone_elses_folder_alone(shelf, tmp_path):
    work = SharedCatalog.create(tmp_path / "work", "work")
    work.publish_shader("mine", Material("#123456"))
    with pytest.raises(CatalogError, match="left alone"):
        fetch(shelf.root, work.root)
    assert work.get("shader", "mine")


def test_a_token_stays_off_an_open_network(shelf, tmp_path):
    with pytest.raises(CatalogError, match="in the clear"):
        fetch("http://example.org/shelf", tmp_path / "copy", token="secret")


@pytest.mark.parametrize("source", ["ftp://example.org/shelf", "file:///etc", "gopher://x/", "https://user:pass@example.org/shelf"])
def test_other_addresses_are_refused(source, tmp_path):
    with pytest.raises(CatalogError):
        fetch(source, tmp_path / "copy")


def test_a_redirect_does_not_carry_a_token_away(shelf, tmp_path):
    seen = []

    def elsewhere(handler):
        seen.append(handler.headers.get("Authorization"))
        handler.send_response(200)
        handler.end_headers()
        return True

    with Static(answer=elsewhere) as other:
        def answer(handler):
            handler.send_response(302)
            handler.send_header("Location", f"{other.url}/manifest.json")
            handler.end_headers()
            return True
        with Static(answer=answer) as web, pytest.raises(CatalogError, match="redirect"):
            fetch(web.url, tmp_path / "copy", token="secret")
    assert seen == []


def test_tokens_guard_a_server(shelf, tmp_path):
    other = SharedCatalog.create(tmp_path / "other", "other")
    other.publish_shader("thing", Material("#123456"))
    tokens = Tokens()
    shelf_only, everything = tokens.issue("ana", ["shelf"]), tokens.issue("bo")
    with CatalogServer([shelf.root, other.root], tokens) as server:
        url = f"{server.url}/shelf/catalog.json"
        assert get(url)[0] == 401
        assert get(url, "wrong")[0] == 401
        assert get(url, shelf_only)[0] == 200
        assert get(f"{server.url}/other/catalog.json", shelf_only)[0] == 404
        assert get(f"{server.url}/other/catalog.json", everything)[0] == 200
        assert fetch(f"{server.url}/shelf", tmp_path / "copy", token=shelf_only).name == "shelf"
        with pytest.raises(CatalogError, match="refused this token"):
            fetch(f"{server.url}/shelf", tmp_path / "again", token="wrong")


def test_a_token_goes_in_a_header_and_not_a_query(shelf):
    tokens = Tokens()
    token = tokens.issue("ana")
    with CatalogServer([shelf.root], tokens) as server:
        assert get(f"{server.url}/shelf/catalog.json?token={token}")[0] == 401


def test_revoking_reaches_a_running_server(shelf, tmp_path):
    file = tmp_path / "secrets" / "tokens.json"
    file.parent.mkdir()
    tokens = Tokens.load(file)
    token = tokens.issue("ana")
    with CatalogServer([shelf.root], Tokens.load(file)) as server:
        assert get(f"{server.url}/shelf/catalog.json", token)[0] == 200
        assert Tokens.load(file).revoke("ana") == 1
        assert get(f"{server.url}/shelf/catalog.json", token)[0] == 401


def test_a_token_file_holds_no_token_and_only_its_owner_can_read_it(tmp_path):
    file = tmp_path / "tokens.json"
    token = Tokens.load(file).issue("ana")
    assert token not in file.read_text()
    assert file.stat().st_mode & 0o777 == 0o600


def test_tokens_cannot_be_served_with_the_catalog(shelf):
    tokens = Tokens.load(shelf.root / "tokens.json")
    with pytest.raises(CatalogError, match="inside a catalog"):
        CatalogServer([shelf.root], tokens)


def test_a_server_past_this_machine_needs_tokens(shelf):
    with pytest.raises(CatalogError, match="reachable"):
        CatalogServer([shelf.root], host="0.0.0.0")


def test_a_server_is_on_this_machine_unless_told(shelf):
    server = CatalogServer([shelf.root])
    assert server.httpd.server_address[0] == "127.0.0.1"
    server.httpd.server_close()


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE", "HEAD"])
def test_a_server_cannot_be_written_to(shelf, method):
    with CatalogServer([shelf.root]) as server:
        assert get(f"{server.url}/shelf/catalog.json", method=method)[0] == 405


@pytest.mark.parametrize("path", ["/shelf/../../../../etc/passwd", "/shelf/%2e%2e/%2e%2e/%2e%2e/etc/passwd", "/shelf/..%2f..%2fetc%2fpasswd",
                                  "/shelf//etc/passwd", "/shelf/secret.txt", "/shelf/.git/config", "/shelf/", "/", "/nothing/catalog.json",
                                  "/shelf/shaders/", "/shelf/shaders/oak/"])
def test_a_server_gives_nothing_but_catalog_files(shelf, path):
    (shelf.root / "secret.txt").write_text("private")
    (shelf.root / ".git").mkdir()
    (shelf.root / ".git/config").write_text("private")
    with CatalogServer([shelf.root]) as server:
        status, body = raw_get(server, path)
    assert status == 404 and b"private" not in body and b"root:" not in body


def test_a_server_does_not_follow_a_link_out(shelf, tmp_path):
    (tmp_path / "outside").write_text("private")
    (shelf.root / "files").mkdir(exist_ok=True)
    name = "e" * 64 + ".png"
    os.symlink(tmp_path / "outside", shelf.root / "files" / name)
    with CatalogServer([shelf.root]) as server:
        assert get(f"{server.url}/shelf/files/{name}")[0] == 404


def test_the_tools_work_from_the_command_line(shelf, keys, tmp_path, capsys):
    (key, signers), _ = keys
    main(["seal", str(shelf.root), str(key)])
    main(["token", str(tmp_path / "tokens.json"), "ana", "shelf"])
    token = capsys.readouterr().out.split()[-1]
    assert Tokens.load(tmp_path / "tokens.json").allows(token, "shelf")
    main(["fetch", str(shelf.root), str(tmp_path / "copy"), "--signers", str(signers)])
    assert SharedCatalog.open(tmp_path / "copy", signers=signers)
