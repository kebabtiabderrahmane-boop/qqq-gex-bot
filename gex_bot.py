"""
QQQ GEX Confluence Bot - LIVE DATA VERSION
============================================
This script fetches REAL, LIVE options data from Yahoo Finance
and calculates actual Gamma Exposure values.

NO HARDCODED PRICES - All data is pulled from live market data.
"""

import yfinance as yf
import numpy as np
from scipy.stats import norm
import datetime
import json
from collections import defaultdict
import pprint

TICKER = "QQQ"

def is_valid_number(val):
    """Check if value is a valid number (not NaN or None)."""
    if val is None:
        return False
    try:
        return not np.isnan(float(val))
    except:
        return False

def calc_gex(strike, oi, spot, iv, dte, is_call):
    """
    Calculate Gamma Exposure using Black-Scholes formula.
    
    GEX = OpenInterest * 100 * Gamma * Spot (for calls)
    GEX = -1 * OpenInterest * 100 * Gamma * Spot (for puts)
    
    Where Gamma = norm.pdf(d1) / (spot * iv * sqrt(T))
    """
    if oi == 0 or iv == 0 or spot == 0:
        return 0.0
    
    T = max(0.5, dte) / 365.0  # Time to expiration in years
    r = 0.05  # Risk-free rate
    
    try:
        # d1 from Black-Scholes
        d1 = (np.log(spot / strike) + (r + 0.5 * iv**2) * T) / (iv * np.sqrt(T))
        
        # Gamma calculation
        gamma = norm.pdf(d1) / (spot * iv * np.sqrt(T))
        
        # GEX = OpenInterest * 100 (contract multiplier) * Gamma * Spot
        # Calls add positive gamma, Puts add negative gamma
        if is_call:
            gex = oi * 100 * gamma * spot
        else:
            gex = -1 * oi * 100 * gamma * spot
        
        return gex
    except Exception as e:
        print(f"      GEX calc error for strike {strike}: {e}")
        return 0.0

def round_strike(strike, step=1.0):
    """Round strike to nearest step (0.5 or 1.0)."""
    return round(strike / step) * step

