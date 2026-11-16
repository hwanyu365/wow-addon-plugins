"""CurseForge 배포용 MCP 서버. 태그 시점 애드온 파일을 zip 으로 묶어 CurseForge 에 release 로 올린다."""
import http.client
import io
import json
import os
import re
import subprocess
import sys
import tarfile
import urllib.error
import urllib.request
import uuid
import zipfile
from pathlib import Path

API = "https://wow.curseforge.com/api"
EXCLUDED_TOP_DIRS = {"docs", "scripts"}
_urlopen = urllib.request.urlopen


class DeployError(Exception):
    pass


def interface_to_versions(interface):
    names = []
    for part in interface.split(","):
        n = int(part.strip())
        names.append(f"{n // 10000}.{n // 100 % 100}.{n % 100}")
    return names


def parse_toc(text):
    fields, files = {}, []
    for line in text.splitlines():
        line = line.strip()
        m = re.match(r"^##\s*([\w-]+)\s*:\s*(.*)$", line)
        if m:
            fields[m.group(1)] = m.group(2).strip()
        elif line and not line.startswith("#"):
            files.append(line.replace("\\", "/"))
    return fields, files


def is_packaged(path):
    parts = path.split("/")
    name = parts[-1].lower()
    if any(p.startswith(".") for p in parts):
        return False
    if len(parts) > 1 and parts[0] in EXCLUDED_TOP_DIRS:
        return False
    return not (name.endswith(".md") or name.endswith(".test.lua"))


def extract_changelog(text, version):
    m = re.search(rf"^##\s*\[{re.escape(version)}\].*?$(.*?)(?=^##\s|\Z)", text, re.MULTILINE | re.DOTALL)
    if not m or not m.group(1).strip():
        raise DeployError(f"CHANGELOG.md 에 ## [{version}] 섹션이 없습니다.")
    return m.group(1).strip()


def resolve_game_versions(names, available):
    by_name = {v.get("name"): v["id"] for v in available}
    missing = [n for n in names if n not in by_name]
    if missing:
        raise DeployError(f"CurseForge 에 게임 버전 {', '.join(missing)} 이 아직 없습니다. TOC Interface 를 확인하거나 등록될 때까지 기다리세요.")
    return [{"name": n, "id": by_name[n]} for n in names]


def build_metadata(addon, version, changelog, game_version_ids):
    return {
        "releaseType": "release",
        "displayName": f"{addon} {version}",
        "changelogType": "markdown",
        "changelog": changelog,
        "gameVersions": game_version_ids,
    }


def _git(repo, *args):
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True)
    if r.returncode != 0:
        raise DeployError(f"git {' '.join(args)} 실패: {r.stderr.decode('utf-8', 'replace').strip()}")
    return r.stdout


def _show(repo, tag, path):
    return _git(repo, "show", f"{tag}:{path}").decode("utf-8-sig")


def build_package(repo, tag):
    if subprocess.run(["git", "-C", repo, "rev-parse", "--verify", "--quiet", f"refs/tags/{tag}"],
                      capture_output=True).returncode != 0:
        raise DeployError(f"태그 {tag} 가 {repo} 에 없습니다.")

    tocs = [n for n in _git(repo, "ls-tree", "--name-only", tag).decode().splitlines() if n.endswith(".toc")]
    if len(tocs) != 1:
        raise DeployError(f"저장소 루트의 .toc 가 정확히 하나여야 합니다 (발견: {tocs or '없음'}).")
    addon = tocs[0][:-4]
    fields, toc_files = parse_toc(_show(repo, tag, tocs[0]))

    version = fields.get("Version", "")
    if version != tag.removeprefix("v"):
        raise DeployError(f"TOC Version '{version}' 이 태그 {tag} 와 다릅니다.")
    project_id = fields.get("X-Curse-Project-ID")
    if not project_id:
        raise DeployError(f"{tocs[0]} 에 ## X-Curse-Project-ID 가 없습니다.")
    try:
        interface_to_versions(fields.get("Interface", ""))
    except ValueError:
        raise DeployError(f"{tocs[0]} 의 ## Interface 가 없거나 숫자가 아닙니다: '{fields.get('Interface', '')}'") from None

    with tarfile.open(fileobj=io.BytesIO(_git(repo, "archive", "--format=tar", tag))) as tar:
        members = [m for m in tar.getmembers() if m.isfile() and is_packaged(m.name)]
        missing = sorted(set(toc_files) - {m.name for m in members})
        if missing:
            raise DeployError(f"TOC 에 나열됐지만 zip 에 없는 파일: {', '.join(missing)}")
        zip_path = Path(repo) / "dist" / f"{addon}-{version}.zip"
        zip_path.parent.mkdir(exist_ok=True)
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
            for m in members:
                z.writestr(f"{addon}/{m.name}", tar.extractfile(m).read())

    return {
        "addon": addon,
        "version": version,
        "project_id": project_id,
        "interface": fields.get("Interface", ""),
        "zip": str(zip_path),
        "files": len(members),
        "size_kb": zip_path.stat().st_size // 1024,
        "changelog": extract_changelog(_show(repo, tag, "CHANGELOG.md"), version),
    }


