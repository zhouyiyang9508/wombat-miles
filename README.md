# 🦘 Wombat Miles

> Skip the $20/month seats.aero subscription. Search award flight availability from your terminal.

Wombat Miles is a personal CLI tool that searches airline mileage programs for award seats — especially **business class**. It queries airline websites directly, so you see real-time availability without paying for third-party services.

## Supported Programs

| Program | Airline | Method | Status |
|---------|---------|--------|--------|
| Alaska Atmos Rewards | Alaska Airlines + partners | Playwright browser automation | ✅ Ready |
| Aeroplan | Air Canada + Star Alliance | Playwright browser automation | ✅ Ready |

## ⚠️ Important: Run Locally

**This tool must run on your local machine** (laptop/desktop with a residential IP). Airlines block requests from cloud servers and data centers. If you run it on a VPS, you'll get 406/403 errors.

## Installation

```bash
# Clone the repo
git clone https://github.com/zhouyiyang9508/wombat-miles.git
cd wombat-miles

# Install dependencies
pip install -r requirements.txt

# Install Chromium for Playwright (required for all scrapers)
playwright install chromium
```

## Usage

### Basic Search

```bash
# Search SFO → Tokyo Narita on a specific date
python -m wombat_miles search SFO NRT 2025-06-15

# Business class only
python -m wombat_miles search SFO NRT 2025-06-15 --class business

# Search using only Alaska
python -m wombat_miles search SEA NRT 2025-06-15 --class business --program alaska

# Search using only Aeroplan
python -m wombat_miles search SFO YYZ 2025-06-15 --class business --program aeroplan
```

### Multi-Day Search

```bash
# Search 7 consecutive days
python -m wombat_miles search SFO NRT 2025-06-01 --days 7 --class business

# Date range with summary view
python -m wombat_miles search SFO NRT --start 2025-06-01 --end 2025-06-30 --class business --summary
```

### Output Options

```bash
# Save results to JSON
python -m wombat_miles search SFO NRT 2025-06-15 -o results.json

# Verbose logging (for debugging)
python -m wombat_miles search SFO NRT 2025-06-15 -v

# Skip cache (force fresh search)
python -m wombat_miles search SFO NRT 2025-06-15 --no-cache
```

### Cache Management

```bash
# View cache info
python -m wombat_miles cache info

# Clear all cached results
python -m wombat_miles cache clear

# Clear only expired entries
python -m wombat_miles cache clear --expired
```

## Example Output

```
✈  SFO → NRT  |  2025-06-15  |  Business class

╭──────────┬─────────┬─────────┬──────────┬────────────────┬────────┬───────┬──────────┬────────────┬──────╮
│ Flight   │ Departs │ Arrives │ Duration │ Aircraft       │  Miles │ Taxes │  Cabin   │ Program    │ WiFi │
├──────────┼─────────┼─────────┼──────────┼────────────────┼────────┼───────┼──────────┼────────────┼──────┤
│ JL 69    │ 12:00   │ 14:30+1 │  10h30m  │ Boeing 787-8   │ 55,000 │   $86 │ Business │ Alaska ✈   │  📶  │
│ AC 758   │ 09:00   │ 17:15   │   5h15m  │ Boeing 787-9   │ 60,000 │  $250 │ Business │ Aeroplan ✈ │  –   │
╰──────────┴─────────┴─────────┴──────────┴────────────────┴────────┴───────┴──────────┴────────────┴──────╯
2 flights found.
```

## How It Works

1. **Alaska Atmos Rewards**: Uses Playwright to load the Alaska Airlines search page and captures the internal API response (`/searchbff/V3/search`)
2. **Aeroplan**: Uses Playwright to load the Air Canada Aeroplan search page and intercepts the award search API (`/loyalty/dapidynamic/*/v2/search/air-bounds`)

Both scrapers filter for direct flights only and return the lowest-miles fare per cabin class.

Results are cached in SQLite (`~/.wombat-miles/cache.db`) with a 4-hour TTL to avoid hammering airline servers.

## Project Structure

```
wombat-miles/
├── wombat_miles/
│   ├── cli.py          # CLI entry point (typer)
│   ├── models.py       # Data models (Flight, FlightFare)
│   ├── scrapers/
│   │   ├── alaska.py   # Alaska Atmos Rewards scraper
│   │   └── aeroplan.py # Aeroplan scraper
│   ├── cache.py        # SQLite caching
│   └── formatter.py    # Rich terminal output
├── tests/              # Unit tests with mock data
├── DESIGN.md           # Technical design document
└── README.md
```

## Limitations

- **Local execution required** — airlines block data center IPs
- **Direct flights only** — connecting itineraries are not shown (yet)
- **Playwright required** — needs Chromium installed (~200MB)
- **Anti-bot detection** — Aeroplan in particular may occasionally block automated requests

## Roadmap

### Near-term
- [ ] Connection/multi-segment flight support
- [ ] Interactive TUI with `textual`
- [ ] Email/Discord alerts when award space opens
- [ ] Auto-search popular routes on schedule

### More Programs
- [ ] United MileagePlus
- [ ] American AAdvantage
- [ ] British Airways Avios
- [ ] Delta SkyMiles
- [ ] Virgin Atlantic Flying Club

### Web UI
- [ ] FastAPI backend + simple web frontend
- [ ] Calendar heatmap view (like seats.aero)
- [ ] Price history tracking

### Advanced Features
- [ ] Multi-program cost comparison (same flight, different programs)
- [ ] Optimal redemption calculator
- [ ] Hub expansion search (e.g., "any West Coast → any Tokyo airport")

## Disclaimer

This tool is for **personal use only**. It accesses publicly available award search pages — the same data you'd see by visiting the airline websites manually. Please be respectful of airline servers and don't abuse the tool.

## License

MIT