def fetch_live_options_chain(ticker, expirations):
    """
    Fetch COMPLETE options chain data from Yahoo Finance.
    Returns raw data + calculated GEX for every strike.
    """
    print("\n" + "="*70)
    print("FETCHING LIVE OPTIONS DATA FROM YAHOO FINANCE")
    print("="*70)
    
    all_calls = []
    all_puts = []
    by_expiration = {}
    
    for exp in expirations:
        print(f"\n📅 Expiration: {exp}")
        try:
            chain = ticker.option_chain(exp)
            dte = max(1, (datetime.datetime.strptime(exp, '%Y-%m-%d') - datetime.datetime.now()).days)
            print(f"   DTE: {dte} days")
            
            exp_calls = []
            exp_puts = []
            
            # Process ALL Call options
            print(f"\n   📊 CALLS ({len(chain.calls)} strikes):")
            for idx, row in chain.calls.iterrows():
                strike = float(row['strike'])
                iv = float(row['impliedVolatility']) if is_valid_number(row['impliedVolatility']) else 0.20
                volume = int(row['volume']) if is_valid_number(row['volume']) else 0
                oi = int(row['openInterest']) if is_valid_number(row['openInterest']) else 0
                last = float(row['lastPrice']) if is_valid_number(row.get('lastPrice', None)) else 0.0
                
                # Calculate GEX for this specific strike
                gex = calc_gex(strike, oi, ticker.fast_info['last_price'], iv, dte, is_call=True)
                
                call_data = {
                    'strike': strike,
                    'expiration': exp,
                    'dte': dte,
                    'iv': iv,
                    'volume': volume,
                    'openInterest': oi,
                    'lastPrice': last,
                    'gex': gex,
                    'gex_positive': gex > 0
                }
                
                all_calls.append(call_data)
                exp_calls.append(call_data)
                
                # Print first 5 and last 5 strikes to prove live data
                if idx < 5 or idx >= len(chain.calls) - 3:
                    print(f"      Strike ${strike:.2f}: OI={oi:,}, Vol={volume:,}, IV={iv:.2%}, GEX={gex:,.0f}")
            
            if len(chain.calls) > 10:
                print(f"      ... ({len(chain.calls) - 8} more strikes) ...")
            
            # Process ALL Put options
            print(f"\n   📊 PUTS ({len(chain.puts)} strikes):")
            for idx, row in chain.puts.iterrows():
                strike = float(row['strike'])
                iv = float(row['impliedVolatility']) if is_valid_number(row['impliedVolatility']) else 0.20
                volume = int(row['volume']) if is_valid_number(row['volume']) else 0
                oi = int(row['openInterest']) if is_valid_number(row['openInterest']) else 0
                last = float(row['lastPrice']) if is_valid_number(row.get('lastPrice', None)) else 0.0
                
                # Calculate GEX for this specific strike
                gex = calc_gex(strike, oi, ticker.fast_info['last_price'], iv, dte, is_call=False)
                
                put_data = {
                    'strike': strike,
                    'expiration': exp,
                    'dte': dte,
                    'iv': iv,
                    'volume': volume,
                    'openInterest': oi,
                    'lastPrice': last,
                    'gex': gex,
                    'gex_positive': gex > 0
                }
                
                all_puts.append(put_data)
                exp_puts.append(put_data)
                
                # Print first 5 and last 5 strikes
                if idx < 5 or idx >= len(chain.puts) - 3:
                    print(f"      Strike ${strike:.2f}: OI={oi:,}, Vol={volume:,}, IV={iv:.2%}, GEX={gex:,.0f}")
            
            if len(chain.puts) > 10:
                print(f"      ... ({len(chain.puts) - 8} more strikes) ...")
            
            by_expiration[exp] = {
                'calls': exp_calls,
                'puts': exp_puts,
                'dte': dte,
                'total_call_oi': sum(c['openInterest'] for c in exp_calls),
                'total_put_oi': sum(p['openInterest'] for p in exp_puts),
                'total_call_vol': sum(c['volume'] for c in exp_calls),
                'total_put_vol': sum(p['volume'] for p in exp_puts)
            }
            
        except Exception as e:
            print(f"   ❌ Error fetching {exp}: {e}")
            continue
    
    print("\n" + "="*70)
    print("SUMMARY OF FETCHED DATA")
    print("="*70)
    print(f"Total Calls fetched: {len(all_calls)}")
    print(f"Total Puts fetched: {len(all_puts)}")
    print(f"Total Open Interest (Calls): {sum(c['openInterest'] for c in all_calls):,}")
    print(f"Total Open Interest (Puts): {sum(p['openInterest'] for p in all_puts):,}")
    print(f"Total Volume (Calls): {sum(c['volume'] for c in all_calls):,}")
    print(f"Total Volume (Puts): {sum(p['volume'] for p in all_puts):,}")
    
    return {
        'calls': all_calls,
        'puts': all_puts,
        'by_expiration': by_expiration
    }

