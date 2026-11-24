"""올림픽공원 공연·행사 일정 수집기.

공공데이터포털 "한국체육산업개발주식회사_올림픽공원 대관정보"(15015212, LINK형, 이용허락범위 제한 없음)가
가리키는 올림픽공원 누리집 일정안내의 월별 목록을 받아 data/events.json 으로 정리한다.
이번 달부터 MONTHS_AHEAD 개월 뒤까지를 받는다.
"""
import json, os, re, sys, urllib.request
from datetime import datetime, timezone, timedelta

URL = "https://www.ksponco.or.kr/olympicpark/eventInfo/eventInfoListAjax.es"
VIEW = "https://www.ksponco.or.kr/olympicpark/eventInfo/eventInfoView.es?mid=a20301010100&evtSeq={}"
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "events.json")
KST = timezone(timedelta(hours=9))
MONTHS_AHEAD = 3

# 누리집 일정안내 화면의 장소 코드
VENUES = {
    "01": "올림픽홀",
    "02": "KSPO DOME",
    "03": "티켓링크 라이브 아레나",
    "04": "우리금융아트홀",
    "05": "K-아트홀",
    "06": "옥외·기타",
    "07": "뮤즈라이브",
}


def fetch_month(ym):
    body = json.dumps({"nowYM": ym, "plcCd": ""}).encode("utf-8")
    req = urllib.request.Request(URL, data=body, headers={
        "User-Agent": "Mozilla/5.0 (olpark-collector)",
        "Content-Type": "application/json;charset=UTF-8",
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read().decode("utf-8", "replace"))
    # 응답은 [진행·예정 목록, 지난 목록] 두 묶음이다.
    return [it for part in data if isinstance(part, list) for it in part]


def clean(s):
    return re.sub(r"\s+", " ", str(s or "")).strip()


def main():
    now = datetime.now(KST)
    months = []
    y, m = now.year, now.month
    for _ in range(MONTHS_AHEAD + 1):
        months.append(f"{y}{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)

    events = {}
    for ym in months:
        for it in fetch_month(ym):
            seq = it.get("evtSeq")
            begin, end = clean(it.get("beginDt")), clean(it.get("endDt"))
            if seq is None or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", begin) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", end):
                continue
            code = clean(it.get("plcCd"))
            events[seq] = {
                "id": seq,
                "title": clean(it.get("title")),
                "venue_code": code,
                "venue": VENUES.get(code) or clean(it.get("plc")),
                "begin": begin,
                "end": end,
                "time_text": clean(it.get("tm")),
                "duration_text": clean(it.get("ndTm")),
                "url": VIEW.format(seq),
            }

    today = now.strftime("%Y-%m-%d")
    rows = sorted((e for e in events.values() if e["end"] >= today), key=lambda e: (e["begin"], e["end"], e["id"]))
    if not rows:
        raise RuntimeError("no upcoming events parsed")

    payload = {
        "source": "한국체육산업개발(주) 올림픽공원 대관정보 (공공데이터포털 15015212)",
        "months": months,
        "events": rows,
    }
    # 내용이 그대로면 파일을 건드리지 않아 불필요한 커밋을 만들지 않는다.
    old = None
    if os.path.exists(OUT):
        with open(OUT, encoding="utf-8") as f:
            try:
                old = json.load(f)
            except ValueError:
                old = None
    if old and {k: old.get(k) for k in payload} == payload:
        print("events unchanged:", len(rows))
        return
    payload["fetched_at_kst"] = now.strftime("%Y-%m-%d %H:%M:%S")
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    print("events written:", len(rows))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("fetch_events failed:", repr(e), file=sys.stderr)
        sys.exit(1)
