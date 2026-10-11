# 라이브 조회와 데이터 해석

## 공식 경로

| 목적 | URL/핵심 조건 | 구조 |
|---|---|---|
| 공개 연도·기관 | POST https://m.academyinfo.go.kr/main/main0780/selectListLink.do, `svyYr`, `schlDivCd` | HTML 선택지. 공식 화면의 30 학교별평균값/36 학과별 분기 확인 |
| 전체 항목 | POST https://m.academyinfo.go.kr/main/main0780/selectItemList.do | `detailItemList`; 연도·기관·실제 ID·계층 제목·학과 여부·PDF 여부 |
| 학교명부 | POST https://m.academyinfo.go.kr/intro/intro0350/selectSchlListAll.do | `resultList`의 `schl_id`, `schl_nm`; 페이지 확인 |
| 소속기관 | POST https://m.academyinfo.go.kr/pubinfo/pubinfo0020/list.do | `collegeList` HTML; 본교와 소속 대학원을 구별 |
| 학과명부 | POST https://m.academyinfo.go.kr/pubinfo/pubinfo1600/selectMjrList.do | `schl_mjr_id`, `mjr_id`, `mjr_nm`; totalRecordCount와 실제 고유행 비교 |
| 주요지표 | POST https://m.academyinfo.go.kr/pubinfo/pubinfo0081/selectFreshStudentRate.do | `svyYr`, `schlId`, `schlMjrId`, `mjrId`, `flag`; `resultList`의 실제 year/val |
| 일반 장표 초기화 | POST https://academyinfo.go.kr/uipnh/unt/unmcom/RdViewer.do | 공개 선택조건 → 메모리 세션; 다운로드 게시판으로 대체하지 않음 |
| 장표 페이지 | 초기화가 반환한 공식 HTTPS URL | 첫 페이지 → 생성상태 → 나머지 전체 페이지 → 최종 상태·수 확인 |
| PDF | POST https://academyinfo.go.kr/file/fileDownPram.do | 실제 첨부 링크의 fileName/filePath/saveName; PDF는 메모리에서 JSON 추출 |

원본 검증 구현은 [stoom-openacainfo](https://github.com/wansucong-stoom/stoom-openacainfo)의 공개 프로토콜 어댑터를 재사용했다. `scripts/vendor/academyinfo_archive`에는 통계 데이터와 저장 모듈이 없으며 필요한 호출·파서 및 MIT LICENSE만 포함한다. 같은 출처 파일 이름의 archive는 원 프로젝트의 모듈명이며 이 스킬은 Archive를 사용하지 않는다.

## 네이티브 학과 지표

| flag | 지표 | 단위 | 원천에서 확인할 기준 |
|---|---|---|---|
| v1 | 신입생 경쟁률 | 대 1 | 당해연도 3월 신입생 |
| v2 | 재학생수 | 명 | 당해연도 4월 1일 |
| v4 | 입학정원 | 명 | 당해연도 신입생 정원 |
| v5 | 학생 1인당 연간 장학금 | 천원 | 전년도 지급; 실제 그래프 연도 별도 |
| v7 | 취업률 | % | 전전년도 8월·전년도 2월 졸업자, 전년도 12월 31일 조사 |
| v8 | 평균 등록금 | 천원 | 등록금 당해연도, 계절학기 수업료 전년도 |

학과 지표 차트의 요청연도와 실제 `year`/`pbnf_bse_yr`를 따로 읽는다. 장표의 취업자 수·분모·종류는 지침으로 검증한다. 모바일 단위를 일반 장표 전체에 적용하지 않는다. legacy v3/v6은 지원 지표로 광고하지 않는다.

`info`는 별도 학과 기본정보의 JSON을 새로 받지만 기본정보 전체 스키마가 검증된 것은 아니다. `schema_verified=false` 상태를 읽으며 `metric`으로 이미 검증한 숫자와 구별한다.

## 범위와 출력

표 데이터는 `rows[].values`, 실제 학교·학과 식별은 `rows[].dimensions`, 의미는 `columns`의 원천 ID·header_path로 전달한다. 코드 없는 표에 이름 유사성으로 코드를 덧붙이지 않는다. 한 행의 의미가 대학·학과·계열·성별·학위·회계·지역 중 무엇인지 열 정의로 확인한다.

일반 장표는 기본 페이지 제한을 넘을 수 있다. `--max-pages`를 필요한 범위로 명시하고, 제한된 결과는 부분 조회로 다룬다. 같은 세션 안에서 최종 생성 페이지 수가 변하면 완료 처리하지 않는다. 반환 `--limit` 및 `--offset`도 전체 원천 수와 구분한다. 숫자 정제 레이아웃 미지원과 원천 데이터 부재는 다르다.

PDF 목록의 요청 순번과 내부 Doc/Page 번호는 다를 수 있다. 검증된 PDF 목록 경로에만 문서 내부 번호 예외를 적용하며 페이지 응답 해시·최종 생성 수로 검증한다. 실제 링크의 원천 페이지·해시·좌표·주변 셀로 대학 소유관계를 확인한다.

원문 0·null·대시·공개제한·미공시 표시는 보존한다. 빈 조회를 통계 0으로 만들지 않는다. Python은 stdout JSON으로 응답하며 이전 결과·숫자 캐시를 읽지 않는다. 원천 접근·변경·레이아웃에 따라 일부 장표 해석이 실패할 수 있다.

0.2.0부터 같은 실행의 여러 질문은 `live_batch.py`로 묶을 수 있다. 같은 장표·페이지 제한을 한 번 새로 받아 학교별·출력 범위별로 나누며, 실행 종료 후에는 재사용하지 않는다. 다중 학교 이름과 간결한 JSON, 단계별 시간의 정확한 의미는 [일괄 조회와 성능 진단](performance.md)을 확인한다.

