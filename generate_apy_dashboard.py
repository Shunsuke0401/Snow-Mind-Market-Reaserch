#!/usr/bin/env python3
"""
Snow Mind — APY Comparison Dashboard Generator

Fetches historical APY data from DefiLlama for 6 target USDC lending
markets on Avalanche and generates an interactive comparison page.
"""

import json
import os
import time
from datetime import datetime, timezone, timedelta

import requests

# ─── Configuration ────────────────────────────────────────────────────────────

YIELDS_BASE = "https://yields.llama.fi"
DATA_DIR = "data"
OUTPUT_FILE = "apy_comparison.html"
DELAY = 0.5
HEADERS = {"User-Agent": "SnowMind-Research/1.0"}

POOLS = [
    {
        "id": "c4b05318-88af-4536-a834-f5fc8940d2d3",
        "label": "Aave V3",
        "tag": "Blue chip conservative",
        "color": "#9b7ddb",
        "border_dash": [],
    },
    {
        "id": "ff59b165-64e0-4868-a6db-6049b5135358",
        "label": "Benqi",
        "tag": "Avalanche native conservative",
        "color": "#1cc0e0",
        "border_dash": [],
    },
    {
        "id": "e96cbd55-a0a0-446a-89ba-ada6e2991d50",
        "label": "Spark",
        "tag": "Base-layer parking",
        "color": "#f5ac37",
        "border_dash": [],
    },
    {
        "id": "e1db168e-7c9d-4285-9d3f-ba83a9ecf105",
        "label": "Euler (9Summits)",
        "tag": "Curated vault, higher yield",
        "color": "#e84142",
        "border_dash": [],
    },
    {
        "id": "7cee66c5-4e83-4beb-8b4d-2c2fd62813c5",
        "label": "Silo (savUSD/USDC)",
        "tag": "Isolated lending, Avant collateral",
        "color": "#3fb950",
        "border_dash": [5, 5],
    },
    {
        "id": "82c8eda4-f27b-4e41-851d-4368af5e4866",
        "label": "Silo (sUSDp/USDC)",
        "tag": "Isolated lending, Parallel collateral",
        "color": "#58a6ff",
        "border_dash": [5, 5],
    },
]


# ─── Data Fetching ────────────────────────────────────────────────────────────

def fetch_pool_current(pool_id):
    """Fetch current snapshot from /pools for a specific pool."""
    r = requests.get(f"{YIELDS_BASE}/pools", headers=HEADERS, timeout=30)
    r.raise_for_status()
    all_pools = r.json().get("data", [])
    for p in all_pools:
        if p.get("pool") == pool_id:
            return p
    return None


def fetch_pool_history(pool_id, label):
    """Fetch historical APY/TVL data for a pool."""
    print(f"  -> {label} ...")
    try:
        r = requests.get(
            f"{YIELDS_BASE}/chart/{pool_id}", headers=HEADERS, timeout=30
        )
        r.raise_for_status()
        data = r.json().get("data", [])
        safe = label.replace(" ", "_").replace("/", "_").replace("(", "").replace(")", "")
        with open(os.path.join(DATA_DIR, f"apy_{safe}.json"), "w") as f:
            json.dump(data, f, indent=2)
        return data
    except Exception as e:
        print(f"     Failed: {e}")
        return []


def fetch_all():
    os.makedirs(DATA_DIR, exist_ok=True)

    print("\n[1/2] Fetching current pool snapshots...")
    r = requests.get(f"{YIELDS_BASE}/pools", headers=HEADERS, timeout=30)
    r.raise_for_status()
    all_pools = r.json().get("data", [])
    pool_map = {p["pool"]: p for p in all_pools}
    time.sleep(DELAY)

    print("\n[2/2] Fetching historical APY data...")
    results = []
    for cfg in POOLS:
        hist = fetch_pool_history(cfg["id"], cfg["label"])
        current = pool_map.get(cfg["id"], {})
        results.append({
            **cfg,
            "history": hist,
            "current_apy": current.get("apy"),
            "current_apy_base": current.get("apyBase"),
            "current_apy_reward": current.get("apyReward"),
            "current_tvl": current.get("tvlUsd"),
            "symbol": current.get("symbol", "USDC"),
            "project": current.get("project", ""),
            "pool_meta": current.get("poolMeta", ""),
        })
        time.sleep(DELAY)

    return results


