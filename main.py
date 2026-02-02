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
        print("❌ [錯誤] 未設定 LINE Token 或 User ID")
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
        print(f"❌ [錯誤] 推播失敗: {e}")

# 格式化訊息
def format_alert_msg(name, symbol, price, title, pct=0, diff=0, target=None, pl_str=""):
    now_str = datetime.now(TZ_TAIWAN).strftime('%H:%M')
    # 富果不需要 .TW，但顯示時我們還是可以保留原本的 ID 讓你看習慣
    change_str = f"{diff:+.2f} ({pct:+.2f}%)" if price > 0 else ""
    msg = f"{title} {name} ({symbol})\n🕒 {now_str}\n💰 {price:.2f} {change_str}"
    if target: msg += f"\n🎯 目標: {target}"
    if pl_str: msg += f"\n{pl_str}"
    return msg

# --- 2. 抓價功能 (V6.0 富果 Fugle 專業版) ---
def fetch_price_data(stock_id):
    # 取得 GitHub Secrets 裡的 Token
    api_token = os.environ.get("FUGLE_TOKEN")
    
    if not api_token:
        print("❌ 錯誤：找不到 FUGLE_TOKEN，請去 GitHub Settings 設定！")
        return None, None, None

    # 1. 處理代碼：富果不吃 ".TW"
    clean_symbol = stock_id.replace(".TW", "").replace(".TWO", "")

    # 2. 呼叫富果 API (Intraday Quote)
    url = f"https://api.fugle.tw/marketdata/v1.0/stock/intraday/quote/{clean_symbol}"
    headers = {
        "X-API-KEY": api_token
    }

    try:
        res = requests.get(url, headers=headers)
        data = res.json()
        
        # 檢查是否有抓到資料
        if "lastTrade" in data and "price" in data["lastTrade"]:
            price = data["lastTrade"]["price"]
            prev_close = data.get("previousClose") # 富果直接給官方昨收，絕對準確
            
            return price, prev_close, clean_symbol
        else:
            print(f"⚠️ 富果回傳無資料: {stock_id} (可能是下市或代號錯誤)")
            return None, None, None

    except Exception as e:
        print(f"❌ 富果連線失敗 {stock_id}: {e}")
        return None, None, None


# --- 3. 核心檢查邏輯 ---
def check_stock():
    gh_token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not gh_token:
        print("❌ 找不到 GH_TOKEN")
        return

    g = Github(gh_token)
    try:
        repo = g.get_repo(REPO_NAME)
        contents = repo.get_contents(JSON_FILE)
        stock_list = json.loads(contents.decoded_content.decode())
    except Exception as e:
        print(f"❌ 讀檔失敗: {e}")
        return

    now = datetime.now(TZ_TAIWAN)
    today_str = now.strftime('%Y-%m-%d')
    current_hour = now.hour
    current_min = now.minute
    event_name = os.environ.get('GITHUB_EVENT_NAME')

    print(f"🔍 目前時間: {current_hour}:{current_min}")

    need_save = False
    
    # === 時間區段 (與之前相同) ===
    is_lunch_time = (current_hour == 11 and current_min <= 30)
    is_tail_time = (current_hour == 13 and current_min <= 30)
    is_close_time = (current_hour >= 13 and current_min >= 40)

    is_report_time = is_lunch_time or is_tail_time or is_close_time
    
    if event_name == 'workflow_dispatch':
        is_report_time = True

    report_msgs = []

    for item in stock_list:
        sid = item['stock_id']
        name = item.get('name', sid)
        
        buy_target = float(item['buy_target']) if item.get('buy_target') else None
        sell_target = float(item['sell_target']) if item.get('sell_target') else None
        cost_price = float(item.get('cost_price', 0))
        notify_record = item.get('last_notify') or {} 

        # 呼叫新的富果抓價功能
        price, prev_close, real_symbol = fetch_price_data(sid)
        
        if price and prev_close:
            change_pct = 0
            diff_val = 0
            
            diff_val = price - prev_close
            if prev_close > 0:
                change_pct = (diff_val / prev_close) * 100
            
            pl_str = ""
            if cost_price > 0:
                pl_val = price - cost_price
                pl_pct = (pl_val / cost_price) * 100
                sign = "+" if pl_val > 0 else ""
                pl_str = f"損益: {sign}{pl_val:.1f} ({sign}{pl_pct:.1f}%)"

            # === 警報檢查區 (維持 9% 預警) ===
            alert_tag = ""
            
            if change_pct <= -9.0:
                if notify_record.get('limit_down') != today_str:
                    msg = format_alert_msg(name, real_symbol, price, "📉[即將跌停]", pct=change_pct, diff=diff_val, pl_str=pl_str)
                    send_line_push(msg)
                    notify_record['limit_down'] = today_str
                    need_save = True
                alert_tag = " 📉[險]"
            
            elif change_pct >= 9.0:
                if notify_record.get('limit_up') != today_str:
                    msg = format_alert_msg(name, real_symbol, price, "🚀[即將漲停]", pct=change_pct, diff=diff_val, pl_str=pl_str)
                    send_line_push(msg)
                    notify_record['limit_up'] = today_str
                    need_save = True
                alert_tag = " 🚀[衝]"
            
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

            if is_report_time:
                icon = "⬆️" if diff_val > 0 else "⬇️" if diff_val < 0 else "➖"
                diff_str = f"{diff_val:+.2f} ({change_pct:+.2f}%)"
                pl_line = f"\n   └ {pl_str}" if pl_str else ""
                line_msg = f"{name}: {price:.2f} {icon} {diff_str}{alert_tag}{pl_line}"
                report_msgs.append(line_msg)
        else:
            print(f"⚠️ {sid} 抓不到資料，跳過。")

    if need_save:
        try:
            new_content = json.dumps(stock_list, indent=2, ensure_ascii=False)
            repo.update_file(contents.path, f"Update record {today_str}", new_content, contents.sha)
        except: pass

    # === 最終發送 ===
    if report_msgs and is_report_time:
        title = "🔎 [即時]"
        if is_lunch_time: title = "🍱 [午盤]"
        elif is_tail_time: title = "☕ [尾盤]"
        elif is_close_time: title = "🌅 [收盤]"
        
        full_msg = f"{title} 行情（精準）\n" + "-"*18 + "\n" + "\n\n".join(report_msgs)
        send_line_push(full_msg)
        print(f"✅ 已發送: {title}")

if __name__ == "__main__":
    check_stock()


