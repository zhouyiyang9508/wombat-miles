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

## 后续改进计划（继续迭代）

### 数据源扩展
- United MileagePlus
- American AAdvantage  
- British Airways Executive Club (Avios)
- Delta SkyMiles
- Virgin Atlantic Flying Club

### 功能增强（优先推荐：无需本地IP）
- **Discord/邮件通知**：里程票出现或跌价时发送 Discord 告警，结合 cron 实现自动监控（★★★ 下一个优先）
- **最优兑换建议**：输入手头里程，推荐最合算的路线/舱位（★★）
- **多城市搜索**：枢纽机场扩展（如 SFO/LAX/SEA 同时出发）（★★）

### 界面升级
- 交互式 TUI (textual 框架)：方向键浏览日历，实时过滤（★★）
- Web UI (FastAPI + 简单前端)（★）

### 其他
- 里程票价格对比（同一航班不同计划的成本对比表）
- 最优兑换建议（根据你手头的里程余额）