# ─── Data Processing ──────────────────────────────────────────────────────────

def process(results):
    """Align all pools to a common date axis (last 90 days)."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=90)
    cutoff_str = cutoff.strftime("%Y-%m-%d")

    # Build per-pool daily APY series keyed by date string
    pool_series = []
    all_dates = set()

    for pool in results:
        daily = {}
        for pt in pool["history"]:
            ts = pt.get("timestamp", "")
            day = ts[:10]  # "YYYY-MM-DD"
            if day >= cutoff_str:
                daily[day] = {
                    "apy": pt.get("apy") or 0,
                    "apyBase": pt.get("apyBase") or 0,
                    "apyReward": pt.get("apyReward") or 0,
                    "tvl": pt.get("tvlUsd") or 0,
                }
                all_dates.add(day)
        pool_series.append(daily)

    common_dates = sorted(all_dates)

    processed = []
    for i, pool in enumerate(results):
        series = pool_series[i]
        dates = []
        apys = []
        tvls = []
        for day in common_dates:
            if day in series:
                dates.append(day)
                apys.append(round(series[day]["apy"], 4))
                tvls.append(round(series[day]["tvl"], 2))
            else:
                dates.append(day)
                apys.append(None)
                tvls.append(None)
        processed.append({**pool, "dates": dates, "apys": apys, "tvls": tvls})

    return processed, common_dates


# ─── HTML Generation ──────────────────────────────────────────────────────────

def build_html(processed, common_dates, fetch_time):
    def fmt_usd(v):
        if v is None:
            return "N/A"
        if abs(v) >= 1e9:
            return f"${v/1e9:.2f}B"
        if abs(v) >= 1e6:
            return f"${v/1e6:.2f}M"
        if abs(v) >= 1e3:
            return f"${v/1e3:.1f}K"
        return f"${v:,.0f}"

    # Chart.js datasets for APY comparison
    datasets_apy = []
    for p in processed:
        datasets_apy.append({
            "label": p["label"],
            "data": p["apys"],
            "borderColor": p["color"],
            "backgroundColor": p["color"] + "18",
            "borderDash": p["border_dash"],
            "fill": False,
            "tension": 0.3,
            "pointRadius": 0,
            "pointHoverRadius": 5,
            "borderWidth": 2.5,
            "spanGaps": True,
        })

    # Chart.js datasets for TVL comparison
    datasets_tvl = []
    for p in processed:
        datasets_tvl.append({
            "label": p["label"],
            "data": p["tvls"],
            "borderColor": p["color"],
            "backgroundColor": p["color"] + "22",
            "borderDash": p["border_dash"],
            "fill": True,
            "tension": 0.3,
            "pointRadius": 0,
            "pointHoverRadius": 5,
            "borderWidth": 2,
            "spanGaps": True,
        })

    labels_json = json.dumps([d[5:] for d in common_dates])  # "MM-DD" format
    ds_apy_json = json.dumps(datasets_apy)
    ds_tvl_json = json.dumps(datasets_tvl)

    # Summary table rows
    table_rows = ""
    sorted_pools = sorted(processed, key=lambda p: p.get("current_apy") or 0, reverse=True)
    for p in sorted_pools:
        apy = p.get("current_apy")
        apy_str = f"{apy:.2f}%" if apy is not None else "N/A"
        base = p.get("current_apy_base")
        base_str = f"{base:.2f}%" if base is not None else "—"
        reward = p.get("current_apy_reward")
        reward_str = f"{reward:.2f}%" if reward and reward > 0 else "—"
        tvl_str = fmt_usd(p.get("current_tvl"))

        # Compute 7d average APY from history
        recent = [a for a in p["apys"][-7:] if a is not None]
        avg7 = sum(recent) / len(recent) if recent else None
        avg7_str = f"{avg7:.2f}%" if avg7 is not None else "—"

        # Compute 30d average APY
        recent30 = [a for a in p["apys"][-30:] if a is not None]
        avg30 = sum(recent30) / len(recent30) if recent30 else None
        avg30_str = f"{avg30:.2f}%" if avg30 is not None else "—"

        # APY volatility (std dev of last 30d)
        if recent30 and len(recent30) > 1:
            mean = sum(recent30) / len(recent30)
            var = sum((x - mean) ** 2 for x in recent30) / len(recent30)
            std = var ** 0.5
            vol_str = f"{std:.2f}%"
        else:
            vol_str = "—"

        dot = f'<span style="color:{p["color"]}">●</span>'
        table_rows += f"""<tr>
            <td>{dot} {p['label']}</td>
            <td class="tag">{p['tag']}</td>
            <td class="num highlight">{apy_str}</td>
            <td class="num">{avg7_str}</td>
            <td class="num">{avg30_str}</td>
            <td class="num">{vol_str}</td>
            <td class="num">{base_str}</td>
            <td class="num">{reward_str}</td>
            <td class="num">{tvl_str}</td>
        </tr>\n"""

    # Best / worst current
    valid = [p for p in processed if p.get("current_apy") is not None]
    best = max(valid, key=lambda p: p["current_apy"]) if valid else None
    worst = min(valid, key=lambda p: p["current_apy"]) if valid else None
    spread = (best["current_apy"] - worst["current_apy"]) if best and worst else 0

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Snow Mind — USDC Lending APY Comparison (Avalanche)</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
:root {{
    --bg: #0d1117; --card: #161b22; --border: #30363d;
    --text: #e6edf3; --text2: #8b949e; --accent: #58a6ff;
    --avax: #e84142; --green: #3fb950; --yellow: #d29922;
}}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: var(--bg); color: var(--text); line-height: 1.6;
}}
.container {{ max-width: 1280px; margin: 0 auto; padding: 24px; }}

header {{ text-align: center; padding: 40px 24px 28px; border-bottom: 1px solid var(--border); margin-bottom: 28px; }}
header h1 {{ font-size: 1.8rem; margin-bottom: 4px; }}
header h1 span {{ color: var(--avax); }}
header .sub {{ color: var(--text2); font-size: 1rem; }}
header .ts {{ color: var(--text2); font-size: 0.8rem; margin-top: 10px; opacity: 0.7; }}

.kpi-grid {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 14px; margin-bottom: 32px;
}}
.kpi {{
    background: var(--card); border: 1px solid var(--border); border-radius: 10px;
    padding: 18px; text-align: center;
}}
.kpi .k-label {{ font-size: 0.75rem; color: var(--text2); text-transform: uppercase; letter-spacing: 0.04em; }}
.kpi .k-val {{ font-size: 1.5rem; font-weight: 700; margin-top: 4px; }}

section {{
    background: var(--card); border: 1px solid var(--border); border-radius: 12px;
    padding: 24px; margin-bottom: 24px;
}}
section h2 {{ font-size: 1.2rem; margin-bottom: 6px; }}
section .insight {{
    color: var(--text2); font-size: 0.88rem; margin-bottom: 18px;
    border-left: 3px solid var(--avax); padding-left: 12px;
}}

.chart-wrap {{ position: relative; width: 100%; }}
.chart-wrap canvas {{ width: 100% !important; }}

table {{ width: 100%; border-collapse: collapse; font-size: 0.85rem; }}
th, td {{ padding: 10px 12px; text-align: left; border-bottom: 1px solid var(--border); }}
th {{ color: var(--text2); font-weight: 600; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.03em; }}
td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
td.highlight {{ font-weight: 700; color: var(--green); font-size: 0.95rem; }}
td.tag {{ color: var(--text2); font-size: 0.78rem; font-style: italic; max-width: 200px; }}
tr:hover {{ background: rgba(88,166,255,0.04); }}

.legend-grid {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: 10px; margin-bottom: 20px;
}}
.legend-item {{
    display: flex; align-items: center; gap: 10px; padding: 8px 12px;
    background: rgba(255,255,255,0.02); border-radius: 6px;
}}
.legend-dot {{ width: 14px; height: 14px; border-radius: 50%; flex-shrink: 0; }}
.legend-name {{ font-weight: 600; font-size: 0.9rem; }}
.legend-tag {{ color: var(--text2); font-size: 0.78rem; }}

.note {{ color: var(--text2); font-size: 0.82rem; margin-top: 14px; font-style: italic; }}

footer {{
    text-align: center; padding: 28px; color: var(--text2); font-size: 0.78rem;
}}
footer a {{ color: var(--accent); }}
</style>
</head>
<body>
<div class="container">

<header>
    <h1>USDC Lending <span>APY Comparison</span> — Avalanche</h1>
    <p class="sub">Snow Mind target markets &middot; 90-day historical view</p>
    <p class="ts">Data from DefiLlama &middot; {fetch_time}</p>
</header>

<!-- KPI Cards -->
<div class="kpi-grid">
    <div class="kpi">
        <div class="k-label">Highest Current APY</div>
        <div class="k-val" style="color:var(--green)">{best['current_apy']:.2f}%</div>
        <div class="k-label" style="margin-top:4px">{best['label']}</div>
    </div>
    <div class="kpi">
        <div class="k-label">Lowest Current APY</div>
        <div class="k-val" style="color:var(--yellow)">{worst['current_apy']:.2f}%</div>
        <div class="k-label" style="margin-top:4px">{worst['label']}</div>
    </div>
    <div class="kpi">
        <div class="k-label">Current Spread</div>
        <div class="k-val" style="color:var(--avax)">{spread:.2f}%</div>
        <div class="k-label" style="margin-top:4px">Best − Worst</div>
    </div>
    <div class="kpi">
        <div class="k-label">Markets Tracked</div>
        <div class="k-val" style="color:var(--accent)">6</div>
        <div class="k-label" style="margin-top:4px">USDC lending</div>
    </div>
    <div class="kpi">
        <div class="k-label">Combined TVL</div>
        <div class="k-val">{fmt_usd(sum(p.get('current_tvl') or 0 for p in processed))}</div>
        <div class="k-label" style="margin-top:4px">Across 6 markets</div>
    </div>
</div>

<!-- Legend -->
<div class="legend-grid">
{"".join(f'''<div class="legend-item">
    <div class="legend-dot" style="background:{p['color']}"></div>
    <div><div class="legend-name">{p['label']}</div><div class="legend-tag">{p['tag']}</div></div>
</div>''' for p in processed)}
</div>

<!-- APY Chart -->
<section>
    <h2>APY Comparison — Last 90 Days</h2>
    <p class="insight">This chart shows the lending APY (supply rate) for USDC across all 6 target markets.
    The spread between the highest and lowest APY at any point in time represents the optimisation
    opportunity — capital rebalancing by Snow Mind captures this differential.</p>
    <div class="chart-wrap" style="height:420px"><canvas id="apyChart"></canvas></div>
    <p class="note">APY = base lending rate + any reward incentives. Gaps indicate the pool did not
    yet exist or had no data for that date.</p>
</section>

<!-- TVL Chart -->
<section>
    <h2>TVL Comparison — Last 90 Days</h2>
    <p class="insight">TVL shows how much capital is deposited in each market. Larger TVL generally
    means more stable rates but lower APY. Smaller pools may offer higher yields but with more
    volatility — exactly the tradeoff Snow Mind navigates.</p>
    <div class="chart-wrap" style="height:360px"><canvas id="tvlChart"></canvas></div>
</section>

<!-- Data Table -->
<section>
    <h2>Market Summary</h2>
    <p class="insight">Current rates, averages, and volatility across all 6 markets. APY Volatility
    (standard deviation over 30 days) indicates rate stability — lower is more predictable.</p>
    <div style="overflow-x:auto">
    <table>
        <thead><tr>
            <th>Market</th><th>Strategy</th><th>APY Now</th><th>7d Avg</th>
            <th>30d Avg</th><th>30d Vol</th><th>Base APY</th><th>Reward APY</th><th>TVL</th>
        </tr></thead>
        <tbody>{table_rows}</tbody>
    </table>
    </div>
</section>

</div>

<footer>
    Snow Mind Market Research &middot; Data from <a href="https://defillama.com">DefiLlama</a>
    &middot; Generated {fetch_time}
</footer>

<script>
const GRID = 'rgba(255,255,255,0.06)';
const TICK = '#8b949e';
Chart.defaults.color = TICK;
Chart.defaults.borderColor = GRID;

const labels = {labels_json};

new Chart(document.getElementById('apyChart'), {{
    type: 'line',
    data: {{ labels, datasets: {ds_apy_json} }},
    options: {{
        responsive: true,
        maintainAspectRatio: false,
        interaction: {{ mode: 'index', intersect: false }},
        plugins: {{
            tooltip: {{
                callbacks: {{
                    label: ctx => {{
                        if (ctx.parsed.y == null) return null;
                        return ctx.dataset.label + ': ' + ctx.parsed.y.toFixed(2) + '%';
                    }}
                }}
            }},
            legend: {{ display: true, position: 'top', labels: {{ usePointStyle: true, pointStyle: 'line', padding: 16 }} }}
        }},
        scales: {{
            y: {{
                title: {{ display: true, text: 'APY (%)' }},
                ticks: {{ callback: v => v.toFixed(1) + '%' }},
                grid: {{ color: GRID }},
                beginAtZero: true,
            }},
            x: {{
                ticks: {{ maxTicksLimit: 15, maxRotation: 45 }},
                grid: {{ display: false }}
            }}
        }}
    }}
}});

new Chart(document.getElementById('tvlChart'), {{
    type: 'line',
    data: {{ labels, datasets: {ds_tvl_json} }},
    options: {{
        responsive: true,
        maintainAspectRatio: false,
        interaction: {{ mode: 'index', intersect: false }},
        plugins: {{
            tooltip: {{
                callbacks: {{
                    label: ctx => {{
                        if (ctx.parsed.y == null) return null;
                        var v = ctx.parsed.y;
                        if (v >= 1e6) return ctx.dataset.label + ': $' + (v/1e6).toFixed(1) + 'M';
                        if (v >= 1e3) return ctx.dataset.label + ': $' + (v/1e3).toFixed(0) + 'K';
                        return ctx.dataset.label + ': $' + v.toFixed(0);
                    }}
                }}
            }},
            legend: {{ display: true, position: 'top', labels: {{ usePointStyle: true, pointStyle: 'line', padding: 16 }} }}
        }},
        scales: {{
            y: {{
                title: {{ display: true, text: 'TVL (USD)' }},
                ticks: {{ callback: v => v >= 1e6 ? '$' + (v/1e6).toFixed(0) + 'M' : '$' + (v/1e3).toFixed(0) + 'K' }},
                grid: {{ color: GRID }},
            }},
            x: {{
                ticks: {{ maxTicksLimit: 15, maxRotation: 45 }},
                grid: {{ display: false }}
            }}
        }}
    }}
}});
</script>
</body>
</html>"""

    return html


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  Snow Mind — APY Comparison Dashboard Generator")
    print("=" * 60)

    fetch_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    print("\nFetching data from DefiLlama Yields API...")
    results = fetch_all()

    print("\nProcessing data (90-day window)...")
    processed, common_dates = process(results)

    print(f"\nGenerating dashboard...")
    html = build_html(processed, common_dates, fetch_time)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\n{'=' * 60}")
    print(f"  Dashboard generated: {OUTPUT_FILE}")
    print(f"  Date range: {common_dates[0]} to {common_dates[-1]}" if common_dates else "")
    print(f"  Data points per pool: {len(common_dates)}")
    for p in processed:
        apy = p.get("current_apy")
        apy_s = f"{apy:.2f}%" if apy is not None else "N/A"
        print(f"  {p['label']:<25} APY: {apy_s:>8}   TVL: ${(p.get('current_tvl') or 0)/1e6:.1f}M")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
