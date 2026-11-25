"""PC에서 10분마다 돌리는 수집기(윈도우 작업 스케줄러용).

GitHub Actions의 예약 실행이 10분 주기를 지키지 못할 때 같은 일을 PC에서 한다.
수집 전용으로 따로 받아 둔 저장소 사본에서 실행한다(작업 중인 사본과 섞이지 않게).
  1) 원격 변경을 받아 온다  2) 실시간 주차현황·인근 주차장·예보를 갱신한다  3) 바뀐 데이터만 커밋해 올린다
기록은 .git/local_collect.log 에 남는다. 창을 띄우지 않으려면 pythonw 로 실행한다.
"""
import os, subprocess, sys, time
from datetime import datetime

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
LOG = os.path.join(ROOT, ".git", "local_collect.log")
LOCK = os.path.join(ROOT, ".git", "local_collect.lock")
FILES = ["data/parking_log.csv", "data/nearby.json", "data/forecast.json"]
ENV = dict(os.environ, GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never", PYTHONIOENCODING="utf-8")
NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)
PY = sys.executable.replace("pythonw.exe", "python.exe")


def log(msg):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n")


def run(*cmd, timeout=120):
    p = subprocess.run(cmd, cwd=ROOT, env=ENV, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=timeout, creationflags=NOWIN)
    return p.returncode, (p.stdout + p.stderr).strip().replace("\n", " | ")[-300:]


def main():
    if os.path.exists(LOCK) and time.time() - os.path.getmtime(LOCK) < 480:
        return log("skip: previous run still going")
    open(LOCK, "w").close()
    try:
        code, out = run("git", "pull", "--rebase", "--autostash")
        if code:
            log("pull failed: " + out)
        code, out = run(PY, "scripts/collect.py")
        if code:
            return log("collect failed: " + out)
        value = out
        for script in ("scripts/fetch_nearby.py", "scripts/build_forecast.py"):
            c, o = run(PY, script)
            if c:
                log(f"{script} failed: {o}")
        run("git", "add", *FILES)
        if run("git", "diff", "--cached", "--quiet")[0] == 0:
            return log("no change")
        run("git", "-c", "user.name=olpark-bot", "-c", "user.email=olpark-bot@users.noreply.github.com",
            "commit", "-m", "data: parking snapshot (local)")
        for _ in range(4):
            if run("git", "pull", "--rebase")[0] == 0 and run("git", "push")[0] == 0:
                return log("ok " + value)
            time.sleep(8)
        log("push failed")
    except Exception as e:
        log("error " + repr(e)[:200])
    finally:
        try:
            os.remove(LOCK)
        except OSError:
            pass


if __name__ == "__main__":
    main()
