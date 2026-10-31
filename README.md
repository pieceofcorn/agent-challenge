# SEU-Pulse

SEU-Pulse 是面向东南大学校园信息的主动式信息管理 Agent 项目。当前进入**第二阶段：单 Agent 信息理解与智能决策**，处于开发准备阶段；主动管理是项目定位，当前没有主动推送或完整个人事项管理功能。

第一阶段已实现并验收 Python 采集、统一通知模型、SQLite 持久化、增量去重、服务层查询和 CLI。网页直接采集列表和正文为主，RSSHub 和静态列表适配器保留，可混合采集。默认来源为教务处国际交流和吴健雄学院通知公告；原始 HTML、正文及去重的历史验收证据见 [第一阶段报告](docs/phase1-report.md)，完整任务与网络诊断记录见 [tasks.md](tasks.md)。

第二阶段将增加通知结构化理解、按需调用只读工具的单 Agent 执行循环、分析结果持久化及规则基线评估，先完成任务 2.1 的设计审查。当前未实现 Information Agent、模型 API 接入、Tool Calling 或 NoticeAnalysis；下面的安装和命令说明均对应已有第一阶段能力，没有可运行的 Agent 命令。

## 文档导航

| 文件 | 职责 |
| --- | --- |
| [AGENTS.md](AGENTS.md) | 项目执行规则 |
| [README.md](README.md) | 项目介绍、安装与运行说明 |
| [require.md](require.md) | 分阶段需求与验收标准 |
| [agent.md](agent.md) | 数据模型与接口契约 |
| [tasks.md](tasks.md) | 开发任务与进度，顶部为第二阶段、后部保留第一阶段历史 |
| [docs/phase1-report.md](docs/phase1-report.md) | 第一阶段实际交付与历史验收报告 |
| [docs/phase2-report.md](docs/phase2-report.md) | 第二阶段开发过程与交付报告，当前尚未实施 |

## 第二阶段开发准备

整体数据流：校园信息采集 → SQLite 通知数据库 → Information Agent → 工具调用与信息补充 → 结构化分析结果 → 数据校验与持久化。

| 任务 | 计划能力 | 实施状态 |
| --- | --- | --- |
| 2.1 通知结构化理解 | 分类、重要性、用户相关性、行动需求、时间地点和理由；程序计算紧迫性 | 尚未实施，先进行最小架构与输出 Schema 审查 |
| 2.2 最小 Tool Calling | get_notice_detail、get_user_preferences 与按需执行循环 | 尚未实施 |
| 2.3 结果持久化与评估 | NoticeAnalysis、SQLite 持久化、10～15 条真实通知与规则基线比较 | 尚未实施 |

