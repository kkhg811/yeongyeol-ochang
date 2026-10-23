# 연결한의원 청주오창 홈페이지

레퍼런스(연결한의원 아산탕정, https://www.yeongyeolkmc.co.kr/)의 구성·디자인을 따라 만든 청주오창점 정적 홈페이지입니다.
사진은 전부 청주오창점 자체 자료(`assets/`)만 사용했습니다.

## 폴더 구조

```
assets/      원본 사진·로고·포스터 (구글드라이브에서 받은 원본, 배포하지 않음)
docs/        ★ 배포용 결과물 (이 폴더 통째로 호스팅에 올리면 됩니다)
  ├ index.html, about.html, location.html, faq.html, philosophy.html, privacy-policy.html
  ├ services/   진료 안내 7개  (공진단·다이어트·추나·교통사고·성장보약·체질개선·산후보약)
  ├ conditions/ 질환 정보 14개
  ├ column/     건강 칼럼 5개
  ├ css/style.css, js/main.js, images/, sitemap.xml, robots.txt
src/         콘텐츠 데이터 (파이썬 dict) — 문구·이력·FAQ·진료시간 수정은 여기서
templates/   페이지 레이아웃 (Jinja2)
tools/       이미지 최적화 스크립트
build.py     HTML 생성기
serve.py     로컬 미리보기 서버
```

## 미리보기

```
python serve.py        # http://localhost:8791 로 브라우저가 열립니다
```

## 수정 방법

1. 문구·진료시간·원장 이력·FAQ 등 → `src/site_info.py`, `src/services.py`, `src/conditions.py`, `src/columns.py`
2. 레이아웃 → `templates/*.html`, 스타일 → `docs/css/style.css`
3. 사진을 바꾸면 `assets/`에 넣고 `tools/build_images.py`의 매핑을 수정한 뒤 실행
4. 마지막에 `python build.py` 실행 → `docs/` 갱신

빌드 시 검색용 `docs/search-index.json`과 기존 로고를 사용한 정사각형 파비콘도 생성합니다. 검색 데이터는 검색창을 사용할 때 불러오며, 모든 검색 결과 링크는 사이트 루트를 기준으로 연결합니다.

공식 사이트명은 `SITE["seo_site_name"]`, 검색결과용 페이지 제목은 `SITE["title"]`로 구분합니다. 구조화된 정보에는 한의원 대표 URL과 각 페이지의 URL을 구분해 기록합니다.

필요 패키지: `pip install jinja2 pillow`

## 연동 링크 (src/site_info.py)

- 네이버 플레이스: https://naver.me/x3HRxoCc
- 네이버 예약: https://m.booking.naver.com/booking/13/bizes/1554365
- 카카오톡 채널: https://pf.kakao.com/_Xkzxgn (연결한의원-청주오창)
- 대표전화: 043-715-3688

## 배포

### 1~80번 질환 가이드 보완 (2026-10-22)

189개 모바일 검색 점검표의 순서와 대표 검색어를 `src/content/priority80.json`에 보존했습니다. 이 80개 주제에는 관찰 체크, 증상별 구분표, 검사·기록 해석과 관련 질문을 추가합니다. 체크를 진단 점수로 사용하거나 저장·전송하지 않으며, 독립된 응급진료 안내 섹션은 추가하지 않습니다. 의료진 검수는 여전히 미확인으로 관리합니다. 기존 조건/칼럼/상세 URL과 이미 상위 노출된 주제의 제목은 보존합니다.

검증: `python tools/compile_clinical_catalog.py`, 기존 이미지 렌더러, `python build.py`, `python tools/check_clinical_guides.py`, `python tools/check_priority_guides.py`, `python -m unittest discover -s tests -v`. 새 사이트와는 원고·라우팅·호스팅을 별도로 유지하며 이 사이트는 진찰에서 구분할 점과 검사 결과의 해석을 중심으로 구성합니다. 실제 배포가 확인된 canonical URL만 `tools/notify_indexnow.py`로 알리며, 요청 접수가 색인·순위·캐러셀을 보장하지 않습니다.

`docs/` 폴더 안의 파일을 그대로 웹호스팅(카페24·가비아·Netlify·Vercel·GitHub Pages 등)에 업로드하면 됩니다.
도메인은 `src/site_info.py`의 `url` 값(현재 https://www.yeongyeolochangkmc.co.kr)을 기준으로 canonical·sitemap이 생성됩니다.

## 변경 페이지를 네이버에 알리기 (IndexNow)

네이버 계정 로그인 없이 공식 IndexNow API로 실제 변경 페이지를 알릴 수 있습니다.
소유 확인용 텍스트 파일은 `docs/`에 포함되며 `tools/indexnow.json`이 해당 파일을 가리킵니다.
이 파일은 빌드 시 지워지지 않으므로 배포 결과에 함께 포함해 주세요.

변경한 HTML을 빌드한 뒤, 먼저 전송 없이 설정과 대표 주소를 검사합니다.

```sh
python tools/notify_indexnow.py --dry-run --files docs/index.html docs/guide/ochang-clinic.html
```

운영 사이트 배포가 성공한 뒤에만 실제 알림을 실행합니다.

```sh
python tools/notify_indexnow.py --submit --files docs/index.html docs/guide/ochang-clinic.html
```

실제 알림 전에 운영 사이트의 소유 확인 파일과 페이지 제목·본문·링크가 로컬 수정본과
일치하는지 확인합니다. 이전 내용이 남아 있으면 전송하지 않습니다.
HTTP 200은 알림 전송 성공, 202는 수신 후 소유 확인 중이라는 뜻입니다.
색인 완료나 검색 순위 상승을 뜻하지는 않습니다. 과거의 모든 URL을 일괄 제출하지 말고
도입 이후 실제로 변경한 페이지만 지정하세요. 실패 시 자동 반복 전송은 하지 않습니다.

공식 안내: https://searchadvisor.naver.com/guide/indexnow-about

## 주제별 개정 1차: 발목 염좌 (2026-10-22)

KMC의 발목 염좌 한 주제만 개정했습니다. 기존 대표 URL·상세 6개·관련 칼럼 URL과 여섯 이미지 파일을 보존하면서 상세 글에 주제별 설명과 직접 답변 FAQ를 추가했습니다. 선택 필드 `reading_sections`, `faq`, `page_metadata`는 출처를 선언한 경우에만 사용하며, 나머지 186개 프로필과 HTML은 바꾸지 않습니다. 체크리스트와 증상 구분표, 독립된 응급진료 섹션 제외 및 의료진 검수 미확인 상태를 유지합니다. 새 사이트의 같은 주제는 비교 기준으로 유지합니다.

검사와 다음 주제는 `verification/ankle-refinement-20261022.json`에 기록했습니다. 붙여 쓴 검색어와 띄어 쓴 검색어를 구분하며, 배포나 구현 상태를 검색 1위·캐러셀 달성으로 대신 기록하지 않습니다.

## 삐끗한 뒤의 진찰 준비 안내 (2026-10-23)

`src/content/patient-scenarios.json`에서 오창 발목 삐끗(`/guide/ochang-ankle-twist`)과 오창 허리 삐끗(기존 `/conditions/허리-삐끗` 주소 유지)의 독립 원고를 관리합니다. 다친 계기만으로 염좌가 확정되지 않음을 설명하며, 기존 염좌 시리즈의 여섯 질문과 설명 도식에 연결합니다. 이미지는 실제 관련 주제의 기존 파일을 유지합니다. 전체 목록·관련 시리즈·사이트맵·사이트 내 검색에서 새 글로 이동할 수 있습니다.

`python build.py`, `python tools/check_patient_scenarios.py`와 기존 질환·우선 주제 검사를 실행합니다. 공개 상태·근거·FAQ 누락을 검사하고 초안은 운영에서 제외합니다. 의료진 검수는 미확인이며 독립된 응급진료 섹션을 추가하지 않습니다. 새 사이트는 별도 원고·라우팅·배포를 사용합니다.

## 기존 8개 주제 개정 (2026-10-23)

추나요법·무릎관절염·요통·협착증·충돌증후군·테니스엘보·고관절통증·골반통증의 기존 허브 8개와 상세 48개를 개정했습니다. URL과 실제 관련 주제의 여섯 이미지 파일은 유지하며, 주제별 설명과 직접 답변 FAQ·관찰 체크·증상 구분 도표를 제공합니다. 협착증의 범위는 요추, 충돌증후군의 범위는 어깨로 표시합니다. 기존 상위 노출 제목은 유지하고 허위 의료진 검수나 순위 달성 기록을 추가하지 않습니다.

원고는 `src/content/clinical-profiles/msk.json`에 있으며 `python tools/compile_clinical_catalog.py` 후 `python build.py`로 생성합니다. 개별 개정일과 우선80개 작업일 중 실제 최근 날짜를 사용합니다. `python tools/check_eight_topics.py`가 개정 56개·이미지·카드 순서·메타데이터·FAQ·사이트맵과 다른 프로필의 보존을 검사합니다. 기존 질환·우선80개·삐끗 안내 검사도 유지합니다.

검증 결과는 `verification/eight-topics-20261023.json`에 기록하며 배포 상태와 네이버 수집·색인·웹문서 1위·캐러셀 노출 확인은 구분합니다. 독립된 응급진료 안내 섹션을 추가하지 않습니다.
