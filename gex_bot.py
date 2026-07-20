import yfinance as yf
import numpy as np
from scipy.stats import norm
import datetime
import json
from collections import defaultdict

TICKER = "QQQ"

def calc_gex(strike, oi, spot, iv, dte, is_call):
    """Calculate Gamma Exposure for a single option."""
    if oi == 0 or iv == 0:
        return 0
    T = max(0.5, dte) / 365.0
    r = 0.05
    try:
        d1 = (np.log(spot / strike) + (r + 0.5 * iv**2) * T) / (iv * np.sqrt(T))
        gamma = norm.pdf(d1) / (spot * iv * np.sqrt(T))
        gex = oi * 100 * gamma * spot * (1 if is_call else -1)
        return gex
    except:
        return 0

def round_strike(strike, step=1.0):
    """Round strike to nearest step (0.5 or 1.0)."""
    return round(strike / step) * step

def get_all_chain_data(ticker, expirations):
    """Fetch complete options chain data for all expirations."""
    all_data = {
        'calls': [],
        'puts': [],
        'by_expiration': {}
    }
    
    for exp in expirations:
        try:
            chain = ticker.option_chain(exp)
            dte = max(1, (datetime.datetime.strptime(exp, '%Y-%m-%d') - datetime.datetime.now()).days)
            
            exp_calls = []
            exp_puts = []
            
            for _, row in chain.calls.iterrows():
                iv = row['impliedVolatility'] if pd_notna(row['impliedVolatility']) else 0.20
                vol = row['volume'] if pd_notna(row['volume']) else 0
                oi = row['openInterest'] if pd_notna(row['openInterest']) else 0
                
                gex = calc_gex(row['strike'], oi, ticker.fast_info['last_price'], iv, dte, True)
                
                call_data = {
                    'strike': row['strike'],
                    'expiration': exp,
                    'dte': dte,
                    'iv': iv,
                    'volume': vol,
                    'openInterest': oi,
                    'gex': gex
                }
                all_data['calls'].append(call_data)
                exp_calls.append(call_data)
                
            for _, row in chain.puts.iterrows():
                iv = row['impliedVolatility'] if pd_notna(row['impliedVolatility']) else 0.20
                vol = row['volume'] if pd_notna(row['volume']) else 0
                oi = row['openInterest'] if pd_notna(row['openInterest']) else 0
                
                gex = calc_gex(row['strike'], oi, ticker.fast_info['last_price'], iv, dte, False)
                
                put_data = {
                    'strike': row['strike'],
                    'expiration': exp,
                    'dte': dte,
                    'iv': iv,
                    'volume': vol,
                    'openInterest': oi,
                    'gex': gex
                }
                all_data['puts'].append(put_data)
                exp_puts.append(put_data)
                
            all_data['by_expiration'][exp] = {'calls': exp_calls, 'puts': exp_puts, 'dte': dte}
            
        except Exception as e:
            print(f"Error fetching {exp}: {e}")
            continue
            
    return all_data

def pd_notna(val):
    """Check if value is not NaN."""
    try:
        return not np.isnan(val)
    except:
        return val is not None

def find_walls(gex_list, spot, gex_type='call'):
    """Find Call Wall (highest GEX above spot) or Put Wall (lowest GEX below spot)."""
    if gex_type == 'call':
        candidates = [x for x in gex_list if x['strike'] > spot and x['gex'] > 0]
        if candidates:
            return max(candidates, key=lambda x: x['gex'])['strike']
    else:
        candidates = [x for x in gex_list if x['strike'] < spot and x['gex'] < 0]
        if candidates:
            return min(candidates, key=lambda x: x['gex'])['strike']
    return spot

def find_gamma_flip(gex_list, spot):
    """Find the price where GEX transitions from positive to negative."""
    sorted_gex = sorted(gex_list, key=lambda x: x['strike'])
    
    for i in range(len(sorted_gex) - 1):
        curr = sorted_gex[i]
        next_strike = sorted_gex[i + 1]
        
        if curr['strike'] <= spot <= next_strike['strike']:
            if curr['gex'] > 0 and next_strike['gex'] < 0:
                return curr['strike']
            if curr['gex'] < 0 and next_strike['gex'] > 0:
                return curr['strike']
    return spot

