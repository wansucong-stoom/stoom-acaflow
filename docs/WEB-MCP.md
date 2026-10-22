# 웹 MCP 연결 안내

대학알리미FLOW 원격 MCP는 공식 원천을 새로 읽는 조회 도구입니다. 웹의 MCP 조회에는 사용자 Python 설치가 필요하지 않습니다. 스킬 ZIP은 분석 지침을 추가하며 원격 연결 등록은 별도입니다.

공식 제품 문서 확인일은 **2026년 10월 20일**입니다. 아래 메뉴가 보이는지는 현재 계정·조직 권한에서 확인하세요. 문서 확인을 계정 설치·UI 조작 성공으로 표시하지 않습니다.

## 공통 연결 정보

| 설정 | 값 |
| --- | --- |
| 이름 | 대학알리미FLOW |
| URL | `https://h-rules.stoom.win/api/academyinfo/mcp` |
| 전송 | HTTPS · Streamable HTTP |
| 인증 | Claude **No sign in**, ChatGPT **No authentication** |
| API 키·고정 인증 헤더 | 현재 공개 읽기 서버에는 불필요 |

```text
https://h-rules.stoom.win/api/academyinfo/mcp
```

한남대 규정용 `https://h-rules.stoom.win/api/mcp`는 다른 서비스입니다. 기존 규정 연결을 임의 삭제하거나 URL을 교체하지 않습니다.

## Claude 웹

개인 계정은 **Customize → Connectors → + Add → Add custom connector**에서 이름·URL을 넣고 인증을 **No sign in**으로 등록합니다. 사용할 대화에서는 입력창의 **+ → Connectors**에서 켭니다. 조직 계정은 관리자의 연결 등록·허용 뒤 개인 연결·대화 활성화를 확인합니다. Free 계정의 사용자 지정 연결 수 등 조건은 [Claude 공식 원격 MCP 안내](https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp)를 확인하세요.

현재 대화에서 실제 대학알리미 도구가 발견되는지 확인합니다. 도구가 아직 로딩되지 않았으면 연결 이름만으로 등록 실패라고 단정하지 말고 요청에 맞는 연결을 찾게 한 뒤 결과로 판단합니다. 규정 도구만 보이는 상태는 대학알리미 도구 가용성과 다릅니다.

## ChatGPT 웹

