# Star Wars Genesis 8.8.41 텍스트 변경 검수

8.8.4 기준 정식 번역과 8.8.41 실물 ESM/STRINGS의 영어 원문을 대조한 결과입니다.

- `translation_candidates.csv`: 기존 패처가 다루던 필드 기준 269행(신규 143, 변경 47, 재인덱싱 79). `reindexed_unchanged`는 다시 번역할 항목이 아닙니다.
- `translation_decisions.json`: 안전하게 반영한 187개 필드와 한국어 번역, 기존 사전 재사용 또는 검수 근거.
- `pending_manual_review.json`: 개발용/내부 항목으로 판단해 원문 유지한 3개.
- `validation_report.json`: 기존 151개 텍스트 레시피의 완전 재생성·검증 집계.

마스터 레코드 식별값이 확실하지 않은 기존 유우잔 봉 INFO 52건과 장비 2건은 임의로 다른 레코드에 치환하지 않았습니다. SWF·PEX·BA2 속의 모든 표시 문구를 검수했다는 의미는 아닙니다.

자세한 설치·HUD·버전 호환성과 검증 범위는 [8.8.41 상태 문서](../../docs/genesis-8.8.41-status.md)를 참조하세요.
