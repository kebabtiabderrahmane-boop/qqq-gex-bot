import yfinance as yf
import numpy as np
from scipy.stats import norm
import datetime
import json
from collections import defaultdict

TICKER = "QQQ"

def calc_gex(strike, oi, spot, iv, dte, is_call):
    if oi == 0: return {'strike': strike, 'gex': 0}
    T = max(0.5, dte) / 365.0
    r = 0.05
    d1 = (np.log(spot / strike) + (r + 0.5 * iv**2) * T) / (iv * np.sqrt(T))
    gamma = norm.pdf(d1) / (spot * iv * np.sqrt(T))
    gex = oi * 100 * gamma * spot * (1 if is_call else -1)
    return {'strike': strike, 'gex': gex}

def get_gex_data():
    ticker = yf.Ticker(TICKER)
    spot = ticker.fast_info['last_price']
    expirations = ticker.options[:3]
    gex_list = []
    
    today_str = datetime.datetime.now().strftime('%Y-%m-%d')
    is_0dte = today_str in expirations
    
    for exp in expirations:
        chain = ticker.option_chain(exp)
        dte = max(1, (datetime.datetime.strptime(exp, '%Y-%m-%d') - datetime.datetime.now()).days)
        
        for _, row in chain.calls.iterrows():
            iv = row['impliedVolatility'] if not np.isnan(row['impliedVolatility']) else 0.20
            gex_list.append(calc_gex(row['strike'], row['openInterest'], spot, iv, dte, True))
        for _, row in chain.puts.iterrows():
            iv = row['impliedVolatility'] if not np.isnan(row['impliedVolatility']) else 0.20
            gex_list.append(calc_gex(row['strike'], row['openInterest'], spot, iv, dte, False))
            
    return spot, gex_list, is_0dte, today_str, ticker

def find_confluence(spot, gex_list, is_0dte, today_str, ticker):
    gex_list.sort(key=lambda x: x['strike'])
    
    cw = max([x for x in gex_list if x['strike'] > spot and x['gex'] > 0], key=lambda x: x['gex'], default={'strike': spot})['strike']
    pw = min([x for x in gex_list if x['strike'] < spot and x['gex'] < 0], key=lambda x: x['gex'], default={'strike': spot})['strike']
    
    flip = spot
    for i in range(len(gex_list)-1):
        if gex_list[i]['strike'] <= spot <= gex_list[i+1]['strike']:
            if (gex_list[i]['gex'] > 0 and gex_list[i+1]['gex'] < 0) or (gex_list[i]['gex'] < 0 and gex_list[i+1]['gex'] > 0):
                flip = gex_list[i]['strike']
                break
                
    dte_cw, dte_pw, dte_flip = 0, 0, 0
    if is_0dte:
        chain = ticker.option_chain(today_str)
        gex_0dte = []
        for _, row in chain.calls.iterrows():
            iv = row['impliedVolatility'] if not np.isnan(row['impliedVolatility']) else 0.20
            gex_0dte.append(calc_gex(row['strike'], row['openInterest'], spot, iv, 0.5, True))
        for _, row in chain.puts.iterrows():
            iv = row['impliedVolatility'] if not np.isnan(row['impliedVolatility']) else 0.20
            gex_0dte.append(calc_gex(row['strike'], row['openInterest'], spot, iv, 0.5, False))
        
        gex_0dte.sort(key=lambda x: x['strike'])
        dte_cw = max([x for x in gex_0dte if x['strike'] > spot and x['gex'] > 0], key=lambda x: x['gex'], default={'strike': spot})['strike']
        dte_pw = min([x for x in gex_0dte if x['strike'] < spot and x['gex'] < 0], key=lambda x: x['gex'], default={'strike': spot})['strike']
        for i in range(len(gex_0dte)-1):
            if gex_0dte[i]['strike'] <= spot <= gex_0dte[i+1]['strike']:
                if (gex_0dte[i]['gex'] > 0 and gex_0dte[i+1]['gex'] < 0) or (gex_0dte[i]['gex'] < 0 and gex_0dte[i+1]['gex'] > 0):
                    dte_flip = gex_0dte[i]['strike']
                    break
    
    return {
        'call_wall': int(cw),
        'put_wall': int(pw),
        'flip': int(flip),
        'dte_call_wall': int(dte_cw),
        'dte_put_wall': int(dte_pw),
        'dte_flip': int(dte_flip) if dte_flip else 0,
        'is_0dte': is_0dte
    }

if __name__ == "__main__":
    spot, gex_list, is_0dte, today_str, ticker = get_gex_data()
    confluence = find_confluence(spot, gex_list, is_0dte, today_str, ticker)
    
    output = {
        'timestamp': datetime.datetime.now().isoformat(),
        'spot': round(spot, 2),
        **confluence
    }
    
    with open('data.json', 'w') as f:
        json.dump(output, f, indent=2)
    
    print(json.dumps(output, indent=2))
