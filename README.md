# wow-addon-plugins

A Claude Code plugin marketplace for World of Warcraft addon development and release.

## Installation

```sh
claude plugin marketplace add hwanyu365/wow-addon-plugins
claude plugin install curseforge@wow-addon-plugins
```

## Plugins

| Plugin | Command | What it does |
| --- | --- | --- |
| `curseforge` | `/curseforge:deploy <tag>` | Packages the addon at the tag into a zip and uploads it to CurseForge as a release |

## curseforge

### Prerequisites

- Python 3.10 or later (standard library only)
- The project must already exist on CurseForge → this plugin does not create projects, it only uploads files.
- Addon repository requirements
  - Exactly one `*.toc` at the repository root
  - `## Version` (the tag without `v`), `## Interface` and `## X-Curse-Project-ID` in the TOC
  - A `## [<version>]` section in `CHANGELOG.md`
  - The tag is pushed to the remote (origin)

### API token

- Each developer uses their own token. This repository contains no token.
- Get one at: https://legacy.curseforge.com/account/api-tokens
- Enter it as the plugin's sensitive `userConfig` value (`api_token`). Sensitive values are stored in the OS secure credential store, not in `settings.json`.
- When it is asked: on install/enable via `/plugin` in a session. `claude plugin install` in the shell does not ask, so enter it with the command below after installing.
- Enter or change: `/plugin configure curseforge@wow-addon-plugins` in a session, or `/plugin` → Installed → Configure options
- Without a token, `/curseforge:deploy` fails without making any network request.

Details: [Claude Code plugin user configuration](https://code.claude.com/docs/en/plugins/manifest-reference.md#user-configuration)

### Packaging rules

- Git-tracked files at the tag are placed under `<addon name>/`.
- Excluded: paths starting with `.`, top-level `docs/` and `scripts/`, `*.md`, `*.test.lua`
- Output: `<repository>/dist/<addon name>-<version>.zip`

Full spec: [docs/spec_curseforge.md](docs/spec_curseforge.md)

## License

[MIT](LICENSE)
