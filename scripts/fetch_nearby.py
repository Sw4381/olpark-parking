"""올림픽공원 인근 공영주차장의 실시간 주차 대수를 받아 data/nearby.json 으로 정리한다.

출처: 서울 열린데이터광장 "서울시 시영주차장 실시간 주차대수 정보"(GetParkingInfo).
인증키는 환경변수 SEOUL_API_KEY 로 받는다(GitHub Secrets). 없으면 포털의 공개 시험용 키 'sample'을 쓰는데,
이 키는 한 번에 5건까지만 내주므로 자치구 단위로 나눠 부른다.
공원에서 지하철 한두 정거장 안이고 실시간 연계가 되는 곳만 고른다.
"""
import json, os, sys, urllib.parse, urllib.request
from datetime import datetime, timezone, timedelta

KEY = os.environ.get("SEOUL_API_KEY") or "sample"
BASE = "http://openapi.seoul.go.kr:8088/{key}/json/GetParkingInfo/1/{n}/{gu}"
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "nearby.json")
KST = timezone(timedelta(hours=9))

# 이름에 들어가는 문구 -> 화면에 쓸 이름과 공원까지 가는 길
LOTS = {
    "천호역": ("천호역 공영주차장", "8호선 천호역에서 몽촌토성역까지 두 정거장"),
    "잠실역": ("잠실역 공영주차장", "8호선 잠실역에서 몽촌토성역까지 한 정거장"),
    "신천유수지": ("신천유수지 공영주차장", "송파구 신천동, 잠실역 방면"),
    "잠실나루역": ("잠실나루역 공영주차장", "2호선 잠실나루역 옆"),
}


def fetch(gu):
    url = BASE.format(key=KEY, n=5 if KEY == "sample" else 200, gu=urllib.parse.quote(gu))
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (olpark-collector)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read().decode("utf-8", "replace"))
    body = data.get("GetParkingInfo") or {}
    return body.get("row") or []


def main():
    lots = []
    for gu in ("송파", "강동"):
        for r in fetch(gu):
            name = str(r.get("PKLT_NM") or "")
            hit = next((k for k in LOTS if k in name), None)
            if not hit or str(r.get("PRK_STTS_YN")) != "1":  # 1: 20분 이내 실시간 값이 있는 곳
                continue
            cap, now = int(float(r.get("TPKCT") or 0)), int(float(r.get("NOW_PRK_VHCL_CNT") or 0))
            if cap <= 0:
                continue
            label, way = LOTS[hit]
            lots.append({
                "name": label, "addr": str(r.get("ADDR") or ""), "way": way,
                "capacity": cap, "now": now, "free": max(cap - now, 0),
                "updated_at_kst": str(r.get("NOW_PRK_VHCL_UPDT_TM") or "")[:16],
            })
    if not lots:
        raise RuntimeError("no nearby lots parsed")
    lots.sort(key=lambda x: -x["free"])
    payload = {
        "source": "서울 열린데이터광장 서울시 시영주차장 실시간 주차대수 정보",
        "fetched_at_kst": datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
        "lots": lots,
    }
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    print("nearby lots:", [(x["name"], x["free"]) for x in lots])


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("fetch_nearby failed:", repr(e), file=sys.stderr)
        sys.exit(1)
