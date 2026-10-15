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

`docs/` 폴더 안의 파일을 그대로 웹호스팅(카페24·가비아·Netlify·Vercel·GitHub Pages 등)에 업로드하면 됩니다.
도메인은 `src/site_info.py`의 `url` 값(현재 https://www.yeongyeolochangkmc.co.kr)을 기준으로 canonical·sitemap이 생성됩니다.
