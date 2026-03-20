#!/usr/bin/env python3
"""
Snow Mind — Unified Dashboard Generator

Reads cached JSON data from data/ and generates a single index.html with
three tabs: Ecosystem, APY Comparison, Utilization.
No network calls — all data comes from previously fetched files.
"""

import json
import os
import math
from datetime import datetime, timezone, timedelta

DATA_DIR = "data"
OUTPUT_FILE = "index.html"

MARKET_POOLS = [
    {"apy_file": "apy_Aave_V3.json",           "util_file": "util_Aave_V3.json",
     "label": "Aave V3",                        "tag": "Blue chip conservative",
     "color": "#9b7ddb", "border_dash": []},
    {"apy_file": "apy_Benqi.json",              "util_file": "util_Benqi.json",
     "label": "Benqi",                          "tag": "Avalanche native conservative",
     "color": "#1cc0e0", "border_dash": []},
    {"apy_file": "apy_Spark.json",              "util_file": "util_Spark.json",
     "label": "Spark",                          "tag": "Base-layer parking",
     "color": "#f5ac37", "border_dash": []},
    {"apy_file": "apy_Euler_9Summits.json",     "util_file": "util_Euler_9Summits.json",
     "label": "Euler (9Summits)",               "tag": "Curated vault, higher yield",
     "color": "#e84142", "border_dash": []},
    {"apy_file": "apy_Silo_savUSD_USDC.json",  "util_file": "util_Silo_savUSD_USDC.json",
     "label": "Silo (savUSD/USDC)",             "tag": "Isolated lending, Avant collateral",
     "color": "#3fb950", "border_dash": [5, 5]},
    {"apy_file": "apy_Silo_sUSDp_USDC.json",   "util_file": "util_Silo_sUSDp_USDC.json",
     "label": "Silo (sUSDp/USDC)",              "tag": "Isolated lending, Parallel collateral",
     "color": "#58a6ff", "border_dash": [5, 5]},
]

TARGET_LENDING_SLUGS = {"benqi-lending", "aave-v3", "euler-v2", "fluid"}
TARGET_LENDING_KEYWORDS = {"benqi", "aave", "euler", "fluid"}
COMPETITOR_SLUGS = ["giza", "zyfai", "almanak"]

# ─── Helpers ────────────────────────────────────────────────────────────

def load_json(filename):
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


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


def fmt_pct(v):
    if v is None:
        return "—"
    return f"{v:+.2f}%"


