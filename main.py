import yfinance as yf
import requests
import os
import json
import time
from datetime import datetime, timedelta, timezone

# 設定檔案與時區
JSON_FILE = 'stocks.json'
TZ_TAIWAN = timezone(timedelta(hours=8))

# --- 1. Discord 推播功能 ---
def send_discord(msg, color=3447003): # 預設藍色
    url = os.environ.get("DISCORD_WEBHOOK")
    if not url:
        print("❌ 錯誤: 未設定 DISCORD_WEBHOOK")
        return
    
    data = {
        "embeds": [{
            "description": msg,
            "color": color
        }]
    }
    try:
        requests.post(url, json=data)
    except Exception as e:
        print(f"推播失敗: {e}")

# --- 2. 智慧抓價功能 (跟網頁一樣聰明) ---
def fetch_price(stock_id):
    # 內部小函式：嘗試抓取
    def _try_get(symbol):
        try:
            stock = yf.Ticker(symbol)
            # 嘗試抓取即時價格
            price = stock.fast_info.last_price
            return price, symbol
        except:
            return None, None

    # A. 如果已經是 .TW 或 .TWO 結尾，直接抓
    if not stock_id.isdigit():
        return _try_get(stock_id)

    # B. 猜上市 (.TW)
    p, s = _try_get(f"{stock_id}.TW")
    if p: return p, s

    # C. 猜上櫃 (.TWO)
    p, s = _try_get(f"{stock_id}.TWO")
    if p: return p, s
    
    return None, None

# --- 3. 檢查邏輯 ---
def check_stock():
    print("🚀 機器人啟動，開始巡邏...")
    
    if not os.path.exists(JSON_FILE):
        print("找不到 stocks.json，跳過。")
        return

    with open(JSON_FILE, 'r') as f:
        stock_list = json.load(f)

    # 判斷是否為整點 (0~4分算整點) -> 只有整點才報報價，不然太吵
    now = datetime.now(TZ_TAIWAN)
    is_hourly_report = (now.minute < 5)
    
    msgs = []
    
    for item in stock_list:
        sid = item['stock_id']
        buy_target = float(item['buy_target']) if item.get('buy_target') else None
        sell_target = float(item['sell_target']) if item.get('sell_target') else None
        
        # 抓價格
        price, real_symbol = fetch_price(sid)
        
        if price:
            print(f"Checking {real_symbol}: {price}")
            
            # 判斷買賣點
            alert_msg = ""
            alert_color = 3447003 # 藍色 (普通)
            
            if buy_target and price <= buy_target:
                alert_msg = f"✅ **到達買點**！ (低於 {buy_target})"
                alert_color = 65280 # 綠色
            elif sell_target and price >= sell_target:
                alert_msg = f"💰 **到達賣點**！ (高於 {sell_target})"
                alert_color = 15158332 # 紅色
            
            # 觸發通知的條件：
            # 1. 有買賣訊號 (alert_msg)
            # 2. 或是整點時刻 (is_hourly_report) 報平安
            
            if alert_msg:
                full_msg = f"📢 **{real_symbol}** 現價 `{price:.2f}`\n{alert_msg}"
                send_discord(full_msg, alert_color)
                time.sleep(1) # 避免 Discord 洗頻限制
            elif is_hourly_report:
                # 整點報價收集起來，最後一次發
                msgs.append(f"**{sid}**: `{price:.2f}`")
        else:
            print(f"⚠️ 無法取得 {sid} 價格")

    # 如果是整點，且有收集到報價，發送彙整報告
    if msgs and is_hourly_report:
        report = "⏰ **整點報價**\n" + "\n".join(msgs)
        send_discord(report)

if __name__ == "__main__":
    check_stock()
