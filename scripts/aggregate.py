#!/usr/bin/env python3
"""Aggregate public live-TV playlists into one subscription file.

- Pulls several public, community-maintained m3u sources.
- Dedupes by channel, liveness-checks every stream, drops dead ones.
- Prefers the highest real resolution (probes HLS master playlists).
- Writes live.m3u (players) + live.txt (TVBox style) + STATUS.md.

Stdlib only. Run: python3 scripts/aggregate.py
"""
import concurrent.futures as cf
import json
import re
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

UA = {"User-Agent": "VLC/3.0.20 LibVLC/3.0.20"}

SOURCES = [
    "https://iptv-org.github.io/iptv/countries/cn.m3u",
    "https://iptv-org.github.io/iptv/countries/hk.m3u",
    "https://iptv-org.github.io/iptv/countries/tw.m3u",
    "https://raw.githubusercontent.com/vbskycn/iptv/master/tv/iptv4.m3u",
    "https://raw.githubusercontent.com/YanG-1989/m3u/main/Gather.m3u",
]

CHECK_TIMEOUT = 6
PROBE_TIMEOUT = 5
WORKERS = 60


def fetch_text(url, timeout=15, limit=2_000_000):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(limit).decode("utf-8", "ignore")


ATTR_RE = re.compile(r'(\S+?)="([^"]*)"')


def parse_m3u(text):
    entries = []
    lines = [ln.strip() for ln in text.splitlines()]
    i = 0
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("#EXTINF"):
            attrs = dict(ATTR_RE.findall(ln))
            name = ln.rsplit(",", 1)[-1].strip()
            url = ""
            j = i + 1
            while j < len(lines):
                if lines[j].startswith("#"):
                    j += 1
                    continue
                url = lines[j]
                break
            if url.startswith("http"):
                entries.append({
                    "name": name,
                    "url": url,
                    "group": attrs.get("group-title", "").strip(),
                    "logo": attrs.get("tvg-logo", "").strip(),
                    "tvgid": attrs.get("tvg-id", "").strip(),
                })
            i = j
        i += 1
    return entries


NOISE_RE = re.compile(
    r"[\[\(（【].*?[\]\)）】]|高清|标清|超清|蓝光|\bFHD\b|\bHD\b|\bSD\b|1080p|720p|4k|2160p|[-_\s]+$",
    re.I,
)


def channel_key(name):
    k = NOISE_RE.sub("", name)
    k = re.sub(r"\s+", "", k).upper()
    return k or name.upper()


def hint_score(entry):
    s = (entry["name"] + " " + entry["url"]).lower()
    if "2160" in s or "4k" in s:
        return 4
    if "1080" in s or "fhd" in s:
        return 3
    if "720" in s or "hd" in s:
        return 2
    if "576" in s or "480" in s or "360" in s:
        return 1
    return 0


def check_alive(url):
    try:
        req = urllib.request.Request(url, headers={**UA, "Range": "bytes=0-2047"})
        with urllib.request.urlopen(req, timeout=CHECK_TIMEOUT) as r:
            if r.status not in (200, 206):
                return False
            chunk = r.read(2048)
            return len(chunk) > 0
    except Exception:
        return False


RES_RE = re.compile(r"RESOLUTION=(\d+)x(\d+)")


def probe_height(url):
    if ".m3u8" not in url:
        return 0
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=PROBE_TIMEOUT) as r:
            text = r.read(65536).decode("utf-8", "ignore")
        heights = [int(h) for _, h in RES_RE.findall(text)]
        return max(heights) if heights else 0
    except Exception:
        return 0


def tier_of(height, hint):
    if height >= 1000 or hint >= 4:
        return 4
    if height >= 700 or hint == 3:
        return 3
    if height >= 400 or hint == 2:
        return 2
    if height > 0 or hint == 1:
        return 1
    return 0


GROUP_PRIORITY = ["央视", "CCTV", "卫视", "港澳台", "香港", "台湾", "澳门"]


def group_rank(group):
    for i, kw in enumerate(GROUP_PRIORITY):
        if kw.lower() in group.lower():
            return i
    return len(GROUP_PRIORITY)


def main():
    started = time.time()
    all_entries = []
    source_stats = {}
    for src in SOURCES:
        try:
            text = fetch_text(src)
            ents = parse_m3u(text)
            source_stats[src] = len(ents)
            all_entries.extend(ents)
            print(f"[source] {src} -> {len(ents)} entries", flush=True)
        except Exception as e:
            source_stats[src] = f"FAILED: {e}"
            print(f"[source] {src} FAILED: {e}", flush=True)

    seen_url = set()
    uniq = []
    for e in all_entries:
        if e["url"] in seen_url:
            continue
        seen_url.add(e["url"])
        uniq.append(e)
    print(f"[dedupe] {len(all_entries)} -> {len(uniq)} unique urls", flush=True)

    with cf.ThreadPoolExecutor(max_workers=WORKERS) as ex:
        results = list(ex.map(lambda e: check_alive(e["url"]), uniq))
    alive_entries = [e for e, ok in zip(uniq, results) if ok]
    print(f"[check] alive {len(alive_entries)} / {len(uniq)}", flush=True)

    with cf.ThreadPoolExecutor(max_workers=WORKERS) as ex:
        heights = list(ex.map(lambda e: probe_height(e["url"]), alive_entries))
    for e, h in zip(alive_entries, heights):
        e["height"] = h
        e["tier"] = tier_of(h, hint_score(e))

    best = {}
    for e in alive_entries:
        key = channel_key(e["name"])
        cur = best.get(key)
        if cur is None or (e["tier"], e["height"]) > (cur["tier"], cur["height"]):
            best[key] = e
    channels = sorted(
        best.values(),
        key=lambda e: (group_rank(e["group"]), e["group"], e["name"]),
    )
    print(f"[channels] {len(channels)} channels kept", flush=True)

    now = datetime.now(timezone(timedelta(hours=8)))
    header = f'#EXTM3U x-tvg-url="" generated="{now.strftime("%Y-%m-%d %H:%M")} CST"'
    lines = [header]
    txt_lines = []
    last_group = None
    for e in channels:
        group = e["group"] or "其他"
        attrs = []
        if e["tvgid"]:
            attrs.append(f'tvg-id="{e["tvgid"]}"')
        if e["logo"]:
            attrs.append(f'tvg-logo="{e["logo"]}"')
        attrs.append(f'group-title="{group}"')
        lines.append(f'#EXTINF:-1 {" ".join(attrs)},{e["name"]}')
        lines.append(e["url"])
        if group != last_group:
            txt_lines.append(f"{group},#genre#")
            last_group = group
        txt_lines.append(f'{e["name"]},{e["url"]}')

    with open("live.m3u", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    with open("live.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(txt_lines) + "\n")

    hd = sum(1 for e in channels if e["tier"] >= 3)
    status = [
        "# 订阅状态",
        "",
        f"- 更新时间：{now.strftime('%Y-%m-%d %H:%M')} (北京时间)",
        f"- 源条目：{len(all_entries)}，去重后 {len(uniq)}，存活 {len(alive_entries)}",
        f"- 最终频道：{len(channels)} 个，其中高清（720p+）{hd} 个",
        f"- 本轮耗时：{time.time() - started:.0f} 秒",
        "",
        "## 来源",
    ]
    for src, n in source_stats.items():
        status.append(f"- {src} -> {n}")
    with open("STATUS.md", "w", encoding="utf-8") as f:
        f.write("\n".join(status) + "\n")
    print("[done]", json.dumps({"channels": len(channels), "hd": hd}))


if __name__ == "__main__":
    sys.exit(main())
