"""올림픽공원 누리집 "주차장 예상 이용률 서비스"의 공개 예상값을 기록한다.

누리집이 주말분으로 게시하는 30분 단위 예상 이용률을 그대로 적어 두었다가,
같은 시각의 실측 주차 대수(data/parking_log.csv)와 나중에 비교하기 위한 것이다.
data/official_forecast_log.csv 에 (기록 시각, 대상 시각, 예상 이용률, 수용 대수)를 누적한다.
같은 대상 시각에 같은 값이 이미 마지막으로 기록돼 있으면 다시 적지 않는다.
"""
import csv, os, re, sys, urllib.parse, urllib.request
from datetime import datetime, timezone, timedelta

URL = "https://www.ksponco.or.kr/online/main/parking.do"
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "official_forecast_log.csv")
KST = timezone(timedelta(hours=9))
HEAD = ["snapshot_at_kst", "target_at_kst", "forecast_pct", "capacity"]


def get(date=None):
    data = urllib.parse.urlencode({"selectdate": date}).encode() if date else None
    req = urllib.request.Request(URL, data=data, headers={"User-Agent": "Mozilla/5.0 (olpark-collector)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def parse(html):
    cap = re.search(r"/\s*([\d,]+)\s*대\s*가능", html)
    cap = int(cap.group(1).replace(",", "")) if cap else ""
    rows = re.findall(
        r"<th>\s*(\d{4}-\d{2}-\d{2})(?:&nbsp;|\s)+(\d{2}:\d{2}):\d{2}\s*</th>.*?<td[^>]*>\s*(\d+)\s*%\s*</td>",
        html, re.S)
    return cap, [(f"{d} {t}", int(p)) for d, t, p in rows]


def main():
    first = get()
    dates = re.findall(r'<option value="(\d{4}-\d{2}-\d{2})"', first)
    found = {}
    cap = ""
    for i, d in enumerate(dates or [None]):
        html = first if i == 0 else get(d)
        c, rows = parse(html)
        cap = c or cap
        for target, pct in rows:
            found[target] = pct
    if not found:
        print("no forecast rows on page (평일에는 게시되지 않을 수 있음)")
        return

    last = {}
    if os.path.exists(OUT):
        with open(OUT, encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                last[r["target_at_kst"]] = r["forecast_pct"]
    now = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
    new_rows = [[now, t, p, cap] for t, p in sorted(found.items()) if last.get(t) != str(p)]
    if not new_rows:
        print("official forecast unchanged:", len(found))
        return
    is_new = not os.path.exists(OUT)
    with open(OUT, "a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if is_new:
            w.writerow(HEAD)
        w.writerows(new_rows)
    print("official forecast rows added:", len(new_rows))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("snapshot failed:", repr(e), file=sys.stderr)
        sys.exit(1)
