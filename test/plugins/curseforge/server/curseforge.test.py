import ast
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

_spec = importlib.util.spec_from_file_location("curseforge", Path(__file__).resolve().parents[4] / "plugins/curseforge/server/curseforge.py")
cf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cf)

TOKEN = "secret-token-123"
GAME_VERSIONS = [{"id": 16984, "name": "12.1.5"}, {"id": 15000, "name": "11.2.7"}]

TOC = """## Interface: 120105
## Title: Demo
## Version: 1.2.0
## X-Curse-Project-ID: 42

# comment
Init.lua

Core\\Main.lua
"""

CHANGELOG = """# Demo Changelog

## [1.2.0] - 2026-10-18

### Changed
- 새 항목

## [1.1.0] - 2026-01-01

- 옛 항목
"""


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def make_repo(files, tag="v1.2.0"):
    d = Path(tempfile.mkdtemp())
    git(d, "init", "-q")
    git(d, "config", "user.email", "t@t")
    git(d, "config", "user.name", "t")
    git(d, "config", "core.autocrlf", "false")
    for rel, text in files.items():
        p = d / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8", newline="")
    git(d, "add", "-A")
    git(d, "commit", "-q", "-m", "init")
    if tag:
        git(d, "tag", tag)
    return d


def demo_files(**override):
    files = {
        "Demo.toc": TOC,
        "Init.lua": "-- init",
        "Core/Main.lua": "-- main",
        "Media/icon.tga": "tga",
        "LICENSE": "MIT",
        "CHANGELOG.md": CHANGELOG,
        "README.md": "readme",
        ".github/workflows/ci.yml": "ci",
        ".luacheckrc": "std",
        "docs/spec.md": "spec",
        "scripts/verify.sh": "sh",
        "Core/Main.test.lua": "-- test",
    }
    files.update(override)
    return {k: v for k, v in files.items() if v is not None}


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeHttp:
    def __init__(self):
        self.requests = []

    def __call__(self, req, timeout=None):
        self.requests.append(req)
        if req.get_method() == "GET":
            return FakeResponse(json.dumps(GAME_VERSIONS).encode())
        return FakeResponse(json.dumps({"id": 9999}).encode())


class Pure(unittest.TestCase):
    def test_TC1_interface_to_versions(self):
        self.assertEqual(cf.interface_to_versions("120105"), ["12.1.5"])
        self.assertEqual(cf.interface_to_versions("120105, 110207"), ["12.1.5", "11.2.7"])

    def test_TC2_parse_toc(self):
        fields, files = cf.parse_toc(TOC)
        self.assertEqual(fields["Version"], "1.2.0")
        self.assertEqual(fields["X-Curse-Project-ID"], "42")
        self.assertEqual(files, ["Init.lua", "Core/Main.lua"])

    def test_TC3_is_packaged(self):
        for path in [".github/workflows/ci.yml", ".luacheckrc", "Core/.hidden", "docs/spec.md",
                     "scripts/verify.sh", "README.md", "README.MD", "Core/Main.test.lua", "Core/X.TEST.LUA"]:
            self.assertFalse(cf.is_packaged(path), path)
        for path in ["LICENSE", "Media/x.tga", "UI/scripts/x.lua", "Init.lua", "Demo.toc"]:
            self.assertTrue(cf.is_packaged(path), path)

    def test_TC10_resolve_game_versions(self):
        self.assertEqual(cf.resolve_game_versions(["12.1.5"], GAME_VERSIONS), [{"name": "12.1.5", "id": 16984}])
        with self.assertRaisesRegex(cf.DeployError, "12.9.9"):
            cf.resolve_game_versions(["12.1.5", "12.9.9"], GAME_VERSIONS)

    def test_TC11_extract_changelog(self):
        got = cf.extract_changelog(CHANGELOG, "1.2.0")
        self.assertIn("새 항목", got)
        self.assertNotIn("옛 항목", got)
        with self.assertRaises(cf.DeployError):
            cf.extract_changelog(CHANGELOG, "9.9.9")
        with self.assertRaises(cf.DeployError):
            cf.extract_changelog("## [2.0.0]\n\n## [1.0.0]\n- x\n", "2.0.0")

    def test_TC12_metadata(self):
        meta = cf.build_metadata("Demo", "1.2.0", "log", [16984])
        self.assertEqual(set(meta), {"releaseType", "displayName", "changelogType", "changelog", "gameVersions"})
        self.assertEqual(meta["releaseType"], "release")
        self.assertEqual(meta["displayName"], "Demo 1.2.0")
        self.assertEqual(meta["changelogType"], "markdown")
        self.assertEqual(meta["changelog"], "log")
        self.assertEqual(meta["gameVersions"], [16984])


