# CurseForge 배포 플러그인 스펙

## 1. 개요

- **문서 정보:** spec_curseforge / hwanyu365 / 작성 2026-10-18 / 기준 커밋: 없음 (신규 저장소)
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

- `US#1` 저장소 소유자로서, 태그를 올린 뒤 "배포"라고만 지시해도 CurseForge 에 올라가길 원한다. 저장소마다 스크립트·토큰을 복사하지 않기 위해서다.

### 기능 요구사항

- `FR#1` 입력은 저장소 경로와 태그다. 태그가 없으면 실패한다. 모든 입력 파일(TOC·CHANGELOG·애드온 파일)은 작업 트리가 아니라 **태그 시점**에서 읽는다 → 커밋하지 않은 변경이 섞이지 않는다.
- `FR#2` 태그 시점 저장소 루트의 `*.toc` 가 정확히 하나여야 한다. 애드온 이름은 TOC 파일명(확장자 제외)이다.
- `FR#3` TOC `## Version` 이 태그에서 앞의 `v` 를 뗀 값과 같아야 한다. 다르면 실패한다 → 옛 버전 파일이 새 버전 이름으로 올라가는 것을 막는다.
- `FR#4` zip 내용은 태그 시점 git 추적 파일에서 아래를 뺀 것이다. 모든 항목은 `<애드온 이름>/` 아래에 둔다.
  - 경로 구성 요소 중 하나라도 `.` 으로 시작하는 파일 (`.github/`, `.claude/`, `.gitignore`, `.luacheckrc` 등)
  - 최상위 `docs/`, `scripts/`
  - `*.md`, `*.test.lua`
- `FR#5` TOC 본문에 나열된 파일이 zip 에 하나라도 없으면 실패한다 → 제외 규칙이 게임에 필요한 파일을 빼는 경우를 잡는다.
- `FR#6` zip 은 `<저장소>/dist/<애드온 이름>-<버전>.zip` 에 매번 새로 쓴다 → 남아 있던 옛 zip 이 올라가지 않는다.
- `FR#7` TOC `## X-Curse-Project-ID` 가 없으면 실패한다.
- `FR#8` TOC `## Interface` (쉼표 구분 다중 값 허용)를 `M.m.p` 이름으로 바꿔 CurseForge 게임 버전 ID 로 조회한다. 하나라도 없으면 실패한다. 변환은 `120105 → 12.1.5`.
- `FR#9` changelog 는 태그 시점 `CHANGELOG.md` 의 `## [<버전>]` 섹션 본문이다. 섹션이 없으면 실패한다 → 공개 페이지의 changelog 는 API 로 고칠 수 없으므로 대체 문구로 올리지 않는다.
- `FR#10` 업로드 메타데이터는 `releaseType=release`, `displayName="<애드온 이름> <버전>"`, `changelogType=markdown`, `changelog`, `gameVersions` 만 담는다 → 배포자 실명·커밋 같은 정보가 공개 페이지에 나가지 않는다.
- `FR#11` 플러그인은 MCP 도구 두 개를 제공한다.
  - `prepare(repo, tag)`: FR#1~FR#9 를 수행하고 업로드할 내용을 돌려준다. 업로드하지 않는다.
  - `upload(repo, tag)`: `prepare` 를 다시 수행한 뒤 업로드하고 CurseForge 파일 ID 를 돌려준다.
- `FR#12` 스킬 `/curseforge:deploy <태그>` 절차
  - 태그가 원격에 있는지 확인한다.
  - `prepare` 결과(애드온·버전·게임 버전·파일 수·크기·changelog)를 보여 준다.
  - `upload` 를 한 번 호출하고 파일 ID 와 프로젝트 Files 페이지를 보고한다.
  - 업로드가 성공 응답을 받은 뒤에는 같은 태그로 다시 올리지 않는다. 응답을 받지 못한 실패는 웹 Files 탭을 사용자가 확인한 뒤에만 재시도한다.
- `FR#13` 토큰이 설정되지 않았으면 네트워크 요청 없이 실패하고, 설정 방법을 안내한다.

### 비기능 요구사항

