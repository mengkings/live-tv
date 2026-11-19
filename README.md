# live-tv

个人电视直播订阅：多源聚合 → 逐条验活 → 死链剔除 → 同频道只留最高清的一条。
GitHub Actions 每 6 小时自动重跑，地址永久不变。

## 订阅地址（国内优先用 CDN 这条）

- CDN（推荐，国内可直连）：https://cdn.jsdelivr.net/gh/mengkings/live-tv@main/live.m3u
- GitHub 原始：https://raw.githubusercontent.com/mengkings/live-tv/main/live.m3u
- TVBox 格式（CDN）：https://cdn.jsdelivr.net/gh/mengkings/live-tv@main/live.txt

把 CDN 那条填进播放器（TiviMate / OTT Navigator / 影视仓 / Kodi 等）的订阅/播放列表地址即可。

## 说明

- 来源为公开维护的公益列表（iptv-org 等），本仓库只做聚合、验活与排序，不存储任何视频内容。
- 验活在境外节点完成，个别源有地区限制时可能误判；每 6 小时复检，死链最迟下一轮剔除。
- 清晰度按 HLS 主播放列表的真实分辨率排序，同频道保留最高的一条。
