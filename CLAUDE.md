# wow-addon-plugins

WoW 애드온 개발·배포용 Claude Code 플러그인 마켓플레이스. 공개 저장소 `hwanyu365/wow-addon-plugins` 로 배포된다.

## 공개 저장소 주의

- API 토큰·개인 키·로컬 절대 경로를 커밋하지 않는다. 토큰은 플러그인 `userConfig` 의 sensitive 값으로만 받는다.
- 테스트의 토큰은 가짜 값만 쓴다.

## 스펙

- `docs/spec_{function}.md`, 작성 규칙은 adk 템플릿의 [rules_spec.md](https://github.com/hwanyu365/agentic-dev-kit/blob/main/plugins/adk/template/docs/rules_spec.md) (이 저장소에는 사본을 두지 않음)

## 검증

```sh
python plugins/curseforge/server/curseforge.test.py
claude plugin validate . --strict
claude plugin validate plugins/curseforge --strict
```

- 테스트 이름은 스펙의 `TC#n` 으로 시작한다.
- 코드 수정은 다음 세션 또는 `/reload-plugins` 에서 반영된다. 동작을 바꾸면 `plugin.json` 의 `version` 을 올린다.