def find_max_pain(chain_data, spot):
    """Calculate Max Pain - strike where option buyers lose most."""
    calls = chain_data['calls']
    puts = chain_data['puts']
    
    all_strikes = sorted(set([c['strike'] for c in calls] + [p['strike'] for p in puts]))
    
    max_pain = spot
    min_pain = float('inf')
    
    for strike in all_strikes:
        pain = 0
        
        # Calculate pain from calls above strike (call buyers lose when price rises above strike)
        for c in calls:
            if c['strike'] >= strike:
                pain += c.get('openInterest', 0) * max(0, c['strike'] - strike)
        
        # Calculate pain from puts below strike (put buyers lose when price falls below strike)
        for p in puts:
            if p['strike'] <= strike:
                pain += p.get('openInterest', 0) * max(0, strike - p['strike'])
        
        if pain < min_pain:
            min_pain = pain
            max_pain = strike
    
    return max_pain

def find_hvl(chain_data, top_n=5):
    """Find High Volume Levels - strikes with highest total volume."""
    volume_by_strike = defaultdict(lambda: {'call_vol': 0, 'put_vol': 0, 'total_vol': 0})
    
    for c in chain_data['calls']:
        volume_by_strike[c['strike']]['call_vol'] += c.get('volume', 0)
        volume_by_strike[c['strike']]['total_vol'] += c.get('volume', 0)
    
    for p in chain_data['puts']:
        volume_by_strike[p['strike']]['put_vol'] += p.get('volume', 0)
        volume_by_strike[p['strike']]['total_vol'] += p.get('volume', 0)
    
    sorted_by_vol = sorted(volume_by_strike.items(), key=lambda x: x[1]['total_vol'], reverse=True)
    return [strike for strike, _ in sorted_by_vol[:top_n]]

def find_top_10_gex(chain_data):
    """Find top 10 strikes by absolute GEX."""
    all_gex = []
    for c in chain_data['calls']:
        all_gex.append({'strike': c['strike'], 'gex': c['gex'], 'type': 'call'})
    for p in chain_data['puts']:
        all_gex.append({'strike': p['strike'], 'gex': abs(p['gex']), 'type': 'put'})
    
    sorted_gex = sorted(all_gex, key=lambda x: abs(x['gex']), reverse=True)
    return [(x['strike'], x['type']) for x in sorted_gex[:10]]

