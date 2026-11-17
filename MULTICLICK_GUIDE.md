# RustDesk 멀티클릭 (Windows)

이 프로젝트는 한 RustDesk 원격 세션의 마우스 이동·좌우 클릭을
다른 연결된 원격 세션으로 복제하는 **실험용 기능**을 구현합니다.

**중요**: 한 PC에서 실행 중인 로컬 게임 창 여러 개를 동시 조작하는 기능은 아닙니다.

- 화면 오른쪽 아래의 멀티클릭 ON/OFF 버튼으로 선택한 원격 세션을 기준 창으로 설정합니다.
- 기준 세션은 한 번에 하나만 선택되며 RustDesk 재시작 시 OFF입니다.
- 휠/키보드/상대 마우스 모드/트랙패드/터치 동작은 복제하지 않습니다.
- 원격 PC의 화면 크기와 배치가 다르면 클릭 지점이 어긋날 수 있습니다.
- 반드시 허가받은 원격 세션에서만 사용하세요.

## 소스 및 빌드

이 저장소의 GitHub Actions 워크플로는 RustDesk 원본의 **고정된 커밋**을
가져와 scripts/apply_multiclick.py를 적용하고 소스를 현재 저장소의
main 브랜치에 반영한 뒤 Windows x64용 Flutter 클라이언트를 빌드하도록 설계됐습니다.

빌드 성공 시 Actions -> Multi-click Windows build -> 실행 결과 -> Artifacts에서
rustdesk-multiclick-windows-x64 ZIP을 다운로드할 수 있습니다.
EXE 하나가 아니라 DLL 및 관련 리소스를 포함한 폴더 전체를 압축한 결과물입니다.
정식 설치본에 덮어쓰지 말고 별도 폴더에서 테스트하세요.

Windows Flutter 빌드는 시간이 걸리고 대형 네이티브 종속성을 사용합니다.
소스 적용, 컴파일 또는 테스트에 실패한다면 Actions의 실패 로그를 확인하세요.
실제 원격 화면에서의 멀티클릭 동작은 별도로 검증해야 합니다.

원본: https://github.com/rustdesk/rustdesk
공식 빌드 설명: https://rustdesk.com/docs/en/dev/build/
원본 프로젝트의 라이선스 표기를 유지합니다.