def _request(req):
    try:
        with _urlopen(req, timeout=300) as r:
            body = r.read()
    except urllib.error.HTTPError as e:
        text = e.read().decode("utf-8", "replace")
        token = req.get_header("X-api-token")
        if token:
            text = text.replace(token, "***")
        raise DeployError(f"HTTP {e.code} {req.full_url}: {text[:500]}")
    except urllib.error.URLError as e:
        raise DeployError(f"{req.full_url} 연결 실패: {e.reason}")
    except (OSError, http.client.HTTPException) as e:
        raise DeployError(f"{req.full_url} 응답을 받지 못했습니다 ({type(e).__name__}) → 요청이 처리됐는지 알 수 없습니다. 업로드였다면 재시도 전에 CurseForge Files 탭을 확인하세요.") from None
    try:
        return json.loads(body)
    except ValueError:
        raise DeployError(f"{req.full_url} 응답을 JSON 으로 읽지 못했습니다 → 요청이 처리됐는지 알 수 없습니다. 업로드였다면 재시도 전에 CurseForge Files 탭을 확인하세요.") from None


def prepare(repo, tag, token):
    pkg = build_package(repo, tag)
    if not token:
        raise DeployError("CurseForge 토큰(api_token)이 설정되지 않았습니다. /plugin → curseforge → Configure options 에서 입력한 뒤 Claude Code 를 재시작하세요.")
    with zipfile.ZipFile(pkg["zip"]) as z:
        leaked = [n for n in z.namelist() if token.encode() in z.read(n)]
    if token in pkg["changelog"]:
        leaked.append("CHANGELOG.md 의 이번 버전 섹션")
    if leaked:
        raise DeployError(f"공개될 내용에 CurseForge 토큰 문자열이 들어 있어 중단합니다: {', '.join(leaked)}")
    available = _request(urllib.request.Request(f"{API}/game/versions", headers={"X-Api-Token": token}))
    return {**pkg, "game_versions": resolve_game_versions(interface_to_versions(pkg["interface"]), available)}


def upload(repo, tag, token):
    p = prepare(repo, tag, token)
    meta = build_metadata(p["addon"], p["version"], p["changelog"], [g["id"] for g in p["game_versions"]])
    boundary = uuid.uuid4().hex
    zip_bytes = Path(p["zip"]).read_bytes()
    body = (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"metadata\"\r\n\r\n".encode()
        + json.dumps(meta, ensure_ascii=False).encode()
        + f"\r\n--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{Path(p['zip']).name}\"\r\n"
          f"Content-Type: application/zip\r\n\r\n".encode()
        + zip_bytes
        + f"\r\n--{boundary}--\r\n".encode()
    )
    req = urllib.request.Request(
        f"{API}/projects/{p['project_id']}/upload-file", data=body, method="POST",
        headers={"X-Api-Token": token, "Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    resp = _request(req)
    file_id = resp.get("id") if isinstance(resp, dict) else None
    if not file_id:
        raise DeployError("업로드 응답에 파일 ID 가 없습니다 → 올라갔을 수 있습니다. 재시도 전에 CurseForge Files 탭을 확인하세요.")
    return {**p, "file_id": file_id}


TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "repo": {"type": "string", "description": "애드온 저장소 절대 경로"},
        "tag": {"type": "string", "description": "릴리스 태그, 예: v1.0.2"},
    },
    "required": ["repo", "tag"],
}
TOOLS = {
    "prepare": (prepare, "태그 시점 파일로 zip 을 만들고 업로드할 내용을 검증해 돌려준다. 업로드하지 않는다."),
    "upload": (upload, "prepare 를 다시 수행한 뒤 CurseForge 에 release 로 업로드하고 파일 ID 를 돌려준다. 되돌릴 수 없는 공개 동작이다."),
}


def handle(msg, token):
    if "id" not in msg:
        return None
    method, params = msg.get("method"), msg.get("params") or {}
    if method == "initialize":
        result = {
            "protocolVersion": params.get("protocolVersion", "2025-06-18"),
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "curseforge", "version": "0.1.1"},
        }
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": [{"name": n, "description": d, "inputSchema": TOOL_SCHEMA} for n, (_, d) in TOOLS.items()]}
    elif method == "tools/call" and params.get("name") in TOOLS:
        fn = TOOLS[params["name"]][0]
        args = params.get("arguments") or {}
        try:
            text, is_error = json.dumps(fn(args["repo"], args["tag"], token), ensure_ascii=False, indent=2), False
        except Exception as e:  # 서버가 죽으면 세션 내내 도구가 사라진다 → 모든 실패를 도구 오류로 돌려준다
            text, is_error = f"{type(e).__name__}: {e}", True
        if token:
            text = text.replace(token, "***")
        result = {"content": [{"type": "text", "text": text}], "isError": is_error}
    else:
        return {"jsonrpc": "2.0", "id": msg["id"], "error": {"code": -32601, "message": f"unknown method {method}"}}
    return {"jsonrpc": "2.0", "id": msg["id"], "result": result}


def main():
    if sys.version_info < (3, 10):
        sys.exit(f"curseforge MCP 서버는 Python 3.10 이상이 필요합니다 (현재 {sys.version_info[0]}.{sys.version_info[1]}).")
    token = os.environ.get("CURSEFORGE_TOKEN", "")
    if token.startswith("${"):  # userConfig 미설정이면 치환되지 않은 자리표시자가 그대로 들어올 수 있다
        token = ""
    for line in sys.stdin.buffer:
        if not line.strip():
            continue
        try:
            resp = handle(json.loads(line), token)
        except json.JSONDecodeError:
            resp = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}
        if resp is not None:
            sys.stdout.buffer.write(json.dumps(resp, ensure_ascii=False).encode() + b"\n")
            sys.stdout.buffer.flush()


if __name__ == "__main__":
    main()
