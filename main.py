import requests
import os
import json
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from github import Github, Auth

# --- 設定區 ---
JSON_FILE = 'stocks.json'
REPO_NAME = "shuoisme/stock-bot"
TZ_TAIWAN = timezone(timedelta(hours=8))

# --- 1. LINE 推播功能 (加強錯誤偵測版) ---
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
        res = requests.post(url, headers=headers, json=payload)
        # 🔥 檢查 LINE 有沒有退信
        if res.status_code != 200:
            print(f"❌ [LINE 拒絕發送] 狀態碼: {res.status_code}, 原因: {res.text}")
        else:
            print("📩 LINE 伺服器已成功接收並傳送到手機！")
    except Exception as e:
        print(f"❌ [錯誤] 網路連線推播失敗: {e}")

# 格式化訊息
def format_alert_msg(name, symbol, price, title, pct=0, diff=0, target=None, pl_str=""):
    now_str = datetime.now(TZ_TAIWAN).strftime('%H:%M')
    price_val = float(price)
    diff_val = float(diff)
    pct_val = float(pct)

    change_str = f"{diff_val:+.2f} ({pct_val:+.2f}%)" if price_val > 0 else ""
    msg = f"{title} {name} ({symbol})\n🕒 {now_str}\n💰 {price_val:.2f} {change_str}"
    if target: msg += f"\n🛑 停損觸發: {target}" if "停損" in title else f"\n🎯 目標: {target}"
    if pl_str: msg += f"\n{pl_str}"
    return msg

# --- 2. 抓價功能 ---
def fetch_price_data(stock_id, today_str):
    api_token = os.environ.get("FUGLE_TOKEN")
    if not api_token:
        print("❌ 錯誤：找不到 FUGLE_TOKEN")
        return None, None, None

    clean_symbol = stock_id.replace(".TWO", "").replace(".TW", "")
    url = f"https://api.fugle.tw/marketdata/v1.0/stock/intraday/quote/{clean_symbol}"
    headers = {"X-API-KEY": api_token}

    try:
        time.sleep(0.5) 
        res = requests.get(url, headers=headers)
        data = res.json()
        
        if "date" in data and data["date"] != today_str:
            return "HOLIDAY", None, clean_symbol

        if "lastTrade" in data and "price" in data["lastTrade"]:
            price = data["lastTrade"]["price"]
            prev_close = data.get("previousClose")
            return price, prev_close, clean_symbol
        else:
            print(f"⚠️ 富果無資料: {clean_symbol}")
            return None, None, None
    except Exception as e:
        print(f"❌ 連線失敗: {e}")
        return None, None, None

