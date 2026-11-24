"""올림픽공원 실시간 주차현황 수집기.
한국체육산업개발(주) 실시간 주차현황 오픈API를 호출해 data/parking_log.csv 에 한 줄씩 누적한다.
"""
import csv, json, os, sys, urllib.request
from datetime import datetime, timezone, timedelta

URL = "https://www.ksponco.or.kr/online/main/parkingorsApi.do?apiKey=PARKING21803504"
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "parking_log.csv")
KST = timezone(timedelta(hours=9))

def main():
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0 (olpark-collector)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read().decode("utf-8", "replace")
    data = json.loads(body)
    value = int(data[0]["parking_sum"])
    now = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
    new = not os.path.exists(OUT)
    with open(OUT, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["collected_at_kst", "parking_sum"])
        w.writerow([now, value])
    print(now, value)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # 수집 실패는 기록만 하고 워크플로는 실패로 표시
        print("collect failed:", repr(e), file=sys.stderr)
        sys.exit(1)