def ts_to_short(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%b '%y")


# ─── Ecosystem Processing ──────────────────────────────────────────────

def process_ecosystem():
    d = {}
    twelve_months_ago = datetime.now(timezone.utc).timestamp() - 365 * 86400

    # 1. Avalanche TVL trend
    tvl_hist = load_json("Avalanche_historical_TVL.json") or []
    tvl_series = [r for r in tvl_hist if r.get("date", 0) >= twelve_months_ago]
    d["tvl_labels"] = json.dumps([ts_to_short(r["date"]) for r in tvl_series][::7])
    d["tvl_values"] = json.dumps([round(r["tvl"] / 1e6, 2) for r in tvl_series][::7])
    d["current_avax_tvl"] = tvl_series[-1]["tvl"] if tvl_series else 0

    # 2. Lending protocols
    all_proto = load_json("All_protocols.json") or []
    lending = []
    for p in all_proto:
        if "Avalanche" not in (p.get("chains") or []):
            continue
        if (p.get("category") or "").strip().lower() != "lending":
            continue
        slug = p.get("slug", "")
        name_lower = p.get("name", "").lower()
        is_target = slug in TARGET_LENDING_SLUGS or any(kw in name_lower for kw in TARGET_LENDING_KEYWORDS)
        avax_tvl = (p.get("chainTvls") or {}).get("Avalanche")
        lending.append({
            "name": p.get("name", "Unknown"), "slug": slug,
            "total_tvl": p.get("tvl") or 0, "avax_tvl": avax_tvl,
            "change_1d": p.get("change_1d"), "change_7d": p.get("change_7d"),
            "is_target": is_target,
        })
    lending.sort(key=lambda x: (x["avax_tvl"] or x["total_tvl"] or 0), reverse=True)
    d["lending"] = lending
    d["total_lending_tvl"] = sum((p["avax_tvl"] or 0) for p in lending)
    d["num_lending"] = len(lending)

    # 3. Stablecoin supply trend
    sc_chart = load_json("Avalanche_stablecoin_chart.json") or []
    sc_series = []
    for r in sc_chart:
        ts = int(r.get("date", 0))
        if ts < twelve_months_ago:
            continue
        circ = r.get("totalCirculatingUSD") or r.get("totalCirculating") or {}
        val = sum(v for v in circ.values() if isinstance(v, (int, float)))
        sc_series.append({"date": ts, "supply": val})
    d["sc_labels"] = json.dumps([ts_to_short(r["date"]) for r in sc_series][::7])
    d["sc_values"] = json.dumps([round(r["supply"] / 1e6, 2) for r in sc_series][::7])
    d["current_sc_supply"] = sc_series[-1]["supply"] if sc_series else 0

    # 4. Stablecoin composition
    stables_raw = load_json("All_stablecoins.json") or {}
    if isinstance(stables_raw, dict):
        stables_raw = stables_raw.get("peggedAssets", [])
    breakdown = {}
    for sc in stables_raw:
        if not isinstance(sc, dict):
            continue
        symbol = sc.get("symbol", "??")
        avax_entry = (sc.get("chainCirculating") or {}).get("Avalanche")
        if avax_entry is None:
            continue
        if isinstance(avax_entry, dict):
            cur = avax_entry.get("current", avax_entry)
            val = cur.get("peggedUSD", 0) if isinstance(cur, dict) else 0
        elif isinstance(avax_entry, (int, float)):
            val = avax_entry
        else:
            val = 0
        if val > 0:
            breakdown[symbol] = breakdown.get(symbol, 0) + val
    sorted_s = sorted(breakdown.items(), key=lambda x: x[1], reverse=True)
    pie, others = {}, 0.0
    for i, (sym, val) in enumerate(sorted_s):
        if i < 5:
            pie[sym] = val
        else:
            others += val
    if others > 0:
        pie["Others"] = others
    d["pie_labels"] = json.dumps(list(pie.keys()))
    d["pie_values"] = json.dumps([round(v / 1e6, 2) for v in pie.values()])

    # 5. Competitors
    competitors = {}
    max_comp_tvl = 0
    for slug in COMPETITOR_SLUGS:
        cdata = load_json(f"Competitor_{slug}.json")
        if not cdata:
            continue
        tvl_raw = cdata.get("tvl")
        if isinstance(tvl_raw, list):
            hist = [{"date": pt.get("date", 0), "tvl": pt.get("totalLiquidityUSD", 0)} for pt in tvl_raw]
            current = hist[-1]["tvl"] if hist else 0
        else:
            current = tvl_raw or 0
            hist = []
        max_comp_tvl = max(max_comp_tvl, current)
        competitors[slug] = {
            "name": cdata.get("name", slug), "tvl": current,
            "chains": cdata.get("chains", []),
            "description": (cdata.get("description") or "")[:200],
            "history": [h for h in hist if h["date"] >= twelve_months_ago],
        }
    d["competitors"] = competitors
    d["max_comp_tvl"] = max_comp_tvl

    # Competitor chart data
    if competitors:
        comp_colors = ["#f59e0b", "#10b981", "#8b5cf6", "#ec4899"]
        all_dates = sorted({h["date"] for c in competitors.values() for h in c["history"]})
        d["comp_labels"] = json.dumps([ts_to_short(dt) for dt in all_dates][::7])
        datasets = []
        for i, (slug, cdata) in enumerate(competitors.items()):
            tvl_map = {h["date"]: h["tvl"] for h in cdata["history"]}
            vals = [round(tvl_map.get(dt, 0) / 1e6, 2) for dt in all_dates][::7]
            datasets.append({
                "label": cdata["name"], "data": vals,
                "borderColor": comp_colors[i % len(comp_colors)],
                "backgroundColor": comp_colors[i % len(comp_colors)] + "33",
                "fill": True, "tension": 0.3,
            })
        d["comp_datasets"] = json.dumps(datasets)
    else:
        d["comp_labels"] = "[]"
        d["comp_datasets"] = "[]"

    # 6. Lending fees
    fees_raw = load_json("Avalanche_fees_overview.json") or {}
    fee_protocols = fees_raw.get("protocols") or []
    lending_fees = []
    for p in fee_protocols:
        if (p.get("category") or "").lower() not in {"lending", "cdp"}:
            continue
        lending_fees.append({
            "name": p.get("name", "Unknown"),
            "fees_24h": p.get("total24h") or p.get("dailyFees") or 0,
            "fees_7d": p.get("total7d") or 0,
            "change_1d": p.get("change_1d"),
        })
    lending_fees.sort(key=lambda x: x["fees_24h"], reverse=True)
    d["lending_fees"] = lending_fees

    # 7. Chain TVL ranking
    chains_raw = load_json("All_chains_TVL.json") or []
    chains = sorted([{"name": c.get("name", "?"), "tvl": c.get("tvl", 0)} for c in chains_raw],
                    key=lambda x: x["tvl"], reverse=True)[:15]
    d["chain_labels"] = json.dumps([c["name"] for c in chains])
    d["chain_values"] = json.dumps([round(c["tvl"] / 1e9, 2) for c in chains])
    d["chain_colors"] = json.dumps(["#e84142" if c["name"] == "Avalanche" else "#3b82f6" for c in chains])
    d["top_chains"] = chains

    return d


# ─── APY Processing ────────────────────────────────────────────────────

def process_apy():
    cutoff_str = (datetime.now(timezone.utc) - timedelta(days=90)).strftime("%Y-%m-%d")
    all_dates = set()
    pool_series = []

    for cfg in MARKET_POOLS:
        raw = load_json(cfg["apy_file"]) or []
        daily = {}
        for pt in raw:
            day = pt.get("timestamp", "")[:10]
            if day >= cutoff_str:
                daily[day] = {
                    "apy": pt.get("apy") or 0,
                    "apyBase": pt.get("apyBase") or 0,
                    "apyReward": pt.get("apyReward") or 0,
                    "tvl": pt.get("tvlUsd") or 0,
                }
                all_dates.add(day)
        pool_series.append(daily)

    common = sorted(all_dates)
    results = []
    for i, cfg in enumerate(MARKET_POOLS):
        series = pool_series[i]
        apys = [round(series[d]["apy"], 4) if d in series else None for d in common]
        tvls = [round(series[d]["tvl"], 2) if d in series else None for d in common]
        last = series.get(common[-1]) if common else None
        results.append({
            "label": cfg["label"], "tag": cfg["tag"],
            "color": cfg["color"], "border_dash": cfg["border_dash"],
            "apys": apys, "tvls": tvls,
            "current_apy": last["apy"] if last else None,
            "current_apy_base": last["apyBase"] if last else None,
            "current_apy_reward": last.get("apyReward") if last else None,
            "current_tvl": last["tvl"] if last else None,
        })

    return results, common


# ─── Utilization Processing ────────────────────────────────────────────

def process_util():
    cutoff_str = (datetime.now(timezone.utc) - timedelta(days=90)).strftime("%Y-%m-%d")
    all_dates = set()
    pool_data = []

    for cfg in MARKET_POOLS:
        raw = load_json(cfg["util_file"]) or []
        daily = {}
        for pt in raw:
            day = pt.get("timestamp", "")[:10]
            if day < cutoff_str:
                continue
            supply = pt.get("totalSupplyUsd") or 0
            borrow = pt.get("totalBorrowUsd") or 0
            util = (borrow / supply * 100) if supply > 0 else 0
            daily[day] = {
                "util": round(util, 2), "supply": supply, "borrow": borrow,
                "borrow_apy": round(pt.get("apyBaseBorrow") or 0, 4),
                "supply_apy": round(pt.get("apyBase") or 0, 4),
            }
            all_dates.add(day)
        pool_data.append({
            **cfg, "daily": daily, "available": len(daily) > 0,
        })

    common = sorted(all_dates)
    return pool_data, common


# ─── HTML Builders ─────────────────────────────────────────────────────

def build_ecosystem_html(eco):
    avax_tvl = eco["current_avax_tvl"]
    sc_supply = eco["current_sc_supply"]
    lending_tvl = eco["total_lending_tvl"]
    utilisation = (lending_tvl / sc_supply * 100) if sc_supply > 0 else 0
    avax_rank = next(
        (i + 1 for i, c in enumerate(eco["top_chains"]) if c["name"] == "Avalanche"), "N/A"
    )
    daily_fees = sum(p["fees_24h"] for p in eco["lending_fees"])
    annual_fees = daily_fees * 365

    # Lending table
    lending_rows = ""
    for i, p in enumerate(eco["lending"], 1):
        cls = ' class="target-row"' if p["is_target"] else ""
        badge = ' <span class="badge">Target</span>' if p["is_target"] else ""
        avax_cell = fmt_usd(p["avax_tvl"]) if p["avax_tvl"] else "—"
        lending_rows += f'<tr{cls}><td>{i}</td><td>{p["name"]}{badge}</td><td>{fmt_usd(p["total_tvl"])}</td><td>{avax_cell}</td><td>{fmt_pct(p["change_1d"])}</td><td>{fmt_pct(p["change_7d"])}</td></tr>\n'

    # Fees table
    fees_rows = ""
    for i, p in enumerate(eco["lending_fees"], 1):
        fees_rows += f'<tr><td>{i}</td><td>{p["name"]}</td><td>{fmt_usd(p["fees_24h"])}</td><td>{fmt_usd(p["fees_7d"])}</td><td>{fmt_pct(p["change_1d"])}</td></tr>\n'
    if not fees_rows:
        fees_rows = '<tr><td colspan="5" class="empty-msg">No lending fee data available</td></tr>'

    # Competitor table
    comp_rows = ""
    if eco["competitors"]:
        for slug, c in eco["competitors"].items():
            comp_rows += f'<tr><td>{c["name"]}</td><td>{fmt_usd(c["tvl"])}</td><td>{", ".join(c["chains"][:5]) or "—"}</td><td class="desc-cell">{c["description"] or "—"}</td></tr>\n'
    else:
        comp_rows = '<tr><td colspan="4" class="empty-msg">No competitor data found — first-mover opportunity.</td></tr>'

    comp_chart = '<div class="chart-wrap" style="margin-top:20px"><canvas id="compChart"></canvas></div>' if eco["competitors"] else ""

    # Takeaways
    takeaways = [
        f'Avalanche DeFi TVL stands at <strong>{fmt_usd(avax_tvl)}</strong>, ranking <strong>#{avax_rank}</strong> among all chains.',
        f'<strong>{fmt_usd(sc_supply)}</strong> in stablecoins on Avalanche, but only <strong>{fmt_usd(lending_tvl)}</strong> ({utilisation:.1f}%) deployed in lending — idle capital an optimizer could activate.',
        f'Lending protocols generate ~<strong>{fmt_usd(annual_fees)}/year</strong> in fees — the yield pool Snow Mind optimises across.',
        f'<strong>{eco["num_lending"]}</strong> lending protocols create fragmentation that makes automated rebalancing valuable.',
    ]
    if eco["max_comp_tvl"] == 0:
        takeaways.append('No autonomous yield-optimizer competitors found — <strong>significant first-mover advantage</strong>.')
    else:
        takeaways.append(f'Largest competitor has only <strong>{fmt_usd(eco["max_comp_tvl"])}</strong> TVL — early-stage market.')
    takeaways_li = "\n".join(f"<li>{t}</li>" for t in takeaways)

    return f"""
<!-- KPI Cards -->
<div class="summary-grid">
  <div class="summary-card"><div class="label">Avalanche DeFi TVL</div><div class="value avax">{fmt_usd(avax_tvl)}</div></div>
  <div class="summary-card"><div class="label">Stablecoin Supply</div><div class="value green">{fmt_usd(sc_supply)}</div></div>
  <div class="summary-card"><div class="label">Lending TVL</div><div class="value blue">{fmt_usd(lending_tvl)}</div></div>
  <div class="summary-card"><div class="label">Lending Protocols</div><div class="value yellow">{eco["num_lending"]}</div></div>
  <div class="summary-card"><div class="label">Largest Competitor</div><div class="value">{fmt_usd(eco["max_comp_tvl"]) if eco["max_comp_tvl"] > 0 else "None found"}</div></div>
</div>

<section>
  <h2>Avalanche DeFi TVL Trend</h2>
  <p class="insight">Total capital locked in DeFi on Avalanche over the past 12 months. Growing TVL = expanding yield-optimisation opportunity.</p>
  <div class="chart-wrap"><canvas id="ecoTvlChart"></canvas></div>
</section>

<section>
  <h2>Avalanche Lending Protocol TVLs</h2>
  <p class="insight">Lending protocols Snow Mind optimises across. Highlighted = primary targets (Benqi, Aave V3, Euler, Fluid).</p>
  <div style="overflow-x:auto"><table>
    <thead><tr><th>#</th><th>Protocol</th><th>Total TVL</th><th>Avalanche TVL</th><th>1d Chg</th><th>7d Chg</th></tr></thead>
    <tbody>{lending_rows}</tbody>
  </table></div>
</section>

<section>
  <h2>Stablecoin Supply on Avalanche</h2>
  <p class="insight">Stablecoins available for deposit into lending — Snow Mind's total addressable market for stable-yield strategies.</p>
  <div class="chart-wrap"><canvas id="ecoScChart"></canvas></div>
</section>

<section>
  <h2>Stablecoin Composition</h2>
  <p class="insight">USDC and USDT dominate — initial strategy focus for Snow Mind.</p>
  <div class="chart-wrap" style="max-width:480px;margin:0 auto"><canvas id="ecoPieChart"></canvas></div>
</section>

<section>
  <h2>Yield Optimizer Competitor TVL</h2>
  <p class="insight">Tracking Giza, ZyfAI, Almanak — absent/minimal TVL signals early-stage market.</p>
  <div style="overflow-x:auto"><table>
    <thead><tr><th>Protocol</th><th>TVL</th><th>Chains</th><th>Description</th></tr></thead>
    <tbody>{comp_rows}</tbody>
  </table></div>
  {comp_chart}
</section>

<section>
  <h2>Lending Protocol Fee Revenue</h2>
  <p class="insight">Fee revenue = yield distributed to depositors. This is what Snow Mind optimises.</p>
  <div style="overflow-x:auto"><table>
    <thead><tr><th>#</th><th>Protocol</th><th>24h Fees</th><th>7d Fees</th><th>1d Chg</th></tr></thead>
    <tbody>{fees_rows}</tbody>
  </table></div>
</section>

<section>
  <h2>Avalanche's Position by Chain TVL</h2>
  <p class="insight">Avalanche is a top-tier chain — large enough to matter, less competition for yield tooling vs Ethereum/Arbitrum.</p>
  <div class="chart-wrap"><canvas id="ecoChainChart"></canvas></div>
</section>

<section class="takeaways">
  <h2>Key Takeaways</h2>
  <ul>{takeaways_li}</ul>
</section>
"""


def build_apy_html(apy_data, common_dates):
    labels = json.dumps([d[5:] for d in common_dates])
    ds_apy = []
    ds_tvl = []
    for p in apy_data:
        base = {
            "label": p["label"], "borderColor": p["color"],
            "borderDash": p["border_dash"], "tension": 0.3,
            "pointRadius": 0, "pointHoverRadius": 5, "borderWidth": 2.5, "spanGaps": True,
        }
        ds_apy.append({**base, "data": p["apys"], "backgroundColor": p["color"] + "18", "fill": False})
        ds_tvl.append({**base, "data": p["tvls"], "backgroundColor": p["color"] + "22", "fill": True, "borderWidth": 2})

    valid = [p for p in apy_data if p["current_apy"] is not None]
    best = max(valid, key=lambda p: p["current_apy"]) if valid else None
    worst = min(valid, key=lambda p: p["current_apy"]) if valid else None
    spread = (best["current_apy"] - worst["current_apy"]) if best and worst else 0
    combined_tvl = sum(p["current_tvl"] or 0 for p in apy_data)

    # Table
    table_rows = ""
    for p in sorted(apy_data, key=lambda x: x.get("current_apy") or 0, reverse=True):
        apy_s = f'{p["current_apy"]:.2f}%' if p["current_apy"] is not None else "N/A"
        base_s = f'{p["current_apy_base"]:.2f}%' if p["current_apy_base"] is not None else "—"
        rew = p.get("current_apy_reward")
        rew_s = f'{rew:.2f}%' if rew and rew > 0 else "—"
        recent7 = [a for a in p["apys"][-7:] if a is not None]
        avg7 = f'{sum(recent7)/len(recent7):.2f}%' if recent7 else "—"
        recent30 = [a for a in p["apys"][-30:] if a is not None]
        avg30 = f'{sum(recent30)/len(recent30):.2f}%' if recent30 else "—"
        if len(recent30) > 1:
            m = sum(recent30) / len(recent30)
            std = (sum((x - m)**2 for x in recent30) / len(recent30)) ** 0.5
            vol = f'{std:.2f}%'
        else:
            vol = "—"
        dot = f'<span style="color:{p["color"]}">●</span>'
        table_rows += f'<tr><td>{dot} {p["label"]}</td><td class="tag">{p["tag"]}</td><td class="num highlight">{apy_s}</td><td class="num">{avg7}</td><td class="num">{avg30}</td><td class="num">{vol}</td><td class="num">{base_s}</td><td class="num">{rew_s}</td><td class="num">{fmt_usd(p["current_tvl"])}</td></tr>\n'

    legend_html = "".join(
        f'<div class="legend-item"><div class="legend-dot" style="background:{p["color"]}"></div><div><div class="legend-name">{p["label"]}</div><div class="legend-tag">{p["tag"]}</div></div></div>'
        for p in apy_data
    )

    return f"""
<div class="kpi-grid">
  <div class="kpi"><div class="k-label">Highest APY</div><div class="k-val" style="color:var(--green)">{best["current_apy"]:.2f}%</div><div class="k-label" style="margin-top:4px">{best["label"]}</div></div>
  <div class="kpi"><div class="k-label">Lowest APY</div><div class="k-val" style="color:var(--yellow)">{worst["current_apy"]:.2f}%</div><div class="k-label" style="margin-top:4px">{worst["label"]}</div></div>
  <div class="kpi"><div class="k-label">Current Spread</div><div class="k-val" style="color:var(--avax)">{spread:.2f}%</div><div class="k-label" style="margin-top:4px">Best − Worst</div></div>
  <div class="kpi"><div class="k-label">Markets Tracked</div><div class="k-val" style="color:var(--accent)">6</div><div class="k-label" style="margin-top:4px">USDC lending</div></div>
  <div class="kpi"><div class="k-label">Combined TVL</div><div class="k-val">{fmt_usd(combined_tvl)}</div><div class="k-label" style="margin-top:4px">Across 6 markets</div></div>
</div>
<div class="legend-grid">{legend_html}</div>

<section>
  <h2>APY Comparison — Last 90 Days</h2>
  <p class="insight">Lending APY (supply rate) for USDC across all 6 target markets. The spread represents the rebalancing opportunity Snow Mind captures.</p>
  <div class="chart-wrap" style="height:420px"><canvas id="apyChart"></canvas></div>
</section>

<section>
  <h2>TVL Comparison — Last 90 Days</h2>
  <p class="insight">Capital deposited in each market. Larger TVL = more stable but lower APY. Smaller pools offer higher yields with more volatility.</p>
  <div class="chart-wrap" style="height:360px"><canvas id="apyTvlChart"></canvas></div>
</section>

<section>
  <h2>Market Summary</h2>
  <p class="insight">Current rates, averages, and volatility (std dev over 30d) across all 6 markets.</p>
  <div style="overflow-x:auto"><table>
    <thead><tr><th>Market</th><th>Strategy</th><th>APY Now</th><th>7d Avg</th><th>30d Avg</th><th>30d Vol</th><th>Base APY</th><th>Reward</th><th>TVL</th></tr></thead>
    <tbody>{table_rows}</tbody>
  </table></div>
</section>
""", labels, json.dumps(ds_apy), json.dumps(ds_tvl)


def build_util_html(pool_data, common_dates):
    labels = json.dumps([d[5:] for d in common_dates])
    ds_util, ds_borrow_apy, ds_supply, ds_borrow = [], [], [], []

    for p in pool_data:
        if not p["available"]:
            continue
        utils, bapys, sups, bors = [], [], [], []
        for day in common_dates:
            d = p["daily"].get(day)
            if d:
                utils.append(d["util"]); bapys.append(d["borrow_apy"])
                sups.append(d["supply"]); bors.append(d["borrow"])
            else:
                utils.append(None); bapys.append(None)
                sups.append(None); bors.append(None)
        base = {
            "label": p["label"], "borderColor": p["color"],
            "backgroundColor": p["color"] + "18", "borderDash": p["border_dash"],
            "tension": 0.3, "pointRadius": 0, "pointHoverRadius": 5,
            "borderWidth": 2.5, "spanGaps": True,
        }
        ds_util.append({**base, "data": utils, "fill": False})
        ds_borrow_apy.append({**base, "data": bapys, "fill": False})
        ds_supply.append({**base, "data": sups, "backgroundColor": p["color"] + "22", "fill": True, "borderWidth": 2})
        ds_borrow.append({**base, "data": bors, "backgroundColor": p["color"] + "22", "fill": True, "borderWidth": 2})

    available = [p for p in pool_data if p["available"] and p["daily"]]
    kpis = []
    for p in available:
        last_day = max(p["daily"].keys())
        cur = p["daily"][last_day]
        kpis.append({"label": p["label"], "util": cur["util"], "color": p["color"]})
    highest = max(kpis, key=lambda x: x["util"]) if kpis else {"label": "—", "util": 0}
    lowest = min(kpis, key=lambda x: x["util"]) if kpis else {"label": "—", "util": 0}
    avg_util = sum(k["util"] for k in kpis) / len(kpis) if kpis else 0
    total_supply = sum(list(p["daily"].values())[-1]["supply"] for p in available)
    total_borrow = sum(list(p["daily"].values())[-1]["borrow"] for p in available)

    # Legend
    legend_html = ""
    for p in pool_data:
        if not p["available"]:
            legend_html += f'<div class="legend-item dimmed"><div class="legend-dot" style="background:{p["color"]};opacity:0.3"></div><div><div class="legend-name">{p["label"]} <span style="color:var(--yellow)">(no data)</span></div><div class="legend-tag">{p["tag"]}</div></div></div>'
        else:
            legend_html += f'<div class="legend-item"><div class="legend-dot" style="background:{p["color"]}"></div><div><div class="legend-name">{p["label"]}</div><div class="legend-tag">{p["tag"]}</div></div></div>'

    # Table
    table_rows = ""
    for p in sorted(available, key=lambda x: list(x["daily"].values())[-1]["util"] if x["daily"] else 0, reverse=True):
        last_day = max(p["daily"].keys())
        cur = p["daily"][last_day]
        util = cur["util"]
        sorted_days = sorted(p["daily"].keys())
        vals7 = [p["daily"][d]["util"] for d in sorted_days[-7:]]
        vals30 = [p["daily"][d]["util"] for d in sorted_days[-30:]]
        avg7 = sum(vals7)/len(vals7) if vals7 else 0
        avg30 = sum(vals30)/len(vals30) if vals30 else 0
        std = (sum((x - avg30)**2 for x in vals30) / len(vals30)) ** 0.5 if len(vals30) > 1 else 0
        u_cls = "util-high" if util > 85 else "util-mid" if util > 60 else "util-low"
        dot = f'<span style="color:{p["color"]}">●</span>'
        table_rows += f'<tr><td>{dot} {p["label"]}</td><td class="tag">{p["tag"]}</td><td class="num {u_cls}">{util:.1f}%</td><td class="num">{avg7:.1f}%</td><td class="num">{avg30:.1f}%</td><td class="num">{std:.1f}%</td><td class="num">{cur["supply_apy"]:.2f}%</td><td class="num">{cur["borrow_apy"]:.2f}%</td><td class="num">{fmt_usd(cur["supply"])}</td><td class="num">{fmt_usd(cur["borrow"])}</td></tr>\n'

    return f"""
<div class="kpi-grid">
  <div class="kpi"><div class="k-label">Highest Utilization</div><div class="k-val" style="color:var(--avax)">{highest["util"]:.1f}%</div><div class="k-label" style="margin-top:4px">{highest["label"]}</div></div>
  <div class="kpi"><div class="k-label">Lowest Utilization</div><div class="k-val" style="color:var(--green)">{lowest["util"]:.1f}%</div><div class="k-label" style="margin-top:4px">{lowest["label"]}</div></div>
  <div class="kpi"><div class="k-label">Average Utilization</div><div class="k-val" style="color:var(--yellow)">{avg_util:.1f}%</div><div class="k-label" style="margin-top:4px">Across all markets</div></div>
  <div class="kpi"><div class="k-label">Total Supplied</div><div class="k-val">{fmt_usd(total_supply)}</div><div class="k-label" style="margin-top:4px">6 markets combined</div></div>
  <div class="kpi"><div class="k-label">Total Borrowed</div><div class="k-val">{fmt_usd(total_borrow)}</div><div class="k-label" style="margin-top:4px">6 markets combined</div></div>
</div>
<div class="legend-grid">{legend_html}</div>

<section>
  <h2>Utilization Rate — Last 90 Days</h2>
  <p class="insight">Utilization = Borrowed / Supplied. Markets near the kink point (80-90%) see sharp APY increases — the highest-value rebalancing signals.</p>
  <div class="chart-wrap" style="height:420px"><canvas id="utilChart"></canvas></div>
</section>

<section>
  <h2>Borrow APY — Last 90 Days</h2>
  <p class="insight">Higher borrow APY = more yield flowing to depositors. Snow Mind can front-run rate moves by rebalancing before full adjustment.</p>
  <div class="chart-wrap" style="height:360px"><canvas id="utilBorrowApyChart"></canvas></div>
</section>

<section>
  <h2>Supply &amp; Borrow Volume — Last 90 Days</h2>
  <p class="insight">The ratio between supply and borrow volume determines utilization. Rapid borrow growth with stable supply is a bullish yield signal.</p>
  <div class="grid-2">
    <div class="chart-wrap" style="height:300px">
      <h3 style="font-size:0.9rem;color:var(--text2);margin-bottom:8px">Total Supplied</h3>
      <canvas id="utilSupplyChart"></canvas>
    </div>
    <div class="chart-wrap" style="height:300px">
      <h3 style="font-size:0.9rem;color:var(--text2);margin-bottom:8px">Total Borrowed</h3>
      <canvas id="utilBorrowChart"></canvas>
    </div>
  </div>
</section>

<section>
  <h2>Market Utilization Summary</h2>
  <p class="insight">Red = high util (&gt;85%), yellow = moderate (60-85%), green = low (&lt;60%). Higher volatility = more rebalancing opportunity.</p>
  <div style="overflow-x:auto"><table>
    <thead><tr><th>Market</th><th>Strategy</th><th>Util Now</th><th>7d Avg</th><th>30d Avg</th><th>30d Vol</th><th>Supply APY</th><th>Borrow APY</th><th>Supplied</th><th>Borrowed</th></tr></thead>
    <tbody>{table_rows}</tbody>
  </table></div>
</section>
""", labels, json.dumps(ds_util), json.dumps(ds_borrow_apy), json.dumps(ds_supply), json.dumps(ds_borrow)


# ─── Main HTML Assembly ────────────────────────────────────────────────

def build_page(eco, apy_data, apy_dates, util_data, util_dates, fetch_time):
    eco_html = build_ecosystem_html(eco)
    apy_html, apy_labels, ds_apy_json, ds_apy_tvl_json = build_apy_html(apy_data, apy_dates)
    util_html, util_labels, ds_util_json, ds_ba_json, ds_sup_json, ds_bor_json = build_util_html(util_data, util_dates)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Snow Mind — Avalanche DeFi Research</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
:root {{
    --bg: #0d1117; --card: #161b22; --border: #30363d;
    --text: #e6edf3; --text2: #8b949e; --accent: #58a6ff;
    --avax: #e84142; --green: #3fb950; --yellow: #d29922;
}}
*{{ margin:0; padding:0; box-sizing:border-box; }}
body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: var(--bg); color: var(--text); line-height:1.6;
}}
.container {{ max-width:1280px; margin:0 auto; padding:0 24px 24px; }}

