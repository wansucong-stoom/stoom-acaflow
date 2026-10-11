# 일괄 조회와 성능 진단

## 실행 원칙

공식 scope/catalog에서 실제 공개연도·기관·항목 ID와 조회 단위를 먼저 확인한다. 학교·학과 코드와 원천 이름도 먼저 식별한다. 숫자 캐시나 과거 내려받은 통계로 새 조회를 대신하지 않는다. `live_batch.py`의 재사용은 한 번의 실행에만 존재하며, 종료하면 메모리의 재사용 자료와 클라이언트를 폐기한다.

같은 `(command, year, division, item, level, max_pages)` 장표는 한 실행에서 한 번 수신한다. 학교·학과 필터와 `limit`·`offset`은 같은 자료의 서로 다른 보기를 만든다. 다른 페이지 제한은 조회 예산을 존중하기 위해 별도 원천 조회로 취급한다. 같은 연도·기관의 검증된 항목 목록도 그 실행 안에서 공유한다. 원천 실패와 부분 결과를 재사용할 때도 해당 오류·부분 상태를 보존한다.

## 일괄 입력

JSON 객체의 `queries` 배열 또는 최상위 배열을 사용한다. 최대 1 MiB, 100개 조회다. `report`, `metric`, `catalog`, `scope`, `schools`, `departments`, `affiliations`, `info`를 지원한다. `attachments`, `pdf`, `guide`는 해당 전용 명령을 사용한다. 알 수 없는 필드, 비공개 전송 옵션, 중복 JSON 키, 잘못된 선택조건은 조회 전에 거절한다.

다음의 꺾쇠 값은 앞선 공식 조회에서 확인한 값으로 채운다. 예시 이름은 실제 원천 명부와 정확히 일치시킨다.

```json
{
  "queries": [
    {"command":"report","year":"<공개연도>","division":"02","item":"<항목ID>","level":"school","school_name":"한남대학교","max_pages":1000,"limit":50},
    {"command":"report","year":"<같은공개연도>","division":"02","item":"<같은항목ID>","level":"school","school_name":"<비교대학의원천이름>","max_pages":1000,"limit":50}
  ]
}
```

```text
python -X utf8 scripts/live_batch.py --input queries.json
python -X utf8 scripts/live_batch.py --input queries.json --full-output
```

`--input -` 또는 생략은 표준입력이다. 입력 경로는 조회 조건만 담으며 통계 캐시가 아니다. 출력의 `results`는 입력 순서와 같다. 일부 성공·부분 결과는 `partial`, 전부 오류면 `error`다. 개별 결과의 `complete`와 `completeness`를 별도로 확인한다. 프로세스 종료코드 0은 전체 결과 완료, 2는 부분·오류다.

`source_complete`는 원천 전체 페이지 수신의 검증 상태이고, `returned_complete`는 필터에 맞는 모든 행을 offset 0부터 반환했는지를 뜻한다. 따라서 정상적으로 다음 범위를 요청해도 `offset > 0`이면 `returned_complete=false`, 사유 `return_range`, 종료코드 2가 나올 수 있다. 이 반환 범위 상태만으로 원천 조회를 재시작하거나 재시도하지 않는다. 페이지 수신·표 검증 실패와 반환 범위 제한을 개별 필드로 구분한다.

단일 장표에 `--school-name` 또는 `--dept-name`을 여러 번 지정할 수도 있다. 한 차원 안의 이름은 OR, 다른 차원은 AND 조건이다. 정확한 학교-학과 쌍의 비교는 별도 `queries` 원소로 나눈다. 필터가 없는 열이나 미해석 표를 정상 학과 자료로 승격하지 않는다.

## 간결한 출력

일괄 조회의 기본값과 `live_report.py report --compact`는 보고서 행의 중복 필드 `keys`, `cells`, `cell_sources`를 생략한다. `values`, `dimensions`, 행 상태, 누락·중복 열 경고, 행 번호, 원천 페이지, 열 정의, 원천 주소·시각·해시, 전체 수신/표 검증/반환 완전성은 유지한다. 세부 셀 좌표를 감사해야 하면 `--full-output` 또는 단독 명령의 기본 전체 출력을 사용한다.

## 시간 필드의 의미

| 명령 | `performance`의 핵심 필드 | 측정 범위 |
|---|---|---|
| report | `stages_seconds.catalog`, `report_initialization`, `generation_wait`, `page_fetch`, `table_parse`, `final_status`, `combine_validation`, `projection`, `output_validation`, `total` | 각 구간의 벽시계 시간. 네트워크 구간에는 요청 간격·재시도가 포함될 수 있다. 수행하지 않은 구간은 생략한다. |
| report | `source_reused`, `fetched_report_pages_this_call`, `source_report_pages` | 현재 질문 보기에서 새 페이지를 가져왔는지와 공유 원천의 페이지 수를 구분한다. 초기화·상태 HTTP 요청 수가 아니다. |
| batch | `stages_seconds.total`, `repeated_report_sources_avoided`, `repeated_json_queries_avoided`, `repeated_queries_avoided` | 한 실행의 전체 처리와 중복 원천 실행을 생략한 횟수. 실제 HTTP 요청 절감 횟수와는 다르다. |
| guide | `stages_seconds.download`, `extraction`, `total`, `fetched_response_count`, `fetched_response_bytes`, `pdf_open_count`, `selected_page_count`, `extracted_page_count` | 새 지침 PDF 수신 및 선택 페이지 추출. 전체 PDF 의미 검증 완료를 뜻하지 않는다. |

report의 `total`은 결과 검증까지이며 JSON 직렬화·모델 답변 작성 시간은 제외한다. 로컬 모의 표 가공 벤치마크를 원천 네트워크를 포함한 실제 응답시간으로 설명하지 않는다. 서버 연결 실패는 서버 장애·학교 데이터 부재·숫자 0의 증거가 아니다.

## 유지하는 검증

각 페이지의 헤더·셀 경계·행 병합·원천 메타데이터 검증을 유지한다. 소수 좌표는 float 근사가 아닌 Decimal로 처리한다. 보고서 첫 페이지 번호, 생성 완료와 최종 페이지 수, 페이지 누락·중복을 확인한다. 표 복원은 원천 응답별로 다시 수행하며, 이전 요청의 표 구조가 다음 요청의 검증을 대신하지 않는다. 같은 실행의 JSON·장표 조회는 익명 클라이언트와 요청 간격 상태를 공유하므로 서로 다른 명령 사이에도 기존 간격이 적용된다. 공식 허용 호스트는 변경하지 않는다.