模型 API、框架及 Schema 校验库尚未在受检代码中实现或验证，不把 Pydantic AI 等候选写成已选型方案。技术选型与设计边界见 [第二阶段需求](require.md#第二阶段需求单-agent-信息理解与智能决策)和[待确认的分析契约](agent.md#第二阶段扩展说明)。持续进度仅在 tasks.md 维护，本表用于区分规划与现有可运行能力。

## 安装与运行

在 Ubuntu 服务器的仓库根目录执行，Python 3.10 及以上可用，建议使用 Python 3.11 及以上。复用仓库已有的 urllib HTTP 客户端和 HTMLParser，完成 HTTPX + BeautifulSoup 的等效列表与正文采集，避免新增重复网络栈；Python 3.10 额外依赖 `tomli`，Python 3.11 及以上使用标准库 `tomllib`。

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
seu-pulse --help
seu-pulse fetch
seu-pulse list --limit 10
seu-pulse runs --limit 10
```

首次安装通常需要能访问 Python 包索引，以获取构建工具或 `tomli`。早期网络受限时，本环境通过现有 setuptools、wheel 和系统 pip 自带的 tomli 1.0.3 构建本地 wheel，在独立虚拟环境完成安装，依赖检查通过。临时复用仅用于本地验证，未将 pip 内部导入或复制依赖加入项目代码。生成的 wheel 在 `data/wheels/`，不纳入 Git。在当前工作区可复验安装：

```bash
python3 -m venv /tmp/seu-pulse-review
/tmp/seu-pulse-review/bin/python -m pip install --no-index --find-links data/wheels seu-pulse
/tmp/seu-pulse-review/bin/python -m pip check
/tmp/seu-pulse-review/bin/seu-pulse --help
```

联网环境中的常规安装不需要这些临时 wheel。

## CLI

所有子命令均输出 JSON，错误摘要写入标准错误；`--config` 放在子命令之前。将下例 `NOTICE_ID` 替换为 `list` 返回的真实 ID。

```bash
seu-pulse --config config.toml fetch --source jwc-international --source wjx-notices
seu-pulse list --source jwc-international --since '2026-10-01T00:00:00+08:00' --limit 20 --offset 0
seu-pulse get NOTICE_ID
seu-pulse get NOTICE_ID --content-only
seu-pulse export --output data/notices.json
seu-pulse export --source radio-academic --since '2026-10-01T00:00:00Z'
seu-pulse runs --limit 20
# 网页直采与已有 RSSHub 可在同一轮并用
seu-pulse fetch --source jwc-international --source cse-notices
```

`fetch` 返回运行 ID、起止时间、逐源状态与读取/新增/更新/未变数量、错误类别及摘要，还包含成功、失败及跳过来源的总数。无条目的有效 RSS/Atom 订阅是 `success` 且读取为 0；请求失败为 `failed`；采集间隔未到为 `skipped`。失败也会计入采集间隔，避免反复请求故障来源。`runs` 展示最近逐源记录，包括跳过记录。

退出码：0 表示命令成功（包括按间隔跳过），1 表示至少一个来源采集失败，2 表示参数、配置或服务级存储/文件错误，3 表示按 ID 查询无记录。`get` 无记录同时输出 `null`。不存在正文的已有通知，`--content-only` 返回对象且 `content=null`。

## 配置

来源放在独立的 [config.toml](config.toml)，可复制到已忽略的 `config.local.toml` 自行修改。数据库相对路径按配置文件所在目录解析；查询不触发联网请求。默认只启用两个重点网页来源，已有三个 RSSHub 来源及研究生院列表来源默认关闭；可修改 enabled 或通过显式 `--source` 使用。接入 RSSHub 时 `app.rsshub_base_url` 可改为自部署地址，例如 `http://127.0.0.1:1200`，保留各来源 `route` 即可。仅配置网页来源时无需 RSSHub 地址。项目不部署 RSSHub，也不需要代理、SSH 接入或远程采集服务。

每个来源配置 `id`、`name`、`url`、`collector`、`enabled`、`category`、`timeout`、`retries`、`interval_seconds` 和 `request_interval_seconds`；RSSHub 来源还需 `route`。超时单位为秒，重试范围 0 至 3，默认最多请求两次；重试只适用于网络故障与部分暂时性 HTTP 错误。客户端限制单个响应为 5 MiB，遵守 robots.txt 并按主机控制请求间隔。

`collector="webplus"` 获取列表及本站正文，`max_items` 限制单次最多处理的通知数（默认 20，上限 100）；`content_classes` 指定已实测的正文容器类名 `wp_articlecontent`、`Article_Content`。`list_container_id` 与 `list_container_class` 可限定栏目列表；教务处实际使用 ID `wp_news_w8`，吴院使用类名 `col_news_list`，避免混入页头轮播的其他栏目通知。配置的列表容器未匹配时会报错，不退回整页搜索。`collector="html"` 保持旧版只采集列表的行为；`collector="rsshub"` 保持原订阅采集方式。

列表请求失败会令来源失败；列表可读但个别正文失败时，保留通知并在 `metadata.detail_status` 和 `metadata.detail_error` 记录原因，`content=null` 或保留之前有效正文。正文恢复后清除旧正文错误。来源 `success` 表示列表采集完成，不代表每篇正文均成功，正文验收需查看元数据或采样报告。

`fetch` 不传 `--source` 时只访问已启用来源；显式 `--source` 可验证尚未启用的已配置来源，仍遵守采集间隔。未知 ID、未知采集器、重复 ID、非法字段或数值显式报错。配置的网址不接受凭据、查询参数和片段，不应放置任何秘密信息。

## 来源核查表

核查日期为 2026 年 10 月 20 日，北京时间。状态区分“实测可用”“仅源码确认”“未验证”“验证失败”。“仅源码确认”仅说明官方源码定义了该路由，不表示公开 RSSHub 实例能正常返回数据；网络故障不用于判断路由不存在。

| 候选来源 | 官方网址或栏目 | 路由与方式 | 验证状态及原因 |
| --- | --- | --- | --- |
| 教务处国际交流 | https://jwc.seu.edu.cn/gjjl/list.psp | WebPlus 列表与正文直采，默认启用 | 实测可用：原始 HTML 含 14 条本站通知及日期，已核对两篇文本正文；部分条目受访问控制限制 |
| 吴健雄学院通知公告 | https://wjx.seu.edu.cn/tzgg/list.htm | WebPlus 列表与正文直采，默认启用 | 实测可用：原始 HTML 含 14 条通知及日期，已核对两篇文本正文；部分为微信跳转、访问限制或 PDF |
| 计算机科学与工程学院通知公告 | https://cse.seu.edu.cn/22536/list.htm | RSSHub `/seu/cse/tzgg`，默认关闭、可选启用 | 路由仅源码确认；前轮本地联网验证失败，连接受限 |
| 研究生招生网硕士招生 | https://yzb.seu.edu.cn/6676/list.htm | RSSHub `/seu/yzb/6676`，默认关闭、可选启用 | 路由仅源码确认；前轮本地联网验证失败，连接受限 |
| 信息科学与工程学院学术活动 | https://radio.seu.edu.cn/_s29/15986/list.psp | RSSHub `/seu/radio/academic`，默认关闭、可选启用 | 路由仅源码确认；前轮本地联网验证失败，连接受限 |
| 研究生院全部公告 | https://seugs.seu.edu.cn/26671/list.htm | 静态 HTML，默认关闭，可显式选择验证 | 联网工具可读栏目列表；本地采集验证失败，原始 HTML 解析效果未验证 |

官方源码依据：[计算机学院](https://github.com/DIYgod/RSSHub/blob/master/lib/routes/seu/cse/index.ts)、[研招网](https://github.com/DIYgod/RSSHub/blob/master/lib/routes/seu/yzb/index.ts)、[信息学院学术活动](https://github.com/DIYgod/RSSHub/blob/master/lib/routes/seu/radio/academic.ts)。这些路由的源码均未要求 Puppeteer。计算机学院源码给出栏目参数 `xyxw/tzgg/jwxx/jyxx/xgsw`；研招网给出 `6676/6677/6679`，本项目只配置所需栏目。

已尝试访问 [RSSHub 官方文档](https://docs.rsshub.app/routes/university)及其 `routes.json`；访问失败，文档核对仍待复验。源码由联网工具返回，检索结果可能有缓存，恢复网络后应再次核对当前上游文件。未预设或访问未经确认的 `/seu/yjs` 等路由。

研究生院全部公告与上述已确认 RSSHub 栏目的内容范围不同，因此提供静态补充适配器；未确认它有对应路由，不能据此断言 RSSHub 缺少该路由。适配器只识别同主机 WebPlus 文章链接，从相邻列表行提取原始日期，正文保持 `null`，不抓取附件或登录数据。默认只采集列表当前页，服务中的历史记录持续保留；不进行全站历史回溯。

原始 HTML 证据在 `data/final-source-inspection/`：教务处 [剑桥项目通知](https://jwc.seu.edu.cn/2026/1013/c21682a585896/page.htm)和[圣芭芭拉项目通知](https://jwc.seu.edu.cn/2026/1012/c21682a585706/page.htm)分别提取到 4518、1723 字符正文；吴院 [二次选拔拟录取公示](https://wjx.seu.edu.cn/2026/0906/c24015a581761/page.htm)和[综合成绩公示](https://wjx.seu.edu.cn/2026/0905/c24015a581710/page.htm)分别提取到 145、169 字符正文。每站均核对标题、原文链接和列表日期。部分其他条目为受限重定向或仅含 PDF，不尝试绕过限制或下载附件；保留其列表记录与正文失败原因。

## Crawl4AI 可选依赖

目前没有证据表明所选栏目必须执行 JavaScript，故未实现或启用浏览器适配器。不要用浏览器绕过当前网络故障、登录、验证码或访问限制。核心采集路径不导入 Crawl4AI，缺少其浏览器或依赖不影响 RSSHub。

未来若核实某公开来源必须渲染，可安装预留的可选依赖和浏览器，参考 [Crawl4AI 官方安装说明](https://docs.crawl4ai.com/core/installation/)：

```bash
python -m pip install -e '.[browser]'
crawl4ai-setup
python -m playwright install chromium
crawl4ai-doctor
```

Linux 浏览器系统库的安装可能需要管理员权限。本阶段未运行以上命令，未验证浏览器依赖；配置暂不接受 `collector="crawl4ai"`。

## Python 服务层

```python
from datetime import datetime, timezone
from seu_pulse import PulseService

with PulseService.from_config("config.toml") as service:
    result = service.fetch_notices(source_ids=["jwc-international", "wjx-notices"])
    recent = service.list_notices(
        source_id="jwc-international",
        since=datetime(2026, 10, 1, tzinfo=timezone.utc),
        limit=20, offset=0,
    )
    if recent:
        notice = service.get_notice(recent[0].id)
        content = service.get_notice_content(recent[0].id)
    payload = service.export_notices()
```

模型字段、空值和签名以 [agent.md](agent.md) 为准。导出顶层为 `{"schema_version":"1","notices":[...]}`，通知字段不额外增加或省略。`since` 依据最近成功看到该条通知的 `fetched_at`，必须带时区，边界包含；排序按 `fetched_at` 降序、`id` 升序。

身份优先采用规范化原文链接，移除片段和已知跟踪参数，保留业务查询参数；无链接时依次采用 feed GUID/Atom ID、规范化标题。身份与来源 ID 一起生成 SHA-256 稳定 ID，数据库同时约束 ID 及 `(source_id, identity)` 唯一。无链接也无上游 ID 时，同源同标题会合并，标题变更会成为新记录；这是首版降级识别的局限。

`content_hash` 仅由规范化标题、链接、发布时间、摘要、正文及分类组成，排除采集时间和来源元数据。重复出现会刷新 `fetched_at`，保留 `first_seen_at`；缺失链接、时间、摘要或正文时保留已有值，有效内容变化才计为更新。元数据变更会保存，但不计为正文更新。发布时间无明确时区时设为 `null`，原始日期保存在 `metadata.raw_published_at`，采集时间统一为 UTC。

## 测试和真实联网复验

离线测试不会请求外网，fixture 均明确标为测试数据。集成测试运行实际 HTTP 客户端逻辑、解析器、适配器、服务与 SQLite，仅替换 HTTP 响应。

```bash
python -m unittest discover -v
python -m compileall -q seu_pulse scripts tests
```

先执行原始 HTML 采样，再执行采集验收。采样脚本保存一个原始列表页，默认最多检查六篇本站文章，取得两篇可读文本正文后停止（跳过 `_redirect` 指针）；`--max-article-attempts` 可在 2..20 内调整。标题、链接、原始日期、正文提取和失败原因写到 `data/source-inspection/`。若文章是访问限制页或仅含附件，会明确记录；不要因为 HTTP 200 就认定正文可读。

独立联网验证默认只验证已启用来源，支持重复 `--source` 指定任意已配置来源；每个来源采集两次、检查入库查询和身份稳定性，针对网页直采还记录 `direct_content_verified`，不以有列表但无正文判定完整闭环通过。为复验重复采集，脚本在内存中将来源采集间隔设为 0，保留请求间隔、robots、超时及有限重试；常规配置文件不修改。

```bash
python scripts/inspect_sources.py
python scripts/verify_live.py --source jwc-international --source wjx-notices --database data/direct-live-verification.db --output data/direct-live-verification.json
seu-pulse fetch
seu-pulse list --source jwc-international --limit 3
seu-pulse export --output data/notices.json
curl --fail --max-time 20 https://jwc.seu.edu.cn/gjjl/list.psp
curl --fail --max-time 20 https://wjx.seu.edu.cn/tzgg/list.htm
# 已保留的 RSSHub 路径按需复验
python scripts/verify_live.py --source cse-notices --source yzb-masters --source radio-academic
curl --fail --max-time 20 https://rsshub.app/seu/cse/tzgg
curl --fail --max-time 20 https://rsshub.app/seu/yzb/6676
curl --fail --max-time 20 https://rsshub.app/seu/radio/academic
curl --fail --max-time 20 https://seugs.seu.edu.cn/26671/list.htm
curl --fail --max-time 20 https://docs.rsshub.app/routes.json
curl --fail --max-time 20 https://raw.githubusercontent.com/DIYgod/RSSHub/master/lib/routes/seu/cse/index.ts
```

2026 年 10 月 20 日早期失败结果保存在 `data/live-verification.json`、`data/direct-live-verification.json` 和各次 `network-retry` 证据中，均保留作历史记录。最终原始结构采样见 `data/final-source-inspection/report.json`，最终两轮入库验证见 `data/final-live-verification.json`，正式 CLI 的单次采集结果见 `data/final-cli-fetch.json`。各次独立验证使用单独数据库，不用测试 fixture 代替实采。

网络故障已定位到执行沙箱：沙箱内连接本机代理返回 `PermissionError: [Errno 1] Operation not permitted`，获准在沙箱外执行后代理连接及两站 HTTP 200 均通过。受限会话中，联网命令需按执行环境的审批策略获准运行；在用户正常 Ubuntu 终端中按常规命令运行即可。项目没有改动全局安全配置或新建代理服务。

## 结构与数据管理

| 文件 | 职责 |
| --- | --- |
| `seu_pulse/models.py` | 通知与结果模型、时间转换、身份和内容指纹 |
| `seu_pulse/config.py` | TOML 来源配置及校验 |
| `seu_pulse/collectors.py` | 公开 HTTP、robots、RSSHub 和 WebPlus 适配器 |
| `seu_pulse/webpages.py` | 网页直采列表及正文、逐篇错误隔离 |
| `seu_pulse/storage.py` | 来源、通知、总运行与逐源结果的 SQLite 存储 |
| `seu_pulse/service.py` | 面向未来调用方的统一服务层 |
| `seu_pulse/cli.py` | 单次采集、查询、导出及运行状态 |
| `tests/` | 离线模型、存储、采集、服务与 CLI 测试 |
| `scripts/verify_live.py` | 独立真实来源验收脚本 |
| `scripts/inspect_sources.py` | 在校园网服务器保存原始列表及正文样本 |

每个来源成功结果单独事务提交，失败来源写入错误并继续。参数、配置和服务级存储故障抛出；存储故障可能留下 `finished_at=null` 的中断运行，不伪装成来源空数据。robots 不允许访问、登录重定向及 401/403 均停止该来源，不绕过访问控制。只保留通知所需字段，不主动提取作者、联系方式或个人账户数据。

数据库、运行日志、缓存、导出及 wheel 位于忽略目录，不应提交。第一阶段曾因缺少有效 Git 元数据而无法使用 git status 和 git diff，此历史限制保留在第一阶段报告中；版本管理操作见下节，当前进度仅在 tasks.md 记录。


## GitHub 认证与本地密钥

请在运行本项目的同一 Ubuntu 用户下配置认证。仓库地址为 https://github.com/pieceofcorn/agent-challenge；Git 的 HTTPS origin 为 `https://github.com/pieceofcorn/agent-challenge.git`。安装 GitHub CLI 后，按终端提示在浏览器授权，无需把 GitHub Token 或设备验证码发送到聊天中：

```bash
cd /home/skylar/myprojects/agent-challenge
sudo apt update
sudo apt install gh
gh auth login --hostname github.com --git-protocol https --web
gh auth setup-git --hostname github.com
gh auth status --hostname github.com
gh api repos/pieceofcorn/agent-challenge --jq '.permissions.push'
```

最后一条返回 true 表示当前账号具有该仓库的推送权限，不会执行推送。服务器无法打开浏览器时，在自己的浏览器打开终端提示的地址并完成设备授权。GitHub CLI 优先使用系统凭据存储，无法使用时可能回退到本地明文文件；存储位置可由 auth status 查看，勿上传该文件。依据：[官方登录说明](https://cli.github.com/manual/gh_auth_login)、[Git 凭据助手说明](https://cli.github.com/manual/gh_auth_setup-git)。

提交身份单独配置，姓名与邮箱请替换为自己的值；邮箱可使用 GitHub 设置中显示的 noreply 地址，不应填写 API Key 或 Token：

```bash
git config --local user.name "你的提交显示名"
git config --local user.email "你的 GitHub noreply 邮箱"
git config --local --get-regexp '^user\.(name|email)$'
git remote get-url origin
git ls-remote --symref origin HEAD
```

DeepSeek API Key 在 [DeepSeek 控制台](https://platform.deepseek.com/api_keys)申请后，仅在本地编辑项目根目录的 `.env`。以下操作不覆盖已有文件内容：

```bash
umask 077
touch .env
chmod 600 .env
nano .env
```

在编辑器中填写一行 `DEEPSEEK_API_KEY=你的真实密钥`，保存退出；不要把真实值写进源码、config.toml、README、命令行参数或聊天。用下面的命令检查忽略规则，无需打印密钥内容：

```bash
git check-ignore -v .env
git status --ignored --short -- .env
```

**当前程序尚未实现 DeepSeek 接入，也不会自动加载 .env。** 上述步骤只完成密钥存放；后续按审查确认的方案实现程序读取与 API 验证。在另一个终端 export 变量不会改变已启动的 Codex 进程环境。

data/ 中的原始 HTML、历史失败与验收 JSON、测试日志、数据库和 wheel 全部保留本地。首次纳入版本控制的材料包括源码、文档、公开配置和明确标识的测试 fixture；采集正文、运行数据库、导出及日志继续忽略。第一阶段报告保留验收摘要和原始证据路径。忽略文件不会删除它们，也不会将其备份到 GitHub。
