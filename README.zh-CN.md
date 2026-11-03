# getcheapapi

[English](README.md) | 简体中文

**别再为数据和媒体 API 多付钱。** getcheapapi 是面向 AI Agent 和开发者的开源比价路由：每次调用前给你能用的所有供应商报价，走最便宜的那家，超预算就拒绝。

官网：[getcheapapi.com/zh/](https://getcheapapi.com/zh/)

```text
$ getcheapapi quote keyword.volume --input '{"keywords":["k1","k2","k3","k4","k5"]}'
  goanyapi keyword-search-volume                    $0.01500   x1.0  5 calls   ok
  dataforseo keywords_data/google_ads/search_volume/live  $0.09000   x6.0  1 call    ok
would run: goanyapi keyword-search-volume $0.01500

$ getcheapapi quote keyword.volume --input @50-keywords.json
  dataforseo keywords_data/google_ads/search_volume/live  $0.09000   x1.0  1 call    ok
  goanyapi keyword-search-volume                    $0.15000   x1.7  50 calls  ok
would run: dataforseo keywords_data/google_ads/search_volume/live $0.09000
```

## 为什么

同样的数据，走不同路线，价格能差 2 到 200 倍，而默认路线往往是贵的那条：

- **聚合商会悄悄切到更贵的上游。** AnyAPI 的同一个接口背后有多个来源，价格最高相差 28 倍（X 搜索）甚至 200 倍；便宜的来源失败时，默认重试会按贵的那家计费。
- **看似无害的选项会抬价。** 只有部分来源返回的字段、“live” 模式、搜索运算符（DataForSEO SERP 上贵 5 倍）。
- **各家计费规则都不一样。** 按次、按行、按关键词；空结果有的收费有的免费；有的批量接口 1,000 条只收一次钱。
- **Agent 没有刹车。** 真实的一晚：关键词搜索量拆成 15 次调用而不是 1 次，外链逐个域名去查，还有个脚本在 402 之后又发了 211 次请求。

getcheapapi 把这些经验写成了代码：一份能力目录、一份本地价格缓存，以及每次付费调用上的护栏。

## 它做什么

- **按能力请求，而不是按供应商**：`serp.google`、`x.search`、`keyword.volume`、`image.generate`……每个能力映射到多家供应商的路线，字段映射和批量处理都已做好。
- **给每条路线报价**，数据来自本地缓存（供应商有实时价格接口的用接口，没有的用公开价目表），在你有 Key 的路线里选最便宜的。没有 Key 的路线也会报价，让你看到多一个 Key 能省多少。
- **花钱前用最新价格再核一次**，把 AnyAPI 固定到最便宜的来源并关闭自动切换，同时保存价格基线，最低价突然上涨就停止运行。
- **守住每次运行**：先估价，超过 `--max-usd` 就拒绝；遇到 402（退出码 2）或第一次失败就停；输入去重并批量发送；保存每次响应；每次调用记入本地账本（`getcheapapi spend`）。
- **媒体也支持**：通过 Yir 生成图片、视频和语音，每个任务开始前先报价，并在服务端封顶。

不在范围内：LLM 文本路由（LiteLLM 和 OpenRouter 已经覆盖），以及社交账号上的任何写操作。

## 供应商

| 供应商 | 用途 | 价格来源 |
|---|---|---|
| [AnyAPI](https://getanyapi.com/?via=q89thkytbw) | SERP、X、Reddit、TikTok、Google Trends | 各来源实时价格 |
| [DataForSEO](https://dataforseo.com) | 关键词搜索量与拓词、外链、SERP | 公开价目表 |
| [GoAnyAPI](https://goanyapi.com/r/ga-ccef6a6e4f) | SERP、DR、流量、关键词搜索量、外链 | 公开目录 |
| [twitterapi.io](https://twitterapi.io/?ref=wn7a9fzv) | X 搜索（只读） | 公开价目表 |
| [Yir](https://yir.ai/?utm_source=getcheapapi&utm_medium=readme)（同一团队） | 图片、视频、语音生成 | 实时报价 |

上表部分供应商链接带有我们的推荐码，缺少 Key 时 CLI 也会打印这些链接。它们不影响路由：路线只按价格排序。

## 安装

```bash
pip install git+https://github.com/getcheapapi/getcheapapi   # PyPI 版本即将发布
mkdir -p ~/.getcheapapi && curl -fsSL https://raw.githubusercontent.com/getcheapapi/getcheapapi/main/.env.example -o ~/.getcheapapi/.env
# 在 ~/.getcheapapi/.env 里填上你有的 Key，一个就够
getcheapapi caps -v
```

给 Agent 用（Claude Code、Codex 等）：安装 [`skills/getcheapapi`](skills/getcheapapi/SKILL.md) 里的 Skill，把这个目录链接或复制到 Agent 的 Skill 目录（例如 `~/.claude/skills/getcheapapi`）。从克隆仓库链接过去的话，不安装包也能运行。

## 用法

```bash
getcheapapi caps -v                                   # 能力列表、输入、示例
getcheapapi quote serp.google --input '{"query":"cheap serp api"}'   # 只比价，不花钱
getcheapapi run serp.google --input '{"query":"cheap serp api"}' --max-usd 0.01
getcheapapi run x.search --input '[{"query":"a"},{"query":"b"}]'      # 传列表就作为一批运行
getcheapapi call dataforseo backlinks/summary/live --input '{"target":"example.com"}'  # 原始接口，同样有护栏
getcheapapi prices refresh                            # 更新本地价格缓存
getcheapapi spend --days 7                            # 按供应商和接口查看花费
getcheapapi balance anyapi
```

状态保存在 `~/.getcheapapi/`（可用 `GETCHEAPAPI_HOME` 覆盖）：价格缓存、价格基线、账本、保存的结果。除了 API 调用本身，没有任何数据离开你的机器。

## 参与贡献

价格和接口会变。要新增或修正路线，编辑 `src/getcheapapi/data/catalog.json`，然后：

```bash
python scripts/check_catalog.py   # 对照供应商实时 schema 检查路线字段（免费）
python -m pytest
```

## 披露

getcheapapi 的设计是中立的：路线只按价格排序。Yir 与 getcheapapi 由同一团队运营；表中已标注，并按同样的规则排序。

## 许可证

MIT
