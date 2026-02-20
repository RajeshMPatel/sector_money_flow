import os
import requests
import pandas as pd
import datetime
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

ASSET_CLASSES = {
    'Equities - Core Sectors': {
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
    },
    'Equities - Sub-Sectors': {
        'SMH': 'Semiconductors',
        'ITA': 'Aerospace & Defense',
        'XHB': 'Homebuilders',
        'XRT': 'Retail',
        'KRE': 'Regional Banks',
        'IYT': 'Transportation'
    },
    'Fixed Income': {
        'TLT': '20+ Year Treasuries (Safe Haven)',
        'HYG': 'High Yield Corp Bonds (Credit Risk)',
    },
    'Commodities': {
        'GLD': 'Gold (Safe Haven)',
        'CPER': 'Copper (Industrial Demand)'
    }
}

SECTORS = {}
for group, assets in ASSET_CLASSES.items():
    for symbol, name in assets.items():
        SECTORS[symbol] = {'name': name, 'group': group}

TICKERS = list(SECTORS.keys()) + ['SPY']

# Directory to store our incremental CSV files
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

def fetch_yahoo_finance(symbol):
    """Fetch data from Yahoo Finance incrementally and cache locally."""
    file_path = os.path.join(DATA_DIR, f"{symbol}.csv")
    
    existing_df = pd.DataFrame()
    if os.path.exists(file_path):
        existing_df = pd.read_csv(file_path, index_col='date', parse_dates=['date'])
        # If we have local data, we just need the last 5 days to update the current live candle 
        # and any missing recent days.
        range_val = "5d" 
    else:
        # If no local data exists, fetch 1 year to build a solid history
        range_val = "1y"
        
    url = f"https://query2.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range={range_val}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            result = data.get('chart', {}).get('result')
            if result:
                result = result[0]
                timestamps = result.get('timestamp', [])
                indicators = result.get('indicators', {}).get('quote', [{}])[0]
                
                if timestamps and indicators:
                    new_df = pd.DataFrame({
                        'date': [pd.to_datetime(t, unit='s').date() for t in timestamps],
                        'open': indicators.get('open', []),
                        'high': indicators.get('high', []),
                        'low': indicators.get('low', []),
                        'close': indicators.get('close', []),
                        'volume': indicators.get('volume', [])
                    })
                    # Convert date to datetime for consistent index mapping
                    new_df['date'] = pd.to_datetime(new_df['date'])
                    new_df.set_index('date', inplace=True)
                    new_df.dropna(inplace=True)
                    
                    if not existing_df.empty:
                        # Combine existing data with new data
                        combined = pd.concat([existing_df, new_df])
                        # Keep the last entry for each date (the most recent fetch overwrites the older partial day)
                        combined = combined[~combined.index.duplicated(keep='last')]
                        combined.sort_index(inplace=True)
                        df = combined
                    else:
                        df = new_df
                        
                    # Filter out today's live data to ensure we only use fully formed End-Of-Day candles
                    today = pd.Timestamp(datetime.date.today())
                    df = df[df.index < today]
                        
                    # Save back to local CSV cache
                    df.to_csv(file_path)
                    return df
    except Exception as e:
        print(f"Error fetching live data for {symbol}: {e}")
        
    # Fallback: if live fetch fails completely, return cached data if we have it
    if not existing_df.empty:
        print(f"Using cached data for {symbol} due to fetch error.")
        today = pd.Timestamp(datetime.date.today())
        return existing_df[existing_df.index < today]
        
    raise Exception(f"Failed to fetch data for {symbol} and no cache exists.")

def get_fred_data():
    """Fetches macro data from FRED API incrementally."""
    api_key = os.environ.get('FRED_API_KEY')
    if not api_key:
        return {"error": "FRED_API_KEY not found in environment"}
        
    file_path = os.path.join(DATA_DIR, "macro_cache.csv")
    
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
                        "date": date,
                        "series": series
                    })
        except Exception as e:
            print(f"Error fetching FRED {series}: {e}")
            
    # If we successfully fetched fresh data, save it to cache
    if macro_data:
        pd.DataFrame(macro_data).to_csv(file_path, index=False)
        return macro_data
        
    # If the fetch failed (e.g. rate limit), try loading from our local CSV cache
    if os.path.exists(file_path):
        return pd.read_csv(file_path).to_dict('records')
        
    return []

@app.get("/api/data")
def get_data():
    results = []
    
    try:
        spy_df = fetch_yahoo_finance('SPY')
    except Exception as e:
        return {"error": f"Failed to fetch baseline SPY data: {e}"}
        
    for symbol, info in SECTORS.items():
        name = info['name']
        group = info['group']
        try:
            sector_df = fetch_yahoo_finance(symbol)
            
            # Align dates using an inner join to only compare dates where both SPY and the sector traded
            aligned = pd.merge(sector_df, spy_df, left_index=True, right_index=True, suffixes=('', '_spy'))
            
            # Ensure we have enough data (at least 21 days for the window)
            if len(aligned) < 22:
                print(f"Not enough data for {symbol}")
                continue
                
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
            past_rs = rs_line.iloc[-21] # 20 trading days ago
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
                "group": group,
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
