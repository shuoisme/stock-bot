import yfinance as yf
import requests
import os
import json
import time
from datetime import datetime, timedelta, timezone
from github import Github

# --- 設定區 ---
JSON_FILE = 'stocks.json'
REPO_NAME = "shuoisme/stock-bot"  # ⚠️ 這裡要是你的 "帳號/專案名稱"
TZ_TAIWAN = timezone(timedelta(hours=8))

# --- 1. LINE Messaging API 推播功能 (新版) ---
def send_line_push(msg):
    # 讀取你在 GitHub Secrets 設定的兩把鑰匙
    token = os.environ.get("LINE_ACCESS_TOKEN")
    user_id = os.environ.get("LINE_USER_ID")
    
    if not token or not user_id:
        print("❌ 錯誤: 未設定 LINE_ACCESS_TOKEN 或 LINE_USER_ID")
        return

    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + token
    }
    # 這是 Messaging API 規定的格式
    payload = {
        "to": user_id,
        "messages": [
            {
                "type": "text",
                "text": msg
            }
        ]
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code != 200:
            print(f"推播失敗: {response.text}")
        else:
            print("✅ LINE 訊息發送成功")
    except Exception as e:
        print(f"推播錯誤: {e}")

# 格式化訊息
def format_alert_msg(symbol, price, title, pct=0, target=None, pl_str=""):
    now_str = datetime.now(TZ_TAIWAN).strftime('%H:%M')
    msg = f"{title} {symbol}\n🕒 {now_str}\n💰 {price:.2f}"
    if pct != 0: msg += f" ({pct:+.2f}%)"
    if target: msg += f"\n🎯 目標: {target}"
    if pl_str: msg += f"\n{pl_str}"
    return msg

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
    # 取得 GitHub 權限 (用來寫入檔案)
    gh_token = os.environ.get("GH_TOKEN")
    if not gh_token:
        print("❌ 未設定 GH_TOKEN，無法記憶通知狀態")
        return

    g = Github(gh_token)
    try:
        repo = g.get_repo(REPO_NAME)
        contents = repo.get_contents(JSON_FILE)
        stock_list = json.loads(contents.decoded_content.decode())
    except Exception as e:
        print(f"讀取檔案失敗: {e}")
        return

    now = datetime.now(TZ_TAIWAN)
    today_str = now.strftime('%Y-%m-%d')
    current_hour = now.hour
    current_min = now.minute
    
    need_save = False
    
    # 定義報告時間 (11:00, 13:00, 13:45)
# 定義報告時間 (11:00, 13:00, 13:45)
    # is_report_time = False
    # if (current_hour == 11 and current_min < 10) or \
    #    (current_hour == 13 and current_min < 10) or \
    #    (current_hour == 13 and 45 <= current_min < 55):
    #     is_report_time = True
    
    # 👇 改成這樣：不管幾點，強迫它現在報價！
    is_report_time = True

    print(f"🔍 開始巡邏... (日期: {today_str})")
    report_msgs = []

    for item in stock_list:
        sid = item['stock_id']
        buy_target = float(item['buy_target']) if item.get('buy_target') else None
        sell_target = float(item['sell_target']) if item.get('sell_target') else None
        cost_price = float(item.get('cost_price', 0))
        
        # 讀取上次通知紀錄
        notify_record = item.get('last_notify', {}) 

        price, prev_close, real_symbol = fetch_price_data(sid)
        
        if price and prev_close:
            change_pct = ((price - prev_close) / prev_close) * 100
            
            # 損益字串
            pl_str = ""
            if cost_price > 0:
                pl_val = price - cost_price
                pl_pct = (pl_val / cost_price) * 100
                sign = "+" if pl_val > 0 else ""
                pl_str = f"損益: {sign}{pl_val:.1f} ({sign}{pl_pct:.1f}%)"

            # --- A. 漲跌停/買賣點 記憶監控 (當天只通知一次) ---
            alert_tag = ""
            
            # 1. 漲停
            if change_pct >= 9.5:
                if notify_record.get('limit_up') != today_str:
                    msg = format_alert_msg(real_symbol, price, "🔥[漲停通知]", pct=change_pct, pl_str=pl_str)
                    send_line_push(msg) # 即時發送
                    notify_record['limit_up'] = today_str
                    need_save = True
                alert_tag = " 🔥[漲停]"

            # 2. 跌停
            elif change_pct <= -9.5:
                if notify_record.get('limit_down') != today_str:
                    msg = format_alert_msg(real_symbol, price, "🤮[跌停通知]", pct=change_pct, pl_str=pl_str)
                    send_line_push(msg)
                    notify_record['limit_down'] = today_str
                    need_save = True
                alert_tag = " 🤮[跌停]"

            # 3. 買點
            elif buy_target and price <= buy_target:
                if notify_record.get('buy') != today_str:
                    msg = format_alert_msg(real_symbol, price, "✅[買進訊號]", target=buy_target, pl_str=pl_str)
                    send_line_push(msg)
                    notify_record['buy'] = today_str
                    need_save = True
                alert_tag = " ✅[買點]"

            # 4. 賣點
            elif sell_target and price >= sell_target:
                if notify_record.get('sell') != today_str:
                    msg = format_alert_msg(real_symbol, price, "💰[獲利訊號]", target=sell_target, pl_str=pl_str)
                    send_line_push(msg)
                    notify_record['sell'] = today_str
                    need_save = True
                alert_tag = " 💰[賣點]"

            # 更新紀錄
            item['last_notify'] = notify_record

            # --- B. 定時報價收集 ---
            if is_report_time:
                icon = "🔺" if change_pct > 0 else "🔻" if change_pct < 0 else "➖"
                pl_line = f"\n   └ {pl_str}" if pl_str else ""
                line_msg = f"{real_symbol}: {price:.2f} {icon}({change_pct:.2f}%){alert_tag}{pl_line}"
                report_msgs.append(line_msg)

    # 存檔 (記憶今天發過誰)
    if need_save:
        try:
            new_content = json.dumps(stock_list, indent=2, ensure_ascii=False)
            repo.update_file(contents.path, f"Update notify record {today_str}", new_content, contents.sha)
            print("💾 紀錄已更新")
        except Exception as e:
            print(f"❌ 存檔失敗: {e}")

    # 發送定時報價
    if report_msgs and is_report_time:
        title = "🍱 [午盤]" if current_hour == 11 else "☕ [尾盤]" if current_hour == 13 and current_min < 10 else "🌅 [收盤]"
        full_msg = f"{title} 行情回報\n" + "-"*15 + "\n" + "\n\n".join(report_msgs)
        send_line_push(full_msg)

if __name__ == "__main__":
    check_stock()


