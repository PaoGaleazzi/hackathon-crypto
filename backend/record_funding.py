import asyncio, json, time
import urllib.request

OUT = "../data/recordings/funding_rates.jsonl"

def fetch(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"error": str(e)}

def get_binance():
    d = fetch("https://fapi.binance.com/fapi/v1/premiumIndex?symbol=BTCUSDT")
    if "lastFundingRate" in d:
        return {"exchange":"binance","funding_rate":float(d["lastFundingRate"]),
                "mark_price":float(d["markPrice"]),"next_funding":d["nextFundingTime"]}
    return None

def get_bybit():
    d = fetch("https://api.bybit.com/v5/market/tickers?category=linear&symbol=BTCUSDT")
    try:
        item = d["result"]["list"][0]
        return {"exchange":"bybit","funding_rate":float(item["fundingRate"]),
                "mark_price":float(item["markPrice"])}
    except: return None

def get_okx():
    d = fetch("https://www.okx.com/api/v5/public/funding-rate?instId=BTC-USDT-SWAP")
    try:
        item = d["data"][0]
        return {"exchange":"okx","funding_rate":float(item["fundingRate"]),
                "next_funding":item.get("fundingTime")}
    except: return None

async def main():
    print(f"Grabando funding rates (REST polling cada 5s) a {OUT}... Ctrl+C para parar")
    count = 0
    with open(OUT,"a") as f:
        while True:
            for getter in (get_binance, get_bybit, get_okx):
                rec = getter()
                if rec:
                    rec["ts"] = time.time()
                    f.write(json.dumps(rec)+"\n"); f.flush()
                    count += 1
            if count % 30 == 0:
                print(f"  {count} registros grabados")
            await asyncio.sleep(5)

asyncio.run(main())