/* Header + Tabs */
.top-bar {{
    position: sticky; top: 0; z-index: 100; background: var(--bg);
    border-bottom: 1px solid var(--border);
}}
.top-bar .inner {{ max-width: 1280px; margin: 0 auto; padding: 0 24px; }}
.top-header {{
    text-align: center; padding: 28px 0 12px;
}}
.top-header h1 {{
    font-size: 1.7rem; margin-bottom: 2px;
    background: linear-gradient(135deg, var(--avax), #ff6b6b, var(--accent));
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
}}
.top-header .sub {{ color: var(--text2); font-size: 0.9rem; }}
.tabs {{
    display: flex; gap: 0; justify-content: center; padding: 0;
}}
.tab-btn {{
    background: none; border: none; color: var(--text2); font-size: 0.95rem;
    padding: 12px 28px; cursor: pointer; border-bottom: 3px solid transparent;
    font-weight: 600; transition: all 0.2s;
}}
.tab-btn:hover {{ color: var(--text); }}
.tab-btn.active {{
    color: var(--text); border-bottom-color: var(--avax);
}}

.tab-panel {{ display: none; padding-top: 28px; }}
.tab-panel.active {{ display: block; }}

/* Summary cards */
.summary-grid {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
    gap: 14px; margin-bottom: 32px;
}}
.summary-card {{
    background: var(--card); border: 1px solid var(--border);
    border-radius: 12px; padding: 18px; text-align: center;
}}
.summary-card .label {{ font-size: 0.78rem; color: var(--text2); text-transform: uppercase; letter-spacing: 0.05em; }}
.summary-card .value {{ font-size: 1.5rem; font-weight: 700; margin-top: 5px; }}
.summary-card .value.avax {{ color: var(--avax); }}
.summary-card .value.green {{ color: var(--green); }}
.summary-card .value.blue {{ color: var(--accent); }}
.summary-card .value.yellow {{ color: var(--yellow); }}

