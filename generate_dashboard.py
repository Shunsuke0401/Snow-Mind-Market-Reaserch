#!/usr/bin/env python3
"""
Snow Mind Market Research Dashboard Generator

Fetches DeFi data from DefiLlama's free API endpoints and generates an HTML
dashboard answering: "How big is the market opportunity for an autonomous
yield optimizer on Avalanche?"
"""

import json
import os
import sys
import time
from datetime import datetime, timezone

import requests

# ─── Configuration ────────────────────────────────────────────────────────────

API_BASE = "https://api.llama.fi"
SC_BASE = "https://stablecoins.llama.fi"
DATA_DIR = "data"
OUTPUT_FILE = "index.html"
DELAY = 0.5
HEADERS = {"User-Agent": "SnowMind-Research/1.0", "Accept": "application/json"}

TARGET_LENDING_SLUGS = {"benqi-lending", "aave-v3", "euler-v2", "fluid"}
TARGET_LENDING_KEYWORDS = {"benqi", "aave", "euler", "fluid"}
COMPETITOR_SLUGS = ["giza", "zyfai", "almanak"]

# ─── Helpers ──────────────────────────────────────────────────────────────────

def fetch_json(url, label):
    """Fetch JSON from URL, save raw response to data/ folder, return parsed."""
    print(f"  -> {label} ...")
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        safe = label.replace(" ", "_").replace("/", "_").replace(":", "")
        with open(os.path.join(DATA_DIR, f"{safe}.json"), "w") as f:
            json.dump(data, f, indent=2)
        return data
    except requests.exceptions.HTTPError as e:
        print(f"     HTTP {e.response.status_code} for {label}")
        return None
    except Exception as e:
        print(f"     Failed: {e}")
        return None


def fmt_usd(v):
    if v is None:
        return "N/A"
    if abs(v) >= 1e9:
        return f"${v / 1e9:.2f}B"
    if abs(v) >= 1e6:
        return f"${v / 1e6:.2f}M"
    if abs(v) >= 1e3:
        return f"${v / 1e3:.1f}K"
    return f"${v:,.2f}"


def fmt_pct(v):
    if v is None:
        return "—"
    return f"{v:+.2f}%"


