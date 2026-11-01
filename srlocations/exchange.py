"""Moving a shared catalog between machines, and knowing it arrived as it was published.

A seal is a manifest of every file in a catalog, by digest, signed with an SSH key. ssh-keygen does the signing and the
checking, so this module holds no cryptography. Readers name who they trust in an allowed-signers file kept outside the
catalog:

    catalog.seal("~/.ssh/catalog_key")
    SharedCatalog.fetch("https://example.org/shelf", "vendor/shelf", signers="trusted_signers")
    SharedCatalog.open("vendor/shelf", signers="trusted_signers")

fetch() reads a CatalogServer, a plain web server over a sealed catalog, or a folder. Everything is written to a staging
folder and checked before the catalog in place is swapped for it, so a failed fetch changes nothing. A manifest's sequence
goes up with each seal, and a fetch refuses a lower one than it holds, so a mirror cannot wind a reader back to an older
sealed state. That only protects someone who has fetched before, and nothing shows a reader that a mirror stopped updating.

CatalogServer is read-only: publishing stays with whoever holds the folder. It binds to this machine unless told otherwise.
A token reads whole catalogs, by name, because a seal covers a whole catalog: keep what one audience may not see in a
catalog of its own. Tokens are stored hashed, in a file outside the catalog. It speaks plain HTTP, so anything past this
machine belongs behind a TLS proxy.
"""
from __future__ import annotations

import argparse
import hashlib
import http.server
import ipaddress
import json
import os
import re
import secrets
import shutil
import subprocess
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from pathlib import Path, PurePosixPath
from typing import IO, Any, Optional, Sequence, Union

from srlocations.catalog import KINDS, NAME, SCHEMA, STORED_FILE, STORED_MODEL, VERSION, SharedCatalog
from srlocations.location import Issue
from srlocations.registry import CatalogError

MANIFEST, SIGNATURE, MARKER = "manifest.json", "manifest.json.sig", ".fetched"
NAMESPACE = "srlocations-catalog"  # a signature made for anything else does not pass here
MAX_MANIFEST = 64 * 2 ** 20
MAX_SIGNATURE = 2 ** 16
MAX_CATALOG = 8 * 2 ** 30
TIMEOUT = 30
PIECE = re.compile(r"[^./\\\x00-\x1f][^/\\\x00-\x1f]*")  # a name in a model's folder: a model may call its files anything else
THUMBNAIL = re.compile(r"[0-9a-f]{64}\.png")
Paths = Union[str, Path]


def allowed(path: str) -> bool:
    """Whether a path is one a catalog can hold. A manifest comes from elsewhere, so nothing else is ever opened."""
    parts = PurePosixPath(path).parts
    if not parts or path != "/".join(parts) or "\\" in path:
        return False
    if len(parts) == 1:
        return path == "catalog.json"
    if parts[0] in KINDS.values():
        return (len(parts) == 3 and NAME.fullmatch(parts[1]) is not None and ".." not in parts[1]
                and parts[2].endswith(".json") and VERSION.fullmatch(parts[2][:-5]) is not None)
    if parts[0] == "files":
        return len(parts) == 2 and STORED_FILE.fullmatch(parts[1]) is not None
    if parts[0] == "models":
        return len(parts) >= 3 and STORED_MODEL.fullmatch(parts[1]) is not None and all(map(PIECE.fullmatch, parts[2:]))
    if parts[0] == "browse":
        return len(parts) == 2 and (parts[1] == "index.html" or THUMBNAIL.fullmatch(parts[1]) is not None)
    return False


def sha256_of(path: Path) -> str:
    made = hashlib.sha256()
    with path.open("rb") as source:
        for piece in iter(lambda: source.read(2 ** 20), b""):
            made.update(piece)
    return made.hexdigest()


