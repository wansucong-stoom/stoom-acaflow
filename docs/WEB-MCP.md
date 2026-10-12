# 대학알리미FLOW 웹 MCP 연결 안내

**웹에서 공식 공시를 조회하려면 전용 MCP를 먼저 등록하고 사용할 대화에서 켜세요.** 스킬은 분석 방법을 알려 주는 추가 지침입니다. 스킬 ZIP을 올리거나 GitHub 주소를 채팅에 붙이는 것만으로 커넥터가 등록되지는 않습니다.

[Claude 웹 등록](#claude-웹) · [ChatGPT 웹 등록](#chatgpt-웹) · [실제 조회 확인](#연결과-실제-조회를-확인하기) · [스킬 ZIP 추가](#claude-웹에-스킬을-추가하기) · [문제 해결](#잘-안될-때)

확인 기준일: 2026년 10월 12일. 메뉴와 계정 권한은 현재 서비스 화면을 확인하세요.

## 공통 연결 정보

| 설정 | 값 |
| --- | --- |
| 이름 | 대학알리미FLOW |
| 원격 서버 URL | `https://h-rules.stoom.win/api/academyinfo/mcp` |
| 연결 방식 | 원격 HTTPS · Streamable HTTP |
| 인증 | Claude: **No sign in** / ChatGPT: **No authentication** |
| API 키·OAuth 값·추가 헤더 | 입력할 값 없음 |
| 기능 | 공식 대학알리미 공개 원천을 새로 읽는 조회 도구 |

주소를 그대로 복사하세요.

```text
https://h-rules.stoom.win/api/academyinfo/mcp
```

한남대FLOW 규정용 `https://h-rules.stoom.win/api/mcp`는 다른 연결입니다. 규정 커넥터만 보이면 대학알리미 새 조회 연결은 아직 확인되지 않은 상태입니다.

웹 MCP 조회에는 사용자의 Python 설치나 코드 실행이 필요하지 않습니다. Claude에서 스킬을 추가할 때 필요한 Skills 활성 조건은 별도입니다.

## Claude 웹

1. **Customize → Connectors**에서 **+ Add → Add custom connector**를 엽니다. 화면이 **Add → Custom → Web**으로 표시되면 그 경로를 사용합니다.
2. 이름과 서버 URL에 위 공통 연결 정보를 입력하고 다음 단계로 진행합니다.
3. 인증 선택이 있으면 **No sign in**을 선택합니다. Request headers는 비워 두고 등록을 마칩니다.
4. 사용할 대화에서 입력창의 **+ → Connectors**를 열어 **대학알리미FLOW**를 켭니다.
5. 아래 첫 확인 질문을 보내 실제 조회 도구의 응답을 확인합니다.

현재 공식 안내상 Free 계정은 사용자 지정 커넥터 1개 제한이 있으므로 이미 등록한 사용자 지정 연결 수를 확인합니다. Team·Enterprise에서는 조직 소유자가 **Organization settings → Connectors → Add → Custom → Web**으로 먼저 등록한 뒤 구성원이 자신의 **Customize → Connectors**에서 **Connect**를 누르고 사용할 대화에서 활성화합니다. 개인 등록 메뉴가 없으면 계정·조직 권한을 확인하세요. [Claude 공식 등록 안내](https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp)

도구가 처음부터 목록에 나타나지 않더라도 바로 미등록으로 판단하지 마세요. **+ → Connectors → Tool access**의 **Auto** 또는 **On demand**에서는 요청에 맞는 커넥터를 찾아 로딩할 수 있습니다. “대학알리미FLOW 커넥터를 찾아서 사용해 줘”라고 요청하고, 필요한 경우 이 대화의 접근 설정을 확인한 뒤 실제 호출 결과로 판단합니다. [Claude 도구 로딩 설정](https://support.claude.com/en/articles/13730515-manage-claude-s-tool-access)

## ChatGPT 웹

1. ChatGPT의 **Plugins → + → Add custom MCP server**를 엽니다.
2. 이름은 **대학알리미FLOW**, Server URL은 위 주소로 입력합니다. Authentication은 **No authentication**입니다.
3. 화면의 연결 확인 안내를 읽고 **Create as a plugin**으로 등록합니다.
4. 개인 플러그인 목록에서 생성된 항목을 열어 **설치**합니다. 생성과 설치는 별도입니다.
5. 공식 Quickstart의 시작 경로는 홈의 **Work** 탭입니다. 새 Work 대화에서 **@**를 입력하고 설치한 대학알리미FLOW를 선택합니다.
6. 아래 첫 확인 질문을 보내 실제 도구 응답을 확인합니다.

[OpenAI 공식 MCP 등록 안내](https://developers.openai.com/api/docs/guides/custom-mcp-server), [웹 Work에서 설치·호출하는 공식 Quickstart](https://developers.openai.com/plugins/quickstart)

Chat 화면에서 사용하려면 해당 계정의 대화에 플러그인이 실제 표시되고 도구가 제공되는지 확인하세요. Work 경로의 안내나 한 대화의 성공을 모든 Chat 화면의 지원으로 확대하지 않습니다. 메뉴가 없으면 현재 계정·워크스페이스의 권한과 정책을 확인하며, GitHub 파일을 채팅에 첨부해 등록을 대신하지 않습니다.

MCP만 직접 연결해 만든 항목에는 이 저장소의 스킬까지 자동으로 들어가는 것으로 가정하지 마세요. 스킬과 MCP를 함께 포함한 플러그인을 설치했다면 두 기능이 실제로 로딩됐는지 각각 확인합니다.

## 연결과 실제 조회를 확인하기

연결 후 실제 조회 확인도 요청하려면 이 질문을 보내세요. 큰 전국 장표를 받기 전에 공개 연도 조회로 연결을 확인합니다. 설치만 요청한 상황에서는 새 수치를 자동 조회하지 않습니다.

> 대학알리미FLOW 커넥터를 찾아 실제 연결된 원격 조회 도구를 확인하고, 공개 연도 조회 도구로 현재 공개 연도를 조회해 줘. 실제 사용한 도구 이름, 조회 시각, 응답에서 확인된 연도를 알려 줘. 도구가 없거나 호출이 실패하면 그 상태를 설명해 줘.

성공 기준은 연결 이름이 목록에 보이는 것에 더해 **공개 연도 조회 도구가 호출되고 응답이 돌아오는 것**입니다. 실제 도구 이름은 `academyinfo_scope`이며, 호스트가 접두사를 붙일 수 있습니다.

공개 연도 조회에 성공한 뒤 필요하면 한 대학의 수치 조회를 확인하세요. 학교명으로 결과를 좁혀도 장표는 전국 원천을 먼저 읽고 필터링하므로 시간이 걸리거나 페이지 제한에 도달할 수 있습니다.

> 대학알리미FLOW로 한남대학교의 최신 공개 취업률을 조회해 줘. 공개 연도와 관련 장표를 먼저 확인하고, 공시연도·실적 기준기간·단위·공식 출처·조회 시각·조회 완료 여부를 함께 알려 줘.

| 확인 단계 | 확인하는 내용 | 이 단계만으로 알 수 없는 것 |
| --- | --- | --- |
| 커넥터 등록·플러그인 설치 | 계정에 연결 항목이 있음 | 현재 대화의 도구 활성화와 원천 응답 |
| 공개 연도 조회 | 도구가 실제 호출되고 공식 목록 응답이 돌아옴 | 수치 장표의 전체 페이지와 해석 정확성 |
| 수치 장표 조회 | 요청 조건, 원천 값, 전체 열 정의와 페이지 범위 | 다른 장표·연도·계정의 성공 |

AI의 “실시간으로 조회했다”라는 문구만으로 확인하지 마세요. 서비스가 제공하는 도구 실행 표시와 위 조회 확인 내용을 함께 봅니다. 독자가 읽는 결과에는 사람이 이해할 수 있는 장표명·범위·기간·단위를 쓰며, 내부 ID·조문키·SHA-256을 본문에 나열할 필요는 없습니다.

순위·전국 합계를 만들 때는 응답의 완료 여부·누락·반복 페이지·표 구조 검증·반환 범위를 확인해야 합니다. 일부 자료가 돌아온 것을 전국 비교 완료로 취급하지 않습니다.

## Claude 웹에 스킬을 추가하기

원격 연결을 먼저 확인한 뒤, 이 저장소의 분석 지침도 사용하려면 다음 스킬 ZIP을 추가하세요.

**[Claude 웹용 스킬 ZIP 다운로드 — 0.2.7](https://github.com/wansucong-stoom/stoom-acaflow/raw/refs/heads/main/downloads/academyinfo-flow-skill-claude-web-0.2.7.zip)**

계정 설정에 접근하는 도구가 없는 일반 Claude 웹 대화의 AI는 Capabilities를 켜거나 계정 Skills를 등록·활성화할 수 없습니다. 아래 단계는 사용자가 직접 수행합니다. AI는 가용 파일 도구로 ZIP 구조를 확인하거나 절차를 안내할 수 있지만, 그 결과를 계정 설치 완료로 보고하지 않습니다. 다른 클라이언트나 실제 계정 설정 도구가 제공되는 환경은 해당 도구·권한을 따로 확인합니다.

1. 개인 Free·Pro·Max 계정은 **Settings → Capabilities**에서 **Code execution and file creation**을 켭니다. Team·Enterprise는 **Organization settings → Plugins & skills → Policy**에서 코드 실행과 Skills가 허용되는지 확인합니다. 조직 정책 변경에는 해당 권한이 필요합니다.
2. **Customize → Skills → + → + Create skill → Upload a skill**에서 위 ZIP을 선택합니다. 일반 채팅에 첨부하는 방식과 구분하세요. 저장소 전체 ZIP이나 플러그인 ZIP 대신 위 스킬 ZIP을 그대로 사용합니다.
3. 목록에 추가된 **대학알리미FLOW**의 토글을 켭니다. 메뉴 명칭은 현재 화면을 따르며 등록과 활성화를 각각 확인합니다. [Claude 공식 Skills 활성·업로드 절차](https://support.claude.com/en/articles/12512180-use-skills-in-claude)

Code execution 활성화는 Skills 기능의 조건이며 원격 MCP 조회를 Python으로 실행해야 한다는 뜻은 아닙니다. 분석 지침을 적용해 조회하려면 스킬과 커넥터가 활성화된 대화에서 그 조회를 요청합니다.

| 상태 | 확인할 내용 | 아직 보장되지 않는 것 |
| --- | --- | --- |
| 일반 채팅 첨부 | 대화에 ZIP 파일을 전달함 | 계정 Skills 등록·활성화 |
| ZIP 구조 검수 | 가용 파일 도구로 최상위 폴더와 포함 파일을 확인함 | 계정 설정 변경·설치 |
| 계정 Skills 등록 | Customize의 Skills 목록에 항목이 생김 | 항목 활성화·MCP 연결 |
| Skills 활성화 | 해당 스킬의 토글을 켬 | MCP 등록·대화 활성화·원천 응답 |
| MCP 연결 | 전용 커넥터 등록·대화 활성화와 실제 조회 도구를 확인함 | 스킬 설치 여부·모든 장표의 완전성 |

이미 사용할 수 있는 MCP 도구가 있고 사용자가 공식 조회를 요청했다면 스킬 수동 설치를 기다리지 않고 그 도구로 조회할 수 있습니다. 스킬 설치만 요청한 경우에는 설치·활성화 상태와 남은 수동 단계를 안내하며 새 수치를 자동 조회하지 않습니다.

ZIP의 최상위 구조는 다음과 같습니다.

```text
academyinfo-flow/
  SKILL.md
  scripts/
  references/
```

이 ZIP에는 MCP 등록 설정과 Codex용 `agents/`가 없습니다. **파일 업로드를 마쳐도 전용 커넥터는 위 절차로 따로 등록해야 합니다.** [Claude 공식 Skills ZIP 구조·활성 조건](https://support.claude.com/en/articles/12512198-how-to-create-custom-skills)

[배포 파일 설명](../downloads/README.md) · [로컬 설치·패키지 형식](INSTALL.md)

## 잘 안될 때

| 보이는 상황 | 먼저 확인할 것 |
| --- | --- |
| 스킬 파일만 올렸고 조회 도구가 없음 | Skills 설치 여부와 전용 커넥터 등록·대화 활성화를 각각 확인 |
| 규정 검색 도구만 보임 | 한남대FLOW 규정 주소와 대학알리미FLOW 전용 주소를 구분 |
| 연결을 추가하는 메뉴가 없음 | 현재 계정의 기능·권한, 조직의 등록 권한, 서비스 공식 안내 |
| 등록했지만 대화에서 도구가 없음 | 현재 대화의 선택·활성화와 설치 상태 확인. Claude Auto·On demand의 도구 검색·로딩을 확인한 뒤 첫 확인 질문 실행 |
| 로그인이나 키 입력을 계속 요구함 | 전용 주소와 인증 선택을 확인. 현재 이 서버의 설정은 무인증 |
| `source_connection_error`가 나옴 | 실패한 도구가 원격 MCP인지 Python 스크립트인지, 실제 오류와 실패 단계를 확인 |
| `source_timeout` / `report_initialize`에서 실패함 | 표 초기화의 개별 원천 요청 시간 제한은 현재 12초, 전체 요청은 45초 한도. 해당 시도의 실패로 기록하며 재시도 성공은 별도 시도로 구분. 지속 원인을 단정하거나 실패를 숫자 0으로 처리하지 않음 |
| 공개 연도는 나오지만 수치 조회는 실패 | 관련 장표·조회 단위·페이지 제한과 실제 오류를 확인. 미확인 수치나 이전 아카이브 값으로 메우지 않음 |
| 표가 부분 응답·제한·누락 상태임 | 확보된 범위만 표시. 전국 순위·합계는 완료로 보고하지 않음 |
| PDF·공시지침 본문이 필요함 | 현재 MCP 지원 범위 밖. 가용 공식 웹/PDF 도구 또는 실행 조건이 확인된 Python 경로 사용 |

Claude 원격 MCP는 Anthropic 클라우드에서 우리 서버에 연결합니다. Python 스크립트의 직접 조회는 코드 실행 환경에서 대학알리미 서버에 접속하므로 두 경로의 네트워크 조건이 다릅니다. 연결 실패 코드만으로 특정 도메인의 허용 목록 누락을 단정하거나 네트워크 설정 변경을 먼저 요구하지 않습니다. [Claude 원격 연결 방식](https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp), [코드 실행 네트워크와 MCP의 구분](https://support.claude.com/en/articles/12111783-create-and-edit-files-with-claude)

## 현재 지원 범위와 검증 상태

| 도구 | 기능 |
| --- | --- |
| `academyinfo_scope` | 공개 연도·기관 구분 |
| `academyinfo_catalog` | 해당 연도 공시 항목 |
| `academyinfo_schools` | 공식 학교 목록 |
| `academyinfo_affiliations` | 소속·계열 목록 |
| `academyinfo_departments` | 학과 목록 |
| `academyinfo_metric` | 지원되는 학과 주요지표 |
| `academyinfo_report` | 학교별·학과별 수치 장표 |

서버의 도구 응답과 공식 원천 조회, ChatGPT 웹 한 대화의 실제 MCP 조회 기록과 사용자 제공 Claude 웹 응답의 실제 원격 장표 조회 성공은 확인했습니다. 모든 계정의 설치·연결 성공이나 모든 장표의 파싱·지침 정의 검증 완료를 보장하는 결과는 아닙니다. 계정 설정·Skills 설치 UI 전체는 별도 미검증입니다. 응답의 `guideline_verified=false`는 해당 지침 정의를 검증 완료로 표시하지 않았다는 뜻이며 장표 조회 성공과 구분합니다.

현재 장표 조회는 최대 16페이지·40개 원천 요청·45초 한도로 동작합니다. 첨부 목록·PDF 본문·공시지침 전체 파싱은 현재 MCP가 제공하지 않습니다. Python 대체 경로는 사용자가 선택하고 실제 실행 도구·공식 원천 네트워크를 확인한 경우 사용합니다.
