# 대학알리미FLOW 설치 안내

**대학알리미FLOW**는 Python 조회 스크립트를 포함한 스킬 플러그인입니다. GitHub 소스: <https://github.com/wansucong-stoom/stoom-acaflow>. 현재 MCP 서버나 공개 원격 연결 주소는 제공하지 않습니다.

## 가장 간단한 설치 요청

파일과 명령을 실행할 수 있는 AI에게 다음 문장을 전달합니다.

> https://github.com/wansucong-stoom/stoom-acaflow 의 대학알리미FLOW를 이 환경에 설치하고 확인해 줘.

AI는 README·AGENTS.md를 읽고 클라이언트와 Python·권한을 확인한 뒤 설치기를 실행합니다. Python 3.11 이상이 필요하며, Git이 없으면 저장소 ZIP을 받아 압축을 풀어 실행할 수도 있습니다. 명령의 `python`은 실제 사용 가능한 Python 경로로 바꿀 수 있습니다.

## 개인 스킬로 설치

```sh
git clone https://github.com/wansucong-stoom/stoom-acaflow.git
cd stoom-acaflow
```

아래 중 사용할 대상 하나를 선택합니다.

```sh
python -B -X utf8 install.py --client codex
python -B -X utf8 install.py --client codex --check
```

```sh
python -B -X utf8 install.py --client claude-code
python -B -X utf8 install.py --client claude-code --check
```

두 환경 설치를 원할 때는 `--client both`를 사용합니다. `--client`를 생략하면 실행 파일·설정 존재 여부로 한 클라이언트만 확인된 경우에만 진행합니다. 둘 다 있거나 둘 다 없으면 대상 선택을 요청하며 어느 쪽에도 자동으로 설치하지 않습니다.

| 클라이언트 | 기본 경로 | 확인·호출 |
| --- | --- | --- |
| Codex | `~/.agents/skills/academyinfo-flow` | `@대학알리미FLOW`, `$academyinfo-flow` |
| Claude Code | `~/.claude/skills/academyinfo-flow` | `/academyinfo-flow`, 자연어 요청 |

`--check`의 출력이 `ok=true`이면 이 체크아웃과 설치된 스킬의 모든 포함 파일이 일치합니다. missing·changed면 종료코드 1을 반환합니다. 파일 검증은 실제 원천 조회와 별개입니다. 세션에 표시되지 않으면 해당 클라이언트를 새로고침하거나 재시작합니다.

설치된 스킬 디렉터리에서 다음 오프라인 진입점 확인을 할 수 있습니다.

```sh
python -B -X utf8 scripts/live_json.py --help
```

사용자가 실제 조회 확인까지 요청한 경우 `scope`를 실행해 공식 공개 연도 응답을 확인합니다. 네트워크 접근 제한이 있으면 호스트 승인을 따르고, 실패를 설치·조회 완료라고 말하지 않습니다.

## 다른 경로와 구버전 Codex

`--dest`는 선택한 클라이언트의 스킬 상위 폴더입니다. 마지막에 `academyinfo-flow`가 추가됩니다.

```sh
python -B -X utf8 install.py --client codex --dest /path/to/skills
python -B -X utf8 install.py --client codex --dest /path/to/skills --check
```

두 클라이언트의 사용자 지정 경로는 `--codex-dest`와 `--claude-dest`를 사용합니다. 같은 폴더나 서로 포함되는 폴더는 허용하지 않습니다.

```sh
python -B -X utf8 install.py --client both --codex-dest /path/to/codex-skills --claude-dest /path/to/claude-skills
```

예전 `~/.codex/skills/academyinfo-flow` 또는 `$CODEX_HOME/skills/academyinfo-flow`가 있으면 기본 설치가 중단되어 중복 스킬을 방지합니다. 기존 경로를 확인하고, 해당 클라이언트에서 그 경로를 계속 사용하는 경우에만 `--dest`로 명시하거나 직접 새 경로로 이동합니다. 설치기는 구형 스킬·설정 파일·플러그인 캐시를 임의로 삭제하지 않습니다. 현재 공식 개인 경로는 `~/.agents/skills`입니다.

## 업데이트와 백업