def inventory(root: Path) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Every file of a catalog, and anything there that a catalog does not hold, such as a link. Names at the top that
    begin with a dot are left out, so a catalog can be a git repository."""
    files: dict[str, dict[str, Any]] = {}
    strange: list[str] = []
    for folder, folders, names in os.walk(root):
        here = Path(folder)
        for name in list(folders):
            if here == root and name.startswith("."):
                folders.remove(name)
            elif (here / name).is_symlink():
                strange.append((here / name).relative_to(root).as_posix())
        for name in names:
            path = here / name
            relative = path.relative_to(root).as_posix()
            if relative in (MANIFEST, SIGNATURE) or (here == root and name.startswith(".")):
                continue
            if path.is_symlink() or not path.is_file() or not allowed(relative):
                strange.append(relative)
            else:
                files[relative] = {"sha256": sha256_of(path), "size": path.stat().st_size}
    return files, sorted(strange)


def manifest_of(root: Path, sequence: int = 0) -> dict[str, Any]:
    files, strange = inventory(root)
    if strange:
        raise CatalogError(f"{root} holds what a catalog does not: {', '.join(strange[:5])}")
    return {"schema": SCHEMA, "name": json.loads((root / "catalog.json").read_text())["name"], "sequence": sequence,
            "files": files}


def encoded(manifest: dict[str, Any]) -> bytes:
    return (json.dumps(manifest, indent=1, sort_keys=True) + "\n").encode()


def _ssh_keygen(*arguments: str, data: Optional[bytes] = None) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["ssh-keygen", "-Y", *arguments], input=data if data is not None else b"",
                              capture_output=True, timeout=TIMEOUT)
    except FileNotFoundError:
        raise CatalogError("seals need ssh-keygen, which comes with OpenSSH") from None


def seal(root: Paths, key: Paths) -> Path:
    """Signs what the catalog holds now. Sealing again raises the sequence. Returns the manifest."""
    root = Path(root).resolve()
    held = root / MANIFEST
    sequence = json.loads(held.read_text())["sequence"] if held.exists() else 0
    data = encoded(manifest_of(root, sequence + 1))
    with tempfile.TemporaryDirectory() as folder:
        draft = Path(folder) / MANIFEST
        draft.write_bytes(data)
        done = _ssh_keygen("sign", "-f", str(Path(key).expanduser()), "-n", NAMESPACE, str(draft))
        if done.returncode != 0:
            raise CatalogError(f"could not sign with {key}: {done.stderr.decode(errors='replace').strip()}")
        signature = draft.with_name(SIGNATURE).read_bytes()
    (root / SIGNATURE).unlink(missing_ok=True)  # never a new manifest beside an old signature that a crash could leave valid
    _replace(held, data)
    _replace(root / SIGNATURE, signature)
    return held


def _replace(path: Path, data: bytes) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}")
    temporary.write_bytes(data)
    temporary.replace(path)


def signers_file(signers: Paths, root: Path) -> Path:
    """An attacker who can change a catalog must not be able to change who it trusts."""
    path = Path(signers).expanduser().resolve()
    if path.is_relative_to(root.resolve()):
        raise CatalogError(f"{path} is inside the catalog it vouches for: keep trusted signers outside it")
    if not path.is_file():
        raise CatalogError(f"no allowed-signers file at {path}")
    return path


def signed_by(data: bytes, signature: bytes, signers: Path) -> str:
    """Who signed these bytes, from the allowed-signers file. Refuses anything else."""
    with tempfile.TemporaryDirectory() as folder:
        mark = Path(folder) / SIGNATURE
        mark.write_bytes(signature)
        found = _ssh_keygen("find-principals", "-f", str(signers), "-s", str(mark))
        identities = found.stdout.decode(errors="replace").split()
        if found.returncode != 0 or not identities:
            raise CatalogError("the seal is not from anyone in the allowed signers")
        checked = _ssh_keygen("verify", "-f", str(signers), "-I", identities[0], "-n", NAMESPACE, "-s", str(mark), data=data)
    if checked.returncode != 0:
        raise CatalogError("the seal's signature does not match its manifest")
    return identities[0]


def check_seal(root: Paths, signers: Paths) -> list[Issue]:
    """Whether the catalog is exactly what a trusted signer sealed."""
    root = Path(root).resolve()
    trusted = signers_file(signers, root)
    if not (root / MANIFEST).is_file() or not (root / SIGNATURE).is_file():
        return [Issue("error", "catalog-seal", f"{root} is not sealed")]
    data = (root / MANIFEST).read_bytes()
    try:
        signed_by(data, (root / SIGNATURE).read_bytes(), trusted)
        sealed = json.loads(data)["files"]
    except (CatalogError, ValueError, KeyError) as error:
        return [Issue("error", "catalog-seal", f"{root}: {error}")]
    files, strange = inventory(root)
    issues = [Issue("error", "catalog-seal", f"{path} was removed after sealing") for path in sorted(set(sealed) - set(files))]
    issues += [Issue("error", "catalog-seal", f"{path} was added after sealing") for path in sorted({*files, *strange} - set(sealed))]
    issues += [Issue("error", "catalog-seal", f"{path} was changed after sealing") for path in sorted(set(files) & set(sealed))
               if files[path]["sha256"] != sealed[path]["sha256"]]
    return issues


def require_seal(root: Paths, signers: Paths) -> None:
    issues = check_seal(root, signers)
    if issues:
        raise CatalogError(f"{issues[0].message}{f', and {len(issues) - 1} more' if len(issues) > 1 else ''}")


class NoRedirects(urllib.request.HTTPRedirectHandler):
    """A redirect would carry a token to wherever it pointed."""

    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        raise CatalogError("the server answered with a redirect, which a fetch does not follow")


def is_local(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


class Web:
    """A catalog at a URL. Each file is named under it, as a CatalogServer or a plain web server gives them."""

    def __init__(self, url: str, token: Optional[str]) -> None:
        parts = urllib.parse.urlsplit(url)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise CatalogError(f"{url!r} is not an http or https address, or a folder")
        if parts.username or parts.password:
            raise CatalogError("put a token in `token`, not in the address")
        if token and parts.scheme == "http" and not is_local(parts.hostname):
            raise CatalogError(f"a token would cross the network in the clear to {parts.hostname}: use https")
        self.url, self.token = url.rstrip("/"), token
        self.opener = urllib.request.OpenerDirector()
        for handler in (urllib.request.HTTPHandler(), urllib.request.HTTPSHandler(), NoRedirects(),
                        urllib.request.HTTPDefaultErrorHandler(), urllib.request.HTTPErrorProcessor()):
            self.opener.add_handler(handler)

    def open(self, path: str) -> IO[bytes]:
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        request = urllib.request.Request(f"{self.url}/{urllib.parse.quote(path)}", headers=headers)
        try:
            return self.opener.open(request, timeout=TIMEOUT)
        except urllib.error.HTTPError as error:
            if error.code in (401, 403):
                raise CatalogError(f"{self.url} refused this token") from None
            raise FileNotFoundError(path) from None
        except OSError as error:
            raise CatalogError(f"cannot reach {self.url}: {error}") from None


class Folder:
    """A catalog on this machine or a network folder."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def open(self, path: str) -> IO[bytes]:
        source = self.root / path
        if source.is_symlink() or not source.resolve().is_relative_to(self.root):
            raise CatalogError(f"{path} leaves the catalog")
        return source.open("rb")