def ts_to_label(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%b %d, %Y")


def ts_to_short(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%b '%y")


# ─── Data Fetching ────────────────────────────────────────────────────────────

def fetch_all():
    os.makedirs(DATA_DIR, exist_ok=True)
    raw = {}

    raw["avax_tvl_hist"] = fetch_json(
        f"{API_BASE}/v2/historicalChainTvl/Avalanche",
        "Avalanche historical TVL",
    )
    time.sleep(DELAY)

    raw["all_protocols"] = fetch_json(
        f"{API_BASE}/protocols",
        "All protocols",
    )
    time.sleep(DELAY)

    raw["avax_stablecoin_chart"] = fetch_json(
        f"{SC_BASE}/stablecoincharts/Avalanche",
        "Avalanche stablecoin chart",
    )
    time.sleep(DELAY)

    raw["all_stablecoins"] = fetch_json(
        f"{SC_BASE}/stablecoins?includePrices=true",
        "All stablecoins",
    )
    time.sleep(DELAY)

    raw["competitors"] = {}
    for slug in COMPETITOR_SLUGS:
        result = fetch_json(f"{API_BASE}/protocol/{slug}", f"Competitor {slug}")
        if result:
            raw["competitors"][slug] = result
        time.sleep(DELAY)

    raw["avax_fees"] = fetch_json(
        f"{API_BASE}/overview/fees/Avalanche",
        "Avalanche fees overview",
    )
    time.sleep(DELAY)

    raw["all_chains"] = fetch_json(
        f"{API_BASE}/v2/chains",
        "All chains TVL",
    )

    return raw


# ─── Data Processing ──────────────────────────────────────────────────────────

def process(raw):
    d = {}
    twelve_months_ago = time.time() - 365 * 86400

    # 1 ── Avalanche TVL trend (last 12 months) ──
    tvl_hist = raw.get("avax_tvl_hist") or []
    tvl_series = [
        {"date": r["date"], "tvl": r["tvl"]}
        for r in tvl_hist
        if r.get("date", 0) >= twelve_months_ago
    ]
    d["tvl_series"] = tvl_series
    d["current_avax_tvl"] = tvl_series[-1]["tvl"] if tvl_series else 0

    # 2 ── Avalanche lending protocols ──
    lending = []
    for p in raw.get("all_protocols") or []:
        chains = p.get("chains") or []
        cat = (p.get("category") or "").strip()
        if "Avalanche" not in chains:
            continue
        if cat.lower() != "lending":
            continue
        slug = p.get("slug") or ""
        name_lower = p.get("name", "").lower()
        is_target = (
            slug in TARGET_LENDING_SLUGS
            or any(kw in name_lower for kw in TARGET_LENDING_KEYWORDS)
        )
        chain_tvls = p.get("chainTvls") or {}
        avax_tvl = chain_tvls.get("Avalanche")
        lending.append({
            "name": p.get("name", "Unknown"),
            "slug": slug,
            "total_tvl": p.get("tvl") or 0,
            "avax_tvl": avax_tvl,
            "change_1d": p.get("change_1d"),
            "change_7d": p.get("change_7d"),
            "is_target": is_target,
        })
    lending.sort(key=lambda x: (x["avax_tvl"] or x["total_tvl"] or 0), reverse=True)
    d["lending_protocols"] = lending
    d["total_lending_tvl"] = sum((p["avax_tvl"] or 0) for p in lending)
    d["num_lending"] = len(lending)

    # 3 ── Stablecoin supply trend ──
    sc_chart = raw.get("avax_stablecoin_chart") or []
    sc_series = []
    for r in sc_chart:
        ts = int(r.get("date", 0))
        if ts < twelve_months_ago:
            continue
        circ_usd = r.get("totalCirculatingUSD") or r.get("totalCirculating") or {}
        val = sum(v for v in circ_usd.values() if isinstance(v, (int, float)))
        sc_series.append({"date": ts, "supply": val})
    d["sc_series"] = sc_series
    d["current_sc_supply"] = sc_series[-1]["supply"] if sc_series else 0

    # 4 ── Stablecoin composition ──
    stables_raw = raw.get("all_stablecoins") or []
    if isinstance(stables_raw, dict):
        stables_raw = stables_raw.get("peggedAssets", stables_raw.get("data", []))
    breakdown = {}
    for sc in stables_raw:
        if not isinstance(sc, dict):
            continue
        symbol = sc.get("symbol", sc.get("name", "??"))
        chain_circ = sc.get("chainCirculating") or {}
        avax_entry = chain_circ.get("Avalanche")
        if avax_entry is None:
            continue
        if isinstance(avax_entry, (int, float)):
            val = avax_entry
        elif isinstance(avax_entry, dict):
            cur = avax_entry.get("current", avax_entry)
            val = cur.get("peggedUSD", 0) if isinstance(cur, dict) else 0
        else:
            val = 0
        if val > 0:
            breakdown[symbol] = breakdown.get(symbol, 0) + val

    sorted_stables = sorted(breakdown.items(), key=lambda x: x[1], reverse=True)
    pie = {}
    others = 0.0
    for i, (sym, val) in enumerate(sorted_stables):
        if i < 5:
            pie[sym] = val
        else:
            others += val
    if others > 0:
        pie["Others"] = others
    d["sc_breakdown"] = pie

    # 5 ── Competitors ──
    competitors = {}
    max_comp_tvl = 0
    for slug, cdata in (raw.get("competitors") or {}).items():
        if not cdata:
            continue
        tvl_raw = cdata.get("tvl")
        if isinstance(tvl_raw, list):
            hist = [
                {"date": pt.get("date", 0), "tvl": pt.get("totalLiquidityUSD", 0)}
                for pt in tvl_raw
            ]
            current = hist[-1]["tvl"] if hist else 0
        else:
            current = tvl_raw or 0
            hist = []
        max_comp_tvl = max(max_comp_tvl, current)
        competitors[slug] = {
            "name": cdata.get("name", slug),
            "tvl": current,
            "chains": cdata.get("chains", []),
            "description": (cdata.get("description") or "")[:200],
            "history": [
                h for h in hist if h["date"] >= twelve_months_ago
            ],
        }
    d["competitors"] = competitors
    d["max_comp_tvl"] = max_comp_tvl

    # 6 ── Lending fees / revenue ──
    fees_raw = raw.get("avax_fees") or {}
    fee_protocols = fees_raw.get("protocols") or []
    lending_fees = []
    lending_cats = {"lending", "cdp"}
    for p in fee_protocols:
        cat = (p.get("category") or "").lower()
        if cat not in lending_cats:
            continue
        lending_fees.append({
            "name": p.get("name", "Unknown"),
            "fees_24h": p.get("total24h") or p.get("dailyFees") or 0,
            "fees_7d": p.get("total7d") or 0,
            "change_1d": p.get("change_1d"),
        })
    lending_fees.sort(key=lambda x: x["fees_24h"], reverse=True)
    d["lending_fees"] = lending_fees

    # 7 ── Chain TVL ranking ──
    chains_raw = raw.get("all_chains") or []
    chains = [{"name": c.get("name", "?"), "tvl": c.get("tvl", 0)} for c in chains_raw]
    chains.sort(key=lambda x: x["tvl"], reverse=True)
    d["top_chains"] = chains[:15]

    return d


# ─── HTML Generation ──────────────────────────────────────────────────────────

def build_html(d, fetch_time):
    # Prepare JSON data for embedding in JS
    tvl_labels = json.dumps([ts_to_short(r["date"]) for r in d["tvl_series"]][::7])
    tvl_values = json.dumps([round(r["tvl"] / 1e6, 2) for r in d["tvl_series"]][::7])

    sc_labels = json.dumps([ts_to_short(r["date"]) for r in d["sc_series"]][::7])
    sc_values = json.dumps([round(r["supply"] / 1e6, 2) for r in d["sc_series"]][::7])

    pie_labels = json.dumps(list(d["sc_breakdown"].keys()))
    pie_values = json.dumps([round(v / 1e6, 2) for v in d["sc_breakdown"].values()])

    chain_labels = json.dumps([c["name"] for c in d["top_chains"]])
    chain_values = json.dumps([round(c["tvl"] / 1e9, 2) for c in d["top_chains"]])
    chain_colors = json.dumps([
        "#e84142" if c["name"] == "Avalanche" else "#3b82f6"
        for c in d["top_chains"]
    ])

    # Competitor chart data
    comp_datasets_js = "[]"
    if d["competitors"]:
        comp_colors = ["#f59e0b", "#10b981", "#8b5cf6", "#ec4899"]
        datasets = []
        all_dates = set()
        for cdata in d["competitors"].values():
            for h in cdata["history"]:
                all_dates.add(h["date"])
        all_dates = sorted(all_dates)
        comp_labels = json.dumps([ts_to_short(dt) for dt in all_dates][::7])

        for i, (slug, cdata) in enumerate(d["competitors"].items()):
            tvl_map = {h["date"]: h["tvl"] for h in cdata["history"]}
            vals = [round(tvl_map.get(dt, 0) / 1e6, 2) for dt in all_dates][::7]
            datasets.append({
                "label": cdata["name"],
                "data": vals,
                "borderColor": comp_colors[i % len(comp_colors)],
                "backgroundColor": comp_colors[i % len(comp_colors)] + "33",
                "fill": True,
                "tension": 0.3,
            })
        comp_datasets_js = json.dumps(datasets)
    else:
        comp_labels = "[]"

    # Lending protocols table rows
    lending_rows = ""
    for i, p in enumerate(d["lending_protocols"], 1):
        cls = ' class="target-row"' if p["is_target"] else ""
        badge = ' <span class="badge">Target</span>' if p["is_target"] else ""
        avax_cell = fmt_usd(p["avax_tvl"]) if p["avax_tvl"] else "—"
        lending_rows += f"""<tr{cls}>
            <td>{i}</td>
            <td>{p['name']}{badge}</td>
            <td>{fmt_usd(p['total_tvl'])}</td>
            <td>{avax_cell}</td>
            <td>{fmt_pct(p['change_1d'])}</td>
            <td>{fmt_pct(p['change_7d'])}</td>
        </tr>\n"""

    # Fees table rows
    fees_rows = ""
    for i, p in enumerate(d["lending_fees"], 1):
        fees_rows += f"""<tr>
            <td>{i}</td>
            <td>{p['name']}</td>
            <td>{fmt_usd(p['fees_24h'])}</td>
            <td>{fmt_usd(p['fees_7d'])}</td>
            <td>{fmt_pct(p['change_1d'])}</td>
        </tr>\n"""

    # Competitor table rows
    comp_rows = ""
    if d["competitors"]:
        for slug, c in d["competitors"].items():
            comp_rows += f"""<tr>
                <td>{c['name']}</td>
                <td>{fmt_usd(c['tvl'])}</td>
                <td>{', '.join(c['chains'][:5]) or '—'}</td>
                <td class="desc-cell">{c['description'] or '—'}</td>
            </tr>\n"""
    else:
        comp_rows = """<tr><td colspan="4" class="empty-msg">
            No competitor data found on DefiLlama — the autonomous yield-optimization
            market on Avalanche appears nascent, signalling a first-mover opportunity.
        </td></tr>"""

    # Key takeaways
    avax_tvl = d["current_avax_tvl"]
    sc_supply = d["current_sc_supply"]
    lending_tvl = d["total_lending_tvl"]
    utilisation = (lending_tvl / sc_supply * 100) if sc_supply > 0 else 0
    avax_rank = next(
        (i + 1 for i, c in enumerate(d["top_chains"]) if c["name"] == "Avalanche"),
        "N/A",
    )
    daily_fees = sum(p["fees_24h"] for p in d["lending_fees"])
    annual_fees = daily_fees * 365

    takeaways = [
        f"Avalanche DeFi TVL stands at <strong>{fmt_usd(avax_tvl)}</strong>, ranking "
        f"<strong>#{avax_rank}</strong> among all chains — a mature but not saturated ecosystem.",

        f"<strong>{fmt_usd(sc_supply)}</strong> in stablecoins sit on Avalanche, but only "
        f"<strong>{fmt_usd(lending_tvl)}</strong> ({utilisation:.1f}%) is deployed in lending protocols. "
        f"The gap represents idle capital that an autonomous optimizer could activate.",

        f"Avalanche lending protocols generate an estimated <strong>{fmt_usd(annual_fees)}/year</strong> "
        f"in fees — the yield pool that Snow Mind would optimise across.",

        f"<strong>{d['num_lending']}</strong> lending protocols operate on Avalanche, creating the "
        f"fragmentation that makes manual yield management impractical and automated rebalancing valuable.",
    ]
    if d["max_comp_tvl"] == 0:
        takeaways.append(
            "No established autonomous yield-optimizer competitors were found on DefiLlama, "
            "suggesting a <strong>significant first-mover advantage</strong> for Snow Mind."
        )
    else:
        takeaways.append(
            f"The largest identified competitor has only <strong>{fmt_usd(d['max_comp_tvl'])}</strong> "
            f"in TVL — the market is early-stage with room to capture significant share."
        )

    takeaways_html = "\n".join(
        f'<li>{t}</li>' for t in takeaways
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Snow Mind — Avalanche DeFi Market Research</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
:root {{
    --bg: #0d1117;
    --card: #161b22;
    --border: #30363d;
    --text: #e6edf3;
    --text2: #8b949e;
    --accent: #58a6ff;
    --avax: #e84142;
    --green: #3fb950;
    --yellow: #d29922;
}}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.6;
}}
.container {{ max-width: 1200px; margin: 0 auto; padding: 24px; }}

header {{
    text-align: center;
    padding: 48px 24px 32px;
    border-bottom: 1px solid var(--border);
    margin-bottom: 32px;
}}
header h1 {{
    font-size: 2rem;
    background: linear-gradient(135deg, var(--avax), #ff6b6b, var(--accent));
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    margin-bottom: 8px;
}}
header .subtitle {{ color: var(--text2); font-size: 1.1rem; }}
header .timestamp {{ color: var(--text2); font-size: 0.85rem; margin-top: 12px; opacity: 0.7; }}

.summary-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 16px;
    margin-bottom: 40px;
}}
.summary-card {{
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 20px;
    text-align: center;
}}
.summary-card .label {{ font-size: 0.8rem; color: var(--text2); text-transform: uppercase; letter-spacing: 0.05em; }}
.summary-card .value {{ font-size: 1.6rem; font-weight: 700; margin-top: 6px; }}
.summary-card .value.avax {{ color: var(--avax); }}
.summary-card .value.green {{ color: var(--green); }}
.summary-card .value.blue {{ color: var(--accent); }}
.summary-card .value.yellow {{ color: var(--yellow); }}

