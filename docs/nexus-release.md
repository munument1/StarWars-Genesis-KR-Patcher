# 넥서스 자동 릴리즈 배포

대상: https://www.nexusmods.com/starfield/mods/18396

## 최초 설정

1. GitHub 저장소 Settings → Secrets and variables → Actions → Secrets에
   `NEXUSMODS_API_KEY`를 등록합니다. 모드 업로드 권한이 있는 넥서스 계정의 API 키를 사용합니다.
2. 이 워크플로를 기본 브랜치에 반영합니다.
3. Actions → Publish patcher to Nexus Mods → Run workflow에서 tag를 지정하고
   기본값인 dry_run=true로 실행하여 다운로드·SHA256·ZIP 검사를 확인합니다.
4. 실제 배포가 필요하면 dry_run=false로 실행합니다.

API 키 발급/확인: https://www.nexusmods.com/users/myaccount?tab=api

메인 파일이 하나인 현재 구조에서는 API를 통해 업로드용 File ID를 자동으로 찾습니다.
파일이 여러 개로 늘어나면 Variables에 `NEXUSMODS_FILE_ID`를 설정하세요.
이 ID는 Manage Files/Advanced에 표시되는 업로드 API File ID이며,
다운로드 링크의 게임별 file_id와는 다를 수 있습니다. 설정한 ID가 해당 모드의
활성 파일에 속하는지도 업로드 전에 확인합니다.

## 자동 실행

- 사람이 발행한 정식 GitHub 릴리즈는 release/published 이벤트로 배포합니다.
- `Build verified v0.2.4 assets`를 수동 실행해 검사·EXE 빌드·ZIP 검증을 통과하면
  새 v0.2.4 GitHub 릴리즈가 생성됩니다. 이미 해당 릴리즈가 있으면 덮어쓰지 않고 실패합니다.
  성공한 빌드의 workflow_run 이벤트로 자동 배포할 수 있습니다.
  이 경로에서는 해당 빌드 실행 중 최신 정식 릴리즈의 자산이 생성된 경우에만 배포합니다.
  GITHUB_TOKEN으로 만든 릴리즈가 다른 release 워크플로를 발생시키지 않는 상황을 처리합니다.
- draft/prerelease는 배포하지 않습니다. 업로드는 저장소별로 직렬 실행합니다.
- 현재 배포 연결은 `v0.2.4`만 처리합니다. 과거 릴리즈를 잘못 8.8.4로 등록하지 않습니다.
- Nexus의 활성 버전에 같은 버전 번호가 있으면 업로드를 생략합니다.
  같은 태그의 파일을 교체해도 다시 배포하지 않으므로, 새 배포에는 새 버전 태그를 사용하세요.
- 릴리즈 파일명과 체크섬 이름은 기존 패키징 규칙을 따릅니다.
  규칙이 달라지면 Select published patcher release의 이름을 수정하세요.
- 이전 버전을 자동 보관하지 않습니다. 패쳐는 직접 실행하는 도구이므로
  새 버전의 모드 매니저 다운로드는 비활성화합니다.
- 파일 설명에 GitHub 릴리즈 링크를 넣습니다. GitHub Markdown 변경 내역을
  Nexus BBCode로 자동 변환하거나 모드 본문을 수정하지 않습니다.

## 버전과 기존 빌드의 범위

넥서스 버전은 `8.8.4-KR` + GitHub 태그에서 v를 제거한 값입니다.
제네시스 상위 모드 버전이 바뀌면 워크플로의 버전 접두사도 바꾸세요.
새 버전 릴리즈를 만들 때는 빌드 워크플로의 태그와 파일명, 패처의 버전 검사,
매니페스트의 `target_version` 및 `version`을 함께 갱신해야 합니다.
현재 이미 올려 둔 버전은 중복 방지 검사에 따라 건너뜁니다.
API 키가 없으면 실제 업로드와 인증 API 검증은 수행할 수 없습니다.