/* KPI grid (APY + Util) */
.kpi-grid {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 14px; margin-bottom: 28px;
}}
.kpi {{
    background: var(--card); border: 1px solid var(--border); border-radius: 10px;
    padding: 16px; text-align: center;
}}
.kpi .k-label {{ font-size: 0.73rem; color: var(--text2); text-transform: uppercase; letter-spacing: 0.04em; }}
.kpi .k-val {{ font-size: 1.4rem; font-weight: 700; margin-top: 4px; }}

/* Sections */
section {{
    background: var(--card); border: 1px solid var(--border); border-radius: 12px;
    padding: 24px; margin-bottom: 24px;
}}
section h2 {{ font-size: 1.2rem; margin-bottom: 6px; }}
section .insight {{
    color: var(--text2); font-size: 0.88rem; margin-bottom: 18px;
    border-left: 3px solid var(--avax); padding-left: 12px;
}}

.chart-wrap {{ position: relative; width: 100%; max-height: 440px; }}
.chart-wrap canvas {{ width: 100% !important; }}

/* Tables */
table {{ width: 100%; border-collapse: collapse; font-size: 0.85rem; }}
th, td {{ padding: 9px 12px; text-align: left; border-bottom: 1px solid var(--border); }}
th {{ color: var(--text2); font-weight: 600; font-size: 0.73rem; text-transform: uppercase; letter-spacing: 0.03em; }}
td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
td.highlight {{ font-weight: 700; color: var(--green); font-size: 0.95rem; }}
td.tag {{ color: var(--text2); font-size: 0.76rem; font-style: italic; max-width: 200px; }}
tr:hover {{ background: rgba(88,166,255,0.04); }}
.target-row {{ background: rgba(232,65,66,0.08); }}
.target-row:hover {{ background: rgba(232,65,66,0.14); }}
.badge {{
    display: inline-block; font-size: 0.63rem; background: var(--avax); color: #fff;
    padding: 2px 7px; border-radius: 4px; margin-left: 6px; vertical-align: middle; font-weight: 600;
}}
.desc-cell {{ max-width: 320px; font-size: 0.82rem; color: var(--text2); }}
.empty-msg {{ text-align: center; color: var(--green); padding: 20px; font-style: italic; }}

