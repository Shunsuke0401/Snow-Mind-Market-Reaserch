#!/usr/bin/env python3
"""
Snow Mind — Utilization Rate Dashboard Generator

Reads cached lend/borrow data from data/util_*.json (fetched from
DefiLlama's chartLendBorrow endpoint) and generates an HTML page
with historical utilization-rate charts for 6 Avalanche lending markets.
"""

import json
import os
from datetime import datetime, timezone, timedelta

DATA_DIR = "data"
OUTPUT_FILE = "utilization.html"

POOLS = [
    {
        "file": "util_Aave_V3.json",
        "label": "Aave V3",
        "tag": "Blue chip conservative",
        "color": "#9b7ddb",
        "border_dash": [],
    },
    {
        "file": "util_Benqi.json",
        "label": "Benqi",
        "tag": "Avalanche native conservative",
        "color": "#1cc0e0",
        "border_dash": [],
    },
    {
        "file": "util_Spark.json",
        "label": "Spark",
        "tag": "Base-layer parking",
        "color": "#f5ac37",
        "border_dash": [],
    },
    {
        "file": "util_Euler_9Summits.json",
        "label": "Euler (9Summits)",
        "tag": "Curated vault, higher yield",
        "color": "#e84142",
        "border_dash": [],
    },
    {
        "file": "util_Silo_savUSD_USDC.json",
        "label": "Silo (savUSD/USDC)",
        "tag": "Isolated lending, Avant collateral",
        "color": "#3fb950",
        "border_dash": [5, 5],
    },
    {
        "file": "util_Silo_sUSDp_USDC.json",
        "label": "Silo (sUSDp/USDC)",
        "tag": "Isolated lending, Parallel collateral",
        "color": "#58a6ff",
        "border_dash": [5, 5],
    },
]


def load_data():
    cutoff = datetime.now(timezone.utc) - timedelta(days=90)
    cutoff_str = cutoff.strftime("%Y-%m-%d")

    all_dates = set()
    pool_data = []

    for cfg in POOLS:
        path = os.path.join(DATA_DIR, cfg["file"])
        if not os.path.exists(path):
            print(f"  MISSING: {cfg['file']} — skipping {cfg['label']}")
            pool_data.append({**cfg, "daily": {}, "available": False})
            continue

        with open(path) as f:
            raw = json.load(f)

        daily = {}
        for pt in raw:
            ts = pt.get("timestamp", "")
            day = ts[:10]
            if day < cutoff_str:
                continue
            supply = pt.get("totalSupplyUsd") or 0
            borrow = pt.get("totalBorrowUsd") or 0
            util = (borrow / supply * 100) if supply > 0 else 0
            borrow_apy = pt.get("apyBaseBorrow") or 0
            supply_apy = pt.get("apyBase") or 0
            daily[day] = {
                "util": round(util, 2),
                "supply": supply,
                "borrow": borrow,
                "borrow_apy": round(borrow_apy, 4),
                "supply_apy": round(supply_apy, 4),
            }
            all_dates.add(day)

        pool_data.append({**cfg, "daily": daily, "available": True})
        print(f"  Loaded: {cfg['label']} — {len(daily)} days")

    common_dates = sorted(all_dates)
    return pool_data, common_dates


def fmt_usd(v):
    if v is None:
        return "N/A"
    if abs(v) >= 1e9:
        return f"${v/1e9:.2f}B"
    if abs(v) >= 1e6:
        return f"${v/1e6:.1f}M"
    if abs(v) >= 1e3:
        return f"${v/1e3:.0f}K"
    return f"${v:,.0f}"


