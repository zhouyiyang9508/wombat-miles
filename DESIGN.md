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

### Phase 1: 项目基础 ⬜
- [ ] 创建项目结构和依赖配置
- [ ] 实现数据模型 (base.py)
- [ ] 实现 CLI 框架 (cli.py with typer)

### Phase 2: Alaska Scraper ⬜
- [ ] 实现 Alaska HTTP 请求
- [ ] 解析 API 响应
- [ ] 过滤商务舱结果
- [ ] 验证测试: SFO→NRT 等主要航线

### Phase 3: Aeroplan Scraper ⬜
- [ ] 实现 Playwright 浏览器自动化
- [ ] 拦截网络请求获取 API 响应
- [ ] 解析 Aeroplan 响应格式
- [ ] 验证测试

### Phase 4: 输出格式化 ⬜
- [ ] Rich 表格输出（按里程数排序）
- [ ] JSON/CSV 导出
- [ ] 彩色终端输出

### Phase 5: 缓存 ⬜
- [ ] SQLite 缓存（TTL: 4小时）
- [ ] 避免重复查询
- [ ] cache 管理命令

### Phase 6: README + 测试 ⬜
- [ ] 完善 README（安装/使用说明）
- [ ] 基本单测
- [ ] 端到端测试
- [ ] 推送到 GitHub

## 后续改进计划（第一版完成后）

### 数据源扩展
- United MileagePlus
- American AAdvantage  
- British Airways Executive Club (Avios)
- Delta SkyMiles
- Virgin Atlantic Flying Club

### 功能增强
- 多城市搜索（枢纽扩展）
- 日历视图（显示一个月的可用情况）
- 价格历史追踪 + 告警
- 邮件/Discord 通知（里程票出现时）
- 自动搜索热门路线

### 界面升级
- Web UI (FastAPI + 简单前端)
- 交互式 TUI (textual 框架)

### 其他
- 里程票价格对比（同一航班不同计划的成本）
- 最优兑换建议（根据你手头的里程）