.util-high {{ color: var(--avax); font-weight: 700; }}
.util-mid {{ color: var(--yellow); font-weight: 700; }}
.util-low {{ color: var(--green); font-weight: 700; }}

/* Legend */
.legend-grid {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
    gap: 10px; margin-bottom: 20px;
}}
.legend-item {{
    display: flex; align-items: center; gap: 10px; padding: 8px 12px;
    background: rgba(255,255,255,0.02); border-radius: 6px;
}}
.legend-item.dimmed {{ opacity: 0.5; }}
.legend-dot {{ width: 14px; height: 14px; border-radius: 50%; flex-shrink: 0; }}
.legend-name {{ font-weight: 600; font-size: 0.88rem; }}
.legend-tag {{ color: var(--text2); font-size: 0.76rem; }}

/* Takeaways */
.takeaways ul {{ list-style: none; padding: 0; }}
.takeaways li {{
    padding: 14px 18px; border-left: 3px solid var(--avax);
    margin-bottom: 12px; background: rgba(232,65,66,0.05);
    border-radius: 0 8px 8px 0; line-height: 1.7;
}}
.takeaways li strong {{ color: var(--accent); }}

.grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }}
@media (max-width:900px) {{ .grid-2 {{ grid-template-columns: 1fr; }} }}

