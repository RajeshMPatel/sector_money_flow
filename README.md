# Institutional Sector Rotation Tracker

This project is a lightweight, high-performance dashboard that tracks institutional "smart money" flows across major asset classes and S&P 500 sectors. It helps investors identify which sectors are seeing accumulation (buying) vs. distribution (selling) using **Chaikin Money Flow (CMF)** and **Relative Strength (RS)**.

![Sector Rotation Dashboard](https://img.shields.io/badge/Status-Active-brightgreen)

Green sectors are where the money is flowing into:
<br>
<img width="873" height="739" alt="Screenshot 2026-02-19 at 8 55 38 PM" src="https://github.com/user-attachments/assets/0ae7ecb2-146f-4770-abd5-bbd91c5d6bee" />
<br>
<img width="1304" height="1271" alt="Screenshot 2026-02-19 at 8 57 32 PM" src="https://github.com/user-attachments/assets/bf31010a-085e-4ca5-a4b9-dab2f0a3ca83" />

## 🎯 What it Does

Instead of just looking at price, this tool combines **Price** and **Volume** to tell you what institutions are doing beneath the surface. It tracks 20+ specific ETFs, grouping them into:
*   **Equities - Core Sectors** (Technology, Financials, Energy, etc.)
*   **Equities - Sub-Sectors** (Semiconductors, Homebuilders, Retail, etc.)
*   **Fixed Income** (Treasuries, High Yield Bonds)
*   **Commodities** (Gold, Copper)

It also pulls live macro-economic data (Treasury Yields, Yield Curve, Inflation Expectations, Credit Spreads) directly from the Federal Reserve Economic Data (FRED) API.

### The Math
*   **21-Day CMF:** Measures volume-weighted accumulation/distribution. Positive = Institutions are buying. Negative = Institutions are selling.
*   **20-Day RS Momentum:** Measures price performance relative to the S&P 500 (SPY).

## 🚀 Setup Instructions

### 1. Prerequisites
You need Python 3 installed on your machine.
You will also need a free API key from FRED to pull macro data. Get one here: [FRED API Keys](https://fred.stlouisfed.org/docs/api/api_key.html)

### 2. Environment Setup
Clone the repository and set up a virtual environment:
```bash
git clone <your-repo-url>
cd chaikin
python3 -m venv venv
source venv/bin/activate
```

Install the required dependencies:
```bash
pip install -r requirements.txt
```

### 3. Add your FRED API Key
**What is FRED?**
FRED (Federal Reserve Economic Data) is a massive online database of economic time-series data maintained by the Federal Reserve Bank of St. Louis. This project uses it to pull critical macro-economic indicators like Treasury Yields and Credit Spreads to provide context on the broader market environment.

**How to get a key:**
1. Go to the [FRED API website](https://fred.stlouisfed.org/docs/api/api_key.html).
2. Create a free user account (or log in).
3. Request an API key. It is instantly generated and 100% free.

Once you have your key, export it to your environment variables so the script can access it:
```bash
export FRED_API_KEY="your_actual_api_key_here"
```

## ⚙️ How to Run the Project

This project separates the heavy data processing from the web server for maximum speed and reliability.

### Step 1: Fetch and Compute Data
First, run the data update script. This script pulls the latest daily data from Yahoo Finance and FRED, runs the technical indicator math, and saves the results to a local `data/dashboard_data.json` file.
```bash
python update_data.py
```
*Note: This script uses incremental fetching and only calculates data based on fully closed trading days to ensure the math doesn't glitch during live market hours.*

### Step 2: Start the Web Server
Once the data is generated, start the FastAPI web server. The server does zero live computing; it just serves the dashboard instantly.
```bash
uvicorn main:app --host 0.0.0.0 --port 4001
```

### Step 3: View the Dashboard
Open your web browser and go to:
**http://localhost:4001**

## 📈 How to Read the Dashboard

The scatter plot and tables divide the market into four quadrants:

1.  🟢 **Leading / Accumulation (Top Right):** Price is outperforming the S&P 500 AND institutions are heavily buying. This is the safest place to allocate capital.
2.  🟠 **Improving (Top Left):** Price is currently underperforming the S&P 500, BUT institutions are quietly accumulating (buying the dip). A breakout may be imminent.
3.  🟡 **Deteriorating (Bottom Right):** Price is outperforming, BUT institutions are quietly distributing (selling into strength). A warning sign to take profits.
4.  🔴 **Weakening / Distribution (Bottom Left):** Price is underperforming AND institutions are selling. Avoid these sectors.

## 🤖 Automation

Because the data relies on End-Of-Day (EOD) closing prices, you only need to run `update_data.py` once per day after the market closes. You can easily automate this using a Cron Job:

```bash
# Example Cron Job to run at 5:30 PM EST Monday-Friday
30 17 * * 1-5 cd /path/to/your/project && source venv/bin/activate && export FRED_API_KEY="your_key" && python update_data.py
```
