# 배포 파일

현재 배포 버전은 **0.3.2**입니다. 같은 소스에서 만든 다음 네 파일 중 사용하는 환경에 맞는 파일을 선택하세요. 저장소의 소스 ZIP은 Claude Skills 업로드용 파일과 다릅니다.

| 파일 | 용도 |
| --- | --- |
| [Claude 웹 스킬 ZIP](academyinfo-flow-skill-claude-web-0.3.2.zip) | Claude의 Skills에 그대로 업로드 |
| [Codex 개인 스킬 ZIP](academyinfo-flow-skill-codex-0.3.2.zip) | 압축을 풀어 개인 스킬 상위 폴더에 설치 |
| [플러그인 ZIP](academyinfo-flow-plugin-0.3.2.zip) | 스킬·MCP 연결 설정·CLI 빌드 소스를 함께 제공 |
| [Python CLI wheel](academyinfo_flow_cli-0.3.2-py3-none-any.whl) | Python 3.11 이상에서 `academyinfo-live` 설치 |

단독 스킬 ZIP은 최상위 `academyinfo-flow/` 아래에 `SKILL.md`, `scripts/`, `references/`가 있습니다. Codex판만 `agents/`를 포함합니다. 두 단독 스킬 ZIP에는 MCP 등록 설정이 없으므로 [웹 연결 안내](../docs/WEB-MCP.md)에 따라 전용 연결을 별도로 등록·활성화하세요.

플러그인 ZIP에는 공통 `mcp.json`과 Codex·Claude Code 호환 `.mcp.json`이 포함됩니다. 파일을 받은 것, 계정에 설치한 것, 대화에서 도구가 제공되는 것과 실제 원천 조회 성공은 각각 확인합니다.

CLI wheel을 내려받았다면 다음처럼 설치할 수 있습니다. PyPI 게시를 전제로 한 명령이 아닙니다.

```sh
python -m pip install ./academyinfo_flow_cli-0.3.2-py3-none-any.whl
academyinfo-live --version
academyinfo-live doctor
```

`doctor`는 기본 오프라인 점검입니다. 실제 공식 서버 연결을 확인하려면 `doctor --check-source`를 명시합니다. [CLI와 개인 스킬 설치](../docs/INSTALL.md)

## 파일 검증

[SHA256SUMS](SHA256SUMS)는 현재 파일과 이전 호환 파일의 SHA-256을 기록합니다. Linux·macOS에서는 해당 파일들이 있는 폴더에서 `sha256sum -c SHA256SUMS`, Windows PowerShell에서는 `Get-FileHash -Algorithm SHA256 <파일>`로 확인할 수 있습니다.

세 ZIP은 빌더 결과를 원본 파일 목록·바이트와 대조합니다. wheel은 원본 Python·참조 파일을 확인한 뒤 별도 폴더에 설치해 오프라인 CLI를 실행합니다. [검증 기록](../docs/VERIFICATION.md) · [변경 이력](../CHANGELOG.md)

이 패키지에는 대학별 통계 관측값·수집 DB·인증키·지침 PDF 전문이 없습니다. 원격 MCP 서버의 코드·배포와 개인 계정의 스킬 설치 상태는 이 배포 파일과 별개입니다.

## 이전 호환 파일

기존 링크를 유지하기 위해 [0.2.8](academyinfo-flow-skill-claude-web-0.2.8.zip), [0.2.7](academyinfo-flow-skill-claude-web-0.2.7.zip), [0.2.6](academyinfo-flow-skill-claude-web-0.2.6.zip) Claude 웹 ZIP을 보존합니다. 신규 설치에는 현재 버전을 사용하세요.
