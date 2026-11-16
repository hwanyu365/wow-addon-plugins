# CurseForge 배포 플러그인 스펙

## 1. 개요

- **문서 정보:** spec_curseforge / hwanyu365 / 작성 2026-10-18 / 기준 커밋: 9a44a5c
- **기능명:** Claude Code 플러그인 `curseforge` (마켓플레이스 `wow-addon-plugins`)
- **목적**
  - CurseForge 업로드 도구가 옛 모노레포 스크립트에만 있다 → 애드온별 저장소로 분리된 뒤 배포 경로가 저장소 밖 폴더에 의존한다.
  - 옛 스크립트는 `<루트>/<Addon>/` 구조를 전제한다 → 분리 저장소(애드온 파일이 루트)에서 그대로 쓸 수 없다.
  - 배포 요청 시 GitHub 릴리스만 하고 CurseForge 업로드가 빠질 수 있다 → 배포 절차를 스킬로 고정한다.

## 2. 목표 및 범위

- **In Scope**
  - 태그 기준으로 애드온 zip 을 만들고 CurseForge 에 release 로 업로드한다.
  - 대상: TOC 가 저장소 루트에 있는 단일 애드온 저장소 (LorePin, TradeLedger).
- **Out of Scope**
  - 버전 bump·CHANGELOG 작성·태그 생성 → 각 저장소의 릴리스 절차가 담당한다.
  - beta/alpha 릴리스 타입, 올라간 파일 수정·삭제 (Upload API 에 엔드포인트가 없다).
  - 중복 업로드 탐지 (Upload API 에 파일 목록 조회가 없다) → 스킬 절차로만 막는다 [FR#12].
  - Wago·WoWInterface 업로드, GitHub 릴리스 첨부.

## 3. 요구사항

### 사용자 스토리

- `US#1` 저장소 소유자로서, 태그를 올린 뒤 "배포"라고만 지시해도 CurseForge 에 올라가길 원한다. 저장소마다 스크립트·토큰을 복사하지 않기 위해서다. [요구사항] → FR#1~FR#14

### 기능 요구사항

- `FR#1` 입력은 저장소 경로와 태그다. 태그가 없으면 실패한다. 모든 입력 파일(TOC·CHANGELOG·애드온 파일)은 작업 트리가 아니라 **태그 시점**에서 읽는다 → 커밋하지 않은 변경이 섞이지 않는다. [as-built]
- `FR#2` 태그 시점 저장소 루트의 `*.toc` 가 정확히 하나여야 한다. 애드온 이름은 TOC 파일명(확장자 제외)이다 → TOC `## Title` 과 달라도 파일명을 쓴다. [as-built]
- `FR#3` TOC `## Version` 이 태그에서 앞의 `v` 를 뗀 값과 같아야 한다. 다르면 실패한다 → 옛 버전 파일이 새 버전 이름으로 올라가는 것을 막는다. [as-built]
- `FR#4` zip 내용은 태그의 `git archive` 결과에서 아래를 뺀 것이다. 모든 항목은 `<애드온 이름>/` 아래에 둔다. [as-built]
  - `.gitattributes` 의 `export-ignore` 대상 → `git archive` 가 이미 뺀다. 저장소 소유자가 배포에서 뺀 파일이다.
  - 심볼릭 링크 → 일반 파일만 담는다.
  - 경로 구성 요소 중 하나라도 `.` 으로 시작하는 파일 (`.github/`, `.claude/`, `.gitignore`, `.luacheckrc` 등)
  - 최상위 `docs/`, `scripts/`
  - `*.md`, `*.test.lua` (확장자는 대소문자를 가리지 않는다)
- `FR#5` TOC 본문에 나열된 파일이 zip 에 하나라도 없으면 실패한다 → 제외 규칙이 게임에 필요한 파일을 빼는 경우를 잡는다. [as-built]
- `FR#6` zip 은 `<저장소>/dist/<애드온 이름>-<버전>.zip` 에 매번 새로 쓴다 → 남아 있던 옛 zip 이 올라가지 않는다. [as-built]
- `FR#7` TOC `## X-Curse-Project-ID` 가 없으면 실패한다. [as-built]
- `FR#8` TOC `## Interface` (쉼표 구분 다중 값 허용)를 `M.m.p` 이름으로 바꿔 CurseForge 게임 버전 ID 로 조회한다. 하나라도 없으면 실패한다. 변환은 `120105 → 12.1.5`. `## Interface` 가 없거나 숫자가 아니면 네트워크 요청 전에 실패한다. [as-built]
- `FR#9` changelog 는 태그 시점 `CHANGELOG.md` 의 `## [<버전>]` 섹션 본문이다. 섹션이 없거나 비어 있으면 실패한다 → 공개 페이지의 changelog 는 API 로 고칠 수 없으므로 대체 문구로 올리지 않는다. [as-built]
- `FR#10` 업로드 메타데이터는 `releaseType=release`, `displayName="<애드온 이름> <버전>"`, `changelogType=markdown`, `changelog`, `gameVersions` 만 담는다 → 배포자 실명·커밋 같은 정보가 공개 페이지에 나가지 않는다. [as-built]
- `FR#11` 플러그인은 MCP 도구 두 개를 제공한다. [as-built]
  - `prepare(repo, tag)`: FR#1~FR#9 를 수행하고 업로드할 내용을 돌려준다. 토큰이 있어도 업로드하지 않는다.
  - `upload(repo, tag)`: `prepare` 를 다시 수행한 뒤 업로드하고 CurseForge 파일 ID 를 돌려준다. 성공 응답에 파일 ID 가 없거나, 본문을 JSON 으로 읽지 못하거나, 응답 대기 시간 초과·수신 중 끊김이면 올라갔을 수 있다는 오류로 실패한다.
  - 모르는 JSON-RPC 메서드는 `-32601` 오류로 답한다.
- `FR#12` 스킬 `/curseforge:deploy <태그>` 절차 [요구사항]
  - 태그 인자가 없으면 `origin/main` 의 최근 태그를 제안하고 확인받는다.
  - 태그가 원격에 있는지 확인한다. 없으면 중단한다.
  - `prepare` 결과(애드온·버전·게임 버전·파일 수·크기·changelog)를 보여 준다. `prepare` 가 실패하면 검사를 우회하려고 TOC·CHANGELOG 를 고치지 않는다 → 고치려면 저장소 절차대로 새 태그를 만든다.
  - `upload` 를 한 번 호출하고 파일 ID·게임 버전·업로드한 zip 경로를 보고한다. CurseForge 의 처리·공개 상태는 이 도구로 조회할 수 없으므로 확인하지 않았다고 적는다.
  - 업로드가 성공 응답을 받은 뒤에는 같은 태그로 다시 올리지 않는다.
  - 응답을 받지 못한 실패(연결 끊김·타임아웃), HTTP 5xx, 파일 ID 없는 응답은 올라갔는지 알 수 없다 → 웹 Files 탭에서 올라가지 않았음을 사용자가 확인한 뒤에만 재시도한다.
  - HTTP 4xx 는 원인을 보고하고 지시를 기다린다.
- `FR#13` 토큰이 설정되지 않았으면 네트워크 요청 없이 실패하고, 설정 방법을 안내한다. 치환되지 않은 자리표시자(`${` 로 시작)도 미설정으로 본다. [as-built]
- `FR#14` 마켓플레이스 `wow-addon-plugins` 가 `./plugins/curseforge` 를 플러그인 `curseforge` 로 등록한다. [as-built]

### 비기능 요구사항

- `NFR#1` Python 3.10 이상의 표준 라이브러리만 쓴다 → 설치 단계가 없다. 3.10 미만이면 서버가 시작하지 않고 필요한 버전을 안내한다. [요구사항]
- `NFR#2` 토큰은 요청 헤더에만 쓴다. 요청 URL·본문, 도구 결과·오류 메시지에 넣지 않는다. 응답 본문에 토큰이 들어 있어도 내보내기 전에 `***` 로 가린다. 오류 문구의 응답 본문은 가린 뒤 500자로 자른다. zip 에 담길 파일이나 changelog 에 토큰 문자열이 있으면 네트워크 요청 전에 실패한다 → 공개 페이지에 올라가면 지울 수 없다. [요구사항]
- `NFR#3` 토큰은 플러그인 `userConfig` 의 sensitive 값으로만 받는다. 저장소 파일에 두지 않는다. [as-built]

## 4. 데이터 및 API 스펙

### 플러그인 구성

| 경로 | 역할 |
| --- | --- |
| `.claude-plugin/marketplace.json` | 마켓플레이스 `wow-addon-plugins` [FR#14] |
| `plugins/curseforge/.claude-plugin/plugin.json` | `userConfig.api_token` (string, sensitive, required) |
| `plugins/curseforge/.mcp.json` | MCP 서버 `curseforge`, env `CURSEFORGE_TOKEN=${user_config.api_token}` |
| `plugins/curseforge/server/curseforge.py` | MCP 서버 (stdio JSON-RPC) + 패키징·업로드 로직 |
| `plugins/curseforge/skills/deploy/SKILL.md` | 배포 절차 [FR#12] |

### MCP 도구

| 도구 | 입력 | 성공 결과 | 실패 |
| --- | --- | --- | --- |
| `prepare` | `repo`: 저장소 절대 경로 (스킬이 넘긴다. 서버는 검사하지 않는다), `tag`: 문자열 | addon, version, project_id, interface, zip, files, size_kb, changelog, game_versions(name·id) | `isError: true` + 원인 문구 |
| `upload` | 같음 | 위 + `file_id` | 같음. HTTP 실패는 상태 코드와 응답 본문 |

### CurseForge Upload API

- `GET https://wow.curseforge.com/api/game/versions` → `[{id, name, ...}]`
- `POST https://wow.curseforge.com/api/projects/{id}/upload-file` (multipart: `metadata` JSON, `file` zip) → `{id}`
- 인증: 헤더 `X-Api-Token`

## 6. 동작 로직 및 정책

### 흐름

```
prepare: 태그 확인 → TOC 읽기 → 버전 대조 → 프로젝트 ID → 파일 선별 → TOC 파일 포함 확인 → zip 쓰기 → changelog → 토큰 확인 → 게임 버전 ID 조회
upload : prepare → multipart POST → file_id
```

- 검사는 네트워크 전에 끝낸다. 토큰 확인 [FR#13] 은 게임 버전 조회 직전이다 → 토큰 없이도 파일 문제는 먼저 드러난다.

### 설계 결정

| 결정 | 선택 | 기각한 대안과 이유 |
| --- | --- | --- |
| 토큰 전달 | userConfig sensitive → MCP 서버 env | 스킬 Bash 실행: 공식 문서상 sensitive 값이 스킬 본문·Bash 환경에 전달되지 않는다. 저장소 `.env`: 저장소마다 복사해야 한다. 사용자 환경변수: 플러그인 설정과 별개로 관리된다 |
| 업로드 실행 주체 | MCP 도구 | 업로드가 별도 도구 호출이 되어 호출마다 권한 확인을 받는다 → 되돌릴 수 없는 공개 동작이 지시 없이 실행되지 않는다 |
| 파일 선별 | 태그의 git 추적 파일 − 제외 규칙 + TOC 포함 확인 | TOC 나열 파일만: Lua 가 경로로 참조하는 텍스처를 놓친다. `.pkgmeta`: 저장소마다 파일을 하나 더 유지해야 한다 |
| zip 생성 | `git archive --format=tar <tag>` 를 읽어 Python `zipfile` 로 다시 쓴다 | 작업 트리 복사: 커밋하지 않은 파일이 섞인다. PowerShell `Compress-Archive`: 내부 경로 구분자가 백슬래시가 되어 압축 해제 시 폴더 구조가 깨진다 |
| changelog 없음 | 실패 | 대체 문구 업로드: 공개 페이지에 남고 API 로 못 고친다 |
| HTTP | `urllib` | `requests`: 설치 단계가 생긴다 [NFR#1] |
| 최소 Python | 3.10, 서버 시작 시 검사 [NFR#1]. 서버 파일은 3.6 문법으로 파싱되므로 3.6~3.9 에서 안내가 나간다. 3.6 미만은 f-string 구문 오류로 먼저 종료된다. 서버 코드만 보면 3.9 에서도 돌지만 검증(TC#17 의 `sys.stdlib_module_names`)이 3.10 이상에서만 돈다 → 검증한 범위로 지원을 제한한다 | 문서에만 적기: 미만 버전에서 원인과 무관한 오류로 죽는다 |
| 공개될 내용 속 토큰 | 실패 [NFR#2] | 가리고 업로드: 확인 화면에는 `***` 만 보여 공개를 알아챌 수 없다 |
| 응답 본문 속 토큰 | `***` 로 가리고 본문은 남긴다 [NFR#2] | 본문 제외: 원인 파악이 어려워진다. 그대로 두기: 서버가 토큰을 되돌려 주는지 확인하지 못했다 |
| HTTP 5xx·파일 ID 없는 응답 뒤 재시도 | Files 탭 확인 후 [FR#11, FR#12] | 바로 재시도: 이미 올라갔다면 중복 공개 파일이 생기고 웹에서만 지울 수 있다 |

## 7. 테스트 및 검증 기준

테스트: `test/plugins/curseforge/server/curseforge.test.py` (unittest, 네트워크 없음). 실행 `python test/plugins/curseforge/server/curseforge.test.py`.

| TC | 시나리오 | 대상 | 비고 |
| --- | --- | --- | --- |
| `TC#1` | `120105` → `12.1.5`, `120105, 110207` → 두 값 | FR#8 | |
| `TC#2` | TOC 헤더와 파일 목록 파싱 (주석·빈 줄 제외, `\` → `/`) | FR#2, FR#5, FR#7 | |
| `TC#3` | 제외 규칙 표: 점 경로·최상위 docs/scripts·`*.md`·`*.test.lua`(대문자 확장자 포함) 제외, `LICENSE`·`Media/x.tga`·하위 `UI/scripts/x.lua` 포함 | FR#4 | |
| `TC#4` | 임시 git 저장소에서 태그 후 작업 트리의 애드온 파일·TOC·CHANGELOG 를 바꿔도 zip·버전·changelog 는 태그 내용, 항목은 `<이름>/` 아래, 경로 구분자는 `/`, `dist/<이름>-<버전>.zip` 에 쓰이고 그 경로에 있던 옛 zip 의 항목은 남지 않는다 | FR#1, FR#4, FR#6, FR#9 | |
| `TC#5` | 없는 태그 → 실패, 같은 이름의 브랜치만 있어도 실패 | FR#1 | |
| `TC#6` | 루트 TOC 0개·2개 → 실패, 하위 폴더의 TOC 는 세지 않는다 | FR#2 | |
| `TC#7` | TOC Version 과 태그 불일치 → 실패 | FR#3 | |
| `TC#8` | TOC 나열 파일이 제외되면 → 실패하고 zip 을 쓰지 않는다 | FR#5 | |
| `TC#9` | 프로젝트 ID 없음 → 실패 | FR#7 | |
| `TC#10` | 게임 버전 목록에 이름이 없으면 → 실패, 있으면 ID 반환 | FR#8 | |
| `TC#11` | changelog 섹션 추출 (다음 섹션 직전까지), 섹션 없으면 → 실패 | FR#9 | |
| `TC#12` | 메타데이터 키가 정확히 5개, releaseType=release, displayName, changelogType=markdown, changelog·gameVersions 는 입력값 그대로 | FR#10 | |
| `TC#13` | MCP `initialize`·`tools/list` → 도구 2개, `tools/call` 실패는 `isError` | FR#11 | |
| `TC#14` | 토큰 없음 → 네트워크 함수 호출 없이 실패, 안내에 설정 위치(`Configure options`)가 있다 | FR#13 | |
| `TC#15` | 업로드 요청: GET·POST URL 이 §4 와 정확히 같고, 토큰은 `X-Api-Token` 헤더에만, URL·본문·결과·오류 메시지에 없음. POST 본문은 `metadata`·`file` 파트이고 `metadata` JSON 은 FR#10 의 5개 키·값과 정확히 같다 | NFR#2, FR#10 | |
| `TC#16` | `SKILL.md` 가 FR#12 의 하위 항목(태그 제안, 원격 태그 확인, `prepare` 결과 표시와 TOC·CHANGELOG 수정 금지, `upload` 1회와 보고 항목, 성공 뒤 재업로드 금지, 무응답·5xx·파일 ID 없는 응답은 웹 확인 후 재시도, 4xx 는 보고 후 대기)을 모두 담는다 | FR#12 | (수동) 스킬 문서 검토 |
| `TC#17` | `curseforge.py` 가 import 하는 최상위 모듈이 모두 `sys.stdlib_module_names` 안에 있다. 밖의 모듈이 있으면 실패 | NFR#1 | |
| `TC#18` | `plugin.json` 의 `userConfig.api_token` 이 `type: string`·`sensitive`·`required` 이고, `.mcp.json` 이 `CURSEFORGE_TOKEN` 에 `${user_config.api_token}` 만 넣는다. 어긋나면 실패 | NFR#3 | |
| `TC#19` | Python 3.9 로 보이게 한 뒤 서버 시작 → 표준 입력을 읽지 않고 `3.10` 안내와 함께 종료 | NFR#1 | |
| `TC#20` | 태그에 `export-ignore` 지정 파일과 심볼릭 링크가 있으면 zip 에 없다 | FR#4 | |
| `TC#21` | HTTP 오류 응답 본문에 토큰이 있으면 도구 오류 문구에는 `***` 로 나오고 토큰은 없다. 도구 결과에 토큰 문자열이 있어도 `***` 로 나온다 | NFR#2 | |
| `TC#22` | `CURSEFORGE_TOKEN=${user_config.api_token}` 으로 서버를 시작해 `prepare` 호출 → 네트워크 요청 없이 토큰 미설정 오류 | FR#13 | |
| `TC#23` | TOC 파일명 `Other.toc`, `## Title: Demo` → 애드온 이름 `Other`, zip `Other-<버전>.zip`, 항목 `Other/` 아래 | FR#2 | |
| `TC#24` | 토큰이 있을 때 `prepare` 는 GET 1건만 보내고 POST 는 없다. 결과 키는 §4 의 9개 | FR#11 | |
| `TC#25` | `marketplace.json` 의 `name` 이 `wow-addon-plugins` 이고 `curseforge` 의 `source` 가 `./plugins/curseforge` | FR#14 | |
| `TC#26` | 토큰도 없고 TOC Version 도 태그와 다르면 Version 불일치 오류가 난다 → 파일 문제가 토큰보다 먼저 드러난다 | FR#13 | |
| `TC#27` | 업로드 응답이 `{}` 이거나 JSON 이 아니면 Files 탭 확인을 안내하는 오류로 실패 | FR#11 | |
| `TC#28` | `## Interface` 가 없거나 `abc` 면 네트워크 요청 없이 Interface 오류 | FR#8 | |
| `TC#29` | 오류 응답 본문 495자 뒤에 토큰이 있으면 오류 문구에 토큰 앞부분도 없고 `***` 가 있다 | NFR#2 | |
| `TC#30` | changelog 섹션이나 zip 에 담길 파일에 토큰이 있으면 `prepare`·`upload` 가 네트워크 요청 없이 실패하고, 오류 문구에 토큰이 없다 | NFR#2 | |
| `TC#31` | 응답 대기 시간 초과와 본문 수신 중 끊김은 Files 탭 확인을 안내하는 오류 | FR#11 | |

### 통합 확인

- `claude plugin validate` 통과.
- 설치 후 새 세션에서 LorePin `v1.0.2` 로 `prepare` 실행 → 파일 16개, 게임 버전 `12.1.5` ID 조회 성공 (토큰이 MCP 서버에 전달됐다는 증거).
- `upload` 실제 호출은 다음 릴리스에서 확인한다 → v1.0.2 는 이미 올라가 있어 다시 올리면 중복 파일이 공개된다.

## 부록. 변경 이력

- GH-1: adk 추적성 형식으로 이전 (US#1 분해, 출처 태그, §7 비고 열), 스펙 전수 대조로 TC 보강 (TC#16~TC#31, FR#14), NFR#1 최소 Python 3.10, NFR#2 응답 본문 토큰 가림·공개될 내용 속 토큰 차단, FR#8 Interface 형식 검사, FR#11·FR#12 결과 불명 응답(5xx·파일 ID 없음) 재시도 조건