# --- 3. 核心檢查邏輯 ---
def check_stock():
    gh_token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not gh_token:
        print("❌ 找不到 GH_TOKEN")
        return

    auth = Auth.Token(gh_token)
    g = Github(auth=auth)

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
    
    is_lunch_time = (current_hour == 11 and current_min <= 30)
    is_tail_time = (current_hour == 13 and current_min <= 30)
    is_close_time = (current_hour == 13 and current_min >= 40)
    is_report_time = is_lunch_time or is_tail_time or is_close_time
    if event_name == 'workflow_dispatch': is_report_time = True

    report_msgs = []
    market_is_open = False

    for item in stock_list:
        sid = item['stock_id']
        name = item.get('name', sid)
        
        buy_target = float(item.get('buy_target') or 0)
        sell_target = float(item.get('sell_target') or 0)
        
        # 🔥 V7.1 修正處：加強對 None 的防護
        # 這裡加了 "or 0"，意思是：如果讀到 None，就用 0 代替
        stop_loss = float(item.get('stop_loss') or 0)
        
        cost_price = float(item.get('cost_price') or 0)
        notify_record = item.get('last_notify') or {} 

        price_raw, prev_raw, real_symbol = fetch_price_data(sid, today_str)
        
        if price_raw == "HOLIDAY":
            continue
            
        if price_raw and prev_raw:
            market_is_open = True
            p_dec = Decimal(str(price_raw))
            prev_dec = Decimal(str(prev_raw))
            diff_dec = p_dec - prev_dec
            pct_dec = Decimal("0")
            if prev_dec > 0:
                pct_dec = ((diff_dec / prev_dec) * 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            
            price = float(p_dec)
            diff_val = float(diff_dec)
            change_pct = float(pct_dec)

            pl_str = ""
            if cost_price > 0:
                cost_dec = Decimal(str(cost_price))
                pl_val_dec = p_dec - cost_dec
                pl_pct_dec = ((pl_val_dec / cost_dec) * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
                sign = "+" if pl_val_dec > 0 else ""
                pl_str = f"損益: {sign}{pl_val_dec} ({sign}{pl_pct_dec}%)"

            # === 警報檢查區 ===
            # 優先檢查停損
            if stop_loss > 0 and price <= stop_loss:
                if notify_record.get('stop_loss') != today_str:
                    msg = format_alert_msg(name, real_symbol, price, "🛑[停損觸發]", pct=change_pct, diff=diff_val, target=stop_loss, pl_str=pl_str)
                    send_line_push(msg)
                    notify_record['stop_loss'] = today_str
                    need_save = True

            elif change_pct <= -9.0:
                if notify_record.get('limit_down') != today_str:
                    msg = format_alert_msg(name, real_symbol, price, "📉[即將跌停]", pct=change_pct, diff=diff_val, pl_str=pl_str)
                    send_line_push(msg)
                    notify_record['limit_down'] = today_str
                    need_save = True
            elif change_pct >= 9.0:
                if notify_record.get('limit_up') != today_str:
                    msg = format_alert_msg(name, real_symbol, price, "🚀[即將漲停]", pct=change_pct, diff=diff_val, pl_str=pl_str)
                    send_line_push(msg)
                    notify_record['limit_up'] = today_str
                    need_save = True
            elif buy_target and price <= buy_target:
                if notify_record.get('buy') != today_str:
                    msg = format_alert_msg(name, real_symbol, price, "✅[買進訊號]", target=buy_target, pl_str=pl_str)
                    send_line_push(msg)
                    notify_record['buy'] = today_str
                    need_save = True
            elif sell_target and price >= sell_target:
                if notify_record.get('sell') != today_str:
                    msg = format_alert_msg(name, real_symbol, price, "💰[獲利訊號]", target=sell_target, pl_str=pl_str)
                    send_line_push(msg)
                    notify_record['sell'] = today_str
                    need_save = True

            item['last_notify'] = notify_record

            if is_report_time:
                alert_tag = ""
                if stop_loss > 0 and price <= stop_loss: alert_tag = " 🛑[損]"
                elif change_pct <= -9.0: alert_tag = " 📉[險]"
                elif change_pct >= 9.0: alert_tag = " 🚀[衝]"
                elif buy_target and price <= buy_target: alert_tag = " ✅[買]"
                elif sell_target and price >= sell_target: alert_tag = " 💰[賣]"

                icon = "⬆️" if diff_val > 0 else "⬇️" if diff_val < 0 else "➖"
                diff_str = f"{diff_val:+.2f} ({change_pct:+.2f}%)"
                pl_line = f"\n   └ {pl_str}" if pl_str else ""
                line_msg = f"{name}: {price:.2f} {icon} {diff_str}{alert_tag}{pl_line}"
                report_msgs.append(line_msg)
        else:
            print(f"⚠️ {sid} 抓不到資料")

    if need_save:
        try:
            new_content = json.dumps(stock_list, indent=2, ensure_ascii=False)
            repo.update_file(contents.path, f"Update record {today_str}", new_content, contents.sha)
        except: pass

    if report_msgs and is_report_time and market_is_open:
        title = "🔎 [即時]"
        if is_lunch_time: title = "🍱 [午盤]"
        elif is_tail_time: title = "☕ [尾盤]"
        elif is_close_time: title = "🌅 [收盤]"
        
        full_msg = f"{title} 行情 \n" + "-"*18 + "\n" + "\n\n".join(report_msgs)
        send_line_push(full_msg)
        print(f"✅ 已發送: {title}")
    elif not market_is_open:
        print("💤 偵測到休市，不發送通知。")

if __name__ == "__main__":
    check_stock()