공식 문서의 현재 등록 경로는 **Plugins → + → Add custom MCP server**입니다. 이름과 위 URL, **No authentication**을 지정해 생성한 뒤 해당 플러그인을 별도로 **설치**합니다. 새 대화의 `@` 선택과 실제 도구 응답으로 사용 여부를 확인합니다. [OpenAI 공식 MCP 연결 안내](https://developers.openai.com/api/docs/guides/custom-mcp-server), [연결·설치·새 대화 호출 절차](https://developers.openai.com/plugins/build/app-quickstart#connect-your-mcp-server-in-chatgpt)

계정·워크스페이스에 메뉴가 없으면 현재 권한과 정책을 확인합니다. GitHub URL을 채팅에 붙이거나 ZIP을 첨부하는 것으로 등록을 대신할 수 없습니다. MCP만 연결해 만든 플러그인에 이 저장소의 스킬까지 자동 포함됐다고 가정하지 않습니다.

## 연결과 실제 조회를 확인하기

연결 등록 뒤 실제 조회도 확인하려면 다음처럼 요청합니다. 설치 안내만 요청한 상황에서는 새 통계 조회를 임의로 추가하지 않습니다.

> 대학알리미FLOW 연결을 찾아 실제로 사용할 수 있는 조회 도구를 확인하고 공개 연도를 조회해 줘. 원천 응답·조회 시각과 확인한 범위를 알려 줘.

실제 도구는 `academyinfo_scope`, `academyinfo_catalog`, `academyinfo_report` 등을 포함하며 호스트가 접두사를 붙일 수 있습니다. 이름·URL 표시, 도구 발견, 원천 응답은 별도 상태입니다.

| 확인 단계 | 확인한 것 | 추가로 확인할 것 |
| --- | --- | --- |
| 연결 등록·플러그인 설치 | 계정에 연결이 있음 | 대화에서 도구 사용 가능 여부 |
| scope 응답 | 공식 공개 연도 조회 성공 | 요청한 수치 표와 지침 정의 |
| report 응답 | 해당 표·조건의 값·출처 | 전체 페이지·반환 범위·표 검증·기준기간 |

scope 성공 후 필요한 수치 질문을 보냅니다.

> 한남대학교의 최신 공개 취업률을 조회하고 공시연도·실적 기준기간·단위·공식 출처·조회 시각과 전체 조회 여부를 함께 알려 줘.

서버 0.2.5의 학과 report는 정확한 학교명 하나가 있으면 공식 명부 검증 후 학교 상세 양식 60을 자동 선택합니다. 전국 장표는 아래 이어받기 도구를 사용합니다.

## Claude 웹에 스킬을 추가하기

[Claude 웹용 스킬 ZIP 0.3.2](../downloads/academyinfo-flow-skill-claude-web-0.3.2.zip)을 사용합니다. 파일·해시·공개 상태는 [배포 파일 설명](../downloads/README.md)에서 확인합니다.

1. 현재 계정에서 코드 실행과 Skills가 허용되는지 확인합니다. 개인 계정은 **Settings → Capabilities**, 조직 계정은 해당 관리 정책을 따릅니다.
2. **Customize → Skills → + → + Create skill → Upload a skill**에서 단독 스킬 ZIP을 올립니다.
3. 목록의 대학알리미FLOW를 켭니다. 대화의 MCP 활성화도 별도로 확인합니다. [Claude 공식 Skills 사용·업로드 안내](https://support.claude.com/en/articles/12512180-use-skills-in-claude)

코드 실행 활성화는 Claude Skills의 조건이며 원격 MCP 조회에 사용자 Python이 필요하다는 뜻은 아닙니다. 계정 설정 도구가 없는 대화의 AI는 안내·ZIP 검수를 할 수 있지만 계정 등록·토글 변경을 대신 완료했다고 말하지 않습니다.

ZIP은 단일 `academyinfo-flow/` 아래 `SKILL.md`, `scripts/`, `references/`를 담습니다. Codex용 `agents/`와 MCP 설정은 제외합니다. 채팅 첨부·구조 검수·Skills 등록·활성화·MCP 연결을 구분합니다. 이미 가용 MCP가 있고 사용자가 조회를 요청했다면 수동 스킬 설치를 기다릴 필요는 없습니다.

## 지원 범위와 제한

| 원격 도구 | 기능 |
| --- | --- |
| `academyinfo_scope`, `academyinfo_catalog` | 공개 연도·기관·공시 항목 |
| `academyinfo_schools`, `academyinfo_affiliations`, `academyinfo_departments` | 학교·소속·학과 명부 |
| `academyinfo_metric` | 지원되는 6종 학과 주요지표 |
| `academyinfo_report` | 일반 학교별·학과별 수치 장표 |

일반 report 한 번의 호출 범위는 기본 16페이지, 최대 32페이지입니다. 전국 이어받기는 이 호출당 분량을 여러 번 이어가며 전체 5,000쪽까지 처리합니다. 초기화 요청 25초·다른 원천 요청 12초·전체 45초·최대 원천 요청 40회와 바이트 제한을 적용합니다. **실제 schema와 응답의 `resource_bounds`가 우선**이며 예산이 부족하면 부분·오류 상태를 반환합니다. `limit`와 이름 필터는 원천 수신 뒤 적용됩니다.

원격 MCP 0.2.5에는 학교 상세 `school_code`와 전국 장표 이어받기 도구 4개가 추가됩니다. 첨부·PDF 본문·지침 전체 파싱은 지원하지 않습니다. 필요한 경우 실행 가능한 Python과 공식 연결이 확인된 환경에서 [로컬 CLI·학교 상세 경로](INSTALL.md)를 사용합니다. 소스·CLI 0.3.2와 원격 MCP 0.2.5는 별도로 배포됩니다.

## 잘 안될 때

| 상태 | 다음 판단 |
| --- | --- |
| 스킬만 있고 조회 도구가 없음 | 커넥터 등록·대화 활성화·실제 도구 발견 확인 |
| `source_timeout` / `report_initialize` | 조건이 맞고 일시적 원천 timeout이면 새 조회를 한 번만 추가 시도. 두 번째도 실패하면 중단하고 단계·확보 범위 보고 |
| `query_deadline_exceeded` | 전체 시간 예산 도달. 개별 원천 timeout과 구분하고 같은 조건을 자동 반복하지 않음 |
| 페이지 상한·`request_budget_exhausted` | 같은 원격 호출·offset 변경 반복 금지. 실제 제한·예상/수신 페이지 확인, 가능한 공식 경로 선택 |
| 원천은 완전하고 반환만 제한 | 이미 확보한 JSON 또는 같은 자료의 지원되는 반환 기능 확인. 반환 제한을 원천 장애로 오해하지 않음 |
| 부분·반복 페이지·표 불일치·미지원 | 확보 범위만 사용하며 전국 합계·누락 없는 순위를 완료로 보고하지 않음 |
| `source_connection_error` | 원격 MCP와 Python 직접 접속을 구분. 도메인 허용목록·요금제·계정 등록 문제 중 하나로 단정하지 않음 |

[장표 복구 지침](../skills/academyinfo-flow/references/report-recovery.md)과 [지역별 재학생 집계](../skills/academyinfo-flow/references/regional-enrollment.md)를 0.3.2 스킬 ZIP에도 포함합니다. 이미 요청한 읽기·검증·집계와 제한된 재시도에는 다시 허락을 요구하지 않습니다.

한 요청의 성공은 다른 계정·연도·항목의 실행과 지침 정의까지 보장하지 않습니다. `guideline_verified=false`는 지침 정의를 검증 완료로 표시하지 않았다는 뜻입니다. 확인한 실행과 미검증 범위는 [검증 기록](VERIFICATION.md)에서 구분합니다.

## 전국 모든 학과의 큰 장표

`academyinfo_report_start`로 초기화하고 같은 job의 `academyinfo_report_continue`를 `job_status=complete`까지 진행합니다. 한 호출의 32쪽 상한으로 전국 수신이 끝나는 구조가 아닙니다. 완료 뒤 전체 JSON 다운로드 또는 `academyinfo_report_read`로 행을 읽습니다. 원천 세션·공개 행의 2시간 임시 보관과 삭제, 실패 복구·완전성은 [이어받기 지침](../skills/academyinfo-flow/references/large-reports.md)을 따릅니다. 도구가 7개만 보이면 호스트에서 연결의 도구 목록을 갱신하고 새 대화에서 11개 도구와 서버 0.2.5를 확인합니다. Claude 계정 조작은 이번 소스 수정과 별도입니다.
