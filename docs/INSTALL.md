# 설치와 실행

스킬·플러그인 버전과 CLI 패키지 버전은 **0.3.2**입니다. 원격 MCP는 별도 호스팅 서비스이며 소스 설치가 서버 배포를 바꾸지는 않습니다. [웹 연결](WEB-MCP.md) · [배포 파일](../downloads/README.md) · [검증 기록](VERIFICATION.md)

## 설치 방식 선택

| 목적 | 설치 방식 |
| --- | --- |
| 웹에서 공식 수치 조회 | 계정에서 전용 MCP 연결을 추가하고 사용할 대화에서 활성화. 사용자 Python 설치 불필요 |
| Codex·Claude Code에 조회·분석 지침 추가 | 개인 스킬 설치기 또는 해당 클라이언트의 플러그인 설치 |
| 터미널에서 JSON 조회·저장 | Python CLI를 저장소 또는 제공된 wheel에서 설치 |
| Claude 웹에 지침 추가 | 단독 Claude 웹 Skills ZIP 업로드. MCP 연결은 별도 |

개인 스킬·플러그인을 같은 클라이언트에 중복 설치하지 않습니다. 기존 소스 폴더나 설치본을 삭제·초기화하지 말고 경로와 변경 내용을 먼저 확인합니다.

## 개인 스킬 설치

Python 3.11 이상과 파일·명령 실행 권한이 있는 환경에서 저장소를 받습니다. Windows에서는 `python` 대신 `py -3.11` 또는 호스트가 제공한 Python 경로를 사용할 수 있습니다.

```sh
git clone https://github.com/wansucong-stoom/stoom-acaflow.git
cd stoom-acaflow
python -B -X utf8 install.py --client codex
python -B -X utf8 install.py --client codex --check
```

Claude Code는 다음을 사용합니다.

```sh
python -B -X utf8 install.py --client claude-code
python -B -X utf8 install.py --client claude-code --check
```

| 클라이언트 | 기본 개인 스킬 경로 | 호출 |
| --- | --- | --- |
| Codex | `~/.agents/skills/academyinfo-flow` | `@대학알리미FLOW` 또는 `$academyinfo-flow` |
| Claude Code | `~/.claude/skills/academyinfo-flow` | `/academyinfo-flow` 또는 자연어 |

두 환경 모두 요청한 경우 `--client both`를 사용합니다. `--client` 생략 시 설치기가 한 클라이언트만 식별할 수 없으면 대상을 선택하게 합니다. `--check`의 `ok=true`는 현재 소스와 설치 파일의 일치이며 클라이언트 로딩·원천 접속 성공을 뜻하지 않습니다.

`--dest`는 스킬의 **상위 폴더**입니다. 설치기가 그 아래 `academyinfo-flow/`를 붙입니다.

```sh
python -B -X utf8 install.py --client codex --dest /path/to/skills
python -B -X utf8 install.py --client codex --dest /path/to/skills --check
```

두 클라이언트의 별도 경로에는 `--codex-dest`·`--claude-dest`를 사용합니다. 같은 경로나 포함 관계의 대상은 허용하지 않습니다. 구형 `~/.codex/skills/academyinfo-flow`가 있으면 중복 방지를 위해 기본 설치가 중단될 수 있습니다. 실제 클라이언트가 사용하는 기존 경로를 확인하고 필요한 경우 `--dest`로 명시합니다. 관리형 플러그인 캐시는 직접 수정하지 않습니다.

## 업데이트와 백업

기존 설치 내용이 같으면 그대로 둡니다. 다른 내용이 있으면 변경을 검토한 뒤 `--update`로 갱신합니다.

```sh
git pull --ff-only
python -B -X utf8 install.py --client codex --update
python -B -X utf8 install.py --client codex --check
```

기존 스킬 전체를 탐색 경로 밖의 백업으로 옮긴 뒤 새 파일을 설치합니다. 백업 위치는 JSON의 `backup`으로 확인합니다. 기본 백업은 `~/.agents/skill-backups/` 또는 `~/.claude/skill-backups/`에 있습니다. 설치기는 개인 MCP 설정·hooks·패키지 의존성을 변경하지 않으며 네트워크 조회를 수행하지 않습니다.

## Claude Code 플러그인

개인 스킬 설치 대신 네이티브 플러그인을 선택할 수 있습니다.

```sh
claude plugin marketplace add wansucong-stoom/stoom-acaflow
claude plugin install academyinfo-flow@stoom-acaflow
claude plugin list
```

