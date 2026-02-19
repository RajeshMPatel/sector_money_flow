import os
import requests
import pandas as pd
import datetime
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

SECTORS = {
    'XLK': 'Technology',
    'XLF': 'Financials',
    'XLE': 'Energy',
    'XLY': 'Consumer Discretionary',
    'XLP': 'Consumer Staples',
    'XLV': 'Health Care',
    'XLI': 'Industrials',
    'XLB': 'Materials',
    'XLRE': 'Real Estate',
    'XLU': 'Utilities',
    'XLC': 'Communication Services',
    'ITA': 'Aerospace & Defense',
    'SMH': 'Semiconductors',
    'IBB': 'Biotechnology',
    'XHB': 'Homebuilders',
    'XRT': 'Retail',
    'KRE': 'Regional Banks',
    'IYT': 'Transportation'
}
TICKERS = list(SECTORS.keys()) + ['SPY']

def fetch_yahoo_finance(symbol, range_val="3mo", interval="1d"):
    """Fetch data from Yahoo Finance direct API."""
    url = f"https://query2.finance.yahoo.com/v8/finance/chart/{symbol}?interval={interval}&range={range_val}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        raise Exception(f"Yahoo API returned {response.status_code} for {symbol}")
        
    data = response.json()
    if not data.get('chart', {}).get('result'):
        raise Exception(f"No result found in Yahoo API response for {symbol}")
        
    result = data['chart']['result'][0]
    timestamps = result.get('timestamp', [])
    indicators = result.get('indicators', {}).get('quote', [{}])[0]
    
    if not timestamps or not indicators:
        raise Exception(f"Missing data in Yahoo API response for {symbol}")
        
    df = pd.DataFrame({
        'date': [pd.to_datetime(t, unit='s').date() for t in timestamps],
        'open': indicators.get('open', []),
        'high': indicators.get('high', []),
        'low': indicators.get('low', []),
        'close': indicators.get('close', []),
        'volume': indicators.get('volume', [])
    })
    
    df.set_index('date', inplace=True)
    # Drop rows with NaN values (e.g. current day still trading might have partial data)
    df.dropna(inplace=True)
    
    return df

def get_fred_data():
    """Fetches macro data from FRED API"""
    api_key = os.environ.get('FRED_API_KEY')
    if not api_key:
        return {"error": "FRED_API_KEY not found in environment"}
    
    # Required indicators
    series_ids = {
        'DGS2': '2Y Treasury Yield',
        'DGS10': '10Y Treasury Yield',
        'DGS20': '20Y Treasury Yield',
        'DGS30': '30Y Treasury Yield',
        'T10Y2Y': 'Yield Curve Slope (10Y-2Y)',
        'T10YIE': 'Inflation Expectations',
        'BAMLH0A0HYM2': 'High Yield Credit Spreads'
    }
    
    macro_data = []
    
    for series, name in series_ids.items():
        url = f"https://api.stlouisfed.org/fred/series/observations?series_id={series}&api_key={api_key}&file_type=json&limit=1&sort_order=desc"
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                if data.get('observations'):
                    val = data['observations'][0]['value']
                    date = data['observations'][0]['date']
                    macro_data.append({
                        "indicator": name,
                        "value": val,
                        "date": date
                    })
        except Exception as e:
            print(f"Error fetching FRED {series}: {e}")
            
    return macro_data

@app.get("/api/data")
def get_data():
    results = []
    
    try:
        spy_df = fetch_yahoo_finance('SPY')
    except Exception as e:
        return {"error": f"Failed to fetch baseline SPY data: {e}"}
        
    for symbol, name in SECTORS.items():
        try:
            sector_df = fetch_yahoo_finance(symbol)
            
            # Align dates
            aligned = pd.merge(sector_df, spy_df, left_index=True, right_index=True, suffixes=('', '_spy'))
            
            # 1. Calculate Chaikin Money Flow (CMF) - 21 periods
            high_low = aligned['high'] - aligned['low']
            high_low = high_low.replace(0, 0.001) # Avoid div by zero
            
            mf_multiplier = ((aligned['close'] - aligned['low']) - (aligned['high'] - aligned['close'])) / high_low
            mf_volume = mf_multiplier * aligned['volume']
            
            cmf_21 = mf_volume.rolling(window=21).sum() / aligned['volume'].rolling(window=21).sum()
            current_cmf = cmf_21.iloc[-1]
            
            # 2. Calculate Relative Strength (RS) against SPY
            rs_line = aligned['close'] / aligned['close_spy']
            
            current_rs = rs_line.iloc[-1]
            past_rs = rs_line.iloc[-21] # 20 trading days ago (roughly 21 index offset)
            rs_pct_change = ((current_rs - past_rs) / past_rs) * 100
            
            if current_cmf > 0 and rs_pct_change > 0:
                quadrant = "Leading / Accumulation"
                color = "green"
            elif current_cmf < 0 and rs_pct_change < 0:
                quadrant = "Weakening / Distribution"
                color = "red"
            elif current_cmf > 0 and rs_pct_change <= 0:
                quadrant = "Improving"
                color = "orange"
            else:
                quadrant = "Deteriorating"
                color = "yellow"
                
            results.append({
                "symbol": symbol,
                "name": name,
                "cmf": round(current_cmf, 4),
                "rs_momentum": round(rs_pct_change, 2),
                "quadrant": quadrant,
                "color": color
            })
        except Exception as e:
            print(f"Error processing {symbol}: {e}")
            continue

    return {
        "sectors": results,
        "macro": get_fred_data()
    }

@app.get("/")
def serve_home():
    with open("static/index.html", "r") as f:
        return HTMLResponse(content=f.read())