footer {{
    text-align: center; padding: 28px; color: var(--text2); font-size: 0.78rem;
}}
footer a {{ color: var(--accent); }}
</style>
</head>
<body>

<!-- ═══ Sticky Top Bar ═══ -->
<div class="top-bar">
<div class="inner">
  <div class="top-header">
    <h1>Snow Mind — Avalanche DeFi Research</h1>
    <p class="sub">Market opportunity &middot; APY comparison &middot; Utilization analytics</p>
  </div>
  <div class="tabs">
    <button class="tab-btn active" onclick="switchTab('eco',this)">Ecosystem</button>
    <button class="tab-btn" onclick="switchTab('apy',this)">APY Comparison</button>
    <button class="tab-btn" onclick="switchTab('util',this)">Utilization</button>
  </div>
</div>
</div>

<div class="container">

<!-- ═══ Tab 1: Ecosystem ═══ -->
<div id="tab-eco" class="tab-panel active">
{eco_html}
</div>

<!-- ═══ Tab 2: APY Comparison ═══ -->
<div id="tab-apy" class="tab-panel">
{apy_html}
</div>

<!-- ═══ Tab 3: Utilization ═══ -->
<div id="tab-util" class="tab-panel">
{util_html}
</div>

</div>

<footer>
  Snow Mind Market Research &middot; Data from <a href="https://defillama.com">DefiLlama</a>
  &middot; Generated {fetch_time}
