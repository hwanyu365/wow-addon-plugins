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
from unittest import mock

_spec = importlib.util.spec_from_file_location("curseforge", Path(__file__).with_name("curseforge.py"))
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
                     "scripts/verify.sh", "README.md", "Core/Main.test.lua"]:
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

    def test_TC12_metadata(self):
        meta = cf.build_metadata("Demo", "1.2.0", "log", [16984])
        self.assertEqual(set(meta), {"releaseType", "displayName", "changelogType", "changelog", "gameVersions"})
        self.assertEqual(meta["releaseType"], "release")
        self.assertEqual(meta["displayName"], "Demo 1.2.0")


class Package(unittest.TestCase):
    def test_TC4_zip_from_tag(self):
        repo = make_repo(demo_files())
        (repo / "Init.lua").write_text("-- dirty", encoding="utf-8")
        (repo / "Untracked.lua").write_text("x", encoding="utf-8")
        pkg = cf.build_package(str(repo), "v1.2.0")
        zip_path = repo / "dist" / "Demo-1.2.0.zip"
        self.assertEqual(Path(pkg["zip"]), zip_path)
        with zipfile.ZipFile(zip_path) as z:
            names = sorted(z.namelist())
            self.assertEqual(z.read("Demo/Init.lua"), b"-- init")
        self.assertEqual(names, sorted(["Demo/Demo.toc", "Demo/Init.lua", "Demo/Core/Main.lua",
                                        "Demo/Media/icon.tga", "Demo/LICENSE"]))
        self.assertEqual(pkg["files"], 5)

    def test_TC5_missing_tag(self):
        repo = make_repo(demo_files(), tag=None)
        with self.assertRaisesRegex(cf.DeployError, "v1.2.0"):
            cf.build_package(str(repo), "v1.2.0")

    def test_TC6_toc_count(self):
        with self.assertRaises(cf.DeployError):
            cf.build_package(str(make_repo(demo_files(**{"Demo.toc": None, "Init.lua": "x"}))), "v1.2.0")
        with self.assertRaises(cf.DeployError):
            cf.build_package(str(make_repo(demo_files(**{"Other.toc": TOC}))), "v1.2.0")

    def test_TC7_version_mismatch(self):
        repo = make_repo(demo_files(), tag="v1.3.0")
        with self.assertRaisesRegex(cf.DeployError, "1.3.0"):
            cf.build_package(str(repo), "v1.3.0")

    def test_TC8_toc_file_excluded(self):
        repo = make_repo(demo_files(**{"Demo.toc": TOC + "docs\\Extra.lua\n", "docs/Extra.lua": "x"}))
        with self.assertRaisesRegex(cf.DeployError, "docs/Extra.lua"):
            cf.build_package(str(repo), "v1.2.0")

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
                with self.assertRaisesRegex(cf.DeployError, "api_token"):
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
        self.assertIn("/projects/42/upload-file", post.full_url)
        for req in (get, post):
            self.assertEqual(req.get_header("X-api-token"), TOKEN)
        self.assertNotIn(TOKEN.encode(), post.data)
        self.assertIn(b'"releaseType": "release"', post.data)

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


if __name__ == "__main__":
    unittest.main()
