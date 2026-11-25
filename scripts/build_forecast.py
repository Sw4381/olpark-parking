"""다가오는 날짜의 주차 예보를 만든다. 표준 라이브러리만 쓴다.

입력: data/model.json   (2025년 입출차 원자료에서 만든 조건별 패턴과 당일 보정 계수)
      data/events.json  (올림픽공원 대관정보의 다가오는 공연)
      data/parking_log.csv (실시간 주차현황 수집 기록)
출력: data/forecast.json

예보 값은 동2·남2·북2문 기준 주차 대수다. 실시간 주차현황 API 값은 이보다 일정하게 크게 나오므로
(출차 기록이 없는 차량이 누적된 것으로 추정) 그 차이(live_offset)를 수집 기록에서 추정해 함께 내보낸다.
당일 실측을 반영한 보정은 화면(assets/common.js)이 같은 계수로 계산한다.
"""
import csv, json, os, statistics
from datetime import datetime, timedelta, timezone

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
KST = timezone(timedelta(hours=9))
BIG_CODES = {"01", "02", "03"}
BIG_NAMES = ("올림픽홀", "KSPO", "핸드볼", "라이브 아레나", "체조경기장")
HORIZON = 21
S0 = 12  # 06:00


def load(name):
    with open(os.path.join(ROOT, name), encoding="utf-8") as f:
        return json.load(f)


def hm(i):
    return f"{i // 2:02d}:{'30' if i % 2 else '00'}"


def to_slot(text):
    h, m = text.split(":")
    return int(h) * 2 + int(m) // 30


def main():
    model = load("model.json")
    try:
        events = load("events.json").get("events", [])
    except Exception:
        events = []
    cap, prof, holidays = model["capacity"], model["profiles"], set(model.get("holidays", []))
    thr = 0.9 * cap

    def is_big(e):
        return e.get("venue_code") in BIG_CODES or any(n in (e.get("venue") or "") for n in BIG_NAMES)

    def key_of(date):
        d = datetime.strptime(date, "%Y-%m-%d")
        kd = 6 if date in holidays else d.weekday()
        shows = [e for e in events if e["begin"] <= date <= e["end"]]
        big = int(any(is_big(e) for e in shows))
        k = f"{kd}|{big}"
        return (k if k in prof else str(kd)), big, shows

    # 실시간 값과 예보 기준의 차이. 새벽(01~05시) 기록이 있으면 그것으로, 없으면 낮 기록과 패턴의 차이로 추정한다.
    night, day = [], []
    try:
        with open(os.path.join(ROOT, "parking_log.csv"), encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    except Exception:
        rows = []
    now = datetime.now(KST)
    for r in rows:
        try:
            t = datetime.strptime(r["collected_at_kst"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=KST)
            v = int(r["parking_sum"])
        except Exception:
            continue
        if now - t > timedelta(days=14):
            continue
        s = t.hour * 2 + t.minute // 30
        if 2 <= s < 10:
            night.append(v - model["night_level"])
        else:
            k, _, _ = key_of(t.strftime("%Y-%m-%d"))
            day.append(v - prof[k]["mean"][s])
    if len(night) >= 3:
        offset = {"value": max(0, round(statistics.median(night))), "n": len(night), "method": "새벽 1~5시 수집값과 2025년 같은 시간대 주차 대수의 차이(중앙값)"}
    elif len(day) >= 3:
        offset = {"value": max(0, round(statistics.median(day))), "n": len(day), "method": "수집값과 2025년 같은 요일·시각 패턴의 차이(중앙값)"}
    else:
        offset = {"value": model.get("live_offset_default", 0), "n": 0, "method": "기본값"}

    days = {}
    for i in range(HORIZON):
        date = (now + timedelta(days=i)).strftime("%Y-%m-%d")
        k, big, shows = key_of(date)
        p = prof[k]
        slots = [{"t": hm(s), "n": p["mean"][s], "pct": round(100 * p["mean"][s] / cap), "lo": p["p25"][s], "hi": p["p75"][s]} for s in range(S0, model["slots"])]
        peak_s = max(range(S0, model["slots"]), key=lambda s: p["mean"][s])
        adv = {"peak_n": p["mean"][peak_s], "peak_pct": round(100 * p["mean"][peak_s] / cap), "peak_time": hm(peak_s),
               "n_days": p["n_days"], "full_days": p["full_days"], "cross": p["cross"]}
        if "peak_q25" in p:      # 같은 조건인 날들의 정점이 얼마나 벌어지는지(가운데 절반)
            adv["peak_range_pct"] = [round(100 * p["peak_q25"] / cap), round(100 * p["peak_q75"] / cap)]
        if p["cross"] and p["full_days"] / p["n_days"] >= 0.3:
            adv["full_from"] = p["cross"]["median"]
            adv["arrive_by"] = hm(max(S0, to_slot(p["cross"]["q25"]) - 1))
        days[date] = {"key": k, "big": big, "holiday": date in holidays, "shows": len(shows), "slots": slots, "advice": adv}

    v = model["validation"]
    ew, n13 = v["당일 보정"]["조기경보"], v["당일 보정"]["13시 실측 반영"]
    pri = v["사전 예보"]
    out = {
        "generated_at_kst": now.strftime("%Y-%m-%d %H:%M"),
        "basis": model["target"], "capacity": cap, "full_level": thr, "live_offset": offset,
        "model_period": model["period"], "model_days": model["days"],
        "days": days,
        "accuracy": {
            "text": (f"예보는 2025년 입출차 기록 {model['days']}일로 만들었습니다. 1~8월로 만든 예보를 9~11월 {v['검증 일수']}일에 대어 보면, "
                     f"만차 수준에 이른 {ew['만차 수준에 이른 날']}일 가운데 {ew['도달 전에 경보한 날']}일을 도달 전에 알렸고 중앙값으로 {ew['앞선 시간(시간) 중앙값']:g}시간 앞섰습니다. "
                     f"하루 정점 오차는 사전 예보 {pri['요일·공휴일·대형 공연 패턴']['정점 MAE']:.0f}대, 13시 실측을 반영하면 {n13['정점 MAE']:.0f}대입니다."),
            "validation": v, "validation_cv": model.get("validation_cv"),
        },
    }
    with open(os.path.join(ROOT, "forecast.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print("forecast days", len(days), "offset", offset)


if __name__ == "__main__":
    main()
