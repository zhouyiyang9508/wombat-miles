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

# Include 1-stop connections
python -m wombat_miles search SFO NRT 2025-06-15 --class business --stops 1

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

### Multi-City Search 🌍

Compare award availability from multiple departure cities to the same destination. Find the best deal by expanding your origin options.

```bash
# Compare SFO, LAX, and SEA to Tokyo
python -m wombat_miles multi-city SFO,LAX,SEA NRT 2025-06-15 --class business

# Bay Area airports to Toronto (Aeroplan only)
python -m wombat_miles multi-city SFO,OAK,SJC YYZ 2025-07-01 --program aeroplan

# Multi-day + multi-city search
python -m wombat_miles multi-city SFO,LAX NRT 2025-06-01 --days 3 --class business

# Save comparison to JSON
python -m wombat_miles multi-city SFO,LAX,SEA NRT 2025-06-15 -o comparison.json
```

Example output:
```
✈  Multi-City Search: → NRT  |  2025-06-15 | Business

📊 Best Options by Origin:
╭────────┬────────────┬───────┬──────────┬──────────┬─────────╮
│ Origin │ Best Miles │ Taxes │ Cabin    │ Program  │ Flights │
├────────┼────────────┼───────┼──────────┼──────────┼─────────┤
│ LAX    │     65,000 │   $45 │ Business │ Alaska ✈ │       3 │
│ SFO    │     70,000 │   $50 │ Business │ Alaska ✈ │       5 │
│ SEA    │     75,000 │   $55 │ Business │ Alaska ✈ │       2 │
╰────────┴────────────┴───────┴──────────┴──────────┴─────────╯

🔍 Top 20 Deals:
[Detailed flight listing with times, stops, miles sorted by price...]
```

**Why use multi-city?** Sometimes flying from a nearby hub saves 10k+ miles. If you live near multiple airports or are flexible about positioning flights, this feature helps you maximize value.

### Optimal Redemption Recommendations 💡

Not sure where to use your miles? Let Wombat Miles search multiple popular destinations and rank them by **value** (CPM, distance, cabin class). Perfect for "I have 70k Alaska miles — where should I go?" questions.

```bash
# Best business class redemptions from SFO in June (searches 26 destinations)
python -m wombat_miles recommend SFO 2025-06-01 --class business --days 7

# Best Asia redemptions with 70k miles budget
python -m wombat_miles recommend SFO 2025-06-01 --region asia --max-miles 70000

# Top 5 recommendations, Alaska only
python -m wombat_miles recommend LAX 2025-07-15 --program alaska --top 5

# Compare all regions, show top 20
python -m wombat_miles recommend SFO 2025-06-01 --top 20
```

Example output:
```
💡 Finding optimal redemptions from SFO...
  Destinations: 26 (all regions)
  Dates: 2025-06-01 to 2025-06-07
  Cabin: business
  Program: all

  Searching SFO → NRT... 5 flight(s)
  Searching SFO → ICN... 3 flight(s)
  ...

🏆 Top 10 Award Redemption Recommendations
╭──────┬──────────────┬────────────┬──────────┬─────────┬────────┬──────────┬──────────┬───────╮
│ Rank │ Route        │ Date       │ Cabin    │   Miles │  Taxes │ Distance │      CPM │ Score │
├──────┼──────────────┼────────────┼──────────┼─────────┼────────┼──────────┼──────────┼───────┤
│   #1 │ SFO→NRT      │ 2025-06-05 │ 💺 Biz   │  55,000 │    $86 │ 5,140 mi │   1.67¢  │ 233.8 │
│   #2 │ SFO→ICN      │ 2025-06-03 │ 💺 Biz   │  62,500 │    $90 │ 5,963 mi │   1.51¢  │ 238.5 │
│   #3 │ SFO→HKG      │ 2025-06-07 │ 💺 Biz   │  75,000 │   $110 │ 6,927 mi │   1.59¢  │ 230.8 │
│  ... │              │            │          │         │        │          │          │       │
╰──────┴──────────────┴────────────┴──────────┴─────────┴────────┴──────────┴──────────┴───────╯

📊 Top 10 average: 66,500 miles, 1.62¢/mi CPM
💡 CPM (cents per mile flown) guideline: <1.5¢=excellent, 1.5-2.0¢=good, >2.0¢=fair
```

