# 대학알리미FLOW

[GitHub 소스 · 설치 주소](https://github.com/wansucong-stoom/stoom-acaflow)

**대학알리미FLOW는 대학알리미 공식 서버에서 대학·학과 공시를 새로 조회하고, 해당 연도 지침의 기준·단위·산식을 확인해 답변하는 스킬 플러그인입니다.** STOOM이 개발하며, 공개 조회 스크립트와 사용 지침을 함께 제공합니다.

실제 작업 규칙은 `skills/academyinfo-flow/SKILL.md`에 있는 **스킬**, 이를 설치·공유하는 묶음은 **플러그인**입니다. 이 버전에는 **MCP 서버가 없습니다.** 표시명은 모든 지원 화면에서 **대학알리미FLOW**로 통일하며, 설치 명령에 쓰는 내부 식별자는 `academyinfo-flow`입니다.

## AI에게 주소를 주고 설치하기

파일을 읽고 명령을 실행할 수 있는 Codex 또는 Claude Code에 아래 요청을 전달하세요.

> https://github.com/wansucong-stoom/stoom-acaflow 의 대학알리미FLOW를 지금 사용하는 AI 환경에 설치해 줘. README와 AGENTS.md를 먼저 읽고, 환경에 맞는 설치기를 실행한 뒤 설치 결과를 확인해 줘.

AI는 저장소를 읽어 현재 클라이언트를 확인하고 설치·검증까지 진행할 수 있습니다. Python 3.11 이상, Git 또는 다운로드 도구, 설치 경로에 대한 쓰기 권한이 필요합니다. 클라이언트가 둘 이상이거나 식별되지 않으면 설치 대상을 선택해야 합니다. 실행 환경에서 요구하는 권한 승인은 그대로 따릅니다.

**일반 ChatGPT·Claude 웹 대화에 주소만 붙이는 것으로 로컬 스크립트가 실행되지는 않습니다.** 파일·Python·네트워크 실행 도구가 있는 환경이나, 별도로 구축한 원격 MCP 연결이 필요합니다. 이 저장소는 원격 서버 주소나 모든 웹 챗 환경의 자동 설치를 제공하지 않습니다. GitHub 공개와 각 서비스의 공식 플러그인 디렉터리 등록은 별도 절차입니다.

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

요청할 때마다 공개 연도와 관련 원천 값을 확인합니다. 대학·학과·계열과 캠퍼스, 공시연도·기준기간, 단위·분모를 구분합니다. 빈 결과·미공개·미지원은 숫자 0으로 바꾸지 않습니다. 수치와 출처, 조회 시각, 확인한 범위 및 제한을 함께 제시합니다.

일반 공시 장표는 공식 전국 표를 조회한 후 학교·학과로 필터링하므로 응답 시간이 달라질 수 있습니다. 같은 대화에서 확인한 선택자나 지침 정의를 재사용할 수 있지만, 새로운 수치 요청은 공식 원천을 다시 조회합니다. 모든 장표가 동일한 속도로 처리되거나 항상 몇 초 안에 완료되는 것은 아닙니다.

## 실행 조건과 포함 범위

기본 JSON 조회와 설치에는 **Python 3.11 이상 표준 라이브러리**만 필요합니다. PDF 본문·지침 파싱에는 `pdfplumber>=0.11,<1`이 선택적으로 필요합니다. 설치기는 패키지나 MCP 설정을 자동으로 변경하지 않습니다. PDF 기능이 필요하면 [설치 안내](docs/INSTALL.md)의 선택 의존성을 설치하세요.

패키지에는 실행 스크립트, 지침, 탐색용 공시·지침 메타데이터가 포함됩니다. 대학별 통계 관측값, 수집 DB, PDF·지침 전문, 인증키는 포함하지 않습니다. 공식 사이트의 접근 제한과 실행 환경의 네트워크 정책을 따릅니다.

```text
plugin.json                    공통 플러그인 선언
.codex-plugin/plugin.json      Codex 호환 선언
.claude-plugin/plugin.json     Claude Code 플러그인 선언
.claude-plugin/marketplace.json Claude Code 설치 목록
install.py                     개인 로컬 스킬 설치·검증
skills/academyinfo-flow/        스킬·Python 스크립트·참고 자료
docs/INSTALL.md                 상세 설치 안내
```

로컬 설치기는 같은 내용이면 그대로 두며, 다른 내용이 이미 있으면 `--update` 없이 덮어쓰지 않습니다. 업데이트는 이전 디렉터리를 스킬 탐색 경로 밖에 백업한 후 교체합니다. `--check`는 모든 포함 파일의 해시를 비교하고 파일을 변경하지 않습니다. 이것은 파일 설치 확인이며, 실제 서비스의 네트워크 조회나 화면에서의 스킬 로딩까지 증명하지는 않습니다.

## 0.2.0에서 개선한 것

- **한 질문 안의 중복 조회 감소:** 같은 장표를 여러 대학·학과·반환 범위에 재사용하는 `live_batch.py`를 추가했습니다. 실행이 끝나면 재사용 자료를 폐기하고 다음 실행은 새로 조회합니다.
- **다중 학교 필터:** `--school-name`, `--dept-name`을 반복 지정할 수 있습니다. 학교와 학과의 특정 쌍을 비교할 때는 일괄 조회의 개별 질문으로 나눕니다.
- **표 복원 최적화:** 같은 셀의 정확한 Decimal 좌표를 반복 계산하지 않고, 행 경계를 따라 필요한 셀을 찾아갑니다. 이후 버리던 XML 트리는 라이브 조회에서 만들지 않습니다. 모든 페이지의 표 구조와 누락·모호성 검증은 유지합니다.
- **간결한 결과:** 일괄 조회는 기본으로 중복 셀 상세를 생략합니다. 숫자·문자열·단위 해석용 열 정의·원천 페이지·출처·해시·완전성·경고는 유지합니다. 전체 출력도 선택할 수 있습니다.
- **지침 여러 항목을 한 번에:** `live_guide.py --codes`가 새 PDF 한 번의 수신으로 필요한 페이지 합집합을 읽습니다.
- **처리 시간 진단:** 원천 초기화·생성 대기·페이지 수신·표 복원·검증·출력 준비 시간을 구분합니다.

일반 장표는 여전히 공식 보고서 전체를 읽은 뒤 학교를 필터링하는 경로입니다. 공식 서버에 없는 학교 필터를 임의로 만들거나, 페이지를 생략하고 전체 결과라고 표시하지 않습니다. 요청 간격도 유지합니다. 최적화된 파서의 속도를 실제 네트워크·LLM을 포함한 응답속도로 해석하면 안 됩니다.

## 실행

저장소를 받은 위치에서 실행합니다. 기본 통계 조회·표 복원은 Python 표준 라이브러리를 사용합니다. 지침/PDF 추출에만 추가로 `pdfplumber>=0.11,<1`이 필요합니다.

```sh
python -B -X utf8 skills/academyinfo-flow/scripts/live_json.py scope
python -B -X utf8 skills/academyinfo-flow/scripts/live_batch.py --input queries.json
python -B -X utf8 skills/academyinfo-flow/scripts/live_batch.py --input queries.json --full-output
```

조회조건 JSON에는 먼저 공식 목록으로 확인한 연도·항목 ID·학교/학과 식별자를 넣습니다. 지원 명령·입력 예시·반환 상태·측정 구간은 [실행 지침](skills/academyinfo-flow/SKILL.md)과 [일괄 조회 명세](skills/academyinfo-flow/references/performance.md)를 참조하세요.

## 검증과 패키지 만들기

```sh
python -B -X utf8 -m unittest discover -s tests -v
python -B -X utf8 scripts/build_plugin.py
claude plugin validate .
```

빌더는 `dist/academyinfo-flow-0.2.0.zip`을 만듭니다. 루트와 호환용 매니페스트, 스킬과 실행 파일을 포함하며 테스트·실행 캐시는 제외합니다. 플러그인 식별자와 기존 기본 프롬프트, 로컬 실행 요구조건을 보존합니다.

이전 설치본은 Git 이력의 `Import installed academyinfo-flow 0.1.0 source` 커밋에 보존했습니다. 해당 버전을 다른 경로에 체크아웃한 다음 다음 명령으로 표 복원 출력과 시간을 비교할 수 있습니다.

```sh
python -B -X utf8 tests/parser_benchmark.py --baseline /path/to/previous-release
```

조회 테스트는 모의 HTTP/PDF 응답과 합성 표를 사용하며, 공공 서버의 전수 조회를 실행하지 않습니다. 설치 테스트는 실제 개인 설정을 바꾸지 않는 임시 사용자 폴더를 사용합니다. 측정 결과와 한계는 [성능 검증 기록](docs/performance.md)에 정리했습니다.

## 원천과 라이선스

공식 데이터 원천은 [대학알리미](https://www.academyinfo.go.kr/)입니다. 번들 공개 프로토콜 어댑터는 [stoom-openacainfo](https://github.com/wansucong-stoom/stoom-openacainfo)에서 가져왔으며 MIT 저작권 고지를 유지합니다. 최적화 내역은 이 저장소에서 관리합니다. 통계의 기준기간·단위·산식은 해당 공시연도 지침과 원천 열을 확인해야 합니다.

문의·개선 제안은 [GitHub Issues](https://github.com/wansucong-stoom/stoom-acaflow/issues)에 남길 수 있습니다. 코드는 [MIT 라이선스](LICENSE)로 배포합니다. 원천 데이터는 해당 제공기관의 이용 조건을 따릅니다.

설치 경로와 패키지 형식은 [OpenAI 공식 스킬 문서](https://learn.chatgpt.com/docs/build-skills), [Claude Code 스킬 문서](https://code.claude.com/docs/en/skills), [Claude Code 플러그인 명세](https://code.claude.com/docs/en/plugins-reference)를 기준으로 작성했습니다.