</footer>

<script>
function switchTab(id, btn) {{
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('tab-' + id).classList.add('active');
  btn.classList.add('active');
  setTimeout(() => window.dispatchEvent(new Event('resize')), 50);
}}

const GRID = 'rgba(255,255,255,0.06)';
const TICK = '#8b949e';
Chart.defaults.color = TICK;
Chart.defaults.borderColor = GRID;
const legendOpts = {{ display: true, position: 'top', labels: {{ usePointStyle: true, pointStyle: 'line', padding: 14 }} }};
const interOpts = {{ mode: 'index', intersect: false }};

/* ── Ecosystem Charts ── */
new Chart(document.getElementById('ecoTvlChart'), {{
  type:'line',
  data:{{ labels:{eco["tvl_labels"]}, datasets:[{{
    label:'Avalanche TVL ($M)', data:{eco["tvl_values"]},
    borderColor:'#e84142', backgroundColor:'rgba(232,65,66,0.10)',
    fill:true, tension:0.3, pointRadius:0, borderWidth:2
  }}] }},
  options:{{ responsive:true, plugins:{{ legend:{{display:false}}, tooltip:{{callbacks:{{label:c=>'$'+c.parsed.y.toLocaleString()+'M'}}}} }},
    scales:{{ y:{{ticks:{{callback:v=>'$'+v+'M'}}, grid:{{color:GRID}}}}, x:{{ticks:{{maxTicksLimit:12}}, grid:{{display:false}}}} }} }}
}});

new Chart(document.getElementById('ecoScChart'), {{
  type:'line',
  data:{{ labels:{eco["sc_labels"]}, datasets:[{{
    label:'Stablecoin Supply ($M)', data:{eco["sc_values"]},
    borderColor:'#3fb950', backgroundColor:'rgba(63,185,80,0.10)',
    fill:true, tension:0.3, pointRadius:0, borderWidth:2
  }}] }},
  options:{{ responsive:true, plugins:{{ legend:{{display:false}}, tooltip:{{callbacks:{{label:c=>'$'+c.parsed.y.toLocaleString()+'M'}}}} }},
    scales:{{ y:{{ticks:{{callback:v=>'$'+v+'M'}}, grid:{{color:GRID}}}}, x:{{ticks:{{maxTicksLimit:12}}, grid:{{display:false}}}} }} }}
}});

new Chart(document.getElementById('ecoPieChart'), {{
  type:'doughnut',
  data:{{ labels:{eco["pie_labels"]}, datasets:[{{
    data:{eco["pie_values"]},
    backgroundColor:['#2775CA','#26A17B','#F5AC37','#8b5cf6','#ec4899','#6b7280'],
    borderColor:'#161b22', borderWidth:2
  }}] }},
  options:{{ responsive:true, plugins:{{ legend:{{position:'right',labels:{{padding:14}}}}, tooltip:{{callbacks:{{label:c=>c.label+': $'+c.parsed.toLocaleString()+'M'}}}} }} }}
}});

(function(){{
  var el=document.getElementById('compChart'); if(!el) return;
  var ds={eco["comp_datasets"]}; if(!ds.length) return;
  new Chart(el,{{ type:'line', data:{{labels:{eco["comp_labels"]}, datasets:ds}},
    options:{{ responsive:true, plugins:{{ tooltip:{{callbacks:{{label:c=>c.dataset.label+': $'+c.parsed.y.toLocaleString()+'M'}}}} }},
      scales:{{ y:{{ticks:{{callback:v=>'$'+v+'M'}}, grid:{{color:GRID}}}}, x:{{ticks:{{maxTicksLimit:12}}, grid:{{display:false}}}} }} }}
  }});
}})();

new Chart(document.getElementById('ecoChainChart'), {{
  type:'bar',
  data:{{ labels:{eco["chain_labels"]}, datasets:[{{
    label:'Chain TVL ($B)', data:{eco["chain_values"]},
    backgroundColor:{eco["chain_colors"]}, borderRadius:4
  }}] }},
  options:{{ responsive:true, indexAxis:'y', plugins:{{ legend:{{display:false}}, tooltip:{{callbacks:{{label:c=>'$'+c.parsed.x.toLocaleString()+'B'}}}} }},
    scales:{{ x:{{ticks:{{callback:v=>'$'+v+'B'}}, grid:{{color:GRID}}}}, y:{{grid:{{display:false}}}} }} }}
}});