section {{
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 28px;
    margin-bottom: 28px;
}}
section h2 {{
    font-size: 1.3rem;
    margin-bottom: 6px;
    display: flex;
    align-items: center;
    gap: 10px;
}}
section h2 .icon {{ font-size: 1.1rem; }}
section .insight {{
    color: var(--text2);
    font-size: 0.9rem;
    margin-bottom: 20px;
    border-left: 3px solid var(--avax);
    padding-left: 12px;
}}
.chart-wrap {{ position: relative; width: 100%; max-height: 420px; }}
.chart-wrap canvas {{ width: 100% !important; }}

table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 0.9rem;
}}
th, td {{
    padding: 10px 14px;
    text-align: left;
    border-bottom: 1px solid var(--border);
}}
th {{
    color: var(--text2);
    font-weight: 600;
    font-size: 0.8rem;
    text-transform: uppercase;
    letter-spacing: 0.04em;
}}
tr:hover {{ background: rgba(88,166,255,0.04); }}
.target-row {{ background: rgba(232,65,66,0.08); }}
.target-row:hover {{ background: rgba(232,65,66,0.14); }}
.badge {{
    display: inline-block;
    font-size: 0.65rem;
    background: var(--avax);
    color: #fff;
    padding: 2px 7px;
    border-radius: 4px;
    margin-left: 6px;
    vertical-align: middle;
    font-weight: 600;
}}
.desc-cell {{ max-width: 320px; font-size: 0.82rem; color: var(--text2); }}
.empty-msg {{
    text-align: center;
    color: var(--green);
    padding: 24px;
    font-style: italic;
}}

