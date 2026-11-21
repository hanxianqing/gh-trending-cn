# GitHub 每日热门中文站 | gh-trending-cn

每天早上自动拉取 GitHub Trending，翻译成中文，做成一个干净的中文榜单站。

**在线站点：https://gh-trending-cn.pages.dev/**

## 有什么

- **每日 Top 15**：每天早上从 GitHub Trending 真实拉取，不是过期数据。
- **周榜、月榜**：按周、按月看热门项目。
- **语言分榜**：Python、JavaScript、TypeScript、Rust、Go 各一个榜。
- **中国开发者榜**：只收中国作者的项目。
- **中文简介**：每个项目一段中文简介，1 分钟扫完整个榜。
- **逐日归档**：可以回看任意一天的榜单。

## 怎么用

```bash
# 拉取今日榜单
python3 fetch_trending.py
# 生成静态站（输出到 site/）
python3 build_site.py
```

定时刷新见 `refresh.sh`（每天跑一次即可）。部署到任意静态托管（Cloudflare Pages、GitHub Pages、Vercel）都能用。

## 今天榜首长什么样（2026-11-21）

1. **Claude-BugHunter**（+1,622 星）—— Claude Code 捉虫技能包
2. **superpowers**（+890 星）—— Agent 技能框架
3. **minimind**（+847 星）—— 两小时从 0 训出 64M 大模型

看得出来，Agent 技能和小模型训练是现在开发者最关注的方向。

## 赞助

站点底部有赞助位，欢迎你的项目来置顶一天。详见站内 /advertise/。

## License

MIT