/* ── APY Charts ── */
var apyLabels = {apy_labels};
new Chart(document.getElementById('apyChart'), {{
  type:'line', data:{{ labels:apyLabels, datasets:{ds_apy_json} }},
  options:{{ responsive:true, maintainAspectRatio:false, interaction:interOpts,
    plugins:{{ tooltip:{{callbacks:{{label:c=>c.parsed.y!=null?c.dataset.label+': '+c.parsed.y.toFixed(2)+'%':null}}}}, legend:legendOpts }},
    scales:{{ y:{{title:{{display:true,text:'APY (%)'}}, ticks:{{callback:v=>v.toFixed(1)+'%'}}, grid:{{color:GRID}}, beginAtZero:true}}, x:{{ticks:{{maxTicksLimit:15,maxRotation:45}}, grid:{{display:false}}}} }}
  }}
}});
new Chart(document.getElementById('apyTvlChart'), {{
  type:'line', data:{{ labels:apyLabels, datasets:{ds_apy_tvl_json} }},
  options:{{ responsive:true, maintainAspectRatio:false, interaction:interOpts,
    plugins:{{ tooltip:{{callbacks:{{label:c=>{{if(c.parsed.y==null)return null;var v=c.parsed.y;return c.dataset.label+': $'+(v>=1e6?(v/1e6).toFixed(1)+'M':(v/1e3).toFixed(0)+'K')}}}}}}, legend:legendOpts }},
    scales:{{ y:{{title:{{display:true,text:'TVL (USD)'}}, ticks:{{callback:v=>v>=1e6?'$'+(v/1e6).toFixed(0)+'M':'$'+(v/1e3).toFixed(0)+'K'}}, grid:{{color:GRID}}}}, x:{{ticks:{{maxTicksLimit:15,maxRotation:45}}, grid:{{display:false}}}} }}
  }}
}});

/* ── Utilization Charts ── */
var utilLabels = {util_labels};
new Chart(document.getElementById('utilChart'), {{
  type:'line', data:{{ labels:utilLabels, datasets:{ds_util_json} }},
  options:{{ responsive:true, maintainAspectRatio:false, interaction:interOpts,
    plugins:{{ tooltip:{{callbacks:{{label:c=>c.parsed.y!=null?c.dataset.label+': '+c.parsed.y.toFixed(1)+'%':null}}}}, legend:legendOpts }},
    scales:{{ y:{{title:{{display:true,text:'Utilization (%)'}}, ticks:{{callback:v=>v+'%'}}, grid:{{color:GRID}}, min:0, max:100}}, x:{{ticks:{{maxTicksLimit:15,maxRotation:45}}, grid:{{display:false}}}} }}
  }}
}});
new Chart(document.getElementById('utilBorrowApyChart'), {{
  type:'line', data:{{ labels:utilLabels, datasets:{ds_ba_json} }},
  options:{{ responsive:true, maintainAspectRatio:false, interaction:interOpts,
    plugins:{{ tooltip:{{callbacks:{{label:c=>c.parsed.y!=null?c.dataset.label+': '+c.parsed.y.toFixed(2)+'%':null}}}}, legend:legendOpts }},
    scales:{{ y:{{title:{{display:true,text:'Borrow APY (%)'}}, ticks:{{callback:v=>v.toFixed(1)+'%'}}, grid:{{color:GRID}}, beginAtZero:true}}, x:{{ticks:{{maxTicksLimit:15,maxRotation:45}}, grid:{{display:false}}}} }}
  }}
}});
var tvlTooltip={{callbacks:{{label:c=>{{if(c.parsed.y==null)return null;var v=c.parsed.y;return c.dataset.label+': $'+(v>=1e6?(v/1e6).toFixed(1)+'M':(v/1e3).toFixed(0)+'K')}}}}}};
var tvlTick={{callback:v=>v>=1e6?'$'+(v/1e6).toFixed(0)+'M':'$'+(v/1e3).toFixed(0)+'K'}};
new Chart(document.getElementById('utilSupplyChart'), {{
  type:'line', data:{{ labels:utilLabels, datasets:{ds_sup_json} }},
  options:{{ responsive:true, maintainAspectRatio:false, interaction:interOpts,
    plugins:{{ tooltip:tvlTooltip, legend:{{display:false}} }},
    scales:{{ y:{{ticks:tvlTick, grid:{{color:GRID}}}}, x:{{ticks:{{maxTicksLimit:10,maxRotation:45}}, grid:{{display:false}}}} }}
  }}
}});
new Chart(document.getElementById('utilBorrowChart'), {{
  type:'line', data:{{ labels:utilLabels, datasets:{ds_bor_json} }},
  options:{{ responsive:true, maintainAspectRatio:false, interaction:interOpts,
    plugins:{{ tooltip:tvlTooltip, legend:{{display:false}} }},
    scales:{{ y:{{ticks:tvlTick, grid:{{color:GRID}}}}, x:{{ticks:{{maxTicksLimit:10,maxRotation:45}}, grid:{{display:false}}}} }}
  }}
}});
</script>
</body>
</html>"""


# ─── Main ──────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  Snow Mind — Unified Dashboard Generator")
    print("=" * 60)

    fetch_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    print("\n[1/4] Processing Ecosystem data...")
    eco = process_ecosystem()
    print(f"  Avalanche TVL: {fmt_usd(eco['current_avax_tvl'])}")
    print(f"  Stablecoin Supply: {fmt_usd(eco['current_sc_supply'])}")
    print(f"  Lending TVL: {fmt_usd(eco['total_lending_tvl'])}")
    print(f"  Lending Protocols: {eco['num_lending']}")

    print("\n[2/4] Processing APY data...")
    apy_data, apy_dates = process_apy()
    for p in apy_data:
        apy_s = f"{p['current_apy']:.2f}%" if p['current_apy'] is not None else "N/A"
        print(f"  {p['label']:<25} APY: {apy_s}")

    print("\n[3/4] Processing Utilization data...")
    util_data, util_dates = process_util()
    for p in util_data:
        if p["available"] and p["daily"]:
            last = list(p["daily"].values())[-1]
            print(f"  {p['label']:<25} Util: {last['util']:.1f}%")
        else:
            print(f"  {p['label']:<25} (no data)")

    print(f"\n[4/4] Generating {OUTPUT_FILE}...")
    html = build_page(eco, apy_data, apy_dates, util_data, util_dates, fetch_time)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\n{'=' * 60}")
    print(f"  Unified dashboard generated: {OUTPUT_FILE}")
    print(f"  3 tabs: Ecosystem | APY Comparison | Utilization")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