**What is CPM?** Cents Per Mile (CPM) measures how much cash you pay per actual mile flown. For example:
- SFO→NRT = 5,140 mi, $86 taxes → **1.67¢/mi**
- Lower CPM = better deal (you're minimizing out-of-pocket cost per distance)
- Typical sweet spot: **1.0-2.0¢** for business class long-haul

**Why it matters:**
- **Long-haul business/first** usually has the best CPM (1.0-1.5¢)
- **Short-haul economy** often has poor CPM (2.5-4.0¢) — save miles for better uses
- **Compare across routes**: Tokyo at 55k miles (1.67¢) beats LA at 12.5k miles (3.5¢)

**Scoring algorithm:**
- Base: `(distance × cabin_multiplier) / miles`
- Cabin multipliers: First=3.0x, Business=2.5x, Economy=1.0x
- Penalties: high taxes, over-budget options
- Higher score = better redemption value

**Regions available:** `asia` (8 destinations), `europe` (8), `oceania` (3), `domestic` (5 US cities)

### Output Options

```bash
# Save results to JSON
python -m wombat_miles search SFO NRT 2025-06-15 -o results.json

# Save results to CSV (great for spreadsheets)
python -m wombat_miles search SFO NRT 2025-06-15 -o results.csv

# Verbose logging (for debugging)
python -m wombat_miles search SFO NRT 2025-06-15 -v

# Skip cache (force fresh search)
python -m wombat_miles search SFO NRT 2025-06-15 --no-cache
```

### Calendar View 📅

See a full month of availability at a glance. Each cell shows the cheapest available award price. Colors are **relative** — green = cheapest days, yellow = moderate, red = expensive.

```bash
# Show June 2025 availability (business class)
python -m wombat_miles calendar-view SFO NRT 2025-06 --class business

# Aeroplan only, two consecutive months
python -m wombat_miles calendar-view SFO YYZ 2025-07 --program aeroplan --months 2

# Include 1-stop connections, no cabin filter
python -m wombat_miles calendar-view SEA NRT 2025-08 --stops 1
```

Example output:
```
✈  SFO → NRT  |  June 2025  |  Business

   Mon      Tue      Wed      Thu      Fri      Sat      Sun
 ─────────────────────────────────────────────────────────────
                                                         1
                                                        55k
   2        3        4        5        6        7        8
   –        –        –       45k       –        –        –
   9       10       11       12       13       14       15
   –       60k       –        –        –        –       70k
  ...
6/30 days with availability.
Best price: 2025-06-05 — 45,000 miles (alaska)
```

### Price History 📈

Every search automatically records prices to a local SQLite database (`~/.wombat-miles/price_history.db`). Over time, this builds a trend dataset and detects when prices drop.

```bash
# View price history for a route (last 30 days)
python -m wombat_miles history show SFO NRT --class business

# Look back 60 days
python -m wombat_miles history show SFO NRT --class business --days 60

# Summary statistics (min/max/avg miles, first/last seen)
python -m wombat_miles history stats SFO NRT

# Clear history for a specific route
python -m wombat_miles history clear SFO NRT

# Clear ALL history
python -m wombat_miles history clear --yes

# Skip recording for a one-off search
python -m wombat_miles search SFO NRT 2025-06-15 --no-history
```

When a new price low is detected vs. the last 30 days, a 🔔 alert is printed inline:

```
🔔 New Price Low Detected!
  SFO→NRT on 2025-06-15 (Business, alaska): 55,000 miles (was 70,000, ↓21.4%)
```

### Alert System 🔔

Set up automatic notifications for when award availability meets your criteria. Supports **multiple webhooks** (Discord, Slack, etc.) and **email** notifications. Combines with `monitor` (run via cron) to get notified when cheap business seats appear.

#### Webhook Notifications (Discord, Slack, etc.)

```bash
# Create an alert with Discord webhook
python -m wombat_miles alert add SFO NRT --class business --max-miles 70000 --webhook https://discord.com/api/webhooks/...

# Multiple webhooks (different channels/platforms)
python -m wombat_miles alert add SFO NRT --class business \
  --webhook https://discord.com/api/webhooks/xxx \
  --webhook https://hooks.slack.com/services/yyy
```

#### Email Notifications 📧

First, configure an SMTP email server:

```bash
# Add an email config (Gmail example with app password)
python -m wombat_miles email-config add default \
  --host smtp.gmail.com --port 587 \
  --user yourname@gmail.com \
  --password your-app-password

# List email configs (passwords redacted)
python -m wombat_miles email-config list

# Remove an email config
python -m wombat_miles email-config remove default
```

Then create alerts with email:

```bash
# Email-only alert
python -m wombat_miles alert add SFO NRT --class business \
  --email user@example.com --email-config default

# Multiple recipients
python -m wombat_miles alert add SFO NRT --class business \
  --email person1@example.com --email person2@example.com \
  --email-config default

# Both webhook + email
python -m wombat_miles alert add SFO NRT --class business \
  --webhook https://discord.com/api/webhooks/xxx \
  --email user@example.com --email-config default
```

#### Managing Alerts

```bash
# List configured alerts (shows notification channels)
python -m wombat_miles alert list

# Remove an alert by ID
python -m wombat_miles alert remove 1

# View alert fire history (audit log)
python -m wombat_miles alert history
python -m wombat_miles alert history 2  # for a specific alert
```

Run the monitor manually or via cron:

```bash
# Check all alert routes, send Discord notifications
python -m wombat_miles monitor

# Preview without sending notifications
python -m wombat_miles monitor --dry-run

# Search 14 days ahead, re-notify every 12 hours
python -m wombat_miles monitor --days 14 --dedup-hours 12

# Add to crontab — run every 6 hours:
# 0 */6 * * * cd /path/to/wombat-miles && python -m wombat_miles monitor
```

When a match is found:
- Fires a Discord **embed** with flight details (route, date, miles, taxes, departure/arrival times)
- 🔥 **NEW LOW** badge + previous price shown when it's a historical minimum
- Dedup logic prevents spamming (same fare won't re-notify within 24h by default)
- All fired alerts are logged to `~/.wombat-miles/alerts.db` for auditing

Example Discord embed content:
```
🦘 Award Alert: SFO → NRT 🔥 NEW LOW!
🛋️ Business · 🌲 Alaska
🗓️ 2025-06-05 · ✈ AS 1
⏰ 10:00 → 14:30
💰 65,000 miles + $85 taxes
📉 Previous low: 72,000 miles (↓9.7%)
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
│   ├── cli.py              # CLI entry point (typer)
│   ├── models.py           # Data models (Flight, FlightFare)
│   ├── scrapers/
│   │   ├── alaska.py       # Alaska Atmos Rewards scraper
│   │   └── aeroplan.py     # Aeroplan scraper
│   ├── cache.py            # SQLite search result cache (4h TTL)
│   ├── price_history.py    # Price history tracking + new-low detection
│   ├── alerts.py           # Alert config + Discord webhook notifications
│   └── formatter.py        # Rich terminal output
├── tests/                  # Unit tests with mock data (81 tests)
├── DESIGN.md               # Technical design document
└── README.md
```

## Limitations

- **Local execution required** — airlines block data center IPs
- **Playwright required** — needs Chromium installed (~200MB)
- **Anti-bot detection** — Aeroplan in particular may occasionally block automated requests

## Roadmap

### Near-term
- [x] Connection/multi-segment flight support (`--stops N`)
- [x] CSV export (`-o results.csv`)
- [x] Monthly calendar view (`calendar-view`)
- [x] Price history tracking + new-low alerts (`history show / stats / clear`)
- [x] Discord webhook alerts + `monitor` cron command (`alert add / list / remove / history`)
- [x] Multi-city hub search (SFO/LAX/SEA simultaneously) — `multi-city` command
- [x] Optimal redemption recommendations (`recommend` command) — searches multiple destinations, ranks by value/CPM
- [ ] Interactive TUI with `textual`
- [ ] Email (SMTP) alert support + multi-webhook configs

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
