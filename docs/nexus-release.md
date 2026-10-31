# Nexus API 릴리스 배포

대상: https://www.nexusmods.com/starfield/mods/18396

v0.2.8은 사용자 요청에 따라 GitHub 정식 릴리스 검증 후 Nexus API로 배포합니다.
자동 예약·push 업로드는 사용하지 않습니다. `Publish patcher to Nexus Mods`를
명시적으로 실행하며, 기본 dry_run=true는 다운로드·SHA-256·ZIP만 검사합니다.
실제 업로드는 tag=v0.2.8, dry_run=false로 실행합니다.

저장소 Secret `NEXUSMODS_API_KEY`와 선택적인 Variable `NEXUSMODS_FILE_ID`를
사용합니다. 키를 소스나 로그에 기록하지 않습니다. 활성 파일이 여러 개면 업로드용
File ID를 지정해야 합니다. 같은 버전은 중복 업로드하지 않습니다.

버전은 `8.8.41-KR0.2.8`입니다. 새 ZIP 업로드와 모드 버전 갱신을 함께 수행하고,
기존 버전은 보존합니다. 업로드 후 Nexus 파일 목록과 모드 버전을 API로 재확인합니다.