class Package(unittest.TestCase):
    def test_TC4_zip_from_tag(self):
        repo = make_repo(demo_files())
        (repo / "Init.lua").write_text("-- dirty", encoding="utf-8")
        (repo / "Untracked.lua").write_text("x", encoding="utf-8")
        (repo / "Demo.toc").write_text(TOC.replace("1.2.0", "9.9.9"), encoding="utf-8")
        (repo / "CHANGELOG.md").write_text(CHANGELOG.replace("새 항목", "작업 트리 항목"), encoding="utf-8")
        zip_path = repo / "dist" / "Demo-1.2.0.zip"
        zip_path.parent.mkdir()
        with zipfile.ZipFile(zip_path, "w") as z:
            z.writestr("Demo/Stale.lua", "old")
        pkg = cf.build_package(str(repo), "v1.2.0")
        self.assertEqual(pkg["version"], "1.2.0")
        self.assertIn("새 항목", pkg["changelog"])
        self.assertEqual(Path(pkg["zip"]), zip_path)
        with zipfile.ZipFile(zip_path) as z:
            names = sorted(z.namelist())
            self.assertEqual(z.read("Demo/Init.lua"), b"-- init")
        self.assertEqual(names, sorted(["Demo/Demo.toc", "Demo/Init.lua", "Demo/Core/Main.lua",
                                        "Demo/Media/icon.tga", "Demo/LICENSE"]))
        self.assertEqual(pkg["files"], 5)

    def test_TC20_skips_export_ignore_and_symlinks(self):
        repo = make_repo(demo_files(**{".gitattributes": "Extra.lua export-ignore\n", "Extra.lua": "x"}), tag=None)
        blob = subprocess.run(["git", "-C", str(repo), "hash-object", "-w", "--stdin"], input=b"Init.lua",
                              check=True, capture_output=True).stdout.decode().strip()
        git(repo, "update-index", "--add", "--cacheinfo", f"120000,{blob},Link.lua")
        git(repo, "commit", "-q", "-m", "link")
        git(repo, "tag", "v1.2.0")
        pkg = cf.build_package(str(repo), "v1.2.0")
        with zipfile.ZipFile(pkg["zip"]) as z:
            names = set(z.namelist())
        self.assertNotIn("Demo/Extra.lua", names)
        self.assertNotIn("Demo/Link.lua", names)
        self.assertIn("Demo/Init.lua", names)

    def test_TC23_addon_name_is_toc_file_name(self):
        repo = make_repo(demo_files(**{"Demo.toc": None, "Other.toc": TOC}))
        pkg = cf.build_package(str(repo), "v1.2.0")
        self.assertEqual(pkg["addon"], "Other")
        self.assertEqual(Path(pkg["zip"]).name, "Other-1.2.0.zip")
        with zipfile.ZipFile(pkg["zip"]) as z:
            self.assertTrue(all(n.startswith("Other/") for n in z.namelist()))

    def test_TC5_missing_tag(self):
        repo = make_repo(demo_files(), tag=None)
        with self.assertRaisesRegex(cf.DeployError, "태그 v1.2.0"):
            cf.build_package(str(repo), "v1.2.0")
        git(repo, "branch", "v1.2.0")
        with self.assertRaisesRegex(cf.DeployError, "태그 v1.2.0"):
            cf.build_package(str(repo), "v1.2.0")

    def test_TC6_toc_count(self):
        with self.assertRaises(cf.DeployError):
            cf.build_package(str(make_repo(demo_files(**{"Demo.toc": None, "Init.lua": "x"}))), "v1.2.0")
        with self.assertRaises(cf.DeployError):
            cf.build_package(str(make_repo(demo_files(**{"Other.toc": TOC}))), "v1.2.0")
        self.assertEqual(cf.build_package(str(make_repo(demo_files(**{"Sub/Other.toc": TOC}))), "v1.2.0")["addon"], "Demo")

    def test_TC7_version_mismatch(self):
        repo = make_repo(demo_files(), tag="v1.3.0")
        with self.assertRaisesRegex(cf.DeployError, "1.3.0"):
            cf.build_package(str(repo), "v1.3.0")

    def test_TC8_toc_file_excluded(self):
        repo = make_repo(demo_files(**{"Demo.toc": TOC + "docs\\Extra.lua\n", "docs/Extra.lua": "x"}))
        with self.assertRaisesRegex(cf.DeployError, "docs/Extra.lua"):
            cf.build_package(str(repo), "v1.2.0")
        self.assertFalse((repo / "dist" / "Demo-1.2.0.zip").exists())

    def test_TC9_missing_project_id(self):
        repo = make_repo(demo_files(**{"Demo.toc": TOC.replace("## X-Curse-Project-ID: 42\n", "")}))
        with self.assertRaisesRegex(cf.DeployError, "X-Curse-Project-ID"):
            cf.build_package(str(repo), "v1.2.0")


