import yfinance as yf
import requests
import os
import json
import time
from datetime import datetime, timedelta, timezone

# 設定檔案與時區 (台灣 GMT+8)
JSON_FILE = 'stocks.json'
TZ_TAIWAN = timezone(timedelta(hours=8))

# --- 1. 推播功能 (支援不同標題與顏色) ---
def send_discord_report(title, description, color):
    url = os.environ.get("DISCORD_WEBHOOK")
    if not url: return

    embed = {
        "title": title,
        "description": description,
        "color": color,
        "timestamp": datetime.now(TZ_TAIWAN).isoformat(),
        "footer": {
            "text": "股市戰情室 • 自動監控中",
            "icon_url": "https://cdn-icons-png.flaticon.com/512/4204/4204600.png"
        }
    }

    payload = {
        "username": "超級股市管家",
        "avatar_url": "https://cdn-icons-png.flaticon.com/512/2910/2910311.png",
        "embeds": [embed]
    }
    
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"推播失敗: {e}")

def send_alert(symbol, price, alert_type, target):
    # 單一個股的買賣警報 (維持原本漂亮的卡片)
    if alert_type == "buy":
        title = f"✅ 買進訊號：{symbol}"
        desc = f"現價 **{price}** 低於目標價 {target}，機會來了！"
        color = 5763719 # 綠色
    else:
        title = f"💰 獲利訊號：{symbol}"
        desc = f"現價 **{price}** 達到獲利點 {target}，恭喜！"
        color = 15548997 # 紅色
        
    send_discord_report(title, desc, color)

# --- 2. 抓價功能 ---
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

# --- 3. 核心檢查邏輯 ---
def check_stock():
    if not os.path.exists(JSON_FILE): return

    # 取得現在的台灣時間
    now = datetime.now(TZ_TAIWAN)
    current_hour = now.hour
    current_min = now.minute

    print(f"目前時間: {now.strftime('%H:%M')}")

    # --- 判斷現在是不是「報告時間」 ---
    
    # 1. 整點報價 (Hourly): 9點~13點 的 00分~04分 之間
    is_hourly = (9 <= current_hour <= 13) and (current_min < 5)
    
    # 2. 收盤報價 (Closing): 13點 的 45分~49分 之間
    is_closing = (current_hour == 13) and (45 <= current_min < 50)

    # 準備清單來存報價
    report_msgs = []
    
    with open(JSON_FILE, 'r') as f:
        stock_list = json.load(f)

    for item in stock_list:
        sid = item['stock_id']
        buy_target = float(item['buy_target']) if item.get('buy_target') else None
        sell_target = float(item['sell_target']) if item.get('sell_target') else None
        
        price, real_symbol = fetch_price(sid)
        
        if price:
            print(f"Checking {real_symbol}: {price}")
            
            # A. 優先處理買賣警報 (隨時都要報)
            if buy_target and price <= buy_target:
                send_alert(real_symbol, price, "buy", buy_target)
                time.sleep(1)
            elif sell_target and price >= sell_target:
                send_alert(real_symbol, price, "sell", sell_target)
                time.sleep(1)
            
            # B. 如果是報告時間，把股價收集起來
            if is_hourly or is_closing:
                # 簡單的格式： 台積電(2330): 1000.0
                report_msgs.append(f"**{real_symbol}**: `{price:.2f}`")

    # --- 發送彙整報告 ---
    if report_msgs:
        if is_closing:
            title = "🌅 收盤行情快報 (13:45)"
            color = 10181046 # 紫色 (收盤感)
            desc = "今日市場收盤參考報價：\n\n" + "\n".join(report_msgs)
            send_discord_report(title, desc, color)
            
        elif is_hourly:
            title = f"⏰ 整點行情 ({current_hour}:00)"
            color = 3447003 # 藍色
            desc = "市場即時報價更新：\n\n" + "\n".join(report_msgs)
            send_discord_report(title, desc, color)

if __name__ == "__main__":
    check_stock()