def _read(source: Union[Web, Folder], path: str, limit: int) -> bytes:
    with source.open(path) as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise CatalogError(f"{path} is larger than {limit} bytes")
    return data


def _copy(source: Union[Web, Folder], path: str, target: Path, expected: dict[str, Any]) -> None:
    """Takes a file only if it is the one the manifest names, stopping at its size whatever the server sends."""
    made, size = hashlib.sha256(), expected["size"]
    target.parent.mkdir(parents=True, exist_ok=True)
    with source.open(path) as stream, target.open("wb") as out:
        while True:
            piece = stream.read(min(2 ** 20, size + 1 - out.tell()) or 1)
            if not piece:
                break
            made.update(piece)
            out.write(piece)
            if out.tell() > size:
                raise CatalogError(f"{path} is larger than its manifest says")
    if made.hexdigest() != expected["sha256"]:
        raise CatalogError(f"{path} does not match its manifest")


def _manifest(data: bytes, limit: int) -> dict[str, Any]:
    """A manifest's shape, before anything in it is acted on."""
    try:
        manifest = json.loads(data)
        files, name, sequence = manifest["files"], manifest["name"], manifest["sequence"]
        total = sum(entry["size"] for entry in files.values())
        sound = (isinstance(sequence, int) and isinstance(name, str) and NAME.fullmatch(name) is not None
                 and all(isinstance(entry["size"], int) and entry["size"] >= 0 and isinstance(entry["sha256"], str)
                         and re.fullmatch("[0-9a-f]{64}", entry["sha256"]) for entry in files.values()))
    except (ValueError, KeyError, TypeError, AttributeError) as error:
        raise CatalogError(f"this is not a catalog manifest: {error}") from None
    if not sound or "catalog.json" not in files:
        raise CatalogError("this is not a catalog manifest")
    wrong = [path for path in files if not allowed(path)]
    if wrong:
        raise CatalogError(f"the manifest names a path no catalog holds: {wrong[0]!r}")
    if total > limit:
        raise CatalogError(f"this catalog is {total} bytes, past the limit of {limit}")
    return manifest


