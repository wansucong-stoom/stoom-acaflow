# 웹용 스킬 배포 파일

[Claude 웹용 스킬 ZIP 다운로드 — 0.2.7](https://github.com/wansucong-stoom/stoom-acaflow/raw/refs/heads/main/downloads/academyinfo-flow-skill-claude-web-0.2.7.zip)

이 파일은 소스 0.2.7의 `scripts/build_plugin.py`로 생성하는 Claude 웹 Skills 업로드용 ZIP입니다. 최상위 `academyinfo-flow/` 아래 `SKILL.md`, `scripts/`, `references/`가 있으며 Codex용 `agents/`와 MCP 설정 파일은 제외됩니다.

계정 설정 도구가 없는 일반 Claude 웹 대화에서는 사용자가 직접 계정 활성 조건을 확인하고 ZIP을 등록한 뒤 스킬 토글을 켭니다. 정확한 메뉴와 조직 조건은 [스킬 추가 안내](../docs/WEB-MCP.md#claude-웹에-스킬을-추가하기)를 따르세요. [Claude 공식 Skills 사용 절차](https://support.claude.com/en/articles/12512180-use-skills-in-claude)

일반 채팅 첨부·ZIP 구조 검수·계정 Skills 등록·활성화·MCP 연결은 별도 상태입니다. **이 ZIP은 전용 커넥터를 자동 등록하지 않습니다.** [웹 MCP 연결 안내](../docs/WEB-MCP.md)에 따라 전용 연결을 등록하고 사용할 대화에서 켜세요.

원격 MCP 조회만 시작하려면 ZIP 업로드 없이 커넥터부터 등록할 수 있습니다. 스킬은 표의 전체 머리글·기간·단위·완전성과 분석 기준을 적용하는 추가 지침입니다. 스킬 활성 조건과 커넥터 조건은 각각 확인합니다.

[개인 폴더 설치·다른 패키지 빌드](../docs/INSTALL.md)
