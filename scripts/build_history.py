"""주차장 혼잡도 정보(CSV)에서 계절·요일별 만차 기록 요약을 만든다.

사용: python scripts/build_history.py "<혼잡도 CSV 경로>"
출력: data/history_stats.json

혼잡도 정보는 운영자가 구역 상태를 바꿀 때 남긴 기록이다. 기록이 꾸준히 남은 기간
(ACTIVE_FROM ~ ACTIVE_TO)만 쓰고, 등록시간은 시(hour)만 쓴다(분·초는 원본에서 월·일과 같은 값이다).
'만차 기록일'은 그날 한 구역이라도 만차로 바뀐 날이다.
"""
import csv, json, os, sys
from collections import defaultdict
from datetime import date, timedelta

ACTIVE_FROM, ACTIVE_TO = date(2025, 2, 12), date(2025, 11, 30)
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "history_stats.json")
SEASON = {12: "겨울", 1: "겨울", 2: "겨울", 3: "봄", 4: "봄", 5: "봄", 6: "여름", 7: "여름", 8: "여름", 9: "가을", 10: "가을", 11: "가을"}


def quantile(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(q * (len(xs) - 1))))]


def main(path):
    full = defaultdict(lambda: {"zones": set(), "first": 24})
    with open(path, encoding="cp949", newline="") as f:
        for r in csv.DictReader(f):
            d = date.fromisoformat(r["등록일"])
            if not (ACTIVE_FROM <= d <= ACTIVE_TO) or r["혼잡도"] != "만차":
                continue
            full[d]["zones"].add(r["주차구역"])
            full[d]["first"] = min(full[d]["first"], int(r["등록시간"][:2]))

    groups = defaultdict(lambda: {"days": 0, "full_days": 0, "wide_days": 0, "first": []})
    weekday = {"days": 0, "full_days": 0}
    d = ACTIVE_FROM
    while d <= ACTIVE_TO:
        if d.weekday() >= 5:
            g = groups[f"{SEASON[d.month]}|{'토' if d.weekday() == 5 else '일'}"]
            g["days"] += 1
            if d in full:
                g["full_days"] += 1
                g["wide_days"] += len(full[d]["zones"]) >= 5
                g["first"].append(full[d]["first"])
        else:
            weekday["days"] += 1
            weekday["full_days"] += d in full
        d += timedelta(days=1)

    out = {}
    for k, g in sorted(groups.items()):
        first = g.pop("first")
        if first:
            g["first_full_hour"] = {"q25": quantile(first, .25), "median": quantile(first, .5), "q75": quantile(first, .75)}
        out[k] = g
    payload = {
        "source": "한국체육산업개발(주) 주차장 혼잡도 정보 (공공데이터포털)",
        "period": [ACTIVE_FROM.isoformat(), ACTIVE_TO.isoformat()],
        "weekend": out,
        "weekday": weekday,
    }
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1])