플러그인 이름공간을 쓰는 호출은 `/academyinfo-flow:academyinfo-flow`입니다. 호환 manifest는 함께 제공하는 `.mcp.json`을 가리키며, 실제 도구 로딩과 원천 응답은 따로 확인합니다. 현재 클라이언트의 명령·권한은 [Claude Code 공식 플러그인 문서](https://code.claude.com/docs/en/plugins)를 따릅니다.

## Python CLI 설치

저장소 루트에서 가상환경 등 원하는 Python 환경에 설치합니다.

```sh
python -m pip install .
academyinfo-live --version
academyinfo-live doctor
academyinfo-live scope
```

설치된 명령을 찾지 못하면 같은 Python으로 `python -m academyinfo_live scope`를 사용합니다. PyPI에 게시됐다고 가정해 패키지 이름만으로 설치하지 않습니다. wheel 파일을 받은 경우에는 확인한 실제 파일 경로를 `python -m pip install <wheel-경로>`에 지정합니다. Python PDF 파싱이 필요할 때만 소스에서 `python -m pip install ".[pdf]"`를 선택합니다.

`doctor`는 기본 오프라인 점검입니다. `doctor --check-source`는 공식 공개 연도 조회까지, `doctor --require-pdf`는 선택 PDF 의존성까지 확인합니다. 실제 조회에는 실행 환경에서 공식 원천에 접근할 수 있어야 합니다. MCP가 이미 가용한 호스트에 Python 점검을 강제하지 않습니다.

설치 없이 저장소의 `python -B -X utf8 skills/academyinfo-flow/scripts/academyinfo_live.py <명령>`을 실행할 수도 있습니다. 스킬 디렉터리에서는 `scripts/academyinfo_live.py`를 사용합니다.

| 명령 | 기능 |
| --- | --- |
| `scope`, `catalog` | 현재 공개 연도·기관과 공시 항목 |
| `schools`, `affiliations`, `departments` | 학교·소속·학과 명부 |
| `metric`, `info` | 지원되는 학과 주요지표·기본정보 |
| `report` | 검증한 학교별·학과별 수치 장표 |
| `attachments`, `pdf`, `guide` | 첨부 목록·지정 PDF·공시지침의 확인 범위 |
| `batch` | 같은 요청의 조회 조건 JSON을 묶어 실행 |

`report --item 7-가`처럼 공시코드를 쓰면 이번 공식 catalog에서 유일한 실제 ID로 연결합니다. 복수·미등록 후보는 임의 선택하지 않습니다. 지원되는 인수는 해당 명령의 `--help`를 확인합니다.

```sh
academyinfo-live report --year 2026 --division 02 --item 7-가 --level department --dept-keyword 수학 --dept-keyword 수리 --max-pages 1000 --limit 10000 --progress --output math.json
```

`--dept-name`은 정확한 이름, 반복 `--dept-keyword`는 학과명 포함어의 OR 검색입니다. 서로 다른 학교의 특정 학과 쌍은 batch의 개별 질문으로 구분합니다. 문자열 일치 뒤 후보 학과명을 검토하며 의미상 모든 관련 학과를 찾았다고 확대하지 않습니다.

## 학교 한 곳의 학과 장표

학교 상세 조회는 `report --level department`에서만 지원합니다. 먼저 현재 공식 명부에서 학교의 정확한 이름·7자리 코드·기관구분을 확인합니다.

```sh
academyinfo-live schools --year 2026 --name 한남대학교
```

아래 `<명부의7자리코드>`를 실제 응답으로 바꿉니다. 같은 요청의 명부를 재사용하고 다른 학교의 코드를 만들거나 추측하지 않습니다.

```sh
academyinfo-live report --year 2026 --division 02 --item 7-가 --level department --school-code <명부의7자리코드> --school-name 한남대학교 --dept-name 수학과 --max-pages 32 --limit 1000 --output hannam-math.json
```

이 인수는 공식 학교 상세 양식 **60**을 선택합니다. 일반 전국 학과 양식 36에 학교코드만 더하는 방식이 아닙니다. 정확한 학교명 하나와 코드·기관구분 일치를 확인합니다. 실제 표에는 대학원·학교 합계·이전 소속 행도 포함될 수 있으므로 학교·학과 열로 다시 필터하고 단과대학·기준연도를 보존합니다. 원격 MCP에는 현재 이 코드 인수가 없습니다.

## 출력과 완전성

`--output <경로.json>`은 JSON 전체를 저장하고 stdout에 저장 요약을 반환합니다. 부모 폴더가 없으면 생성하며 기존 파일은 `--force` 없이 덮어쓰지 않습니다. `--progress`는 stderr의 JSON Lines 진행 이벤트, `--full-output`은 장표의 중복 셀 상세를 포함하는 선택입니다.

종료 코드는 `0` 완료, `2` 오류, `3` 부분 결과, `130` 사용자 중단입니다. 종료 코드와 JSON의 `status`·`complete`·경고를 함께 확인합니다. 출력은 JSON이며 Excel 직접 저장·실행 후 세션 재개 기능은 제공하지 않습니다.

전국 장표는 생성 완료·최종 페이지 수와 전체 페이지 수신·표 검증을 모두 확인합니다. `limit`·`offset`은 반환 범위이며 수신량을 줄이지 않습니다. [복구·제한 대응](../skills/academyinfo-flow/references/report-recovery.md)에 따라 초기화 실패, 전체 요청 시간, 페이지 상한과 반환 제한을 구분합니다.

## 패키지 형식

| 파일 | 용도·구조 |
| --- | --- |
| `academyinfo-flow-plugin-0.3.2.zip` | 스킬·호환 manifest·MCP 연결 설정을 포함한 플러그인 |
| `academyinfo-flow-skill-codex-0.3.2.zip` | 단일 `academyinfo-flow/` 스킬 폴더, Codex UI 메타데이터 포함 |
| `academyinfo-flow-skill-claude-web-0.3.2.zip` | 단일 `academyinfo-flow/` 스킬 폴더, Codex `agents/` 제외 |
| `academyinfo_flow_cli-0.3.2-*.whl` | `academyinfo-live`·`python -m academyinfo_live`용 Python 패키지 |

단독 스킬 ZIP에는 MCP 등록 설정·루트 설치기가 없습니다. 압축을 푼 `academyinfo-flow/`를 스킬 상위 폴더에 두거나 웹 Skills에 올립니다. GitHub 전체 소스 ZIP·플러그인 ZIP과 구분합니다. 현재 파일·해시는 [downloads](../downloads/README.md), 실제 검증은 [검증 기록](VERIFICATION.md)에서 확인합니다.
