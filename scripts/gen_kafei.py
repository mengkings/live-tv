#!/usr/bin/env python3
"""
咖啡直播 (kafeizhibo.cc) 订阅源生成器
原理: 该站没有静态 m3u 订阅, 每场比赛的流地址由后端 API 动态下发.
  - 直播列表: GET https://kafeizhibo.cc/api/v1/archor
  - 单房间信号: GET https://kafeizhibo.cc/api/v1/room/{room_id}
  - 赛程(含未开赛): GET https://kafeizhibo.cc/api/v1/schedule?type=all&page=1&size=100&platform=pc
流地址规律:
  - 中文解说(直播N): https://hello.ooo0ooo.top/live/{nami_id}.m3u8  (无token, 跟比赛走, 每场一换)
  - 原声(原声N): https://pul-tenm.gkykp.com/live/...{nami_id}.m3u8?txSecret=...&txTime=... (带时效token, 必须实时取)
用法: python3 gen_kafei.py  -> 生成 kafei.m3u / kafei.txt / kafei.json
建议: 看前跑一次, 或挂定时任务每 5-10 分钟刷新 (原声token会过期).
"""
import json, urllib.request, pathlib, datetime

BASE = "https://kafeizhibo.cc"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Referer": BASE + "/pc"}
OUT = pathlib.Path(__file__).parent.parent

def get(path):
    req = urllib.request.Request(BASE + path, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))

def main():
    archor = get("/api/v1/archor").get("data", [])
    # 只保留有流地址的; live 优先, upcoming 次之
    items = [a for a in archor if a.get("stream_url")]
    items.sort(key=lambda a: (0 if a.get("status") == "live" else 1, -(a.get("heat") or 0)))

    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    m3u = ["#EXTM3U x-tvg-url=\"\"", f"# 咖啡直播 动态订阅 生成于 {now} 共{len(items)}路"]
    txt = []
    for a in items:
        league = a.get("league_name") or "体育"
        title = a.get("title") or f"{a.get('home_team','')} vs {a.get('away_team','')}"
        name = a.get("name", "")
        status = "直播中" if a.get("status") == "live" else "未开赛"
        group = f"咖啡直播·{league}"
        display = f"{title} [{name}·{status}]"
        url = a["stream_url"]
        logo = ""
        mi = a.get("match_info") or {}
        # 用截图作台标图
        shot = a.get("screenshot") or ""
        if shot:
            logo = BASE + shot.split("?")[0] if shot.startswith("/") else shot
        m3u.append(f'#EXTINF:-1 tvg-logo="{logo}" group-title="{group}",{display}')
        m3u.append("#EXTVLCOPT:http-referrer=https://kafeizhibo.cc/")
        m3u.append("#EXTVLCOPT:http-user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
        m3u.append(url)
        txt.append(f"{display},{url}")

    (OUT / "kafei.m3u").write_text("\n".join(m3u) + "\n", encoding="utf-8")
    (OUT / "kafei.txt").write_text("\n".join(txt) + "\n", encoding="utf-8")
    (OUT / "kafei.json").write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK: {len(items)} streams -> kafei.m3u / .txt / .json")
    for a in items:
        print(f"  [{a.get('status')}] {a.get('title')} | {a.get('name')} | {a['stream_url'][:80]}")

if __name__ == "__main__":
    main()