같은 내용은 변경하지 않습니다. 내용이 다르면 기본 설치는 중단합니다. 저장소 변경과 기존 로컬 수정 내용을 검토한 뒤 업데이트합니다.

```sh
git pull --ff-only
python -B -X utf8 install.py --client codex --update
python -B -X utf8 install.py --client codex --check
```

업데이트는 기존 스킬 디렉터리 전체를 백업하고 새 파일을 설치합니다. 기본 백업은 `~/.agents/skill-backups/` 또는 `~/.claude/skill-backups/`에 고유 이름으로 보관합니다. 사용자 지정 스킬 루트의 백업은 그 루트의 형제 폴더에 둡니다. 정확한 위치는 JSON 결과의 `backup`에 표시됩니다. 이전 SKILL.md가 다시 스킬로 발견되지 않도록 백업을 스킬 탐색 폴더 밖에 보관합니다. 백업을 삭제하거나 다른 클라이언트 파일을 덮어쓰지 않습니다.

`--check`는 읽기만 수행합니다. 설치기는 네트워크 다운로드, pip 설치, 실행 hooks, MCP 서버 등록, 클라이언트 설정 변경을 하지 않습니다. 소스의 ID·필수 스크립트·포함 파일 해시와 경로를 확인하며 symlink·Windows junction은 거부합니다. 검사 자체가 다운로드한 코드의 안전성을 보증하지는 않으므로 실행 전에 소스를 검토하세요.

## Claude Code 네이티브 플러그인

개인 스킬 설치 대신 Claude Code가 관리하는 플러그인 설치를 선택할 수 있습니다.

```sh
claude plugin marketplace add wansucong-stoom/stoom-acaflow
claude plugin install academyinfo-flow@stoom-acaflow
claude plugin list
```

화면 표시명은 **대학알리미FLOW**, 설치 ID는 `academyinfo-flow@stoom-acaflow`, 스킬 명령은 `/academyinfo-flow:academyinfo-flow`입니다. 로컬 검증은 `claude plugin validate .`로 수행합니다. 실제 로딩 여부는 사용 중인 Claude Code에서 확인해야 합니다. 개인 스킬과 플러그인을 중복 설치하면 두 항목이 보일 수 있습니다.

## PDF 선택 의존성

기본 조회에는 외부 Python 패키지가 필요 없습니다. PDF 본문·공시지침을 Python으로 파싱하려는 경우 해당 Python 환경에 선택 의존성을 설치합니다. 기존 공유 런타임은 소유자의 정책과 승인에 따릅니다.

```sh
python -m pip install "pdfplumber>=0.11,<1"
```

가상환경을 쓰는 경우 그 환경의 Python으로 조회 스크립트를 실행합니다. 의존성이 없으면 가용 웹/PDF 도구로 지침을 읽거나 PDF 기능의 제한을 설명합니다.

## ChatGPT·Claude 웹과 MCP

일반 웹 대화는 GitHub 파일을 읽더라도 사용자 컴퓨터의 Python 스크립트를 자동으로 실행할 수 없습니다. 파일·Python·네트워크 실행 도구가 지원되는 환경에서 스킬을 실행하거나, 향후 별도로 구축·호스팅한 원격 MCP 서버를 연결해야 합니다. **이 저장소에는 MCP 서버 구현이나 호스팅된 endpoint가 없습니다.** 웹 연결 확장은 향후 선택 작업이며 기본 설치 완료에 포함되지 않습니다.

공식 플러그인 디렉터리 업로드·심사나 계정별 설치 기능은 서비스가 제공하는 절차와 권한을 따라야 합니다. 저장소의 공개·다운로드 가능 상태를 디렉터리 등록이나 실제 웹 조회 성공으로 해석하지 마세요.

공식 참고: [OpenAI 스킬](https://learn.chatgpt.com/docs/build-skills), [OpenAI 플러그인](https://developers.openai.com/plugins/concepts/plugins), [Claude Code 스킬](https://code.claude.com/docs/en/skills), [Claude Code 플러그인](https://code.claude.com/docs/en/plugins-reference), [Claude Code marketplace](https://code.claude.com/docs/en/plugin-marketplaces).
