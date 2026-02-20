import os
import requests
import pandas as pd
import datetime
import json

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

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

def fetch_yahoo_finance(symbol):
    """Fetch data from Yahoo Finance incrementally and cache locally."""
    file_path = os.path.join(DATA_DIR, f"{symbol}.csv")
    
    existing_df = pd.DataFrame()
    if os.path.exists(file_path):
        existing_df = pd.read_csv(file_path, index_col='date', parse_dates=['date'])
        range_val = "5d" 
    else:
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
                    new_df['date'] = pd.to_datetime(new_df['date'])
                    new_df.set_index('date', inplace=True)
                    new_df.dropna(inplace=True)
                    
                    if not existing_df.empty:
                        combined = pd.concat([existing_df, new_df])
                        combined = combined[~combined.index.duplicated(keep='last')]
                        combined.sort_index(inplace=True)
                        df = combined
                    else:
                        df = new_df
                        
                    today = pd.Timestamp(datetime.date.today())
                    df = df[df.index < today]
                        
                    df.to_csv(file_path)
                    return df
    except Exception as e:
        print(f"Error fetching live data for {symbol}: {e}")
        
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
            
    if macro_data:
        pd.DataFrame(macro_data).to_csv(file_path, index=False)
        return macro_data
        
    if os.path.exists(file_path):
        return pd.read_csv(file_path).to_dict('records')
        
    return []

def main():
    print("Starting data update process...")
    results = []
    
    try:
        spy_df = fetch_yahoo_finance('SPY')
    except Exception as e:
        print(f"Failed to fetch baseline SPY data: {e}")
        return
        
    for symbol, info in SECTORS.items():
        name = info['name']
        group = info['group']
        print(f"Processing {symbol}...")
        try:
            sector_df = fetch_yahoo_finance(symbol)
            
            aligned = pd.merge(sector_df, spy_df, left_index=True, right_index=True, suffixes=('', '_spy'))
            
            if len(aligned) < 22:
                print(f"Not enough data for {symbol}")
                continue
                
            high_low = aligned['high'] - aligned['low']
            high_low = high_low.replace(0, 0.001) 
            
            mf_multiplier = ((aligned['close'] - aligned['low']) - (aligned['high'] - aligned['close'])) / high_low
            mf_volume = mf_multiplier * aligned['volume']
            
            cmf_21 = mf_volume.rolling(window=21).sum() / aligned['volume'].rolling(window=21).sum()
            current_cmf = cmf_21.iloc[-1]
            
            rs_line = aligned['close'] / aligned['close_spy']
            
            current_rs = rs_line.iloc[-1]
            past_rs = rs_line.iloc[-21] 
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

    macro_data = get_fred_data()
    
    final_output = {
        "sectors": results,
        "macro": macro_data,
        "last_updated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    
    output_path = os.path.join(DATA_DIR, "dashboard_data.json")
    with open(output_path, 'w') as f:
        json.dump(final_output, f, indent=4)
        
    print(f"Data successfully updated and saved to {output_path}")

if __name__ == "__main__":
    main()
