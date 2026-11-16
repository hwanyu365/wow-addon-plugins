---
name: deploy
description: WoW 애드온 릴리스 태그를 CurseForge 에 release 로 업로드한다. 애드온 저장소에서 "배포", "CurseForge 에 올려", "릴리스 배포" 지시를 받았을 때, 태그·GitHub 릴리스를 만든 뒤 이어서 쓴다.
argument-hint: "<태그, 예: v1.0.2>"
---

# /curseforge:deploy

업로드는 되돌릴 수 없는 공개 동작이다. 저장소 소유자의 배포 지시가 있을 때만 쓴다.

## 1. 대상 확정

- 저장소: `git rev-parse --show-toplevel` 의 절대 경로.
- 태그: 인자로 받은 값. 없으면 `git describe --tags --abbrev=0 origin/main` 으로 제안하고 확인받는다.
- `git ls-remote --tags origin <태그>` 로 태그가 원격에 있는지 확인한다. 없으면 중단한다 → 공개된 파일이 저장소 이력에 없는 내용이 된다.

## 2. prepare

- curseforge MCP 의 `prepare` 도구를 `repo`, `tag` 로 호출한다.
- 실패하면 오류를 그대로 보고하고 중단한다. 검사를 우회하려고 TOC·CHANGELOG 를 고치지 않는다 → 고치려면 저장소 절차대로 새 태그를 만든다.
- 성공하면 애드온·버전·게임 버전·파일 수·크기·changelog 를 사용자에게 보여 준다.

## 3. upload

- `upload` 도구를 한 번 호출한다.
- 성공 응답(`file_id`)을 받았으면 같은 태그로 다시 올리지 않는다 → Upload API 는 중복을 막지 않고, 올라간 파일은 웹 UI 에서만 지울 수 있다.
- 응답 없이 실패(연결 끊김·타임아웃)했거나, HTTP 5xx 이거나, 응답에 파일 ID 가 없으면(본문을 읽지 못한 경우 포함) 올라갔는지 알 수 없다 → 사용자가 CurseForge Files 탭에서 올라가지 않았음을 확인한 뒤에만 재시도한다.
- HTTP 4xx 는 원인을 보고하고 지시를 기다린다.

## 4. 보고

- `file_id`, 게임 버전, 업로드한 zip 경로를 보고한다.
- CurseForge 의 처리·공개 상태는 이 도구로 조회할 수 없다 → 확인하지 않았다고 적는다.
