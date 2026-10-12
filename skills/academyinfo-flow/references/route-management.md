# 장표별 조회 경로를 누적하고 재사용한다

## 다음 조회의 출발점

`query-routes.json`은 패키지에 포함한 공개 경로의 시작 목록이다. 실제 사용에서 추가되는 상태는 호출자의 작업 폴더 `.academyinfo-flow-state/routes.json`에 보관한다. 다른 위치가 필요하면 `ACADEMYINFO_FLOW_STATE_DIR` 또는 `--state-file`을 사용한다. 여러 대화가 같은 기록을 활용하려면 사용자가 지정한 동일한 영속 작업 폴더를 사용한다. 작업 폴더가 매번 초기화되는 웹 환경은 이 상태 파일을 재사용 가능한 저장소에 보존하고 다음 실행에서 읽어야 누적된다. 설치 경로와 현재 작업 폴더를 혼동하지 않는다.

```text
python -B -X utf8 scripts/route_registry.py lookup --keyword "신입생 충원" --division 02 --level department
python -B -X utf8 scripts/route_registry.py record --input result.json
python -B -X utf8 scripts/route_registry.py learn
```

각 장표는 출처 종류, 이름, 기관, 학교/학과 단위, 실제 확인한 공개 인자, 기간, 검증 단계, 마지막 성공·실패 시각과 근거로 식별한다. 파일 목록에서 확인한 장표와 본문 검증을 끝낸 장표는 다른 상태다. 경로 목록이 오래됐다는 이유만으로 숫자를 최신값이라고 표시하지 않는다. 실제 요청에 해당하는 경로를 확인하는 것으로 충분하며 전체 목록 재검증은 별도 요청 없이는 하지 않는다.