.takeaways {{ padding: 0; }}
.takeaways ul {{ list-style: none; padding: 0; }}
.takeaways li {{
    padding: 14px 18px;
    border-left: 3px solid var(--avax);
    margin-bottom: 12px;
    background: rgba(232,65,66,0.05);
    border-radius: 0 8px 8px 0;
    line-height: 1.7;
}}
.takeaways li strong {{ color: var(--accent); }}

footer {{
    text-align: center;
    padding: 32px;
    color: var(--text2);
    font-size: 0.8rem;
}}
</style>
</head>
<body>
<div class="container">

<header>
    <h1>Snow Mind — Avalanche DeFi Market Research</h1>
    <p class="subtitle">How big is the market opportunity for an autonomous yield optimizer on Avalanche?</p>
    <p class="timestamp">Data fetched from DefiLlama on {fetch_time}</p>
</header>

<!-- ═══ Summary Cards ═══ -->
<div class="summary-grid">
    <div class="summary-card">
        <div class="label">Avalanche DeFi TVL</div>
        <div class="value avax">{fmt_usd(avax_tvl)}</div>
    </div>
    <div class="summary-card">
        <div class="label">Stablecoin Supply</div>
        <div class="value green">{fmt_usd(sc_supply)}</div>
    </div>
    <div class="summary-card">
        <div class="label">Lending TVL (Avalanche)</div>
        <div class="value blue">{fmt_usd(lending_tvl)}</div>
    </div>
    <div class="summary-card">
        <div class="label">Lending Protocols</div>
        <div class="value yellow">{d['num_lending']}</div>
    </div>
    <div class="summary-card">
        <div class="label">Largest Competitor TVL</div>
        <div class="value">{fmt_usd(d['max_comp_tvl']) if d['max_comp_tvl'] > 0 else 'None found'}</div>
    </div>