def fetch(source: Paths, folder: Paths, token: Optional[str] = None, signers: Optional[Paths] = None,
          limit: int = MAX_CATALOG) -> SharedCatalog:
    """Brings a catalog to `folder`, or brings a copy there up to date, downloading only what changed. With `signers`, it
    must be sealed by someone they name and no older than the copy here. Without them digests only catch a broken
    transfer, not a changed catalog, because they come from the same place as the files."""
    folder = Path(folder).resolve()
    origin: Union[Web, Folder] = Web(str(source), token) if re.match(r"[a-z][a-z0-9+.-]*://", str(source)) else Folder(Path(source))
    trusted = signers_file(signers, folder) if signers else None
    if folder.exists() and any(folder.iterdir()) and not (folder / MARKER).exists():
        raise CatalogError(f"{folder} holds something a fetch did not put there, so it is left alone")
    try:
        data = _read(origin, MANIFEST, MAX_MANIFEST)
        if trusted:
            signature = _read(origin, SIGNATURE, MAX_SIGNATURE)
    except FileNotFoundError:
        if trusted or not isinstance(origin, Folder):
            raise CatalogError(f"{source} has no {'seal' if trusted else 'manifest'}; a plain web server needs it sealed") from None
        data = encoded(manifest_of(origin.root))
    if trusted:
        signed_by(data, signature, trusted)
    manifest = _manifest(data, limit)
    held = folder / MANIFEST
    if trusted and held.exists() and json.loads(held.read_text()).get("sequence", 0) > manifest["sequence"]:
        raise CatalogError(f"{source} is older than the copy in {folder}: sequence {manifest['sequence']} is behind")
    folder.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(dir=folder.parent, prefix=f".{folder.name}."))
    try:
        for path, expected in manifest["files"].items():
            mine, target = folder / path, staging / path
            if mine.is_file() and not mine.is_symlink() and sha256_of(mine) == expected["sha256"]:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(mine, target)
                continue
            try:
                _copy(origin, path, target, expected)
            except FileNotFoundError:
                raise CatalogError(f"{source} does not have {path}, which its manifest names") from None
        (staging / MANIFEST).write_bytes(data)
        if trusted:
            (staging / SIGNATURE).write_bytes(signature)
        (staging / MARKER).write_text(str(source).split("?")[0] + "\n")
        found = SharedCatalog.open(staging)
        if found.name != manifest["name"]:
            raise CatalogError(f"the manifest is for {manifest['name']!r} and the catalog is {found.name!r}")
        try:
            errors = [issue for issue in found.verify() if issue.severity == "error"]
        except (KeyError, TypeError, ValueError, AttributeError) as error:
            raise CatalogError(f"the fetched catalog is unsound: {error!r}") from None
        if errors:
            raise CatalogError(f"the fetched catalog is unsound: {errors[0].message}")
        retired = folder.with_name(f".{folder.name}.{secrets.token_hex(4)}")
        if folder.exists():
            folder.replace(retired)
        staging.replace(folder)
        shutil.rmtree(retired, ignore_errors=True)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return SharedCatalog.open(folder, signers=signers) if signers else SharedCatalog.open(folder)


