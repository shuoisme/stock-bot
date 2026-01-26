import twstock
import requests
import os
import json
from datetime import datetime

JSON_FILE = 'stocks.json'

def send_discord(msg, color=3447003):
    url = os.environ.get("DISCORD_WEBHOOK")
    if not url: return
    data = {"embeds": [{"description": msg, "color": color}]}
    requests.post(url, json=data)

def check_stock():
    print("🚀 檢查股價...")
    try:
        with open(JSON_FILE, 'r') as f:
            data = json.load(f)
    except:
        return

    # 整點判斷 (0-4分)
    is_hourly = (datetime.now().minute < 5)
    
    for item in data:
        sid = item['stock_id']
        buy = float(item['buy_target']) if item['buy_target'] else None
        sell = float(item['sell_target']) if item['sell_target'] else None
        
        try:
            stock = twstock.realtime.get(sid)
            if not stock['success']: continue
            
            name = stock['info']['name']
            price = float(stock['realtime']['latest_trade_price'])
            
            # 漲跌停判斷
            asks = stock['realtime']['best_ask_price'] # 委賣
            bids = stock['realtime']['best_bid_price'] # 委買
            limit_up = (not asks) or (len(asks)>0 and float(asks[0])==0)
            limit_down = (not bids) or (len(bids)>0 and float(bids[0])==0)

            msgs = []
            if buy and price <= buy: msgs.append(f"✅ **到達買點** (低於 {buy})")
            if sell and price >= sell: msgs.append(f"💰 **到達賣點** (高於 {sell})")
            if limit_up: msgs.append("🔥 **漲停鎖死**")
            if limit_down: msgs.append("🥶 **跌停鎖死**")

            # 有事才報，或是整點報
            if msgs:
                full_msg = f"📢 **{name} ({sid})** 現價: `{price}`\n" + "\n".join(msgs)
                send_discord(full_msg, 15158332) # 紅色
            elif is_hourly:
                send_discord(f"⏰ 整點報價: **{name} ({sid})** 現價 `{price}`", 3447003) # 藍色

        except Exception as e:
            print(f"Error {sid}: {e}")

if __name__ == "__main__":
    check_stock()