class Network(unittest.TestCase):
    def test_TC14_no_token_no_network(self):
        repo = make_repo(demo_files())
        http = FakeHttp()
        with mock.patch.object(cf, "_urlopen", http):
            for fn in (cf.prepare, cf.upload):
                with self.assertRaisesRegex(cf.DeployError, "api_token.*Configure options"):
                    fn(str(repo), "v1.2.0", "")
        self.assertEqual(http.requests, [])

    def test_TC15_token_only_in_header(self):
        repo = make_repo(demo_files())
        http = FakeHttp()
        with mock.patch.object(cf, "_urlopen", http):
            result = cf.upload(str(repo), "v1.2.0", TOKEN)
        self.assertEqual(result["file_id"], 9999)
        self.assertEqual(result["game_versions"], [{"name": "12.1.5", "id": 16984}])
        self.assertNotIn(TOKEN, json.dumps(result))
        get, post = http.requests
        self.assertEqual(get.full_url, "https://wow.curseforge.com/api/game/versions")
        self.assertEqual(post.full_url, "https://wow.curseforge.com/api/projects/42/upload-file")
        for req in (get, post):
            self.assertEqual(req.get_header("X-api-token"), TOKEN)
        self.assertNotIn(TOKEN.encode(), post.data)
        self.assertIn(b'Content-Disposition: form-data; name="metadata"', post.data)
        self.assertIn(b'Content-Disposition: form-data; name="file"; filename="Demo-1.2.0.zip"', post.data)
        meta = json.loads(post.data.split(b'name="metadata"\r\n\r\n')[1].split(b"\r\n--")[0])
        self.assertEqual(meta, {"releaseType": "release", "displayName": "Demo 1.2.0", "changelogType": "markdown",
                                "changelog": cf.extract_changelog(CHANGELOG, "1.2.0"), "gameVersions": [16984]})

    def test_TC24_prepare_never_uploads(self):
        repo = make_repo(demo_files())
        http = FakeHttp()
        with mock.patch.object(cf, "_urlopen", http):
            result = cf.prepare(str(repo), "v1.2.0", TOKEN)
        self.assertEqual([r.get_method() for r in http.requests], ["GET"])
        self.assertEqual(set(result), {"addon", "version", "project_id", "interface", "zip", "files", "size_kb", "changelog", "game_versions"})

    def test_TC27_upload_without_file_id_is_unknown(self):
        repo = make_repo(demo_files())
        for body in (b"{}", b"<html>ok</html>"):
            def http(req, timeout=None, body=body):
                return FakeResponse(json.dumps(GAME_VERSIONS).encode() if req.get_method() == "GET" else body)

            with mock.patch.object(cf, "_urlopen", http):
                with self.assertRaisesRegex(cf.DeployError, "Files 탭"):
                    cf.upload(str(repo), "v1.2.0", TOKEN)

    def test_TC28_bad_interface_fails_before_network(self):
        for interface in ("", "## Interface: abc\n"):
            toc = TOC.replace("## Interface: 120105\n", interface)
            repo = make_repo(demo_files(**{"Demo.toc": toc}))
            http = FakeHttp()
            with mock.patch.object(cf, "_urlopen", http):
                with self.assertRaisesRegex(cf.DeployError, "Interface"):
                    cf.prepare(str(repo), "v1.2.0", TOKEN)
            self.assertEqual(http.requests, [])

    def test_TC26_file_problems_before_token(self):
        repo = make_repo(demo_files(), tag="v1.3.0")
        with self.assertRaisesRegex(cf.DeployError, "Version"):
            cf.prepare(str(repo), "v1.3.0", "")

    def test_TC15_error_message_hides_token(self):
        repo = make_repo(demo_files())

        def failing(req, timeout=None):
            raise cf.urllib.error.HTTPError(req.full_url, 403, "Forbidden", {}, io.BytesIO(b"bad token"))

        with mock.patch.object(cf, "_urlopen", failing):
            with self.assertRaises(cf.DeployError) as ctx:
                cf.prepare(str(repo), "v1.2.0", TOKEN)
        self.assertIn("403", str(ctx.exception))
        self.assertNotIn(TOKEN, str(ctx.exception))