</div>

<!-- ═══ 1. Avalanche TVL Trend ═══ -->
<section>
    <h2><span class="icon">📈</span> Avalanche DeFi TVL Trend</h2>
    <p class="insight">Tracks the total capital locked in DeFi on Avalanche over the past 12 months.
    A growing TVL signals expanding opportunity for yield optimisation — more capital means more
    yield to capture and redistribute.</p>
    <div class="chart-wrap"><canvas id="tvlChart"></canvas></div>
</section>

<!-- ═══ 2. Lending Protocol TVLs ═══ -->
<section>
    <h2><span class="icon">🏦</span> Avalanche Lending Protocol TVLs</h2>
    <p class="insight">These are the lending protocols Snow Mind would optimise across.
    Highlighted rows are Snow Mind's primary target protocols (Benqi, Aave V3, Euler, Fluid).
    A fragmented lending landscape with multiple viable protocols is ideal for an automated optimizer.</p>
    <div style="overflow-x:auto">
    <table>
        <thead><tr>
            <th>#</th><th>Protocol</th><th>Total TVL</th><th>Avalanche TVL</th><th>1d Chg</th><th>7d Chg</th>
        </tr></thead>
        <tbody>{lending_rows}</tbody>
    </table>
    </div>
</section>

<!-- ═══ 3. Stablecoin Supply ═══ -->
<section>
    <h2><span class="icon">💵</span> Stablecoin Supply on Avalanche Over Time</h2>
    <p class="insight">Stablecoins are the primary asset deposited into lending protocols.
    This chart shows how much stablecoin capital exists on Avalanche that COULD be deposited
    into lending protocols — representing Snow Mind's total addressable market for stable-yield strategies.</p>
    <div class="chart-wrap"><canvas id="scChart"></canvas></div>
