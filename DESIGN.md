# Wombat Miles - 设计文档

## 项目概述

一个命令行工具，用于搜索航空里程兑换商务舱机票的可用性。
目标是替代 seats.aero 的核心功能，免费使用。

## 第一版支持的里程计划

- **Alaska Atmos Rewards** (formerly Mileage Plan)
- **Aeroplan** (Air Canada)

## 技术架构

### 数据来源
1. **Alaska Airlines**
   - API: `https://www.alaskaair.com/searchbff/V3/search`
   - 参数: `origins`, `destinations`, `dates`, `numADTs=1`, `fareView=as_awards`
   - 无需认证，直接 HTTP 请求
   
2. **Aeroplan (Air Canada)**
   - 入口页: `https://www.aircanada.com/aeroplan/redeem/availability/outbound`
   - 数据 API: `*/loyalty/dapidynamic/*/v2/search/air-bounds`
   - 需要 Playwright 浏览器自动化（有 Akamai 反爬虫保护）

### 项目结构
```
wombat-miles/
├── README.md
├── DESIGN.md
├── requirements.txt
├── pyproject.toml
├── wombat_miles/
│   ├── __init__.py
│   ├── cli.py              # 主 CLI 入口 (typer)
│   ├── scrapers/
│   │   ├── __init__.py
│   │   ├── base.py         # 基类 + 数据模型
│   │   ├── alaska.py       # Alaska Atmos Rewards
│   │   └── aeroplan.py     # Aeroplan (Air Canada)
│   ├── cache.py            # SQLite 缓存（避免重复查询）
│   └── formatter.py        # 结果格式化输出
└── tests/
    ├── test_alaska.py
    └── test_aeroplan.py
```

### 数据模型
```python
@dataclass
class FlightFare:
    miles: int              # 里程数
    cash: float             # 税费 (USD)
    cabin: str              # economy / business / first
    booking_class: str      # 订座代码 (J, C, I, etc.)
    program: str            # alaska / aeroplan

@dataclass
class Flight:
    flight_no: str          # 如 AS 1234
    origin: str             # IATA 机场代码
    destination: str        # IATA 机场代码
    departure: datetime
    arrival: datetime
    duration: int           # 分钟
    aircraft: str           # 机型
    fares: list[FlightFare]
    has_wifi: bool | None
```

## CLI 使用方式

```bash
# 搜索指定日期的商务舱里程票
wombat-miles search SFO NRT 2024-06-01 --class business

# 搜索日期范围
wombat-miles search SFO NRT --start 2024-06-01 --end 2024-07-01 --class business

# 只查 Alaska
wombat-miles search SFO NRT 2024-06-01 --program alaska

# 只查 Aeroplan  
wombat-miles search SFO NRT 2024-06-01 --program aeroplan

# 搜索结果保存到 JSON
wombat-miles search SFO NRT 2024-06-01 --output results.json
```

## 实现计划清单

### Phase 1: 项目基础 ✅
- [x] 创建项目结构和依赖配置
- [x] 实现数据模型 (models.py)
- [x] 实现 CLI 框架 (cli.py with typer)

### Phase 2: Alaska Scraper ✅
- [x] 实现 Playwright 浏览器自动化（直接 HTTP 被 406 block）
- [x] 解析 API 响应
- [x] 过滤商务舱结果
- [x] 单元测试通过（mock data）
- ⚠️ 注意：需在本地运行（航空公司 block 数据中心 IP）

### Phase 3: Aeroplan Scraper ✅
- [x] 实现 Playwright 浏览器自动化
- [x] 拦截网络请求获取 API 响应
- [x] 解析 Aeroplan 响应格式
- [x] 单元测试通过（mock data）

### Phase 4: 输出格式化 ✅
- [x] Rich 表格输出（按里程数排序）
- [x] JSON 导出
- [x] 彩色终端输出（绿=经济, 黄=商务, 红=头等）

### Phase 5: 缓存 ✅
- [x] SQLite 缓存（TTL: 4小时）
- [x] 避免重复查询
- [x] cache 管理命令（info/clear/clear --expired）

### Phase 6: README + 测试 ✅
- [x] 完善 README（安装/使用说明）
- [x] 基本单测
- [x] 推送到 GitHub

### Phase 7: 日历视图 ✅ (2026-02-19)
- [x] `calendar-view` 命令（`wombat-miles calendar-view SFO NRT 2025-06 --class business`）
- [x] 月度日历网格展示（7列×周行）
- [x] 相对价格颜色编码（绿=便宜, 黄=中等, 红=贵, 灰=无可用）
- [x] 跨月支持（`--months 2` 显示连续多月）
- [x] 最佳日期摘要（统计可用天数 + 最低价日期）
- [x] Cabin 过滤（只显示对应舱位最优价格）
- [x] 11 个单元测试全部通过

### Phase 8: 价格历史追踪 ✅ (2026-02-19)
- [x] `wombat_miles/price_history.py`：SQLite 存储所有搜索结果
- [x] `search` 命令自动记录价格（可用 `--no-history` 跳过）
- [x] 新低检测：与历史最低价比较，出现更低价格时在 CLI 醒目提示
- [x] `history show SFO NRT --class business` 命令：显示路线价格趋势表
- [x] `history stats SFO NRT` 命令：汇总统计（记录数、最低/最高/均价、首次/最近记录时间）
- [x] `history clear [SFO NRT]` 命令：清除路线或全部历史
- [x] 价格趋势表支持相对颜色编码（绿=最低三分之一, 黄=中间, 红=最贵）
- [x] 17 个单元测试全部通过