def find_d1_bounds(gex_list, spot):
    """Find Max D1 (upper) and Min D1 (lower) bounds of highest GEX cluster."""
    # Sort by absolute GEX
    sorted_by_gex = sorted(gex_list, key=lambda x: abs(x['gex']), reverse=True)
    
    # Get top 20% of strikes by GEX
    top_count = max(5, len(sorted_by_gex) // 5)
    top_gex = sorted_by_gex[:top_count]
    
    if not top_gex:
        return spot + 10, spot - 10
    
    strikes = [x['strike'] for x in top_gex]
    max_d1 = max(strikes)
    min_d1 = min(strikes)
    
    return max_d1, min_d1

def find_intraday_levels(chain_data, expirations):
    """Find strikes with unusual volume vs open interest."""
    unusual = []
    
    for exp in expirations[:3]:
        if exp not in chain_data['by_expiration']:
            continue
        exp_data = chain_data['by_expiration'][exp]
        
        for c in exp_data['calls']:
            if c['openInterest'] > 0:
                ratio = c['volume'] / c['openInterest']
                if ratio > 2:  # Unusual volume
                    unusual.append((c['strike'], 'call', ratio))
        
        for p in exp_data['puts']:
            if p['openInterest'] > 0:
                ratio = p['volume'] / p['openInterest']
                if ratio > 2:
                    unusual.append((p['strike'], 'put', ratio))
    
    # Return top 5 unusual levels
    unusual.sort(key=lambda x: x[2], reverse=True)
    return [(s, t) for s, t, r in unusual[:5]]

def build_confluence(spot, chain_data, today_str, is_0dte):
    """Build confluence dictionary - group signals by strike price."""
    all_gex = chain_data['calls'] + chain_data['puts']
    all_gex.sort(key=lambda x: x['strike'])
    
    # Calculate all signal types
    signals_by_strike = defaultdict(list)
    
    # 1. 0DTE Levels
    if is_0dte and today_str in chain_data['by_expiration']:
        exp_data = chain_data['by_expiration'][today_str]
        exp_calls = exp_data['calls']
        exp_puts = exp_data['puts']
        exp_gex = exp_calls + exp_puts
        
        dte_cw = find_walls(exp_gex, spot, 'call')
        dte_pw = find_walls(exp_gex, spot, 'put')
        dte_flip = find_gamma_flip(exp_gex, spot)
        
        signals_by_strike[round_strike(dte_cw)].append("0DTE CW")
        signals_by_strike[round_strike(dte_pw)].append("0DTE PW")
        signals_by_strike[round_strike(dte_flip)].append("0DTE Flip")
    
    # 2. Aggregate Levels (all expirations combined)
    agg_cw = find_walls(all_gex, spot, 'call')
    agg_pw = find_walls(all_gex, spot, 'put')
    agg_flip = find_gamma_flip(all_gex, spot)
    
    signals_by_strike[round_strike(agg_cw)].append("Agg CW")
    signals_by_strike[round_strike(agg_pw)].append("Agg PW")
    signals_by_strike[round_strike(agg_flip)].append("Agg Flip")
    
    # 3. Gamma Flips
    gamma_flip = find_gamma_flip(all_gex, spot)
    signals_by_strike[round_strike(gamma_flip)].append("Gamma Flip")
    
    # 4. Max Pain
    max_pain = find_max_pain(chain_data, spot)
    signals_by_strike[round_strike(max_pain)].append("Max Pain")
    
    # 5. Top 10 GEX Levels
    top_10 = find_top_10_gex(chain_data)
    for strike, typ in top_10:
        signals_by_strike[round_strike(strike)].append(f"Top 10 GEX")
    
    # 6. HVL (High Volume Levels)
    hvl = find_hvl(chain_data)
    for strike in hvl:
        signals_by_strike[round_strike(strike)].append("HVL")
    
    # 7. D1 Bounds
    max_d1, min_d1 = find_d1_bounds(all_gex, spot)
    signals_by_strike[round_strike(max_d1)].append("Max D1")
    signals_by_strike[round_strike(min_d1)].append("Min D1")
    
    # 8. Intraday/Unusual Volume Levels
    intraday = find_intraday_levels(chain_data, list(chain_data['by_expiration'].keys())[:3])
    for strike, typ in intraday:
        signals_by_strike[round_strike(strike)].append("Intraday")
    
    # Build confluence output - ONLY include strikes with score >= 2
    confluence = []
    
    for strike, tags in sorted(signals_by_strike.items()):
        score = len(tags)
        
        if score < 2:
            continue
        
        # Determine type based on tags
        call_tags = sum(1 for t in tags if 'CW' in t or 'call' in t.lower() or 'Top' in t)
        put_tags = sum(1 for t in tags if 'PW' in t or 'put' in t.lower())
        
        if 'Flip' in ' '.join(tags):
            conf_type = 'FLIP'
        elif call_tags > put_tags:
            conf_type = 'CALL'
        elif put_tags > call_tags:
            conf_type = 'PUT'
        else:
            conf_type = 'NEUTRAL'
        
        confluence.append({
            'strike': round(strike, 2),
            'tags': ' + '.join(tags),
            'score': score,
            'type': conf_type
        })
    
    # Sort by score descending, then by distance from spot
    confluence.sort(key=lambda x: (-x['score'], abs(x['strike'] - spot)))
    
    return confluence[:10]  # Return top 10 confluence levels

if __name__ == "__main__":
    print("QQQ GEX Confluence Bot - Starting...")
    
    ticker = yf.Ticker(TICKER)
    spot = ticker.fast_info['last_price']
    print(f"Current QQQ Spot: ${spot:.2f}")
    
    expirations = list(ticker.options)[:6]  # Get up to 6 expirations
    print(f"Found {len(expirations)} expiration dates")
    
    today_str = datetime.datetime.now().strftime('%Y-%m-%d')
    is_0dte = today_str in expirations
    print(f"0DTE: {is_0dte}")
    
    # Fetch all chain data
    chain_data = get_all_chain_data(ticker, expirations)
    print(f"Loaded {len(chain_data['calls'])} calls and {len(chain_data['puts'])} puts")
    
    # Build confluence
    confluence = build_confluence(spot, chain_data, today_str, is_0dte)
    
    # Build output
    output = {
        'spot': round(spot, 2),
        'confluence': confluence,
        'updated': datetime.datetime.now().strftime('%H:%M:%S'),
        'is_0dte': is_0dte
    }
    
    # Save to file
    with open('data.json', 'w') as f:
        json.dump(output, f, indent=2)
    
    print(f"\nFound {len(confluence)} confluence levels (score >= 2):")
    for c in confluence:
        print(f"  ${c['strike']:.2f} [{c['type']}] Score {c['score']}: {c['tags']}")
    
    print(f"\nData saved to data.json")
    print(json.dumps(output, indent=2))