class Mcp(unittest.TestCase):
    def test_TC13_protocol(self):
        init = cf.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                          "params": {"protocolVersion": "2025-06-18"}}, TOKEN)
        self.assertEqual(init["result"]["protocolVersion"], "2025-06-18")
        self.assertIn("tools", init["result"]["capabilities"])
        self.assertIsNone(cf.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}, TOKEN))
        tools = cf.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, TOKEN)["result"]["tools"]
        self.assertEqual(sorted(t["name"] for t in tools), ["prepare", "upload"])
        call = cf.handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                          "params": {"name": "prepare", "arguments": {"repo": "Z:/nope", "tag": "v1"}}}, TOKEN)
        self.assertTrue(call["result"]["isError"])
        self.assertEqual(cf.handle({"jsonrpc": "2.0", "id": 4, "method": "nope"}, TOKEN)["error"]["code"], -32601)


class Manifest(unittest.TestCase):
    plugin = Path(_spec.origin).parents[1]

    def test_TC17_server_imports_stdlib_only(self):
        tree = ast.parse(Path(_spec.origin).read_text(encoding="utf-8"))
        modules = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        modules |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.level == 0}
        self.assertEqual(sorted(modules - sys.stdlib_module_names), [])

    def test_TC18_token_from_sensitive_user_config_only(self):
        token = json.loads((self.plugin / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))["userConfig"]["api_token"]
        self.assertEqual(token.get("type"), "string")
        self.assertIs(token.get("sensitive"), True)
        self.assertIs(token.get("required"), True)
        server = json.loads((self.plugin / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]["curseforge"]
        self.assertEqual(server.get("env"), {"CURSEFORGE_TOKEN": "${user_config.api_token}"})

    def test_TC25_marketplace_registers_plugin(self):
        market = json.loads((self.plugin.parents[1] / ".claude-plugin/marketplace.json").read_text(encoding="utf-8"))
        self.assertEqual(market["name"], "wow-addon-plugins")
        self.assertEqual([p["source"] for p in market["plugins"] if p["name"] == "curseforge"], ["./plugins/curseforge"])


def run_server(env_token, *messages):
    stdin = SimpleNamespace(buffer=io.BytesIO(b"".join(json.dumps(m).encode() + b"\n" for m in messages)))
    stdout = SimpleNamespace(buffer=io.BytesIO())
    with mock.patch.dict(os.environ, {"CURSEFORGE_TOKEN": env_token}), \
            mock.patch.object(cf.sys, "stdin", stdin), mock.patch.object(cf.sys, "stdout", stdout):
        cf.main()
    return [json.loads(line) for line in stdout.buffer.getvalue().splitlines()]


def call(name, repo, tag="v1.2.0", id=1):
    return {"jsonrpc": "2.0", "id": id, "method": "tools/call", "params": {"name": name, "arguments": {"repo": str(repo), "tag": tag}}}


class Server(unittest.TestCase):
    def test_TC19_refuses_python_below_3_10(self):
        stdin = mock.MagicMock()
        with mock.patch.object(cf.sys, "version_info", (3, 9, 18, "final", 0)), mock.patch.object(cf.sys, "stdin", stdin):
            with self.assertRaises(SystemExit) as ctx:
                cf.main()
        self.assertIn("3.10", str(ctx.exception.code))
        stdin.buffer.__iter__.assert_not_called()

    def test_TC21_redacts_token_echoed_in_response(self):
        repo = make_repo(demo_files())

        def failing(req, timeout=None):
            raise cf.urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, io.BytesIO(f'{{"error": "invalid {TOKEN}"}}'.encode()))

        with mock.patch.object(cf, "_urlopen", failing):
            text = cf.handle(call("prepare", repo), TOKEN)["result"]["content"][0]["text"]
        self.assertIn("401", text)
        self.assertIn("invalid ***", text)
        self.assertNotIn(TOKEN, text)
        with mock.patch.dict(cf.TOOLS, {"prepare": (lambda repo, tag, token: {"echo": f"a {token} b"}, "")}):
            result = cf.handle(call("prepare", "x"), TOKEN)["result"]
        self.assertFalse(result["isError"])
        self.assertIn("a *** b", result["content"][0]["text"])
        self.assertNotIn(TOKEN, result["content"][0]["text"])

    def test_TC30_token_in_published_content_fails_before_network(self):
        for files in ({"CHANGELOG.md": CHANGELOG.replace("새 항목", f"새 항목 {TOKEN}")}, {"Init.lua": f"-- {TOKEN}"}):
            repo = make_repo(demo_files(**files))
            for fn in (cf.prepare, cf.upload):
                http = FakeHttp()
                with mock.patch.object(cf, "_urlopen", http):
                    with self.assertRaisesRegex(cf.DeployError, "토큰") as ctx:
                        fn(str(repo), "v1.2.0", TOKEN)
                self.assertEqual(http.requests, [])
                self.assertNotIn(TOKEN, str(ctx.exception))

    def test_TC31_unreadable_response_is_unknown(self):
        class Cut(FakeResponse):
            def read(self, *a):
                raise cf.http.client.IncompleteRead(b"{", 10)

        def timeout(req, timeout=None):
            raise TimeoutError("timed out")

        for opener in (timeout, lambda req, timeout=None: Cut()):
            with mock.patch.object(cf, "_urlopen", opener):
                with self.assertRaisesRegex(cf.DeployError, "Files 탭"):
                    cf._request(cf.urllib.request.Request("https://wow.curseforge.com/api/x", data=b"x", method="POST"))

    def test_TC29_redacts_before_truncating_body(self):
        repo = make_repo(demo_files())

        def failing(req, timeout=None):
            raise cf.urllib.error.HTTPError(req.full_url, 400, "Bad", {}, io.BytesIO(("x" * 495 + TOKEN + "tail").encode()))

        with mock.patch.object(cf, "_urlopen", failing):
            with self.assertRaises(cf.DeployError) as ctx:
                cf.prepare(str(repo), "v1.2.0", TOKEN)
        self.assertNotIn(TOKEN[:5], str(ctx.exception))
        self.assertIn("***", str(ctx.exception))

    def test_TC22_placeholder_token_means_unset(self):
        repo = make_repo(demo_files())
        http = FakeHttp()
        with mock.patch.object(cf, "_urlopen", http):
            (resp,) = run_server("${user_config.api_token}", call("prepare", repo))
        self.assertTrue(resp["result"]["isError"])
        self.assertIn("api_token", resp["result"]["content"][0]["text"])
        self.assertEqual(http.requests, [])


if __name__ == "__main__":
    unittest.main()
