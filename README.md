# wow-addon-plugins

World of Warcraft 애드온 개발·배포용 Claude Code 플러그인 마켓플레이스.

## 설치

```sh
claude plugin marketplace add hwanyu365/wow-addon-plugins
claude plugin install curseforge@wow-addon-plugins
```

## 플러그인

| 플러그인 | 명령 | 하는 일 |
| --- | --- | --- |
| `curseforge` | `/curseforge:deploy <태그>` | 태그 시점의 애드온을 zip 으로 패키징해 CurseForge 에 release 로 업로드 |

## curseforge

### 준비

- Python 3.10 이상 (표준 라이브러리만 사용)
- CurseForge 에 프로젝트가 이미 생성되어 있어야 한다 → 이 플러그인은 프로젝트를 만들지 않고 파일만 올린다.
- 애드온 저장소 조건
  - 저장소 루트에 `*.toc` 가 정확히 하나
  - TOC 에 `## Version`(태그에서 `v` 를 뗀 값), `## Interface`, `## X-Curse-Project-ID`
  - `CHANGELOG.md` 에 `## [<버전>]` 섹션
  - 태그가 원격(origin)에 push 되어 있음

### API 토큰

- 토큰은 개발자마다 자기 것을 쓴다. 이 저장소에는 토큰이 없다.
- 발급: https://legacy.curseforge.com/account/api-tokens
- 플러그인의 `userConfig` 민감 값(`api_token`)으로 입력한다. 민감 값은 `settings.json` 이 아니라 OS 보안 자격 증명 저장소에 저장된다.
- 입력 시점: 세션의 `/plugin` 에서 설치·활성화할 때 묻는다. 셸의 `claude plugin install` 은 묻지 않으므로 설치 뒤 아래 명령으로 입력한다.
- 입력·변경: 세션에서 `/plugin configure curseforge@wow-addon-plugins`, 또는 `/plugin` → Installed → Configure options
- 토큰이 없으면 `/curseforge:deploy` 는 네트워크 요청 없이 실패한다.

상세: [Claude Code 플러그인 user configuration](https://code.claude.com/docs/en/plugins/manifest-reference.md#user-configuration)

### 패키징 규칙

- 태그 시점의 git 추적 파일을 `<애드온 이름>/` 아래에 담는다.
- 제외: `.` 으로 시작하는 경로, 최상위 `docs/`·`scripts/`, `*.md`, `*.test.lua`
- 출력: `<저장소>/dist/<애드온 이름>-<버전>.zip`

상세 스펙: [docs/spec_curseforge.md](docs/spec_curseforge.md)

## 라이선스

[MIT](LICENSE)
