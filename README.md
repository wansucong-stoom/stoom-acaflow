# 대학알리미FLOW

[GitHub 소스 · 설치 주소](https://github.com/wansucong-stoom/stoom-acaflow)

**대학알리미FLOW는 대학·학과 공시의 새 수치와 현재 비교를 공식 원천에서 새로 조회하고, 해당 연도 지침의 기준·단위·산식을 확인하는 스킬 플러그인입니다.** 실제 조회에서 검증한 장표별 경로와 공통 호출 규칙을 누적하며, 사용자가 지정한 보존본·역사·스냅샷 분석에는 자료 시점을 표시합니다. STOOM이 개발합니다.

실제 작업 규칙은 `skills/academyinfo-flow/SKILL.md`에 있는 **스킬**, 이를 설치·공유하는 묶음은 **플러그인**입니다. 플러그인은 대학알리미 공식 원천을 새로 조회하는 STOOM 호스팅 읽기 MCP의 연결 설정을 포함합니다. endpoint는 `https://h-rules.stoom.win/api/academyinfo/mcp`입니다. 표시명은 모든 지원 화면에서 **대학알리미FLOW**로 통일하며, 설치 명령에 쓰는 내부 식별자는 `academyinfo-flow`입니다.

## 웹에서 먼저 연결하기

**웹의 원격 MCP 연결과 선택적인 스킬 추가는 별도입니다.** 공식 수치 조회부터 시작하려면 전용 연결을 등록하고 대화에서 켜세요. 원격 MCP 조회에는 사용자의 Python 설치가 필요하지 않습니다.

**[웹 MCP 연결 안내 바로 보기](docs/WEB-MCP.md)** — [Claude](docs/WEB-MCP.md#claude-웹) · [ChatGPT](docs/WEB-MCP.md#chatgpt-웹) · [실제 조회 확인](docs/WEB-MCP.md#연결과-실제-조회를-확인하기) · [문제 해결](docs/WEB-MCP.md#잘-안될-때)

| 설정 | Claude 웹 | ChatGPT 웹 |
| --- | --- | --- |
| 이름 | 대학알리미FLOW | 대학알리미FLOW |
| 서버 URL | `https://h-rules.stoom.win/api/academyinfo/mcp` | 같은 주소 |
| 인증 | No sign in | No authentication |
| 사용 준비 | 커넥터 등록 → 대화에서 켜기 | MCP 플러그인 생성 → 설치 → 대화에서 선택 |
| 분석 지침 추가 | [웹용 스킬 ZIP](https://github.com/wansucong-stoom/stoom-acaflow/raw/refs/heads/main/downloads/academyinfo-flow-skill-claude-web-0.2.6.zip)을 Skills에 업로드 | 스킬과 MCP를 포함한 플러그인의 실제 로딩 확인 |

[한남대 규정용 연결과의 구분, 계정 조건, 업로드 파일 형식](docs/WEB-MCP.md)을 먼저 확인하세요. 로컬 Codex·Claude Code 설치는 아래 절차입니다.

## 로컬 AI에게 주소를 주고 설치하기

파일을 읽고 명령을 실행할 수 있는 Codex 또는 Claude Code에 아래 요청을 전달하세요.

> https://github.com/wansucong-stoom/stoom-acaflow 의 대학알리미FLOW를 지금 사용하는 AI 환경에 설치해 줘. README와 AGENTS.md를 먼저 읽고, 환경에 맞는 설치기를 실행한 뒤 설치 결과를 확인해 줘.

AI는 저장소를 읽어 현재 클라이언트를 확인하고 설치·검증까지 진행할 수 있습니다. Python 3.11 이상, Git 또는 다운로드 도구, 설치 경로에 대한 쓰기 권한이 필요합니다. 클라이언트가 둘 이상이거나 식별되지 않으면 설치 대상을 선택해야 합니다. 실행 환경에서 요구하는 권한 승인은 그대로 따릅니다.

**먼저 현재 대화에서 사용할 수 있는 읽기 MCP 도구를 발견하고 입력 schema를 확인합니다.** 연결된 도구가 있으면 공개 연도·공시 목록·학교·소속·학과·학과 주요지표·일반 장표를 새로 조회할 수 있으며, 이 경로에는 사용자의 Python이 필요하지 않습니다. 도구가 없으면 먼저 현재 클라이언트의 MCP 등록·대화 활성화 절차를 확인합니다. 사용자가 Python 대체 경로를 선택한 경우 실행 도구·Python 3.11 이상·공식 원천 네트워크를 실제로 점검해 번들 스크립트를 사용합니다. endpoint의 존재, 계정의 실제 연결, 도구 가용성, 웹에서의 전체 실행은 각각 확인해야 합니다.

| 환경 | 설치·불러오기 | 실제 조회 조건과 확인 범위 |
| --- | --- | --- |
| ChatGPT 웹 | [MCP 플러그인 등록·설치·호출](docs/WEB-MCP.md#chatgpt-웹), Work부터 확인 | 한 대화의 MCP 조회 기록 확인. 계정별 스킬 설치·연결·실제 도구·원천 응답은 각각 확인. 선택한 Python 경로는 런타임·네트워크 점검 |
| Claude 웹 | Skills ZIP 업로드와 전용 Connectors 등록·대화 활성화를 각각 수행 | Skills는 공식 활성 조건을 따름. 원격 MCP는 사용자 Python 없이 실행. 실제 도구·scope 응답 확인. 웹 전체 실행은 미검증 |
| Codex | 개인 스킬 폴더 또는 스킬 플러그인 설치 | 읽기 도구를 먼저 확인하고, 없으면 제공 Python·원천 네트워크 점검. 파일·로딩·조회 각각 확인 |
| Claude Code | 개인 스킬 또는 네이티브 플러그인 설치 | 플러그인의 MCP 설정과 실제 도구 로딩 확인. 개인 스킬 설치만으로 MCP가 등록되지는 않음 |

현재 읽기 MCP는 서버 응답·7개 도구 발견과 2026 공개 연도·항목 목록, 한남대학교 캡스톤 장표 9쪽의 조회를 확인했습니다. ChatGPT 웹 한 대화의 scope·catalog·report MCP 조회 기록도 확인했습니다. 이는 모든 계정의 스킬 설치·연결 성공을 보장하지 않으며, 실제 스킬 설치까지 검증한 결과는 아닙니다. Claude 웹의 등록부터 조회까지 전체 실행은 미검증입니다. 패키지 형식은 [OpenAI 플러그인 구성](https://developers.openai.com/plugins/concepts/plugins)을 참고하세요.

웹의 계정별 등록·활성화·도구 응답은 [웹 전용 안내](docs/WEB-MCP.md)에 따라 확인합니다.

## 직접 설치하기

저장소를 내려받고 사용할 클라이언트 하나를 선택합니다.

```sh
git clone https://github.com/wansucong-stoom/stoom-acaflow.git
cd stoom-acaflow
python -B -X utf8 install.py --client codex
python -B -X utf8 install.py --client codex --check
```

Claude Code는 두 명령의 `--client codex`를 `--client claude-code`로 바꾸세요. 두 환경 모두 설치하려면 `--client both`를 명시하세요. Windows에서 `python` 대신 `py -3.11` 또는 호스트가 제공한 Python 3.11 이상 경로를 사용할 수 있습니다.

| 환경 | 기본 개인 스킬 설치 경로 | 호출 |
| --- | --- | --- |
| Codex | `~/.agents/skills/academyinfo-flow` | `@대학알리미FLOW` 또는 `$academyinfo-flow` |
| Claude Code 스킬 | `~/.claude/skills/academyinfo-flow` | `/academyinfo-flow` 또는 자연어 요청 |
| Claude Code 플러그인 | Claude Code가 관리하는 플러그인 캐시 | `/academyinfo-flow:academyinfo-flow` |

Claude Code에서 플러그인으로 설치하려면 위 개인 스킬 설치 대신 다음 명령을 사용합니다.

```sh
claude plugin marketplace add wansucong-stoom/stoom-acaflow
claude plugin install academyinfo-flow@stoom-acaflow
claude plugin list
```

같은 환경에 개인 스킬과 플러그인을 모두 설치하면 두 항목이 보일 수 있으므로 한 방식을 선택하세요. 자세한 대상 선택·업데이트·검증 방법은 [설치 안내](docs/INSTALL.md)를 읽으세요.

## 사용 예시

- `@대학알리미FLOW 한남대학교의 최신 공개 취업률을 조회하고 기준기간과 단위를 설명해 줘.`
- `@대학알리미FLOW 공개된 전체 공시 항목과 대학·학과별 조회 가능 여부를 보여 줘.`
- `@대학알리미FLOW 두 대학의 장학금 지표를 같은 기준으로 비교하고 공식 근거를 달아 줘.`
- `@대학알리미FLOW 특정 학과의 등록금과 경쟁률을 조회해 줘.`

새 수치·현재 비교 요청마다 공개 연도와 관련 원천 값을 새로 확인합니다. 대학·학과·계열과 캠퍼스, 공시연도·기준기간, 단위·분모를 구분합니다. 빈 결과·미공개·미지원은 숫자 0으로 바꾸지 않습니다. 수치와 출처, 조회 시각, 확인한 범위 및 제한을 함께 제시합니다.

확보한 장표별 경로 목록은 호출 경로·공개 인자·검증 근거를 재사용하는 메타데이터입니다. 이전 통계값을 새 수치 대신 사용하는 기능이 아닙니다. 사용자가 보존본·역사·스냅샷을 지정한 경우에만 연결된 아카이브의 확보 범위와 시점을 확인해 그 용도로 사용하며, 현재 값을 요청한 범위는 공식 원천에서 새로 조회합니다. 같은 내용의 공식 추이 파일이 있으면 실제 목록에서 필요한 파일 한 개를 새로 받아 장기 시계열을 분석할 수 있습니다. 일반 라이브 장표는 전국 표를 받은 뒤 학교·학과로 필터링하므로 응답 시간이 달라질 수 있습니다. 보존본과 새 조회의 시점은 구분해 표시합니다.

## 실행 조건과 포함 범위

연결된 읽기 MCP 도구를 사용할 때는 사용자의 Python이 필요하지 않습니다. Python 대체 경로의 기본 JSON 조회와 개인 폴더 설치기에는 **Python 3.11 이상 표준 라이브러리**만 필요합니다. 현재 MCP의 지원 범위에는 첨부 목록·PDF 본문·지침 전체 파싱이 포함되지 않습니다. 이 기능은 번들 Python 경로나 가용 공식 웹/PDF 도구를 사용하며, Python PDF 파싱에는 `pdfplumber>=0.11,<1`이 선택적으로 필요합니다. 설치기는 패키지나 개인 MCP 설정을 자동으로 변경하지 않습니다. 연결 예시와 선택 의존성은 [설치 안내](docs/INSTALL.md)를 읽으세요.

패키지에는 실행 스크립트, 지침, 탐색용 공시·지침 메타데이터가 포함됩니다. 대학별 통계 관측값, 수집 DB, PDF·지침 전문, 인증키는 포함하지 않습니다. 공식 사이트의 접근 제한과 실행 환경의 네트워크 정책을 따릅니다.

```text
plugin.json                    공통 플러그인 선언
mcp.json                       공통 원격 MCP 연결 설정(streamable-http)
.mcp.json                      Codex·Claude Code 호환 MCP 연결 설정(http)
.codex-plugin/plugin.json      Codex 호환 선언
.claude-plugin/plugin.json     Claude Code 플러그인 선언
.claude-plugin/marketplace.json Claude Code 설치 목록
install.py                     개인 로컬 스킬 설치·검증
skills/academyinfo-flow/        스킬·Python 스크립트·참고 자료
docs/INSTALL.md                 상세 설치 안내
```

로컬 설치기는 같은 내용이면 그대로 두며, 다른 내용이 이미 있으면 `--update` 없이 덮어쓰지 않습니다. 업데이트는 이전 디렉터리를 스킬 탐색 경로 밖에 백업한 후 교체합니다. `--check`는 모든 포함 파일의 해시를 비교하고 파일을 변경하지 않습니다. 이것은 파일 설치 확인이며, 실제 서비스의 네트워크 조회나 화면에서의 스킬 로딩까지 증명하지는 않습니다.

## 0.2.6에서 개선한 것

- **Claude 웹 전용 커넥터 안내:** Skills ZIP 업로드와 MCP 등록·대화 활성화를 구분하고 전용 URL·무인증 설정·실제 읽기 도구 확인을 안내합니다. 연결 도구가 없으면 등록부터 확인하며 Python 대체 경로는 사용자가 선택하고 실행 조건을 점검합니다.

## 0.2.5에서 통합한 것

- **읽기 MCP 우선 조회:** 검증한 원격 endpoint 연결 설정을 플러그인에 포함하고, 스킬은 실제 도구·schema를 먼저 확인합니다. Python 없는 환경도 가용 읽기 도구 범위에서 조회하며, 지원 밖의 PDF·지침은 기존 경로를 사용합니다.
- **조회 용도 구분:** 새 수치·현재 비교는 공식 새 조회를 기본으로 하고, 지정한 보존본·역사·스냅샷은 자료 시점을 밝혀 분석합니다. 0.2.4의 조회 경로 관리·공식 파일 조회 기능을 유지합니다.
- **평균·비율 분석 기준:** 학교별 단순평균·중앙값과 분모 가중평균·합산 비율을 구분하며 표본·분모·결측·실제 0·반올림 기준을 확인합니다. [평균 분석 지침](skills/academyinfo-flow/references/analysis-averages.md)을 참고하세요.

## 0.2.4에서 개선한 것

- **장표별 경로 목록:** 기존 아카이브 다운로드 명세와 기관별 공식 공시목록을 `references/query-routes.json`으로 보관합니다. 필요한 장표만 조회하고 설치된 캐시 밖의 작업 폴더에 검증 이력을 누적합니다.
- **공통 호출 규칙 학습:** 같은 방식·호스트·경로·공개 인자 키를 묶고, 공식 목록에 있는 선택자만 새 후보로 만듭니다. 후보와 본문 검증 성공을 구분하며 실패가 마지막 성공 기록을 덮어쓰지 않습니다.
- **공식 시계열 파일 직접 조회:** `live_files.py`가 실제 파일 목록·목적 등록·첨부파일 검증을 수행합니다. 웹의 HTTP 도구도 같은 공개 경로와 명세를 사용할 수 있습니다.
- **조회 때 자동 기록:** JSON·장표·일괄·파일 CLI가 공개 경로 메타데이터를 기록합니다. 숫자·쿠키·SQL·세션 URL은 경로 저장소에 넣지 않습니다. 저장 실패는 통계 조회 결과를 바꾸지 않습니다.

경로 정책과 사용법은 [경로 관리](skills/academyinfo-flow/references/route-management.md)를 참고하세요. 같은 기록을 여러 웹 세션에서 누적하려면 상태 파일을 영속 저장소에 보관하고 다음 실행에 제공해야 합니다.

## 0.2.3에서 개선한 것

- **표 정체성 검증:** master·header·body 메타데이터의 항목 식별자나 표 구분이 상충하거나, 요청한 학교·학과 단위와 표 구분이 다르면 검증 완료로 처리하지 않습니다.
- **반복 페이지 검증:** 다른 요청 페이지 번호에서 같은 XML이나 같은 파싱 본문이 반복되면 전체 보고서가 완료되었다고 표시하지 않습니다.

## 0.2.2에서 개선한 것

- **환경별 실행 전 점검:** Python과 선택 PDF 패키지를 확인하고, `--check-source`를 요청한 경우에만 공식 공개 연도를 새로 조회합니다.
- **용도별 세 ZIP:** 플러그인, Codex 폴더 설치용 스킬, Claude 웹 업로드용 스킬을 별도 파일로 만듭니다. Claude 웹판은 Codex용 `agents/`만 제외하며 같은 핵심 코드를 담습니다.
- **열 선택과 독자용 표기:** 전체 상위 헤더와 하위 열을 확인하고 원천 값과 파생 합계를 구분합니다. 본문은 학교·항목명·기간·단위·링크·조회일로 표기하며 원천 JSON의 식별자·좌표·해시는 유지합니다.

0.2.0의 기존 조회·최적화 기능도 유지합니다.

- **한 질문 안의 중복 조회 감소:** 같은 장표를 여러 대학·학과·반환 범위에 재사용하는 `live_batch.py`를 추가했습니다. 실행이 끝나면 재사용 자료를 폐기하고 다음 실행은 새로 조회합니다.
- **다중 학교 필터:** `--school-name`, `--dept-name`을 반복 지정할 수 있습니다. 학교와 학과의 특정 쌍을 비교할 때는 일괄 조회의 개별 질문으로 나눕니다.
- **표 복원 최적화:** 같은 셀의 정확한 Decimal 좌표를 반복 계산하지 않고, 행 경계를 따라 필요한 셀을 찾아갑니다. 이후 버리던 XML 트리는 라이브 조회에서 만들지 않습니다. 모든 페이지의 표 구조와 누락·모호성 검증은 유지합니다.
- **간결한 결과:** 일괄 조회는 기본으로 중복 셀 상세를 생략합니다. 숫자·문자열·단위 해석용 열 정의·원천 페이지·출처·해시·완전성·경고는 유지합니다. 전체 출력도 선택할 수 있습니다.
- **지침 여러 항목을 한 번에:** `live_guide.py --codes`가 새 PDF 한 번의 수신으로 필요한 페이지 합집합을 읽습니다.
- **처리 시간 진단:** 원천 초기화·생성 대기·페이지 수신·표 복원·검증·출력 준비 시간을 구분합니다.

일반 장표는 여전히 공식 보고서 전체를 읽은 뒤 학교를 필터링하는 경로입니다. 공식 서버에 없는 학교 필터를 임의로 만들거나, 페이지를 생략하고 전체 결과라고 표시하지 않습니다. 요청 간격도 유지합니다. 최적화된 파서의 속도를 실제 네트워크·LLM을 포함한 응답속도로 해석하면 안 됩니다.

## 실행

연결된 MCP의 실제 도구와 schema를 확인한 뒤 요청에 맞는 읽기 도구를 사용합니다. Claude 웹에서 도구가 없으면 전용 커넥터 등록·대화 활성화를 먼저 확인합니다. 다음은 사용자가 선택한 Python 대체 경로입니다. 실제 실행 도구·Python·원천 네트워크가 확인된 환경에서 저장소를 받은 위치를 기준으로 실행하며, 기본 통계 조회·표 복원은 Python 표준 라이브러리를 사용합니다. 지침/PDF 추출에만 추가로 `pdfplumber>=0.11,<1`이 필요합니다.

```sh
python -B -X utf8 skills/academyinfo-flow/scripts/runtime_preflight.py
python -B -X utf8 skills/academyinfo-flow/scripts/live_json.py scope
python -B -X utf8 skills/academyinfo-flow/scripts/live_batch.py --input queries.json
python -B -X utf8 skills/academyinfo-flow/scripts/live_batch.py --input queries.json --full-output
python -B -X utf8 skills/academyinfo-flow/scripts/route_registry.py lookup --keyword "신입생 충원" --division 02 --level department
python -B -X utf8 skills/academyinfo-flow/scripts/live_files.py catalog --division 02
```

조회조건 JSON에는 먼저 공식 목록으로 확인한 연도·항목 ID·학교/학과 식별자를 넣습니다. 지원 명령·입력 예시·반환 상태·측정 구간은 [실행 지침](skills/academyinfo-flow/SKILL.md)과 [일괄 조회 명세](skills/academyinfo-flow/references/performance.md)를 참조하세요.

## 검증과 패키지 만들기

```sh
python -B -X utf8 -m unittest discover -s tests -v
python -B -X utf8 scripts/build_plugin.py
claude plugin validate .
```

빌더는 다음 세 파일을 만듭니다. 기존 식별자와 기본 프롬프트를 유지하며 테스트·실행 캐시는 제외합니다.

| 파일 | 용도 |
| --- | --- |
| `dist/academyinfo-flow-plugin-0.2.6.zip` | 플러그인 설치·배포용 |
| `dist/academyinfo-flow-skill-codex-0.2.6.zip` | 압축을 풀어 개인 스킬 상위 폴더에 설치 |
| `dist/academyinfo-flow-skill-claude-web-0.2.6.zip` | Claude 웹 Skills에 그대로 업로드 |

두 스킬 ZIP의 최상위 폴더는 `academyinfo-flow/`이며 MCP 설정 파일은 포함하지 않습니다. Codex판에는 `agents/openai.yaml`이 포함되며 Claude 웹판에서는 `agents/`를 제외합니다. 플러그인 ZIP에는 공통 `mcp.json`과 Codex·Claude Code 호환 `.mcp.json`이 포함됩니다. 업로드·클라이언트 로딩·MCP 연결·도구 가용성·원천 조회를 각각 검증합니다.

이전 설치본은 Git 이력의 `Import installed academyinfo-flow 0.1.0 source` 커밋에 보존했습니다. 해당 버전을 다른 경로에 체크아웃한 다음 다음 명령으로 표 복원 출력과 시간을 비교할 수 있습니다.

```sh
python -B -X utf8 tests/parser_benchmark.py --baseline /path/to/previous-release
```

조회 테스트는 모의 HTTP/PDF 응답과 합성 표를 사용하며, 공공 서버의 전수 조회를 실행하지 않습니다. 설치 테스트는 실제 개인 설정을 바꾸지 않는 임시 사용자 폴더를 사용합니다. 측정 결과와 한계는 [성능 검증 기록](docs/performance.md)에 정리했습니다.

## 원천과 라이선스

공식 데이터 원천은 [대학알리미](https://www.academyinfo.go.kr/)입니다. 번들 공개 프로토콜 어댑터는 [stoom-openacainfo](https://github.com/wansucong-stoom/stoom-openacainfo)에서 가져왔으며 MIT 저작권 고지를 유지합니다. 최적화 내역은 이 저장소에서 관리합니다. 통계의 기준기간·단위·산식은 해당 공시연도 지침과 원천 열을 확인해야 합니다.

문의·개선 제안은 [GitHub Issues](https://github.com/wansucong-stoom/stoom-acaflow/issues)에 남길 수 있습니다. 코드는 [MIT 라이선스](LICENSE)로 배포합니다. 원천 데이터는 해당 제공기관의 이용 조건을 따릅니다.

설치 경로와 패키지 형식은 [OpenAI 공식 스킬 문서](https://learn.chatgpt.com/docs/build-skills), [Claude Code 스킬 문서](https://code.claude.com/docs/en/skills), [Claude Code 플러그인 명세](https://code.claude.com/docs/en/plugins-reference)를 기준으로 작성했습니다.