def build_html(pool_data, common_dates, fetch_time):
    # ── Prepare chart datasets ──
    ds_util = []
    ds_borrow_apy = []
    ds_supply = []
    ds_borrow = []

    for p in pool_data:
        if not p["available"]:
            continue
        utils = []
        borrow_apys = []
        supplies = []
        borrows = []
        for day in common_dates:
            d = p["daily"].get(day)
            if d:
                utils.append(d["util"])
                borrow_apys.append(d["borrow_apy"])
                supplies.append(d["supply"])
                borrows.append(d["borrow"])
            else:
                utils.append(None)
                borrow_apys.append(None)
                supplies.append(None)
                borrows.append(None)

        base = {
            "label": p["label"],
            "borderColor": p["color"],
            "backgroundColor": p["color"] + "18",
            "borderDash": p["border_dash"],
            "tension": 0.3,
            "pointRadius": 0,
            "pointHoverRadius": 5,
            "borderWidth": 2.5,
            "spanGaps": True,
        }
        ds_util.append({**base, "data": utils, "fill": False})
        ds_borrow_apy.append({**base, "data": borrow_apys, "fill": False})
        ds_supply.append({
            **base,
            "data": supplies,
            "backgroundColor": p["color"] + "22",
            "fill": True,
            "borderWidth": 2,
        })
        ds_borrow.append({
            **base,
            "data": borrows,
            "backgroundColor": p["color"] + "22",
            "fill": True,
            "borderWidth": 2,
        })

    labels_json = json.dumps([d[5:] for d in common_dates])
    ds_util_json = json.dumps(ds_util)
    ds_borrow_apy_json = json.dumps(ds_borrow_apy)
    ds_supply_json = json.dumps(ds_supply)
    ds_borrow_json = json.dumps(ds_borrow)

    # ── Current stats table ──
    table_rows = ""
    available = [p for p in pool_data if p["available"] and p["daily"]]
    for p in sorted(available, key=lambda x: list(x["daily"].values())[-1]["util"] if x["daily"] else 0, reverse=True):
        last_day = max(p["daily"].keys()) if p["daily"] else None
        if not last_day:
            continue
        cur = p["daily"][last_day]
        util = cur["util"]

        # 7d and 30d averages
        sorted_days = sorted(p["daily"].keys())
        vals_7 = [p["daily"][d]["util"] for d in sorted_days[-7:]]
        vals_30 = [p["daily"][d]["util"] for d in sorted_days[-30:]]
        avg7 = sum(vals_7) / len(vals_7) if vals_7 else 0
        avg30 = sum(vals_30) / len(vals_30) if vals_30 else 0

        # Volatility
        if len(vals_30) > 1:
            mean = sum(vals_30) / len(vals_30)
            std = (sum((x - mean)**2 for x in vals_30) / len(vals_30)) ** 0.5
        else:
            std = 0

        # Color code utilization
        if util > 85:
            util_class = "util-high"
        elif util > 60:
            util_class = "util-mid"
        else:
            util_class = "util-low"

        dot = f'<span style="color:{p["color"]}">●</span>'
        table_rows += f"""<tr>
            <td>{dot} {p['label']}</td>
            <td class="tag">{p['tag']}</td>
            <td class="num {util_class}">{util:.1f}%</td>
            <td class="num">{avg7:.1f}%</td>
            <td class="num">{avg30:.1f}%</td>
            <td class="num">{std:.1f}%</td>
            <td class="num">{cur['supply_apy']:.2f}%</td>
            <td class="num">{cur['borrow_apy']:.2f}%</td>
            <td class="num">{fmt_usd(cur['supply'])}</td>
            <td class="num">{fmt_usd(cur['borrow'])}</td>
        </tr>\n"""

    # ── KPI values ──
    kpis = []
    for p in available:
        if p["daily"]:
            last = list(p["daily"].values())[-1]
            kpis.append({"label": p["label"], "util": last["util"], "color": p["color"]})
    highest = max(kpis, key=lambda x: x["util"]) if kpis else {"label": "—", "util": 0, "color": "#fff"}
    lowest = min(kpis, key=lambda x: x["util"]) if kpis else {"label": "—", "util": 0, "color": "#fff"}
    avg_util = sum(k["util"] for k in kpis) / len(kpis) if kpis else 0
    total_supply = sum(list(p["daily"].values())[-1]["supply"] for p in available if p["daily"])
    total_borrow = sum(list(p["daily"].values())[-1]["borrow"] for p in available if p["daily"])

    # ── Legend ──
    legend_html = ""
    for p in pool_data:
        if not p["available"]:
            legend_html += f"""<div class="legend-item dimmed">
                <div class="legend-dot" style="background:{p['color']};opacity:0.3"></div>
                <div><div class="legend-name">{p['label']} <span style="color:var(--yellow)">(no data)</span></div>
                <div class="legend-tag">{p['tag']}</div></div></div>"""
        else:
            legend_html += f"""<div class="legend-item">
                <div class="legend-dot" style="background:{p['color']}"></div>
                <div><div class="legend-name">{p['label']}</div>
                <div class="legend-tag">{p['tag']}</div></div></div>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Snow Mind — Utilization Rate Dashboard (Avalanche)</title>
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

table {{ width: 100%; border-collapse: collapse; font-size: 0.82rem; }}
th, td {{ padding: 9px 10px; text-align: left; border-bottom: 1px solid var(--border); }}
th {{ color: var(--text2); font-weight: 600; font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.03em; }}
td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
td.tag {{ color: var(--text2); font-size: 0.75rem; font-style: italic; max-width: 180px; }}
tr:hover {{ background: rgba(88,166,255,0.04); }}
.util-high {{ color: var(--avax); font-weight: 700; }}
.util-mid {{ color: var(--yellow); font-weight: 700; }}
.util-low {{ color: var(--green); font-weight: 700; }}

.legend-grid {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: 10px; margin-bottom: 20px;
}}
.legend-item {{
    display: flex; align-items: center; gap: 10px; padding: 8px 12px;
    background: rgba(255,255,255,0.02); border-radius: 6px;
}}
.legend-item.dimmed {{ opacity: 0.5; }}
.legend-dot {{ width: 14px; height: 14px; border-radius: 50%; flex-shrink: 0; }}
.legend-name {{ font-weight: 600; font-size: 0.9rem; }}
.legend-tag {{ color: var(--text2); font-size: 0.78rem; }}

.note {{ color: var(--text2); font-size: 0.82rem; margin-top: 14px; font-style: italic; }}
.grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }}
@media (max-width: 900px) {{ .grid-2 {{ grid-template-columns: 1fr; }} }}

footer {{ text-align: center; padding: 28px; color: var(--text2); font-size: 0.78rem; }}
footer a {{ color: var(--accent); }}
</style>
</head>
<body>
<div class="container">

<header>
    <h1><span>Utilization Rate</span> Dashboard — Avalanche</h1>
    <p class="sub">Supply vs. Borrow dynamics across Snow Mind's 6 target USDC markets</p>
    <p class="ts">Data from DefiLlama &middot; {fetch_time}</p>
</header>

<div class="kpi-grid">
    <div class="kpi">
        <div class="k-label">Highest Utilization</div>
        <div class="k-val" style="color:var(--avax)">{highest['util']:.1f}%</div>
        <div class="k-label" style="margin-top:4px">{highest['label']}</div>
    </div>
    <div class="kpi">
        <div class="k-label">Lowest Utilization</div>
        <div class="k-val" style="color:var(--green)">{lowest['util']:.1f}%</div>
        <div class="k-label" style="margin-top:4px">{lowest['label']}</div>
    </div>
    <div class="kpi">
        <div class="k-label">Average Utilization</div>
        <div class="k-val" style="color:var(--yellow)">{avg_util:.1f}%</div>
        <div class="k-label" style="margin-top:4px">Across all markets</div>
    </div>
    <div class="kpi">
        <div class="k-label">Total Supplied</div>
        <div class="k-val">{fmt_usd(total_supply)}</div>
        <div class="k-label" style="margin-top:4px">6 markets combined</div>
    </div>
    <div class="kpi">
        <div class="k-label">Total Borrowed</div>
        <div class="k-val">{fmt_usd(total_borrow)}</div>
        <div class="k-label" style="margin-top:4px">6 markets combined</div>
    </div>
</div>

<div class="legend-grid">{legend_html}</div>

<!-- Utilization Rate Chart -->
<section>
    <h2>Utilization Rate — Last 90 Days</h2>
    <p class="insight">Utilization rate = Total Borrowed / Total Supplied. Higher utilization means
    more demand for borrowing relative to deposits, which drives up both supply and borrow APY.
    Markets near the kink point (typically 80-90%) see sharp APY increases — these transitions are
    the highest-value rebalancing signals for Snow Mind.</p>
    <div class="chart-wrap" style="height:420px"><canvas id="utilChart"></canvas></div>
    <p class="note">Spark shows 0% utilization because it operates as a fixed-rate savings vault
    (DSR) rather than a traditional borrow/lend market.</p>
</section>

<!-- Borrow APY Chart -->
<section>
    <h2>Borrow APY — Last 90 Days</h2>
    <p class="insight">The cost of borrowing from each market. A higher borrow APY means borrowers
    pay more, which flows to depositors as supply yield. When borrow APY spikes, the supply APY follows
    — Snow Mind can front-run these moves by rebalancing into the market before rates fully adjust.</p>
    <div class="chart-wrap" style="height:360px"><canvas id="borrowApyChart"></canvas></div>
</section>

<!-- Supply vs Borrow Volume -->
<section>
    <h2>Supply &amp; Borrow Volume — Last 90 Days</h2>
    <p class="insight">Absolute capital deployed. The ratio between supply and borrow volume
    determines utilization. Rapid borrow growth with stable supply is a bullish signal for
    rising yields.</p>
    <div class="grid-2">
        <div class="chart-wrap" style="height:300px">
            <h3 style="font-size:0.9rem;color:var(--text2);margin-bottom:8px">Total Supplied</h3>
            <canvas id="supplyChart"></canvas>
        </div>
        <div class="chart-wrap" style="height:300px">
            <h3 style="font-size:0.9rem;color:var(--text2);margin-bottom:8px">Total Borrowed</h3>
            <canvas id="borrowChart"></canvas>
        </div>
    </div>
</section>

<!-- Data Table -->
<section>
    <h2>Market Utilization Summary</h2>
    <p class="insight">Current state and recent averages. Red = high utilization (&gt;85%),
    yellow = moderate (60-85%), green = low (&lt;60%). Volatility shows how unstable the
    utilization rate has been — higher volatility = more rebalancing opportunity.</p>
    <div style="overflow-x:auto">
    <table>
        <thead><tr>
            <th>Market</th><th>Strategy</th><th>Util Now</th><th>7d Avg</th>
            <th>30d Avg</th><th>30d Vol</th><th>Supply APY</th><th>Borrow APY</th>
            <th>Supplied</th><th>Borrowed</th>
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
Chart.defaults.color = '#8b949e';
Chart.defaults.borderColor = GRID;
const labels = {labels_json};
const legendOpts = {{ display: true, position: 'top', labels: {{ usePointStyle: true, pointStyle: 'line', padding: 16 }} }};

new Chart(document.getElementById('utilChart'), {{
    type: 'line',
    data: {{ labels, datasets: {ds_util_json} }},
    options: {{
        responsive: true, maintainAspectRatio: false,
        interaction: {{ mode: 'index', intersect: false }},
        plugins: {{
            tooltip: {{ callbacks: {{ label: ctx => ctx.parsed.y != null ? ctx.dataset.label + ': ' + ctx.parsed.y.toFixed(1) + '%' : null }} }},
            legend: legendOpts
        }},
        scales: {{
            y: {{ title: {{ display: true, text: 'Utilization (%)' }}, ticks: {{ callback: v => v + '%' }}, grid: {{ color: GRID }}, min: 0, max: 100 }},
            x: {{ ticks: {{ maxTicksLimit: 15, maxRotation: 45 }}, grid: {{ display: false }} }}
        }}
    }}
}});

new Chart(document.getElementById('borrowApyChart'), {{
    type: 'line',
    data: {{ labels, datasets: {ds_borrow_apy_json} }},
    options: {{
        responsive: true, maintainAspectRatio: false,
        interaction: {{ mode: 'index', intersect: false }},
        plugins: {{
            tooltip: {{ callbacks: {{ label: ctx => ctx.parsed.y != null ? ctx.dataset.label + ': ' + ctx.parsed.y.toFixed(2) + '%' : null }} }},
            legend: legendOpts
        }},
        scales: {{
            y: {{ title: {{ display: true, text: 'Borrow APY (%)' }}, ticks: {{ callback: v => v.toFixed(1) + '%' }}, grid: {{ color: GRID }}, beginAtZero: true }},
            x: {{ ticks: {{ maxTicksLimit: 15, maxRotation: 45 }}, grid: {{ display: false }} }}
        }}
    }}
}});

const tvlTooltip = {{ callbacks: {{ label: ctx => {{
    if (ctx.parsed.y == null) return null;
    var v = ctx.parsed.y;
    return ctx.dataset.label + ': $' + (v >= 1e6 ? (v/1e6).toFixed(1) + 'M' : (v/1e3).toFixed(0) + 'K');
}} }} }};
const tvlTick = {{ callback: v => v >= 1e6 ? '$' + (v/1e6).toFixed(0) + 'M' : '$' + (v/1e3).toFixed(0) + 'K' }};

new Chart(document.getElementById('supplyChart'), {{
    type: 'line',
    data: {{ labels, datasets: {ds_supply_json} }},
    options: {{
        responsive: true, maintainAspectRatio: false,
        interaction: {{ mode: 'index', intersect: false }},
        plugins: {{ tooltip: tvlTooltip, legend: {{ display: false }} }},
        scales: {{
            y: {{ ticks: tvlTick, grid: {{ color: GRID }} }},
            x: {{ ticks: {{ maxTicksLimit: 10, maxRotation: 45 }}, grid: {{ display: false }} }}
        }}
    }}
}});

new Chart(document.getElementById('borrowChart'), {{
    type: 'line',
    data: {{ labels, datasets: {ds_borrow_json} }},
    options: {{
        responsive: true, maintainAspectRatio: false,
        interaction: {{ mode: 'index', intersect: false }},
        plugins: {{ tooltip: tvlTooltip, legend: {{ display: false }} }},
        scales: {{
            y: {{ ticks: tvlTick, grid: {{ color: GRID }} }},
            x: {{ ticks: {{ maxTicksLimit: 10, maxRotation: 45 }}, grid: {{ display: false }} }}
        }}
    }}
}});
</script>
</body>
</html>"""

    return html


def main():
    print("=" * 60)
    print("  Snow Mind — Utilization Rate Dashboard")
    print("=" * 60)

    fetch_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    print("\nLoading cached data from data/util_*.json ...")
    pool_data, common_dates = load_data()

    available = sum(1 for p in pool_data if p["available"])
    print(f"\nAvailable: {available}/{len(pool_data)} pools")
    print(f"Date range: {common_dates[0]} to {common_dates[-1]}" if common_dates else "No data")

    print(f"\nGenerating {OUTPUT_FILE} ...")
    html = build_html(pool_data, common_dates, fetch_time)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\n{'=' * 60}")
    print(f"  Dashboard written: {OUTPUT_FILE}")
    print(f"  Pools with data: {available}/6")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