</section>

<!-- ═══ 4. Stablecoin Composition ═══ -->
<section>
    <h2><span class="icon">🥧</span> Stablecoin Composition on Avalanche</h2>
    <p class="insight">Understanding which stablecoins dominate Avalanche helps Snow Mind prioritise
    which assets to support first. USDC and USDT strategies should be the initial focus given their
    liquidity and lending-pool availability.</p>
    <div class="chart-wrap" style="max-width:480px;margin:0 auto"><canvas id="pieChart"></canvas></div>
</section>

<!-- ═══ 5. Competitor Comparison ═══ -->
<section>
    <h2><span class="icon">⚔️</span> Yield Optimizer Competitor TVL Comparison</h2>
    <p class="insight">Tracking competitors (Giza, ZyfAI, Almanak) reveals market maturity.
    Absent or minimal competitor TVL on DefiLlama signals an early-stage market where Snow Mind
    can establish dominance before others scale.</p>
    <div style="overflow-x:auto">
    <table>
        <thead><tr>
            <th>Protocol</th><th>TVL</th><th>Chains</th><th>Description</th>
        </tr></thead>
        <tbody>{comp_rows}</tbody>
    </table>
    </div>
    {"<div class='chart-wrap' style='margin-top:20px'><canvas id='compChart'></canvas></div>" if d["competitors"] else ""}
