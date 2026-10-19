# 대학알리미FLOW

대학·학과 공시를 공식 원천에서 새로 조회하고, 기준기간·단위·산식과 표의 완전성을 확인하는 스킬·플러그인·Python CLI입니다. STOOM이 개발하며 내부 식별자는 `academyinfo-flow`입니다.

현재 소스 버전은 **0.3.1**입니다. 설치된 0.3.0 CLI·학교 상세 조회와 0.2.8의 복구·지역 집계 지침을 공식 GitHub 소스에 통합했습니다. [변경 이력](CHANGELOG.md) · [검증 기록](docs/VERIFICATION.md) · [배포 파일](downloads/README.md)

## 환경에 맞게 시작하기

| 사용 환경 | 시작 경로 | 필요한 조건 |
| --- | --- | --- |
| Claude·ChatGPT 웹 | [원격 MCP 연결](docs/WEB-MCP.md) | 계정의 연결 권한과 대화에서 사용할 수 있는 도구. 사용자 Python 설치 불필요 |
| Codex·Claude Code | [개인 스킬 설치](docs/INSTALL.md#개인-스킬-설치) 또는 플러그인 | 파일·실행 권한. 실제 조회는 가용 MCP 또는 정상 연결된 Python 사용 |
| 터미널·Python 자동화 | [CLI 설치](docs/INSTALL.md#python-cli-설치) | Python 3.11 이상, 공식 원천에 접근 가능한 네트워크 |

스킬은 조회·분석 지침이고 MCP는 원격 실행 도구입니다. 단독 스킬 ZIP을 추가하는 것만으로 MCP가 등록되지는 않습니다.

## 웹에서 조회하기

전용 원격 주소는 다음과 같습니다. 현재 공개 읽기 서버는 별도 로그인·API 키·고정 인증 헤더가 필요하지 않습니다.

```text
https://h-rules.stoom.win/api/academyinfo/mcp
```

[Claude·ChatGPT 등록 절차](docs/WEB-MCP.md)에 따라 연결을 추가하고 사용할 대화에서 활성화합니다. 연결 후 다음처럼 요청합니다.

> 대학알리미FLOW의 실제 조회 도구를 확인하고 현재 공개 연도를 조회해 줘. 조회 시각과 원천 응답을 기준으로 확인한 범위를 알려 줘.

Claude에 분석 지침도 추가하려면 [웹용 스킬 ZIP 0.3.1](downloads/academyinfo-flow-skill-claude-web-0.3.1.zip)을 사용합니다. 코드 실행 활성 조건·스킬 업로드·커넥터 등록은 [웹 안내](docs/WEB-MCP.md#claude-웹에-스킬을-추가하기)에서 구분합니다. 파일의 공개·검증 상태는 [배포 파일 설명](downloads/README.md)을 확인하세요.

## Codex·Claude Code 개인 스킬 설치

저장소를 받은 뒤 사용할 클라이언트 하나를 선택합니다.

```sh
git clone https://github.com/wansucong-stoom/stoom-acaflow.git
cd stoom-acaflow
python -B -X utf8 install.py --client codex
python -B -X utf8 install.py --client codex --check
```

Claude Code는 `--client claude-code`를 사용합니다. Codex 기본 경로는 `~/.agents/skills/academyinfo-flow`, Claude Code는 `~/.claude/skills/academyinfo-flow`입니다. 기존 내용이 다르면 검토 후 `--update`로 백업하고 갱신합니다. [다른 경로·업데이트·플러그인 설치](docs/INSTALL.md)

Codex에서는 `@대학알리미FLOW` 또는 `$academyinfo-flow`, Claude Code 개인 스킬은 `/academyinfo-flow`로 요청할 수 있습니다.

> 한남대학교의 최신 공개 취업률을 조회하고 공시연도·기준기간·단위·공식 근거를 설명해 줘.

파일 설치 확인, 클라이언트에서 스킬 로딩, MCP 연결, 공식 원천 조회 성공은 각각 확인합니다. 개인 스킬 설치기는 MCP 설정을 변경하지 않습니다.

## Python CLI 사용

내려받은 저장소 루트에서 설치합니다. 아래 명령은 로컬 소스를 사용하며 PyPI 배포를 전제로 하지 않습니다.

```sh
python -m pip install .
academyinfo-live --version
academyinfo-live doctor
academyinfo-live scope
```

`doctor`는 기본 오프라인 점검입니다. 실제 원천 연결도 확인하려면 `academyinfo-live doctor --check-source`를 사용합니다. 설치 후에는 `python -m academyinfo_live`로도 같은 명령을 실행할 수 있습니다.

다음은 전국 장표에서 이름에 수학·수리가 포함된 학과를 찾고 JSON을 저장하는 예입니다. 실제 공개 연도·장표와 학과명 후보를 확인해 사용하세요.

```sh
academyinfo-live report --year 2026 --division 02 --item 7-가 --level department --dept-keyword 수학 --dept-keyword 수리 --max-pages 1000 --limit 10000 --progress --output math.json
```

`7-가` 같은 공시코드는 이번 공식 목록에서 유일한 항목 ID로 연결합니다. `--dept-keyword`는 학과명 문자열의 OR 검색이며 통계 계열이나 의미상 모든 관련 학과를 뜻하지 않습니다. 학교 한 곳의 학과 장표는 명부의 정확한 이름·코드를 확인한 뒤 `--school-code`와 `--school-name`을 함께 사용하면 학교 상세 경로를 선택할 수 있습니다. [CLI·학교 상세 예시](docs/INSTALL.md#학교-한-곳의-학과-장표)

`--output`은 전체 JSON을 저장하고 stdout에는 저장 요약을 출력합니다. 기존 파일은 `--force` 없이 덮어쓰지 않습니다. `--progress`의 진행 이벤트는 stderr로 나갑니다. Excel 직접 출력·중단된 세션 재개는 제공하지 않습니다.

| CLI 종료 코드 | 의미 |
| --- | --- |
| `0` | 완료 |
| `2` | 입력·조회 오류 |
| `3` | 부분 결과 |
| `130` | 사용자 중단 |

## 조회 경로와 범위

| 경로 | 지원 범위 | 확인할 제한 |
| --- | --- | --- |
| 원격 MCP | scope·catalog·schools·affiliations·departments·metric·report | generic report의 학교·학과 필터는 수신 후 적용. 학교 상세 코드 인수·PDF·지침 파싱 미지원 |
| Python 전국 장표 | 학교별·학과별 전체 보고서와 이름 필터 | 생성 완료·최종 페이지 수·전체 수신·표 검증을 확인. 호스트 네트워크·실행 시간과 `max_pages` 적용 |
| Python 학교 상세 | 정확한 학교 한 곳의 학과 장표, 공식 양식 60 | `--school-code`와 정확한 `--school-name` 하나, 현재 명부의 기관구분 일치 필요. 합계·대학원·이전 소속 행은 다시 필터 |
| Python 첨부·PDF·지침 | 첨부 목록과 확인한 PDF의 지정 범위 | PDF 파싱에만 선택 의존성 `pdfplumber>=0.11,<1` 필요 |

현재 원격 도구는 기본 **16페이지·최대 32페이지**, 초기화 **25초**, 다른 원천 요청 **12초**, 전체 **45초**와 원천 요청 수 예산을 적용합니다. **실제 도구 schema와 응답 `resource_bounds`가 우선**입니다. `limit`는 반환 행 범위이며 초기화 작업을 줄이지 않습니다. [제한·실패 대응](skills/academyinfo-flow/references/report-recovery.md)

소스·플러그인·CLI wheel의 0.3.1과 원격 서버의 표시 버전은 별도로 관리합니다. 원격 서버가 `0.2.4`를 표시하더라도 이 소스 설치만으로 서버 버전·인수·실행 한도가 바뀌지는 않습니다.

## 결과를 해석할 때

원천의 실제 전체 머리글, 기준기간·단위·기관·캠퍼스를 확인합니다. 공시연도와 행의 실적연도는 다를 수 있습니다. 빈칸·미공개·오류를 0으로 바꾸지 않으며, `complete=false`나 반환 누락이 있는 자료로 전국 합계·누락 없는 순위를 계산하지 않습니다.

- [연도별 지침 확인](skills/academyinfo-flow/references/guidelines.md): 포함·제외대상, 기준일·단위·산식.
- [평균과 비율](skills/academyinfo-flow/references/analysis-averages.md): 학교별 단순평균·중앙값과 분자·분모 합산 비율 구분.
- [시도별 재학생 수](skills/academyinfo-flow/references/regional-enrollment.md): 재학·재적, 복수 기간, 캠퍼스 중복과 결합 지역의 귀속 확인.
- [경로 관리](skills/academyinfo-flow/references/route-management.md): 검증한 호출 메타데이터 재사용. 이전 통계값으로 새 조회를 대신하지 않음.

패키지는 스크립트·지침·탐색 메타데이터를 포함합니다. 대학별 관측 통계·수집 DB·PDF 전문·인증키는 포함하지 않습니다.

## 자연어 요청 예시

- `@대학알리미FLOW 공개된 전체 공시 항목과 대학·학과별 조회 가능 여부를 보여 줘.`
- `@대학알리미FLOW 두 대학의 장학금을 같은 기간·단위로 비교하고 공식 근거를 달아 줘.`
- `@대학알리미FLOW 전국 17개 시도별 재학생 수를 집계하고 기관 범위·기준일·미분류를 밝혀 줘.`

지역별 집계는 관측행 수만으로 완전성을 판단하지 않습니다. 결합 지역·캠퍼스·기간과 전체 원천 수신을 확인한 뒤 합산하며, 원천 값과 파생 합계를 구분합니다.

## 개발과 패키지 검증

```sh
python -B -X utf8 -m unittest discover -s tests -v
python -B -X utf8 scripts/build_plugin.py
python -m pip wheel . --no-deps --wheel-dir dist
python -B -X utf8 scripts/verify_release.py --artifacts dist
python -B -X utf8 scripts/verify_wheel.py --artifacts dist
```

플러그인·Codex 스킬·Claude 웹 스킬 ZIP과 CLI wheel은 용도가 다릅니다. [설치·패키지 형식](docs/INSTALL.md#패키지-형식), [현재 파일과 해시](downloads/README.md), [실제로 수행한 검증과 한계](docs/VERIFICATION.md)를 확인하세요. 소스 공개·계정 설치·원격 배포·공식 디렉터리 게시를 구분합니다.

릴리스 검증기는 버전·로컬 문서 링크·ZIP의 파일 목록과 소스 바이트를 대조합니다. wheel 검증기는 별도 임시 위치에 설치해 오프라인 진입점과 참조 파일을 확인합니다. [GitHub Actions 설정](.github/workflows/verify.yml)은 Windows·Ubuntu와 Python 3.11·3.12에서 합성 테스트와 패키지 검증을 수행하도록 구성하며, 공식 통계를 수집하거나 예약 실행하지 않습니다. 설정 추가와 원격 CI 성공은 별도입니다.

공식 통계 원천은 [대학알리미](https://www.academyinfo.go.kr/)이며, 번들 어댑터의 [stoom-openacainfo](https://github.com/wansucong-stoom/stoom-openacainfo) MIT 고지를 유지합니다. 이 저장소의 코드는 [MIT](LICENSE)로 배포하며 원천 자료에는 제공기관의 이용 조건이 적용됩니다. [문의·개선 제안](https://github.com/wansucong-stoom/stoom-acaflow/issues)
