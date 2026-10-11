# stoom-acaflow

대학알리미를 LLM에서 이용하기 위한 **대학알리미FLOW** 스킬/플러그인 원본입니다.

공식 서버를 새로 조회하고, 학교·학과·공시 항목을 식별한 뒤 연도별 지침과 함께 해석합니다. Python 3.11 이상과 공식 원천에 접속할 수 있는 실행 환경이 필요합니다. 통계 관측값·인증키·이전 요청의 응답 캐시는 포함하지 않습니다.

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

```bash
python -X utf8 skills/academyinfo-flow/scripts/live_json.py scope
python -X utf8 skills/academyinfo-flow/scripts/live_batch.py --input queries.json
python -X utf8 skills/academyinfo-flow/scripts/live_batch.py --input queries.json --full-output
```

조회조건 JSON에는 먼저 공식 목록으로 확인한 연도·항목 ID·학교/학과 식별자를 넣습니다. 지원 명령·입력 예시·반환 상태·측정 구간은 [실행 지침](skills/academyinfo-flow/SKILL.md)과 [일괄 조회 명세](skills/academyinfo-flow/references/performance.md)를 참조하세요.

## 검증과 패키지 만들기

```bash
python -m unittest discover -s tests -v
python scripts/build_plugin.py
```

두 번째 명령은 `dist/academyinfo-flow-0.2.0.zip`을 만듭니다. 루트와 호환용 매니페스트, 스킬과 실행 파일만 포함하며 테스트·실행 캐시는 제외합니다. 플러그인 이름, 기존 기본 프롬프트, 작성자, 로컬 실행 요구조건은 설치본에서 보존했습니다.

이전 설치본은 Git 이력의 `Import installed academyinfo-flow 0.1.0 source` 커밋에 보존했습니다. 해당 버전을 다른 경로에 체크아웃한 다음 다음 명령으로 표 복원 출력과 시간을 비교할 수 있습니다.

```bash
python tests/parser_benchmark.py --baseline /path/to/previous-release
```

테스트는 모의 HTTP/PDF 응답과 합성 표를 사용하며, 공공 서버의 전수 조회를 실행하지 않습니다. 측정 결과와 한계는 [성능 검증 기록](docs/performance.md)에 정리했습니다.

## 원천과 라이선스

공식 데이터 원천은 [대학알리미](https://www.academyinfo.go.kr/)입니다. 번들 공개 프로토콜 어댑터는 [stoom-openacainfo](https://github.com/wansucong-stoom/stoom-openacainfo)에서 가져왔으며 MIT 저작권 고지를 유지합니다. 최적화 내역은 이 저장소에서 관리합니다. 통계의 기준기간·단위·산식은 해당 공시연도 지침과 원천 열을 확인해야 합니다.
