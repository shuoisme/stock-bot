import yfinance as yf
import requests
import os
import json
import time
from datetime import datetime, timedelta, timezone
from github import Github

# --- 設定區 ---
JSON_FILE = 'stocks.json'
REPO_NAME = "shuoisme/stock-bot"  # ⚠️ 確認這裡跟你的專案名稱一樣
TZ_TAIWAN = timezone(timedelta(hours=8))

# --- LINE 推播 ---
def send_line_push(msg):
    token = os.environ.get("LINE_ACCESS_TOKEN")
    user_id = os.environ.get("LINE_USER_ID")
    
    if not token or not user_id:
        print("❌ 未設定 LINE Token 或 User ID")
        return

    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Content-Type": "application/json", "Authorization": "Bearer " + token}
    payload = {"to": user_id, "messages": [{"type": "text", "text": msg}]}
    
    try:
        requests.post(url, headers=headers, json=payload)
    except Exception as e:
        print(f"推播錯誤: {e}")

# 格式化
def format_alert_msg(symbol, price, title, pct=0, target=None, pl_str=""):
    now_str = datetime.now(TZ_TAIWAN).strftime('%H:%M')
    msg = f"{title} {symbol}\n🕒 {now_str}\n💰 {price:.2f}"
    if pct != 0: msg += f" ({pct:+.2f}%)"
    if target: msg += f"\n🎯 目標: {target}"
    if pl_str: msg += f"\n{pl_str}"
    return msg

# 抓價
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

# --- 核心邏輯 (強制測試版) ---
def check_stock():
    gh_token = os.environ.get("GH_TOKEN")
    if not gh_token: return

    g = Github(gh_token)
    try:
        repo = g.get_repo(REPO_NAME)
        contents = repo.get_contents(JSON_FILE)
        stock_list = json.loads(contents.decoded_content.decode())
    except:
        return

    now = datetime.now(TZ_TAIWAN)
    today_str = now.strftime('%Y-%m-%d')
    
    # 👇👇👇 改了這裡：強制開啟報價功能 👇👇👇
    is_report_time = True 
    # (原本的的時間判斷被我拿掉了，這樣你現在跑一定會有反應)

    print(f"🔍 強制測試開始... (日期: {today_str})")
    report_msgs = []
    need_save = False

    for item in stock_list:
        sid = item['stock_id']
        buy_target = float(item['buy_target']) if item.get('buy_target') else None
        sell_target = float(item['sell_target']) if item.get('sell_target') else None
        cost_price = float(item.get('cost_price', 0))
        notify_record = item.get('last_notify', {}) 

        price, prev_close, real_symbol = fetch_price_data(sid)
        
        if price and prev_close:
            change_pct = ((price - prev_close) / prev_close) * 100
            
            pl_str = ""
            if cost_price > 0:
                pl_val = price - cost_price
                pl_pct = (pl_val / cost_price) * 100
                sign = "+" if pl_val > 0 else ""
                pl_str = f"損益: {sign}{pl_val:.1f} ({sign}{pl_pct:.1f}%)"

            # 警報邏輯 (保留)
            if change_pct >= 9.5:
                if notify_record.get('limit_up') != today_str:
                    send_line_push(format_alert_msg(real_symbol, price, "🔥[漲停通知]", pct=change_pct, pl_str=pl_str))
                    notify_record['limit_up'] = today_str
                    need_save = True
            elif change_pct <= -9.5:
                if notify_record.get('limit_down') != today_str:
                    send_line_push(format_alert_msg(real_symbol, price, "🤮[跌停通知]", pct=change_pct, pl_str=pl_str))
                    notify_record['limit_down'] = today_str
                    need_save = True
            elif buy_target and price <= buy_target:
                if notify_record.get('buy') != today_str:
                    send_line_push(format_alert_msg(real_symbol, price, "✅[買進訊號]", target=buy_target, pl_str=pl_str))
                    notify_record['buy'] = today_str
                    need_save = True
            elif sell_target and price >= sell_target:
                if notify_record.get('sell') != today_str:
                    send_line_push(format_alert_msg(real_symbol, price, "💰[獲利訊號]", target=sell_target, pl_str=pl_str))
                    notify_record['sell'] = today_str
                    need_save = True

            item['last_notify'] = notify_record

            # 收集報價 (因為 is_report_time 強制為 True，這裡一定會執行)
            if is_report_time:
                icon = "🔺" if change_pct > 0 else "🔻" if change_pct < 0 else "➖"
                pl_line = f"\n   └ {pl_str}" if pl_str else ""
                line_msg = f"{real_symbol}: {price:.2f} {icon}({change_pct:.2f}%){pl_line}"
                report_msgs.append(line_msg)

    # 存檔
    if need_save:
        try:
            new_content = json.dumps(stock_list, indent=2, ensure_ascii=False)
            repo.update_file(contents.path, f"Update record {today_str}", new_content, contents.sha)
        except: pass

    # 發送測試報告
    if report_msgs:
        full_msg = f"🧪 [強制測試] 行情回報\n" + "-"*15 + "\n" + "\n\n".join(report_msgs)
        send_line_push(full_msg)

if __name__ == "__main__":
    check_stock()
