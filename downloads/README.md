# 웹용 스킬 배포 파일

[Claude 웹용 스킬 ZIP 다운로드 — 0.2.6](https://github.com/wansucong-stoom/stoom-acaflow/raw/refs/heads/main/downloads/academyinfo-flow-skill-claude-web-0.2.6.zip)

이 파일은 공개 소스 0.2.6의 `scripts/build_plugin.py`로 생성한 Claude 웹 Skills 업로드용 ZIP입니다. 최상위 `academyinfo-flow/` 아래 `SKILL.md`, `scripts/`, `references/`가 있으며 Codex용 `agents/`와 MCP 설정 파일은 제외됩니다. CRC와 원본 파일 일치를 확인했습니다.

Claude의 **Customize → Skills**에 그대로 업로드합니다. 일반 채팅 첨부나 GitHub 소스 ZIP 업로드와 구분하세요. **이 ZIP은 전용 커넥터를 자동 등록하지 않습니다.** [웹 MCP 연결 안내](../docs/WEB-MCP.md)에 따라 연결을 먼저 등록하고 사용할 대화에서 켜세요.

원격 MCP 조회만 시작하려면 ZIP 업로드 없이 커넥터부터 등록할 수 있습니다. 스킬은 표의 전체 머리글·기간·단위·완전성과 분석 기준을 적용하는 추가 지침입니다. 스킬 활성 조건과 커넥터 조건은 각각 확인합니다.

[개인 폴더 설치·다른 패키지 빌드](../docs/INSTALL.md)
