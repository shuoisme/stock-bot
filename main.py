import yfinance as yf
import requests
import os
import json
import time
from datetime import datetime, timedelta, timezone

# 設定檔案與時區
JSON_FILE = 'stocks.json'
TZ_TAIWAN = timezone(timedelta(hours=8))

# --- 1. 推播功能 ---
def send_discord_report(title, description, color):
    url = os.environ.get("DISCORD_WEBHOOK")
    if not url: return

    embed = {
        "title": title,
        "description": description,
        "color": color,
        "timestamp": datetime.now(TZ_TAIWAN).isoformat(),
        "footer": {
            "text": "股市戰情室 • 損益即時試算",
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

def send_alert(symbol, price, alert_type, target=None, pct=0):
    if alert_type == "limit_up":
        title = f"🔥 漲停通知：{symbol}"
        desc = f"股價強勢攻頂！現價 **{price}** (漲幅 {pct:.2f}%)"
        color = 10038562 
    elif alert_type == "limit_down":
        title = f"🤮 跌停通知：{symbol}"
        desc = f"股價重挫跌停！現價 **{price}** (跌幅 {pct:.2f}%)"
        color = 3066993 
    elif alert_type == "buy":
        title = f"✅ 買進訊號：{symbol}"
        desc = f"現價 **{price}** 低於目標價 {target}，機會來了！"
        color = 5763719 
    else: 
        title = f"💰 獲利訊號：{symbol}"
        desc = f"現價 **{price}** 達到獲利點 {target}，恭喜！"
        color = 15548997 
        
    send_discord_report(title, desc, color)

# --- 2. 抓價功能 ---
def fetch_price_data(stock_id):
    def _try_get(symbol):
        try:
            stock = yf.Ticker(symbol)
            price = stock.fast_info.last_price
            prev = stock.fast_info.previous_close
            return price, prev, symbol
        except:
            return None, None, None

    if not stock_id.isdigit(): return _try_get(stock_id)
    p, prev, s = _try_get(f"{stock_id}.TW")
    if p: return p, prev, s
    p, prev, s = _try_get(f"{stock_id}.TWO")
    if p: return p, prev, s
    return None, None, None

# --- 3. 核心檢查邏輯 ---
def check_stock():
    if not os.path.exists(JSON_FILE): return

    now = datetime.now(TZ_TAIWAN)
    current_hour = now.hour
    current_min = now.minute

    # 放寬判定時間：整點 00~09 分都算 (解決 GitHub 延遲問題)
    is_hourly = (9 <= current_hour <= 13) and (current_min < 10)
    is_closing = (current_hour == 13) and (45 <= current_min < 55)

    report_msgs = []
    
    with open(JSON_FILE, 'r') as f:
        stock_list = json.load(f)

    for item in stock_list:
        sid = item['stock_id']
        buy_target = float(item['buy_target']) if item.get('buy_target') else None
        sell_target = float(item['sell_target']) if item.get('sell_target') else None
        cost_price = float(item.get('cost_price', 0)) # 讀取成本價
        
        price, prev_close, real_symbol = fetch_price_data(sid)
        
        if price and prev_close:
            print(f"Checking {real_symbol}: {price}")
            
            # 計算日漲跌幅
            change_pct = ((price - prev_close) / prev_close) * 100
            
            # 計算個人損益 (如果有設成本)
            pl_str = ""
            if cost_price > 0:
                pl_val = price - cost_price
                pl_pct = (pl_val / cost_price) * 100
                # 加上正負號與表情
                sign = "+" if pl_val > 0 else ""
                emoji = "🤑" if pl_pct > 0 else "💸"
                pl_str = f" | {emoji} {sign}{pl_val:.1f} ({sign}{pl_pct:.1f}%)"

            # 1. 漲跌停檢查
            if change_pct >= 9.5:
                send_alert(real_symbol, price, "limit_up", pct=change_pct)
                time.sleep(1)
            elif change_pct <= -9.5:
                send_alert(real_symbol, price, "limit_down", pct=change_pct)
                time.sleep(1)
            
            # 2. 到價檢查
            elif buy_target and price <= buy_target:
                send_alert(real_symbol, price, "buy", target=buy_target)
                time.sleep(1)
            elif sell_target and price >= sell_target:
                send_alert(real_symbol, price, "sell", target=sell_target)
                time.sleep(1)
            
            # 3. 整點報價收集 (加入損益資訊)
            if is_hourly or is_closing:
                icon = "🔺" if change_pct > 0 else "🔻" if change_pct < 0 else "➖"
                # 格式：2330.TW: 1000.0 🔺(+2.0%) | 🤑 +200.0 (+25.0%)
                msg = f"**{real_symbol}**: `{price:.2f}` {icon}({change_pct:.2f}%){pl_str}"
                report_msgs.append(msg)

    # --- 發送整點/收盤報告 ---
    if report_msgs:
        if is_closing:
            title = "🌅 收盤行情與損益試算 (13:45)"
            color = 10181046 
            desc = "今日收盤最終戰績：\n\n" + "\n".join(report_msgs)
            send_discord_report(title, desc, color)
        elif is_hourly:
            title = f"⏰ 整點報價 ({current_hour}:00)"
            color = 3447003
            desc = "即時行情與損益監控：\n\n" + "\n".join(report_msgs)
            send_discord_report(title, desc, color)

if __name__ == "__main__":
    check_stock()