def calculate_all_gex_levels(spot, chain_data, today_str, is_0dte):
    """
    Calculate ALL GEX-based levels from the fetched data.
    This is the actual mathematical analysis - NO HARDCODING.
    """
    print("\n" + "="*70)
    print("CALCULATING GEX LEVELS (MATHEMATICAL ANALYSIS)")
    print("="*70)
    
    all_gex = chain_data['calls'] + chain_data['puts']
    
    # Sort by strike for analysis
    all_gex_by_strike = sorted(all_gex, key=lambda x: x['strike'])
    
    print(f"\nAnalyzing {len(all_gex_by_strike)} total options...")
    
    signals_by_strike = defaultdict(list)
    
    # =================================================================
    # 1. 0DTE LEVELS (Only if today is an expiration)
    # =================================================================
    if is_0dte and today_str in chain_data['by_expiration']:
        print("\n📌 0DTE LEVELS (Today's Expiration)")
        print("-" * 40)
        
        exp_data = chain_data['by_expiration'][today_str]
        exp_all_gex = exp_data['calls'] + exp_data['puts']
        
        # Find 0DTE Call Wall: highest positive GEX above spot
        call_candidates = [x for x in exp_all_gex if x['strike'] > spot and x['gex'] > 0]
        if call_candidates:
            dte_cw_strike = max(call_candidates, key=lambda x: x['gex'])['strike']
            dte_cw_gex = max(call_candidates, key=lambda x: x['gex'])['gex']
            signals_by_strike[round_strike(dte_cw_strike)].append("0DTE CW")
            print(f"   0DTE Call Wall: ${dte_cw_strike:.2f} (GEX: {dte_cw_gex:,.0f})")
        
        # Find 0DTE Put Wall: most negative GEX below spot
        put_candidates = [x for x in exp_all_gex if x['strike'] < spot and x['gex'] < 0]
        if put_candidates:
            dte_pw_strike = min(put_candidates, key=lambda x: x['gex'])['strike']
            dte_pw_gex = min(put_candidates, key=lambda x: x['gex'])['gex']
            signals_by_strike[round_strike(dte_pw_strike)].append("0DTE PW")
            print(f"   0DTE Put Wall: ${dte_pw_strike:.2f} (GEX: {dte_pw_gex:,.0f})")
        
        # Find 0DTE Gamma Flip
        sorted_exp = sorted(exp_all_gex, key=lambda x: x['strike'])
        for i in range(len(sorted_exp) - 1):
            curr = sorted_exp[i]
            next_s = sorted_exp[i + 1]
            if curr['gex'] > 0 and next_s['gex'] < 0 and curr['strike'] <= spot <= next_s['strike']:
                signals_by_strike[round_strike(curr['strike'])].append("0DTE Flip")
                print(f"   0DTE Gamma Flip: ${curr['strike']:.2f}")
                break
    else:
        print("\n📌 0DTE LEVELS: Not applicable (no 0DTE today)")
    
    # =================================================================
    # 2. AGGREGATE LEVELS (All expirations combined)
    # =================================================================
    print("\n📌 AGGREGATE LEVELS (All Expirations)")
    print("-" * 40)
    
    # Aggregate Call Wall
    agg_call_candidates = [x for x in all_gex if x['strike'] > spot and x['gex'] > 0]
    if agg_call_candidates:
        agg_cw_strike = max(agg_call_candidates, key=lambda x: x['gex'])['strike']
        agg_cw_gex = max(agg_call_candidates, key=lambda x: x['gex'])['gex']
        signals_by_strike[round_strike(agg_cw_strike)].append("Agg CW")
        print(f"   Aggregate Call Wall: ${agg_cw_strike:.2f} (GEX: {agg_cw_gex:,.0f})")
    
    # Aggregate Put Wall
    agg_put_candidates = [x for x in all_gex if x['strike'] < spot and x['gex'] < 0]
    if agg_put_candidates:
        agg_pw_strike = min(agg_put_candidates, key=lambda x: x['gex'])['strike']
        agg_pw_gex = min(agg_put_candidates, key=lambda x: x['gex'])['gex']
        signals_by_strike[round_strike(agg_pw_strike)].append("Agg PW")
        print(f"   Aggregate Put Wall: ${agg_pw_strike:.2f} (GEX: {agg_pw_gex:,.0f})")
    
    # =================================================================
    # 3. GAMMA FLIP (Where GEX crosses zero)
    # =================================================================
    print("\n📌 GAMMA FLIP POINTS")
    print("-" * 40)
    
    sorted_all = sorted(all_gex, key=lambda x: x['strike'])
    gamma_flips_found = 0
    for i in range(len(sorted_all) - 1):
        curr = sorted_all[i]
        next_s = sorted_all[i + 1]
        if curr['gex'] > 0 and next_s['gex'] < 0:
            signals_by_strike[round_strike(curr['strike'])].append("Gamma Flip")
            print(f"   Gamma Flip: ${curr['strike']:.2f} (GEX: {curr['gex']:,.0f} → {next_s['gex']:,.0f})")
            gamma_flips_found += 1
    if gamma_flips_found == 0:
        print("   No gamma flips found in current chain")
    
    # =================================================================
    # 4. MAX PAIN (Where option buyers lose the most)
    # =================================================================
    print("\n📌 MAX PAIN CALCULATION")
    print("-" * 40)
    
    # Get unique strikes
    all_strikes = sorted(set([x['strike'] for x in all_gex]))
    max_pain_strike = spot
    min_pain_value = float('inf')
    
    # Calculate pain at each strike
    pain_samples = []
    for test_strike in all_strikes:
        pain = 0
        for c in chain_data['calls']:
            if c['strike'] >= test_strike:
                pain += c['openInterest'] * max(0, c['strike'] - test_strike)
        for p in chain_data['puts']:
            if p['strike'] <= test_strike:
                pain += p['openInterest'] * max(0, test_strike - p['strike'])
        
        pain_samples.append((test_strike, pain))
        
        if pain < min_pain_value:
            min_pain_value = pain
            max_pain_strike = test_strike
    
    signals_by_strike[round_strike(max_pain_strike)].append("Max Pain")
    print(f"   Max Pain Strike: ${max_pain_strike:.2f} (Total Pain: ${min_pain_value:,.0f})")
    
    # =================================================================
    # 5. TOP 10 GEX LEVELS
    # =================================================================
    print("\n📌 TOP 10 GEX LEVELS")
    print("-" * 40)
    
    # Sort by absolute GEX
    by_gex = sorted(all_gex, key=lambda x: abs(x['gex']), reverse=True)
    top_10_gex = by_gex[:10]
    
    for i, opt in enumerate(top_10_gex, 1):
        sig_type = "CALL" if opt['gex'] > 0 else "PUT"
        signals_by_strike[round_strike(opt['strike'])].append("Top 10 GEX")
        print(f"   #{i}: ${opt['strike']:.2f} ({sig_type}) - GEX: {opt['gex']:,.0f}")
    
    # =================================================================
    # 6. HIGH VOLUME LEVELS (HVL)
    # =================================================================
    print("\n📌 HIGH VOLUME LEVELS")
    print("-" * 40)
    
    volume_by_strike = defaultdict(int)
    for c in chain_data['calls']:
        volume_by_strike[c['strike']] += c['volume']
    for p in chain_data['puts']:
        volume_by_strike[p['strike']] += p['volume']
    
    sorted_by_vol = sorted(volume_by_strike.items(), key=lambda x: x[1], reverse=True)
    hvl_strikes = [strike for strike, vol in sorted_by_vol[:5]]
    
    for i, (strike, vol) in enumerate(sorted_by_vol[:5], 1):
        signals_by_strike[round_strike(strike)].append("HVL")
        print(f"   #{i}: ${strike:.2f} - Total Volume: {vol:,}")
    
    # =================================================================
    # 7. D1 BOUNDS (Outer bounds of high GEX cluster)
    # =================================================================
    print("\n📌 D1 BOUNDS (GEX Cluster Edges)")
    print("-" * 40)
    
    # Get top 20% by absolute GEX
    top_count = max(5, len(by_gex) // 5)
    top_gex_strikes = [x['strike'] for x in by_gex[:top_count]]
    
    if top_gex_strikes:
        max_d1 = max(top_gex_strikes)
        min_d1 = min(top_gex_strikes)
        
        signals_by_strike[round_strike(max_d1)].append("Max D1")
        signals_by_strike[round_strike(min_d1)].append("Min D1")
        print(f"   Max D1 (Upper Bound): ${max_d1:.2f}")
        print(f"   Min D1 (Lower Bound): ${min_d1:.2f}")
    
    # =================================================================
    # 8. INTRADAY LEVELS (Unusual volume vs OI)
    # =================================================================
    print("\n📌 INTRADAY UNUSUAL VOLUME")
    print("-" * 40)
    
    unusual = []
    for opt in all_gex:
        if opt['openInterest'] > 100:  # Minimum OI threshold
            ratio = opt['volume'] / opt['openInterest'] if opt['openInterest'] > 0 else 0
            if ratio > 2.0:  # Volume 2x greater than OI
                unusual.append((opt['strike'], ratio, opt['volume'], opt['openInterest']))
    
    unusual.sort(key=lambda x: x[1], reverse=True)
    for strike, ratio, vol, oi in unusual[:5]:
        signals_by_strike[round_strike(strike)].append("Intraday")
        print(f"   ${strike:.2f}: Vol/OI Ratio = {ratio:.2f}x (Vol: {vol:,}, OI: {oi:,})")
    
    return signals_by_strike

def build_confluence_output(spot, signals_by_strike):
    """
    Build the final confluence output.
    ONLY include strikes with 2+ signals (score >= 2).
    """
    print("\n" + "="*70)
    print("CONFLUENCE ANALYSIS (Score >= 2 Required)")
    print("="*70)
    
    confluence = []
    
    for strike, tags in sorted(signals_by_strike.items()):
        score = len(tags)
        
        if score < 2:
            continue
        
        # Determine type based on tag composition
        call_score = sum(1 for t in tags if 'CW' in t or 'Top' in t)
        put_score = sum(1 for t in tags if 'PW' in t or 'put' in t.lower())
        
        if any('Flip' in t for t in tags):
            conf_type = 'FLIP'
        elif call_score > put_score:
            conf_type = 'CALL'
        elif put_score > call_score:
            conf_type = 'PUT'
        else:
            conf_type = 'NEUTRAL'
        
        level = {
            'strike': round(strike, 2),
            'tags': ' + '.join(tags),
            'score': score,
            'type': conf_type
        }
        
        confluence.append(level)
        print(f"\n   ✅ ${level['strike']:.2f}")
        print(f"      Type: {level['type']}")
        print(f"      Score: {level['score']}")
        print(f"      Tags: {level['tags']}")
    
    # Sort by score descending, then by distance from spot
    confluence.sort(key=lambda x: (-x['score'], abs(x['strike'] - spot)))
    
    print(f"\n\n📊 TOTAL CONFLUENCE LEVELS FOUND: {len(confluence)}")
    
    return confluence[:10]  # Return max 10

def generate_pine_script(confluence, spot, is_0dte, updated):
    """Generate a TradingView Pine Script with the confluence values hardcoded."""
    
    # Build level inputs
    level_configs = []
    for i, c in enumerate(confluence[:10], 1):
        level_configs.append(f'''// LEVEL {i}
input bool SHOW_{i} = true
input float STRIKE_{i} = {c['strike']:.2f}
input string TAGS_{i} = "{c['tags']}"
input int SCORE_{i} = {c['score']}
input string TYPE_{i} = "{c['type']}"''')
    
    # Build draw calls
    draw_calls = []
    for i in range(1, 11):
        draw_calls.append(f'DrawLevel(SHOW_{i}, STRIKE_{i}, TAGS_{i}, SCORE_{i}, TYPE_{i})')
    
    pine_code = f'''//@version=5
indicator("QQQ GEX Confluence Auto", overlay=true, max_lines_count=500)

// ============================================================
// QQQ GEX CONFLOENCE INDICATOR - AUTO-GENERATED
// ============================================================
// Generated by GitHub Actions from LIVE market data
// Last Updated: {updated}
// Spot Price: ${spot:.2f}
// 0DTE: {"Yes" if is_0dte else "No"}
// Levels: {len(confluence)}
// 
// This file is AUTO-GENERATED - do not edit manually!
// Data source: gex_bot.py on GitHub Actions
// ============================================================

// ----------------------
// COLORS
// ----------------------
color COLOR_CALL = #00FF00
color COLOR_PUT = #FF0000
color COLOR_FLIP = #FFFF00
color COLOR_BG = #1a1a1a

// ----------------------
// LEVEL INPUTS (AUTO-GENERATED)
// ----------------------
{chr(10).join(level_configs)}

// ----------------------
// HELPER FUNCTIONS
// ----------------------
color getColor(string t) =>
    switch t
        "CALL" => COLOR_CALL
        "PUT" => COLOR_PUT
        "FLIP" => COLOR_FLIP
        => COLOR_BG

// ----------------------
// DRAW LEVEL
// ----------------------
void DrawLevel(bool show, float strike, string tags, int score, string typ) =>
    if show and strike > 0
        clr = getColor(typ)
        line.new(x1=bar_index - 100, y1=strike, x2=bar_index, y2=strike, 
                 xloc=xloc.bar_index, color=clr, style=line.style_solid, width=3)
        label.new(x=bar_index + 3, y=strike, 
                  text="⚡" + str.tostring(score) + " " + tags + " @" + str.tformat(strike, format.mintick),
                  xloc=xloc.bar_index, color=color.new(clr, 60), textcolor=clr, 
                  size=size.normal, style=label.style_label_right)

// ----------------------
// EXECUTE
// ----------------------
{chr(10).join(draw_calls)}

// ============================================================
// AUTO-UPDATE INSTRUCTIONS
// ============================================================
// This indicator updates automatically via GitHub Actions!
// 
// When new data arrives:
// 1. GitHub Actions commits a new version of this file
// 2. In TradingView, click "Add to Chart" on the indicator
// 3. Or click the refresh icon on the indicator
//
// No manual copying needed! 🎉
// ============================================================'''

    return pine_code

if __name__ == "__main__":
    print("\n" + "#"*70)
    print("# QQQ GEX CONFLUENCE BOT - LIVE DATA EDITION")
    print("# NO HARDCODED PRICES - ALL DATA FROM LIVE MARKET")
    print("#"*70)
    
    # Initialize ticker
    ticker = yf.Ticker(TICKER)
    
    # Get current spot price
    spot = ticker.fast_info['last_price']
    print(f"\n📈 CURRENT QQQ SPOT PRICE: ${spot:.2f}")
    
    # Get available expirations
    expirations = list(ticker.options)[:6]  # Up to 6 expirations
    print(f"📅 AVAILABLE EXPIRATIONS: {len(expirations)}")
    for exp in expirations:
        print(f"      - {exp}")
    
    # Check if today is an expiration
    today_str = datetime.datetime.now().strftime('%Y-%m-%d')
    is_0dte = today_str in expirations
    print(f"\n🎯 IS 0DTE TODAY: {is_0dte}")
    
    # =====================================================================
    # STEP 1: FETCH ALL LIVE OPTIONS DATA
    # =====================================================================
    chain_data = fetch_live_options_chain(ticker, expirations)
    
    # =====================================================================
    # STEP 2: CALCULATE ALL GEX LEVELS
    # =====================================================================
    signals_by_strike = calculate_all_gex_levels(spot, chain_data, today_str, is_0dte)
    
    # =====================================================================
    # STEP 3: BUILD CONFLUENCE (Score >= 2 Only)
    # =====================================================================
    confluence = build_confluence_output(spot, signals_by_strike)
    
    # =====================================================================
    # STEP 4: SAVE TO JSON
    # =====================================================================
    output = {
        'spot': round(spot, 2),
        'confluence': confluence,
        'updated': datetime.datetime.now().strftime('%H:%M:%S'),
        'is_0dte': is_0dte
    }
    
    with open('data.json', 'w') as f:
        json.dump(output, f, indent=2)
    
    # =====================================================================
    # STEP 5: GENERATE AUTO-UPDATE PINE SCRIPT
    # =====================================================================
    updated = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    pine_code = generate_pine_script(confluence, spot, is_0dte, updated)
    
    with open('qqq-gex-auto.pine', 'w') as f:
        f.write(pine_code)
    
    print("\n" + "="*70)
    print("FINAL OUTPUT SAVED TO data.json")
    print("="*70)
    print(json.dumps(output, indent=2))
    print("\n" + "="*70)
    print("PINE SCRIPT SAVED TO qqq-gex-auto.pine")
    print("="*70)
    print("\n✅ Script completed successfully!")
