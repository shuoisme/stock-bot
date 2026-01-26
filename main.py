import yfinance as yf
import requests
import os
import json
import time
from datetime import datetime, timedelta, timezone

# 設定檔案與時區
JSON_FILE = 'stocks.json'
TZ_TAIWAN = timezone(timedelta(hours=8))

# --- 1. 專業美化推播功能 ---
def send_discord_pretty(symbol, price, alert_type, target_price=None):
    url = os.environ.get("DISCORD_WEBHOOK")
    if not url: return

    # 設定不同情境的顏色與標題
    if alert_type == "buy":
        title = f"✅ 買進訊號：{symbol}"
        desc = "股價已回檔至設定的便宜價格，請留意進場機會！"
        color = 5763719  # 綠色 (Green)
        icon = "📉"      # 低點圖示
    elif alert_type == "sell":
        title = f"💰 獲利訊號：{symbol}"
        desc = "股價已上漲至設定的目標價格，恭喜發財！"
        color = 15548997 # 紅色 (Red)
        icon = "📈"      # 高點圖示
    else:
        title = f"⏰ 整點報價：{symbol}"
        desc = "市場即時行情更新"
        color = 3447003  # 藍色 (Blue)
        icon = "⏱️"

    # 建立卡片內容 (Embed)
    embed = {
        "title": f"{icon} {title}",
        "description": desc,
        "color": color,
        "fields": [
            {
                "name": "💵 目前股價",
                "value": f"**`{price:.2f}`**",
                "inline": True
            },
            {
                "name": "🎯 設定目標",
                "value": f"`{target_price}`" if target_price else "`整點回報`",
                "inline": True
            },
            {
                "name": "🕒 通知時間",
                "value": datetime.now(TZ_TAIWAN).strftime('%Y-%m-%d %H:%M:%S'),
                "inline": False
            }
        ],
        "footer": {
            "text": "🤖 股市戰情室 • 24hr 自動監控中",
            "icon_url": "https://cdn-icons-png.flaticon.com/512/4204/4204600.png" # 機器人小圖示
        }
    }

    payload = {
        "username": "超級股市管家",   # 機器人名字
        "avatar_url": "https://cdn-icons-png.flaticon.com/512/2910/2910311.png", # 機器人頭像
        "embeds": [embed]
    }
    
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"推播失敗: {e}")

# --- 2. 智慧抓價功能 ---
def fetch_price(stock_id):
    def _try_get(symbol):
        try:
            stock = yf.Ticker(symbol)
            price = stock.fast_info.last_price
            return price, symbol
        except:
            return None, None

    if not stock_id.isdigit(): return _try_get(stock_id)
    p, s = _try_get(f"{stock_id}.TW")
    if p: return p, s
    p, s = _try_get(f"{stock_id}.TWO")
    if p: return p, s
    return None, None

# --- 3. 檢查邏輯 ---
def check_stock():
    print("🚀 機器人啟動 (美化版)...")
    
    if not os.path.exists(JSON_FILE): return

    with open(JSON_FILE, 'r') as f:
        stock_list = json.load(f)

    # 判斷是否為整點 (0-4分)
    now = datetime.now(TZ_TAIWAN)
    is_hourly_report = (now.minute < 5)
    
    # 避免整點報價洗版，我們把整點的資訊收集起來一次發比較整齊
    hourly_msgs = []
    
    for item in stock_list:
        sid = item['stock_id']
        buy_target = float(item['buy_target']) if item.get('buy_target') else None
        sell_target = float(item['sell_target']) if item.get('sell_target') else None
        
        price, real_symbol = fetch_price(sid)
        
        if price:
            print(f"Checking {real_symbol}: {price}")
            
            # 優先觸發重要警報
            if buy_target and price <= buy_target:
                send_discord_pretty(real_symbol, price, "buy", buy_target)
                time.sleep(1) # 避免太快被 Discord 擋
            elif sell_target and price >= sell_target:
                send_discord_pretty(real_symbol, price, "sell", sell_target)
                time.sleep(1)
            elif is_hourly_report:
                # 沒觸發警報，但現在是整點，加入清單
                hourly_msgs.append(f"**{real_symbol}**: `{price:.2f}`")

    # 如果是整點，發送一張彙整的卡片
    if hourly_msgs:
        url = os.environ.get("DISCORD_WEBHOOK")
        if url:
            desc = "\n".join(hourly_msgs)
            embed = {
                "title": "⏰ 整點行情快報",
                "description": desc,
                "color": 3447003, # 藍色
                "timestamp": datetime.now(TZ_TAIWAN).isoformat(),
                "footer": {"text": "股市戰情室"}
            }
            requests.post(url, json={"username": "超級股市管家", "embeds": [embed]})

if __name__ == "__main__":
    check_stock()