</section>

<!-- ═══ 6. Lending Fee Revenue ═══ -->
<section>
    <h2><span class="icon">💰</span> Avalanche Lending Protocol Fee Revenue</h2>
    <p class="insight">Fee revenue represents the yield generated by lending protocols and distributed
    to depositors. This is the yield pool that Snow Mind would optimise across — higher fees mean
    more reward for smart allocation.</p>
    <div style="overflow-x:auto">
    <table>
        <thead><tr>
            <th>#</th><th>Protocol</th><th>24h Fees</th><th>7d Fees</th><th>1d Chg</th>
        </tr></thead>
        <tbody>{fees_rows if fees_rows else '<tr><td colspan="5" class="empty-msg">No lending fee data available for Avalanche</td></tr>'}</tbody>
    </table>
    </div>
</section>

<!-- ═══ 7. Chain TVL Comparison ═══ -->
<section>
    <h2><span class="icon">🌐</span> Avalanche's Position in DeFi by Chain TVL</h2>
    <p class="insight">Contextualises Avalanche within the broader DeFi landscape.
    Avalanche is a top-tier chain with meaningful TVL — large enough to matter, but with less
    competition for yield-optimisation tooling compared to Ethereum or Arbitrum.</p>
    <div class="chart-wrap"><canvas id="chainChart"></canvas></div>
</section>

<!-- ═══ Key Takeaways ═══ -->
<section class="takeaways">
    <h2><span class="icon">🎯</span> Key Takeaways</h2>
    <ul>{takeaways_html}</ul>
</section>

</div>

<footer>
    Snow Mind Market Research &middot; Data sourced from <a href="https://defillama.com" style="color:var(--accent)">DefiLlama</a>
    &middot; Generated {fetch_time}
</footer>

<script>
const GRID_COLOR = 'rgba(255,255,255,0.06)';
const TICK_COLOR = '#8b949e';
Chart.defaults.color = TICK_COLOR;
Chart.defaults.borderColor = GRID_COLOR;

// 1. TVL Trend
new Chart(document.getElementById('tvlChart'), {{
    type: 'line',
    data: {{
        labels: {tvl_labels},
        datasets: [{{
            label: 'Avalanche TVL ($M)',
            data: {tvl_values},
            borderColor: '#e84142',
            backgroundColor: 'rgba(232,65,66,0.10)',
            fill: true,
            tension: 0.3,
            pointRadius: 0,
            borderWidth: 2,
        }}]
    }},
    options: {{
        responsive: true,
        plugins: {{
            legend: {{ display: false }},
            tooltip: {{ callbacks: {{ label: ctx => '$' + ctx.parsed.y.toLocaleString() + 'M' }} }}
        }},
        scales: {{
            y: {{ ticks: {{ callback: v => '$' + v + 'M' }}, grid: {{ color: GRID_COLOR }} }},
            x: {{ ticks: {{ maxTicksLimit: 12 }}, grid: {{ display: false }} }}
        }}
    }}
}});