원본 명세는 [GitHub의 query-routes.json](https://github.com/wansucong-stoom/stoom-acaflow/blob/main/skills/academyinfo-flow/references/query-routes.json), 기계 조회 주소는 [raw JSON](https://raw.githubusercontent.com/wansucong-stoom/stoom-acaflow/main/skills/academyinfo-flow/references/query-routes.json)이다. 설치된 시작 목록과 사용자의 영속 상태를 병합해 사용한다. GitHub 게시본 갱신은 소유 저장소의 변경 검증과 승인된 업데이트 절차로 수행하며, 일반 조회가 원격 Git 쓰기 권한을 추가하지 않는다.

## 이미 연결된 공식 파일 아카이브

FLOW의 기존 공개 자료에는 대학알리미 학교별 요약 42종과 학교 개황·교육편제·교육과정이 있다. 2026-10-08 확보판이며 학과별 공시 원자료 40종을 모두 보존했다는 뜻은 아니다. 이 범위는 기록 시점 정보이고 현재 응답을 확인한다.

| 용도 | 연결된 도구 | 공개 HTTP 경로 |
| --- | --- | --- |
| 보존 범위·확인 시각 | `list_disclosure_datasets` | `GET /api/disclosures` |
| 조건 조회 | `query_disclosure_data` | `GET /api/disclosures/query` |
| 확보판·변경 확인 | `list_disclosure_versions` | `GET /api/disclosures/versions` |
| 조건에 맞는 전체 원문값 | — | `GET /exports/disclosures/{datasetId}.json` |

현재 확인한 플랫폼 연결의 기본 주소는 `https://hannam-regulations-wiki.esceeee.chatgpt.site`다. 연결된 도구를 우선 사용하고 주소를 임의로 다른 호스트로 바꾸지 않는다. 독립 호스트로 이전됐다면 실제 목록·해당 장표·기간·출처를 검증한 뒤 기존 경로와 새 경로의 관계를 기록한다. 사이트 주소가 같은 자료인지 도메인 이름만으로 판단하지 않는다.

조회 인자는 `datasetId`, `schoolCode`, `departmentCode`, `schoolType`, `publicationYear`, `referenceYear`, `referencePeriod`, `surveyYear`, `degree`, `unitStatus`, `term`, `detailGroup`, `snapshotId`, `offset`, `limit`다. 학교코드는 문자열로 유지하고 현재 도구 스키마가 허용하는 인자를 사용한다. 전체학교 조회·내보내기의 기본 학교 선택을 확인한다. 교육편제에는 폐지·변경 이력이 있으므로 행수를 현재 학과수로 합산하지 않는다. 현재 학교 개황으로 과거 속성을 덮어쓰지 않는다.

## 공시 추이의 검증된 공통 절차

기존 아카이브 수집에서 성공한 파일 다운로드들은 같은 호출 규칙을 사용한다.

1. `POST https://www.academyinfo.go.kr/main/main0830/selectGongsiDataList.do`에 기관 구분과 검색어를 보내 `resultList`의 실제 파일 메타데이터를 확인한다.
2. 공식 다운로드 이용목적 절차를 수행한다. `POST /popup/main2120/doInsert.do`의 공개 인자와 성공 응답을 확인한다.
3. `POST https://www.academyinfo.go.kr/main/main0830/FileDown.do`에 `schl_div_cd`, `searchValue`, `file_nm`, `file_path`, `file_dtl_nm`, `std_dta_div_cd`를 전송한다. 인자는 실제 목록값을 사용한다.
4. HTTP 상태 외에 첨부파일 유형과 XLSX 구조를 검증한다. 원문 파일을 파싱할 때 열 정의·기간·기관·중복·합계행을 별도로 확인한다. XLSX의 차원 표시가 `A1`뿐이면 내용이 1셀이라고 판단하지 말고 실제 행을 읽는다. openpyxl의 읽기 전용 모드에서는 `reset_dimensions()`가 필요할 수 있다.
5. 실제 수신 시각·원문 지문·장표명·확인 범위로 경로 관측을 기록한다.

`live_files.py`는 위 절차를 표준 라이브러리로 실행한다. 원문을 저장하는 `--output`은 설치 경로 밖의 사용자가 지정한 작업 파일이다. 데이터 분석에 필요한 XLSX 파서는 해당 환경에서 별도로 사용할 수 있다. JSON으로 제공하는 연결된 아카이브를 쓰면 XLSX 파싱 없이 구조화된 값을 받는다.

웹 실행에서도 같은 공개 호출 규칙을 사용한다. 도구·네트워크가 허용되어야 실제 수신이 가능하며, 메타데이터만 읽거나 패키지를 설치한 상태를 조회 성공으로 보고하지 않는다. 실행이 가능한 웹 세션에서 코드가 구조화된 결과를 만들고 LLM은 필요한 열과 요약만 읽는다.

## 검증 단계와 패턴 학습

호출 규칙은 HTTP 방식, 공식 호스트와 경로, 공개 인자 키의 조합으로 묶는다. 장표별 차이는 실제 목록의 항목·파일 식별자, 기관·연도·조회 단위로 유지한다. 파일 이름의 숫자가 연속이라는 이유로 새 파일을 생성하지 않는다. 라이브 장표 초기화 후 생성되는 세션 URL·임시 키는 재사용 경로가 아니므로 기록하지 않는다.

확보 상태의 뜻은 다음과 같다.

- 목록 확인: 항목과 선택자를 찾았으나 본문은 검증하지 않았다.
- 수신·구조 확인: 다운로드/응답을 수신하고 파일 또는 표 구조를 검증했다.
- 본문 확인: 필요한 장표의 열·시간·행 차원과 완전성을 확인했다.
- 부분·실패: 검증을 끝내지 못했다. 마지막 성공 기록은 유지하고 이번 실패를 추가한다.

새 후보는 해당 기관·연도의 공식 목록에 있는 값으로만 만든다. 학습된 공통 규칙이 있다는 사실과 새 장표에 실제로 성공했다는 사실을 구분한다. 다른 기관·연도·학교/학과 단위에 검증 결과를 자동 전파하지 않는다.

저장 대상은 공개 선택조건과 검증 메타데이터다. 통계 행, PDF 본문, 쿠키, 인증키, 원천 SQL, 세션 키·생성 보고서 URL을 경로 목록에 넣지 않는다. 원문 자료와 관측 숫자는 별도의 분석/아카이브 자산이다. 실패·변경으로 기록을 갱신하더라도 기존 성공 경로와 과거 근거를 유지한다.