@dataclass
class Tokens:
    """Who may read which catalogs. Only hashes are kept, so reading this file gives nobody a way in. A change on disk
    applies to a running server at the next request."""
    path: Optional[Path] = None
    grants: dict[str, dict[str, Any]] = field(default_factory=dict)
    stamp: int = -1

    @classmethod
    def load(cls, path: Paths) -> "Tokens":
        tokens = cls(Path(path).expanduser().resolve())
        tokens.refresh()
        return tokens

    def refresh(self) -> None:
        if self.path and self.path.exists() and self.path.stat().st_mtime_ns != self.stamp:
            self.stamp = self.path.stat().st_mtime_ns
            self.grants = json.loads(self.path.read_text())

    def save(self) -> None:
        if self.path:
            temporary = self.path.with_name(f".{self.path.name}.{os.getpid()}")
            with os.fdopen(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as out:
                json.dump(self.grants, out, indent=1, sort_keys=True)
            temporary.replace(self.path)

    def issue(self, name: str, catalogs: Sequence[str] = ("*",)) -> str:
        """A new token for `name`, who may read catalogs matching these patterns. This is the only time it can be seen."""
        token = secrets.token_urlsafe(32)
        self.grants[hashed(token)] = {"name": name, "catalogs": list(catalogs)}
        self.save()
        return token

    def revoke(self, name: str) -> int:
        """Removes every token of `name`, and says how many."""
        kept = {key: grant for key, grant in self.grants.items() if grant["name"] != name}
        gone = len(self.grants) - len(kept)
        self.grants = kept
        self.save()
        return gone

    def allows(self, token: str, catalog: str) -> Optional[bool]:
        """None when the token is nobody's."""
        self.refresh()
        grant = self.grants.get(hashed(token))
        return None if grant is None else any(fnmatchcase(catalog, pattern) for pattern in grant["catalogs"])


def hashed(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class CatalogServer:
    """Serves catalogs read-only, each under its name: http://host:port/<catalog>/<path>. Without `tokens` anyone who can
    reach it can read, which is refused past this machine unless `public` says so."""

    def __init__(self, catalogs: Sequence[Paths], tokens: Optional[Tokens] = None, host: str = "127.0.0.1", port: int = 0,
                 public: bool = False) -> None:
        if tokens is None and not public and not is_local(host):
            raise CatalogError(f"{host} is reachable from elsewhere, so give tokens, or public=True if everyone may read")
        self.catalogs = {found.name: found.root for found in map(SharedCatalog.open, catalogs)}
        if tokens is not None and tokens.path and any(tokens.path.is_relative_to(root) for root in self.catalogs.values()):
            raise CatalogError(f"{tokens.path} is inside a catalog being served")
        self.tokens = tokens
        server = self

        class Handler(http.server.BaseHTTPRequestHandler):
            server_version, sys_version = "srlocations", ""

            def log_message(self, *args: Any) -> None:
                pass

            def refuse(self, code: int) -> None:
                self.send_response(code)
                if code == 401:
                    self.send_header("WWW-Authenticate", "Bearer")
                self.send_header("Content-Length", "0")
                self.end_headers()

            def do_GET(self) -> None:
                split = urllib.parse.urlsplit(self.path)
                catalog, _, path = urllib.parse.unquote(split.path).lstrip("/").partition("/")
                if server.tokens is not None:
                    scheme, _, token = self.headers.get("Authorization", "").partition(" ")
                    allowed_here = server.tokens.allows(token, catalog) if scheme == "Bearer" else None
                    if allowed_here is None:
                        return self.refuse(401)
                    if not allowed_here:
                        return self.refuse(404)  # no different from a catalog that is not here
                served = server.answer(catalog, path)
                if served is None:
                    return self.refuse(404)
                self.send_response(200)
                self.send_header("Content-Type", served[0])
                self.send_header("Content-Length", str(served[1]))
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(served[2]) if isinstance(served[2], bytes) else served[2](self.wfile)

            def do_HEAD(self) -> None:
                self.refuse(405)

            do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD

        self.httpd = http.server.ThreadingHTTPServer((host, port), Handler)
        self.httpd.daemon_threads = True
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def answer(self, catalog: str, path: str) -> Optional[tuple[str, int, Any]]:
        root = self.catalogs.get(catalog)
        if root is None:
            return None
        if path == MANIFEST and not (root / MANIFEST).exists():
            data = encoded(manifest_of(root))
            return "application/json", len(data), data
        if not allowed(path) and path not in (MANIFEST, SIGNATURE):
            return None
        source = root / path
        if source.is_symlink() or not source.is_file() or not source.resolve().is_relative_to(root):
            return None
        kind = {".json": "application/json", ".html": "text/html; charset=utf-8", ".png": "image/png"}.get(source.suffix,
                                                                                                         "application/octet-stream")

        def send(out: IO[bytes]) -> None:
            with source.open("rb") as stream:
                shutil.copyfileobj(stream, out)
        return kind, source.stat().st_size, send

    @property
    def url(self) -> str:
        host, port = self.httpd.server_address[:2]
        return f"http://{host}:{port}"

    def start(self) -> "CatalogServer":
        self.thread.start()
        return self

    def stop(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()

    def __enter__(self) -> "CatalogServer":
        return self.start()

    def __exit__(self, *_: Any) -> None:
        self.stop()


def main(arguments: Optional[Sequence[str]] = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m srlocations.exchange", description="Seal, serve and fetch shared catalogs")
    steps = parser.add_subparsers(dest="step", required=True)
    step = steps.add_parser("seal", help="sign what a catalog holds now")
    step.add_argument("catalog")
    step.add_argument("key")
    step = steps.add_parser("browse", help="write a catalog's page, with thumbnails")
    step.add_argument("catalog")
    step = steps.add_parser("serve", help="serve catalogs read-only until stopped")
    step.add_argument("catalogs", nargs="+")
    step.add_argument("--tokens")
    step.add_argument("--host", default="127.0.0.1")
    step.add_argument("--port", type=int, default=8740)
    step.add_argument("--public", action="store_true")
    step = steps.add_parser("token", help="give someone a token, printed once")
    step.add_argument("file")
    step.add_argument("name")
    step.add_argument("catalogs", nargs="*", default=["*"])
    step = steps.add_parser("revoke", help="remove someone's tokens")
    step.add_argument("file")
    step.add_argument("name")
    step = steps.add_parser("fetch", help="bring a catalog here. A token comes from SRLOCATIONS_TOKEN")
    step.add_argument("source")
    step.add_argument("folder")
    step.add_argument("--signers")
    chosen = parser.parse_args(arguments)
    if chosen.step == "seal":
        print(seal(chosen.catalog, chosen.key))
    elif chosen.step == "browse":
        print(SharedCatalog.open(chosen.catalog).browse())
    elif chosen.step == "token":
        print(Tokens.load(chosen.file).issue(chosen.name, chosen.catalogs))
    elif chosen.step == "revoke":
        print(Tokens.load(chosen.file).revoke(chosen.name))
    elif chosen.step == "fetch":
        print(fetch(chosen.source, chosen.folder, os.environ.get("SRLOCATIONS_TOKEN"), chosen.signers).root)
    else:
        tokens = Tokens.load(chosen.tokens) if chosen.tokens else None
        with CatalogServer(chosen.catalogs, tokens, chosen.host, chosen.port, chosen.public) as server:
            print(server.url, flush=True)
            server.thread.join()


if __name__ == "__main__":
    main()