- `NFR#1` Python 3 표준 라이브러리만 쓴다 → 설치 단계가 없다.
- `NFR#2` 토큰은 요청 헤더에만 쓴다. 도구 결과·오류 메시지·로그에 넣지 않는다.
- `NFR#3` 토큰은 플러그인 `userConfig` 의 sensitive 값으로만 받는다. 저장소 파일에 두지 않는다.

## 4. 데이터 및 API 스펙

### 플러그인 구성

| 경로 | 역할 |
| --- | --- |
| `.claude-plugin/marketplace.json` | 마켓플레이스 `wow-addon-plugins` |
| `plugins/curseforge/.claude-plugin/plugin.json` | `userConfig.api_token` (string, sensitive, required) |
| `plugins/curseforge/.mcp.json` | MCP 서버 `curseforge`, env `CURSEFORGE_TOKEN=${user_config.api_token}` |
| `plugins/curseforge/server/curseforge.py` | MCP 서버 (stdio JSON-RPC) + 패키징·업로드 로직 |
| `plugins/curseforge/skills/deploy/SKILL.md` | 배포 절차 [FR#12] |

### MCP 도구

| 도구 | 입력 | 성공 결과 | 실패 |
| --- | --- | --- | --- |
| `prepare` | `repo`: 절대 경로, `tag`: 문자열 | addon, version, project_id, interface, zip, files, size_kb, changelog, game_versions(name·id) | `isError: true` + 원인 한 줄 |
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

## 7. 테스트 및 검증 기준

테스트: `plugins/curseforge/server/curseforge.test.py` (unittest, 네트워크 없음). 실행 `python plugins/curseforge/server/curseforge.test.py`.

| TC | 시나리오 | 대상 |
| --- | --- | --- |
| `TC#1` | `120105` → `12.1.5`, `120105, 110207` → 두 값 | FR#8 |
| `TC#2` | TOC 헤더와 파일 목록 파싱 (주석·빈 줄 제외, `\` → `/`) | FR#2, FR#5, FR#7 |
| `TC#3` | 제외 규칙 표: 점 경로·최상위 docs/scripts·`*.md`·`*.test.lua` 제외, `LICENSE`·`Media/x.tga`·하위 `UI/scripts/x.lua` 포함 | FR#4 |
| `TC#4` | 임시 git 저장소에서 태그 후 작업 트리를 바꿔도 zip 은 태그 내용, 항목은 `<이름>/` 아래, 경로 구분자는 `/`, `dist/<이름>-<버전>.zip` 에 쓰인다 | FR#1, FR#4, FR#6 |
| `TC#5` | 없는 태그 → 실패 | FR#1 |
| `TC#6` | 루트 TOC 0개·2개 → 실패 | FR#2 |
| `TC#7` | TOC Version 과 태그 불일치 → 실패 | FR#3 |
| `TC#8` | TOC 나열 파일이 제외되면 → 실패 | FR#5 |
| `TC#9` | 프로젝트 ID 없음 → 실패 | FR#7 |
| `TC#10` | 게임 버전 목록에 이름이 없으면 → 실패, 있으면 ID 반환 | FR#8 |
| `TC#11` | changelog 섹션 추출 (다음 섹션 직전까지), 섹션 없으면 → 실패 | FR#9 |
| `TC#12` | 메타데이터 키가 정확히 5개, releaseType=release | FR#10 |
| `TC#13` | MCP `initialize`·`tools/list` → 도구 2개, `tools/call` 실패는 `isError` | FR#11 |
| `TC#14` | 토큰 없음 → 네트워크 함수 호출 없이 실패 | FR#13 |
| `TC#15` | 업로드 요청: 토큰은 `X-Api-Token` 헤더에만, 본문·결과·오류 메시지에 없음 | NFR#2 |

### 통합 확인

- `claude plugin validate` 통과.
- 설치 후 새 세션에서 LorePin `v1.0.2` 로 `prepare` 실행 → 파일 16개, 게임 버전 `12.1.5` ID 조회 성공 (토큰이 MCP 서버에 전달됐다는 증거).
- `upload` 실제 호출은 다음 릴리스에서 확인한다 → v1.0.2 는 이미 올라가 있어 다시 올리면 중복 파일이 공개된다.
- FR#12·NFR#3 은 스킬 문서·매니페스트 검토로 확인한다 (코드 TC 없음).