### Phase 9: Discord/Webhook 告警系统 ✅ (2026-02-19)
- [x] `wombat_miles/alerts.py`：SQLite 存储告警配置 + Discord Webhook 发送
- [x] `alert add SFO NRT --class business --max-miles 70000 --webhook <url>` 命令
- [x] `alert list` 命令：列出所有活跃告警（表格展示）
- [x] `alert remove <id>` 命令：删除告警
- [x] `alert history [id]` 命令：查看告警触发记录（dedup/审计日志）
- [x] `monitor` 命令：扫描所有告警路线，触发时发 Discord Webhook
  - `--dry-run`：预览不发送
  - `--days N`：搜索未来 N 天（默认 7）
  - `--dedup-hours N`：N 小时内同一结果不重复推送（默认 24h）
  - 自动与 `price_history` 集成，检测历史新低并标注 🔥
- [x] Discord Embed 格式：标题/颜色/里程/税费/新低标记/时间戳
- [x] 25 个单元测试全部通过（mock webhook、dedup、route/cabin/program 过滤）
- [x] 无需本地 IP，纯 SQLite + HTTP POST，cron 友好

### Phase 10: 多城市搜索 ✅ (2026-02-19)
- [x] `multi-city` 命令：支持逗号分隔的多个出发城市（如 `SFO,LAX,SEA`）
- [x] 并行搜索所有路线，自动汇总结果
- [x] 按里程价格排序，显示最优选项
- [x] 双表格输出：
  - 📊 摘要表：每个出发城市的最佳价格 + 可用航班数
  - 🔍 详细表：Top 20 最优航班（跨所有城市比较）
- [x] 结果表格清楚标注出发城市（彩色高亮）
- [x] 支持所有现有参数：`--class`, `--program`, `--days`, `--stops`, `-o` (JSON 导出)
- [x] 复用现有 cache、scraper 逻辑，无需本地 IP
- [x] 4 个单元测试全部通过

### Phase 11: 最优兑换建议 ✅ (2026-02-20)
- [x] `wombat_miles/recommend.py`：推荐引擎核心逻辑
- [x] `recommend` 命令：搜索多个热门目的地并按价值排序
  - 支持指定区域（`--region asia/europe/oceania/domestic`）
  - 支持里程预算过滤（`--max-miles 70000`）
  - 支持舱位过滤（`--class business`）
  - 支持计划过滤（`--program alaska`）
  - 显示 Top N 推荐（`--top 10`）
- [x] 价值指标计算：
  - CPM (Cents Per Mile)：每飞行里程成本
  - 舱位倍数：头等/商务舱价值更高
  - 飞行距离：长途航线更值
  - 综合评分：距离×舱位倍数/里程数
- [x] Rich 表格输出：排名、路线、日期、舱位、里程、税费、距离、CPM、评分
- [x] 热门目的地库：亚洲/欧洲/大洋洲/美国国内共 26 个机场
- [x] 飞行距离数据库：覆盖主要西海岸出发地到热门目的地
- [x] 6 个单元测试全部通过
- [x] 无需本地 IP，纯搜索+分析逻辑

### Phase 12: 告警系统升级 ✅ (2026-02-20)
- [x] **多 Webhook 支持**：每个 alert 可配置多个 webhook URL
  - Discord、Slack、其他任意支持 JSON webhook 的平台
  - `alert add --webhook URL1 --webhook URL2` 语法（可重复）
  - 并行发送到所有 webhook，部分失败不影响整体成功
- [x] **SMTP 邮件通知**：支持邮件告警
  - `email-config` 命令组：add/list/remove 邮件配置
  - 支持 TLS/无 TLS SMTP 服务器
  - `alert add --email user@example.com --email-config default` 语法
  - 纯文本邮件格式（包含 emoji + 航班详情）
- [x] **通知灵活组合**：同一 alert 可同时配置 webhook + email
- [x] **数据库迁移逻辑**：向后兼容旧 `discord_webhook` 字段
  - 自动将旧单个 webhook 迁移到新的 JSON 数组格式
  - 新增 `email_configs` 表存储 SMTP 配置
- [x] **CLI 更新**：
  - `alert add` 支持 `--webhook`（多个）、`--email`（多个）、`--email-config`
  - `alert list` 显示通知渠道摘要（"2 webhook(s), 1 email(s)"）
  - `email-config add/list/remove` 管理 SMTP 配置
- [x] 16 个新单元测试全部通过（email config CRUD、多 webhook、混合通知、失败处理、迁移）
- [x] 107 个总测试全部通过（包括旧测试的兼容更新）
- [x] 无需本地 IP，纯 SQLite + HTTP POST + SMTP

## 后续改进计划（继续迭代）

### 数据源扩展
- United MileagePlus
- American AAdvantage  
- British Airways Executive Club (Avios)
- Delta SkyMiles
- Virgin Atlantic Flying Club

### 功能增强（无需本地IP）
- **连接航班支持**：搜索中转航线（如 SFO→ICN→BKK），自动匹配可行连接（★★★ 下一个优先）
- **推荐引擎升级**：考虑停留时长、舱位质量（平躺/直飞偏好）、历史价格趋势（★★）
- **告警增强**：Telegram bot 集成、短信通知（Twilio）（★）

### 界面升级
- 交互式 TUI (textual 框架)：方向键浏览日历，实时过滤（★★）
- Web UI (FastAPI + 简单前端)（★）

### 其他
- 里程票价格对比（同一航班不同计划的成本对比表）
- 多币种支持（显示人民币/欧元等价税费）
