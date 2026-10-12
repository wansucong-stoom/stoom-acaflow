# 대학알리미FLOW 설치 안내

**대학알리미FLOW**는 읽기 MCP 연결 설정과 Python 대체 경로를 포함한 스킬 플러그인입니다. [GitHub 소스](https://github.com/wansucong-stoom/stoom-acaflow). 대학알리미 공식 원천을 새로 조회하는 STOOM 호스팅 읽기 MCP endpoint는 `https://h-rules.stoom.win/api/academyinfo/mcp`입니다.

0.2.5는 기존 장표별 경로 관리·공식 파일 조회 기능과 읽기 MCP를 함께 제공합니다. 새 수치·현재 비교는 공식 원천에서 새로 조회하고, 사용자가 지정한 보존본·역사·스냅샷에는 자료 시점을 표시합니다. 경로 목록은 공개 호출 경로·인자·검증 근거의 메타데이터이며 이전 통계값으로 새 조회를 대신하지 않습니다. `route_registry.py lookup`은 Python 경로의 도구로, Python 없이 가용 읽기 MCP를 사용하는 환경에 실행을 강제하지 않습니다. 경로 기록·파일 조회는 [경로 관리](../skills/academyinfo-flow/references/route-management.md)를 참고하세요.

## 가장 간단한 설치 요청

파일과 명령을 실행할 수 있는 AI에게 다음 문장을 전달합니다.

> https://github.com/wansucong-stoom/stoom-acaflow 의 대학알리미FLOW를 이 환경에 설치하고 확인해 줘.

AI는 README·AGENTS.md를 읽고 현재 클라이언트와 실제 읽기 MCP 도구·schema를 확인합니다. 개인 폴더 설치기를 실행할 때는 Python 3.11 이상과 쓰기 권한을 확인합니다. Git이 없으면 저장소 ZIP을 받아 압축을 풀어 실행할 수도 있습니다. 명령의 `python`은 실제 사용 가능한 Python 경로로 바꿀 수 있습니다. 연결된 읽기 도구를 통한 조회에는 사용자의 Python이 필요하지 않습니다.

## 개인 스킬로 설치

다음 개인 폴더 설치는 Codex·Claude Code에 적용합니다. 웹 환경은 아래의 환경별 절차를 사용합니다.

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
python -B -X utf8 scripts/runtime_preflight.py
```

사용자가 실제 조회 확인까지 요청한 경우 연결된 읽기 도구와 입력 schema를 먼저 발견합니다. 지원되는 scope 기능으로 공식 공개 연도 응답을 확인하며, MCP가 없거나 지원하지 않는 기능은 `runtime_preflight.py --check-source` 또는 `live_json.py scope` 등 Python 경로를 사용합니다. 같은 요청에서 scope를 이중 조회하지 않습니다. `runtime_ready_source_unverified`는 오프라인 조건만 확인한 상태이며 `source_verified`도 공개 연도 조회 성공만 뜻합니다. Python PDF 기능이 필요하면 `--require-pdf`를 추가합니다. 실패를 설치·조회 완료라고 말하지 않습니다.

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

화면 표시명은 **대학알리미FLOW**, 설치 ID는 `academyinfo-flow@stoom-acaflow`, 스킬 명령은 `/academyinfo-flow:academyinfo-flow`입니다. 플러그인은 Codex·Claude Code 호환 `.mcp.json` 연결 설정을 포함합니다. 로컬 검증은 `claude plugin validate .`로 수행합니다. 실제 스킬 로딩·MCP 연결·도구 가용성은 사용 중인 Claude Code에서 확인해야 합니다. 개인 스킬과 플러그인을 중복 설치하면 두 항목이 보일 수 있습니다.

## PDF 선택 의존성

Python 경로의 기본 조회에는 외부 Python 패키지가 필요 없습니다. 현재 읽기 MCP는 첨부 목록·PDF 본문·공시지침 전체 파싱을 지원하지 않습니다. 이 기능에는 번들 Python 경로나 가용 공식 웹/PDF 도구를 사용합니다. Python으로 파싱하려는 경우 해당 Python 환경에 선택 의존성을 설치합니다. 기존 공유 런타임은 소유자의 정책과 승인에 따릅니다.

```sh
python -m pip install "pdfplumber>=0.11,<1"
```

가상환경을 쓰는 경우 그 환경의 Python으로 조회 스크립트를 실행합니다. 의존성이 없으면 가용 웹/PDF 도구로 지침을 읽거나 PDF 기능의 제한을 설명합니다.

## ChatGPT·Claude 웹과 MCP

스킬은 현재 대화에서 읽기 MCP 도구를 먼저 발견하고 입력 schema를 확인합니다. 가용 도구가 있으면 scope·catalog·학교·소속·학과·metric·report 기능의 공식 새 조회를 수행할 수 있습니다. MCP 도구가 없거나 요청 기능을 지원하지 않으면 Python 3.11 이상 실행 도구와 공식 원천 네트워크를 점검합니다. Python이 없는 환경도 실제 연결된 읽기 도구 범위에서 조회할 수 있습니다.

서버의 endpoint 응답, 7개 읽기 도구 발견, 2026 공개 연도·공시 목록과 한남대학교 캡스톤 장표 9쪽의 조회는 확인했습니다. **일반 ChatGPT 웹 계정에서 플러그인·스킬·MCP를 불러와 조회하는 전체 절차는 미검증입니다.** endpoint 존재, 계정의 실제 연결, 도구 가용성, 웹 전체 실행을 구분합니다. 스킬을 불러오거나 ZIP을 검사한 결과만으로 최신 수치 조회 성공을 주장하지 않습니다.

### 연결 설정 파일의 용도

플러그인 ZIP의 루트 `mcp.json`은 공통 Agent Plugins 형식의 `streamable-http` 연결 설정입니다. 고정된 루트 경로와 전송 형식은 [OpenAI 패키지 안내](https://developers.openai.com/plugins/build/plugins)와 [Agent Plugins MCP JSON schema](https://agent-plugins.org/schemas/1.0.0/mcp.schema.json)를 따릅니다. 다음은 해당 파일의 설정 예시입니다.

```json
{
  "$schema": "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json",
  "mcpServers": {
    "academyinfo-flow": {
      "type": "streamable-http",
      "url": "https://h-rules.stoom.win/api/academyinfo/mcp"
    }
  }
}
```

루트 `.mcp.json`은 Codex·Claude Code 호환 `http` 형식으로 같은 endpoint를 선언합니다. 호환 manifest의 `mcpServers: "./.mcp.json"` 포인터도 이 파일을 가리킵니다. 형식과 경로는 [OpenAI 호환 플러그인 안내](https://developers.openai.com/api/docs/guides/agents-api/tools/plugins)와 [Claude Code의 mcpServers 명세](https://code.claude.com/docs/en/plugins-reference#mcpservers)를 참고하세요.

```json
{
  "mcpServers": {
    "academyinfo-flow": {
      "type": "http",
      "url": "https://h-rules.stoom.win/api/academyinfo/mcp"
    }
  }
}
```

위 예시는 패키지 연결 설정을 설명합니다. 수동 연결을 선택하면 현재 클라이언트가 제공하는 절차와 지원 형식을 따릅니다. 개인 스킬 설치기는 개인 MCP 설정을 수정하지 않습니다. 설정 파일이 패키지에 있어도 현재 계정·클라이언트에서 실제 도구를 제공하는지는 별도 확인합니다. 처음에는 도구 목록과 schema를 확인하고 scope 응답으로 공개 연도를 검증한 뒤 요청한 항목을 조회합니다.

| 환경 | 설치 방식 | 검증할 조건 |
| --- | --- | --- |
| 일반 ChatGPT Chat | 현재 계정·클라이언트의 Skills/플러그인·MCP 연결 절차 | 스킬 로딩·실제 읽기 도구·schema·원천 응답 확인. 웹 전체 실행은 미검증 |
| Claude 웹 | `academyinfo-flow-skill-claude-web-0.2.5.zip` 업로드. MCP 연결은 별도 절차 | 공식 안내상 Skills 사용에는 Code execution 활성화 필요. 실제 읽기 도구·원천 응답 확인. MCP 조회에는 사용자 Python 실행 불필요. 웹 전체 실행은 미검증 |
| Codex | 위 설치기 또는 `academyinfo-flow-skill-codex-0.2.5.zip` 폴더 설치, 또는 플러그인 설치 | 파일 일치·클라이언트 로딩·가용 MCP 도구 확인. 필요하면 Python·원천 네트워크 점검 |
| Claude Code | 위 개인 스킬 또는 네이티브 플러그인 | 파일·목록·클라이언트 로딩·실제 MCP 도구·원천 응답 확인. 필요하면 Python 점검 |

스킬 ZIP의 수동 폴더 설치는 압축 해제된 `academyinfo-flow/`를 스킬 상위 폴더에 두는 방식입니다. 두 단독 스킬 ZIP은 이 단일 폴더 구조를 유지하며 `mcp.json`·`.mcp.json`을 포함하지 않습니다. 스킬 업로드만으로 MCP 연결이 등록되지는 않습니다. `install.py`는 전체 저장소를 대상으로 하므로 스킬 ZIP만 받은 경우에는 그 안에서 설치기를 실행하지 않습니다.

### Claude 웹 업로드

1. 계정 또는 조직 설정에서 Skills 업로드 권한과 **Code execution and file creation** 활성화를 확인합니다. 현재 공식 안내상 Skills 기능은 Code execution 활성화를 요구하므로 계정·클라이언트의 조건을 따릅니다. 이는 실제 읽기 MCP 조회에 사용자의 Python 실행이 필요하다는 뜻은 아닙니다. [Claude 공식 Skills 활성 조건](https://support.claude.com/en/articles/12512198-how-to-create-custom-skills)
2. **Customize > Skills**의 생성·업로드 기능에서 `academyinfo-flow-skill-claude-web-0.2.5.zip`을 그대로 업로드하고 활성화합니다. 세부 메뉴 이름은 현재 클라이언트 표시를 따릅니다.
3. ZIP 최상위 `academyinfo-flow/` 바로 아래 `SKILL.md`, `scripts/`, `references/`가 있는지 확인합니다. 웹판은 Codex용 `agents/`를 제외하고 같은 조회 코드를 포함합니다. MCP 연결 설정은 포함하지 않습니다. 플러그인 전체 ZIP이나 GitHub 소스 ZIP과 구분합니다. 기존 스킬 ZIP이 이미 이 구조라면 구조 조건은 충족한 것입니다.
4. “대학알리미FLOW를 불러오고 연결된 읽기 MCP 도구와 schema를 먼저 확인한 뒤 공식 공개 연도를 조회해 줘”라고 요청합니다. MCP가 없으면 스킬 디렉터리에서 `python -B -X utf8 scripts/runtime_preflight.py --check-source` 결과를 확인하도록 합니다. 필요한 도구·허용된 원천 네트워크가 없으면 제한을 설명하도록 합니다.

공식 안내: [ZIP 구조](https://support.claude.com/en/articles/12512198-how-to-create-custom-skills), [스킬 활성화·실행 조건](https://support.claude.com/en/articles/12512180-use-skills-in-claude). 로컬 ZIP 검증과 서버 호출 검증은 실제 Claude 웹 세션의 전체 조회 검증과 구분합니다.

공식 플러그인 디렉터리 업로드·심사나 계정별 설치 기능은 서비스가 제공하는 절차와 권한을 따라야 합니다. 저장소의 공개·다운로드 가능 상태를 디렉터리 등록이나 실제 웹 조회 성공으로 해석하지 마세요.

공식 참고: [OpenAI 스킬](https://learn.chatgpt.com/docs/build-skills), [OpenAI 플러그인](https://developers.openai.com/plugins/concepts/plugins), [Claude Code 스킬](https://code.claude.com/docs/en/skills), [Claude Code 플러그인](https://code.claude.com/docs/en/plugins-reference), [Claude Code marketplace](https://code.claude.com/docs/en/plugin-marketplaces).
