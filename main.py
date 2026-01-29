import yfinance as yf
import requests
import os
import json
import time
from datetime import datetime, timedelta, timezone
from github import Github

# --- 設定區 ---
JSON_FILE = 'stocks.json'
REPO_NAME = "shuoisme/stock-bot"  # ⚠️ 確認你的帳號/專案名稱
TZ_TAIWAN = timezone(timedelta(hours=8))

# --- 1. LINE 推播功能 ---
def send_line_push(msg):
    token = os.environ.get("LINE_ACCESS_TOKEN")
    user_id = os.environ.get("LINE_USER_ID")
    
    if not token or not user_id:
        print("❌ 未設定 LINE Token 或 User ID")
        return

    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + token
    }
    payload = {
        "to": user_id,
        "messages": [{"type": "text", "text": msg}]
    }
    
    try:
        requests.post(url, headers=headers, json=payload)
    except Exception as e:
        print(f"推播錯誤: {e}")

# 格式化訊息 (加入名稱顯示)
def format_alert_msg(name, symbol, price, title, pct=0, target=None, pl_str=""):
    now_str = datetime.now(TZ_TAIWAN).strftime('%H:%M')
    # 顯示格式：[漲停] 台積電 (2330)
    clean_symbol = symbol.replace(".TW", "").replace(".TWO", "")
    msg = f"{title} {name} ({clean_symbol})\n🕒 {now_str}\n💰 {price:.2f}"
    if pct != 0: msg += f" ({pct:+.2f}%)"
    if target: msg += f"\n🎯 目標: {target}"
    if pl_str: msg += f"\n{pl_str}"
    return msg

# --- 2. 抓價功能 ---
def fetch_price_data(stock_id):
    def _get_data(ticker):
        try:
            stock = yf.Ticker(ticker)
            price = stock.fast_info.last_price
            prev = stock.fast_info.previous_close
            
            if price is None or price == 0:
                hist = stock.history(period="1d")
                if not hist.empty:
                    price = hist['Close'].iloc[-1]
                    if prev is None: prev = price 
            return price, prev
        except:
            return None, None

    if stock_id.endswith('.TW') or stock_id.endswith('.TWO'):
        p, prev = _get_data(stock_id)
        if p: return p, prev, stock_id
        return None, None, None

    p, prev = _get_data(f"{stock_id}.TW")
    if p: return p, prev, f"{stock_id}.TW"

    p, prev = _get_data(f"{stock_id}.TWO")
    if p: return p, prev, f"{stock_id}.TWO"

    return None, None, None

# --- 3. 核心檢查邏輯 ---
def check_stock():
    gh_token = os.environ.get("GH_TOKEN")
    if not gh_token: return

    g = Github(gh_token)
    try:
        repo = g.get_repo(REPO_NAME)
        contents = repo.get_contents(JSON_FILE)
        stock_list = json.loads(contents.decoded_content.decode())
    except: return

    now = datetime.now(TZ_TAIWAN)
    today_str = now.strftime('%Y-%m-%d')
    current_hour = now.hour
    current_min = now.minute
    
    need_save = False
    
    # 定時報告 (11:00, 13:00, 13:45)
    is_report_time = False
    if (current_hour == 11 and current_min < 15) or \
       (current_hour == 13 and current_min < 15) or \
       (current_hour == 13 and 45 <= current_min < 55):
        is_report_time = True

    print(f"🔍 開始巡邏... ({today_str})")
    report_msgs = []

    for item in stock_list:
        sid = item['stock_id']
        # 👇 讀取名稱 (如果沒有就用代號)
        name = item.get('name', sid)
        
        buy_target = float(item['buy_target']) if item.get('buy_target') else None
        sell_target = float(item['sell_target']) if item.get('sell_target') else None
        cost_price = float(item.get('cost_price', 0))
        notify_record = item.get('last_notify') or {} 

        price, prev_close, real_symbol = fetch_price_data(sid)
        
        if price:
            change_pct = 0
            if prev_close and prev_close > 0:
                change_pct = ((price - prev_close) / prev_close) * 100
            
            pl_str = ""
            if cost_price > 0:
                pl_val = price - cost_price
                pl_pct = (pl_val / cost_price) * 100
                sign = "+" if pl_val > 0 else ""
                pl_str = f"損益: {sign}{pl_val:.1f} ({sign}{pl_pct:.1f}%)"

            # --- 警報檢查 ---
            alert_tag = ""
            
            if change_pct <= -9.5:
                if notify_record.get('limit_down') != today_str:
                    msg = format_alert_msg(name, real_symbol, price, "🤮[跌停通知]", pct=change_pct, pl_str=pl_str)
                    send_line_push(msg)
                    notify_record['limit_down'] = today_str
                    need_save = True
                alert_tag = " 🤮[跌停]"

            elif change_pct >= 9.5:
                if notify_record.get('limit_up') != today_str:
                    msg = format_alert_msg(name, real_symbol, price, "🔥[漲停通知]", pct=change_pct, pl_str=pl_str)
                    send_line_push(msg)
                    notify_record['limit_up'] = today_str
                    need_save = True
                alert_tag = " 🔥[漲停]"

            elif buy_target and price <= buy_target:
                if notify_record.get('buy') != today_str:
                    msg = format_alert_msg(name, real_symbol, price, "✅[買進訊號]", target=buy_target, pl_str=pl_str)
                    send_line_push(msg)
                    notify_record['buy'] = today_str
                    need_save = True
                alert_tag = " ✅[買點]"

            elif sell_target and price >= sell_target:
                if notify_record.get('sell') != today_str:
                    msg = format_alert_msg(name, real_symbol, price, "💰[獲利訊號]", target=sell_target, pl_str=pl_str)
                    send_line_push(msg)
                    notify_record['sell'] = today_str
                    need_save = True
                alert_tag = " 💰[賣點]"

            item['last_notify'] = notify_record

            # --- 報價列表 ---
            if is_report_time:
                icon = "🔺" if change_pct > 0 else "🔻" if change_pct < 0 else "➖"
                pl_line = f"\n   └ {pl_str}" if pl_str else ""
                # 這裡也改成顯示名稱
                line_msg = f"{name}: {price:.2f} {icon}({change_pct:.2f}%){alert_tag}{pl_line}"
                report_msgs.append(line_msg)

    if need_save:
        try:
            new_content = json.dumps(stock_list, indent=2, ensure_ascii=False)
            repo.update_file(contents.path, f"Update record {today_str}", new_content, contents.sha)
        except: pass

    if report_msgs and is_report_time:
        title = "🍱 [午盤]" if current_hour == 11 else "☕ [尾盤]" if current_hour == 13 else "🌅 [收盤]"
        full_msg = f"{title} 行情回報\n" + "-"*15 + "\n" + "\n\n".join(report_msgs)
        send_line_push(full_msg)

if __name__ == "__main__":
    check_stock()
