# 올림픽공원 주차 예보

한국체육산업개발(주) 공공데이터를 활용한 공연일 주차 혼잡 예보 서비스 (2026년도 공공데이터 활용 경진대회 출품작, 개발 중).

- `scripts/collect.py` : 실시간 주차현황 오픈API를 10분마다 수집 (GitHub Actions)
- `data/parking_log.csv` : 수집 누적 데이터
- `index.html` : 서비스 화면 (GitHub Pages)