// 3. Stablecoin Supply
new Chart(document.getElementById('scChart'), {{
    type: 'line',
    data: {{
        labels: {sc_labels},
        datasets: [{{
            label: 'Stablecoin Supply ($M)',
            data: {sc_values},
            borderColor: '#3fb950',
            backgroundColor: 'rgba(63,185,80,0.10)',
            fill: true,
            tension: 0.3,
            pointRadius: 0,
            borderWidth: 2,
        }}]
    }},
    options: {{
        responsive: true,
        plugins: {{
            legend: {{ display: false }},
            tooltip: {{ callbacks: {{ label: ctx => '$' + ctx.parsed.y.toLocaleString() + 'M' }} }}
        }},
        scales: {{
            y: {{ ticks: {{ callback: v => '$' + v + 'M' }}, grid: {{ color: GRID_COLOR }} }},
            x: {{ ticks: {{ maxTicksLimit: 12 }}, grid: {{ display: false }} }}
        }}
    }}
}});

// 4. Stablecoin Pie
new Chart(document.getElementById('pieChart'), {{
    type: 'doughnut',
    data: {{
        labels: {pie_labels},
        datasets: [{{
            data: {pie_values},
            backgroundColor: ['#2775CA','#26A17B','#F5AC37','#8b5cf6','#ec4899','#6b7280'],
            borderColor: '#161b22',
            borderWidth: 2,
        }}]
    }},
    options: {{
        responsive: true,
        plugins: {{
            legend: {{ position: 'right', labels: {{ padding: 16 }} }},
            tooltip: {{ callbacks: {{ label: ctx => ctx.label + ': $' + ctx.parsed.toLocaleString() + 'M' }} }}
        }}
    }}
}});

// 5. Competitor Chart
(function() {{
    var el = document.getElementById('compChart');
    if (!el) return;
    var ds = {comp_datasets_js};
    if (!ds.length) return;
    new Chart(el, {{
        type: 'line',
        data: {{ labels: {comp_labels}, datasets: ds }},
        options: {{
            responsive: true,
            plugins: {{
                tooltip: {{ callbacks: {{ label: ctx => ctx.dataset.label + ': $' + ctx.parsed.y.toLocaleString() + 'M' }} }}
            }},
            scales: {{
                y: {{ ticks: {{ callback: v => '$' + v + 'M' }}, grid: {{ color: GRID_COLOR }} }},
                x: {{ ticks: {{ maxTicksLimit: 12 }}, grid: {{ display: false }} }}
            }}
        }}
    }});
}})();

// 7. Chain TVL Bar
new Chart(document.getElementById('chainChart'), {{
    type: 'bar',
    data: {{
        labels: {chain_labels},
        datasets: [{{
            label: 'Chain TVL ($B)',
            data: {chain_values},
            backgroundColor: {chain_colors},
            borderRadius: 4,
        }}]
    }},
    options: {{
        responsive: true,
        indexAxis: 'y',
        plugins: {{
            legend: {{ display: false }},
            tooltip: {{ callbacks: {{ label: ctx => '$' + ctx.parsed.x.toLocaleString() + 'B' }} }}
        }},
        scales: {{
            x: {{ ticks: {{ callback: v => '$' + v + 'B' }}, grid: {{ color: GRID_COLOR }} }},
            y: {{ grid: {{ display: false }} }}
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
    print("  Snow Mind — Avalanche DeFi Market Research Dashboard")
    print("=" * 60)
    fetch_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    print("\n[1/3] Fetching data from DefiLlama...")
    raw = fetch_all()

    print("\n[2/3] Processing data...")
    processed = process(raw)

    print("\n[3/3] Generating dashboard...")
    html = build_html(processed, fetch_time)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\n{'=' * 60}")
    print(f"  Dashboard generated: {OUTPUT_FILE}")
    print(f"  Raw data saved to:   {DATA_DIR}/")
    print(f"  Avalanche TVL:       {fmt_usd(processed['current_avax_tvl'])}")
    print(f"  Stablecoin Supply:   {fmt_usd(processed['current_sc_supply'])}")
    print(f"  Lending TVL:         {fmt_usd(processed['total_lending_tvl'])}")
    print(f"  Lending Protocols:   {processed['num_lending']}")
    print(f"  Competitors Found:   {len(processed['competitors'])}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
