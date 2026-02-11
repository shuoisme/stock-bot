import streamlit as st
import json
import time
import requests 
import yfinance as yf
from github import Github

# --- 設定頁面 ---
st.set_page_config(page_title="家族股市帳本", page_icon="💰", layout="wide") 

# --- 設定區 ---
# ⚠️ 請確認這裡跟你的 GitHub 專案名稱一模一樣
REPO_NAME = "shuoisme/stock-bot" 
WORKFLOW_FILE = "main.yml" 
BRANCH_NAME = "main"       

# --- 1. 連接 GitHub ---
def get_repo():
    token = st.secrets["GH_TOKEN"]
    g = Github(token)
    return g.get_repo(REPO_NAME)

def load_data():
    try:
        repo = get_repo()
        content = repo.get_contents("stocks.json")
        decoded = content.decoded_content.decode()
        if not decoded: return [], content.sha
        return json.loads(decoded), content.sha
    except:
        return [], None

def save_data(data, sha):
    repo = get_repo()
    content = repo.get_contents("stocks.json")
    repo.update_file("stocks.json", "Update from App", json.dumps(data, indent=2, ensure_ascii=False), content.sha)

# --- 🚀 呼叫機器人 ---
def trigger_bot():
    token = st.secrets["GH_TOKEN"]
    url = f"https://api.github.com/repos/{REPO_NAME}/actions/workflows/{WORKFLOW_FILE}/dispatches"
    
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    data = {
        "ref": BRANCH_NAME 
    }
    
    try:
        response = requests.post(url, json=data, headers=headers)
        if response.status_code == 204:
            return True, "🚀 指令已發送！機器人約 30 秒後會回報。"
        else:
            return False, f"❌ 發送失敗 (代碼 {response.status_code})：{response.text}"
    except Exception as e:
        return False, f"❌ 連線錯誤：{str(e)}"

# --- 2. 抓價功能 ---
def get_price_data(ticker):
    try:
        stock = yf.Ticker(ticker)
        price = stock.fast_info.last_price
        if price is None or price == 0:
            hist = stock.history(period="1d")
            if not hist.empty:
                price = hist['Close'].iloc[-1]
        return price
    except:
        return None

def get_current_price(stock_id):
    if stock_id.endswith('.TW') or stock_id.endswith('.TWO'):
        price = get_price_data(stock_id)
        if price: return price
        return 0
    price = get_price_data(f"{stock_id}.TW")
    if price: return price
    price = get_price_data(f"{stock_id}.TWO")
    if price: return price
    return 0

# --- 3. 介面設計 ---
st.title("💰 家族股市帳本")

# 👇 側邊欄放「遙控器」
with st.sidebar:
    st.header("🎮 機器人遙控器")
    st.write("按下去，機器人會馬上把最新報價傳到 LINE 群組！")
    
    if st.button("📣 立即 LINE 回報", type="primary", use_container_width=True):
        with st.spinner("正在呼叫機器人起床..."):
            success, msg = trigger_bot()
            if success:
                st.success(msg)
            else:
                st.error(msg)
    
    st.divider()
    st.info("💡 提示：機器人啟動需要一點時間 (約 20~60 秒)，請耐心等待手機響起。")

tab1, tab2 = st.tabs(["📊 資產看板", "➕ 新增股票"])

current_stocks, sha = load_data()

# === 分頁 1: 資產看板 ===
with tab1:
    if not current_stocks:
        st.info("目前沒有股票，請去隔壁新增 👉")
    else:
        total_market_value = 0 
        total_invest_cost = 0  
        
        for i, item in enumerate(current_stocks):
            sid = item['stock_id']
            name = item.get('name', sid)
            
            cost = float(item.get('cost_price', 0))
            qty = float(item.get('qty', 1.0))
            buy_target = float(item.get('buy_target', 0) or 0)
            sell_target = float(item.get('sell_target', 0) or 0)
            # 🔥 新增：讀取停損價
            stop_loss = float(item.get('stop_loss', 0) or 0)
            
            price = get_current_price(sid)
            
            invest_cost = cost * qty * 1000
            market_value = 0
            profit = 0
            profit_pct = 0
            
            if price:
                market_value = price * qty * 1000
                if cost > 0:
                    profit = market_value - invest_cost
                    profit_pct = (profit / invest_cost) * 100
                
                total_market_value += market_value
                total_invest_cost += invest_cost

            with st.container(border=True):
                clean_id = sid.replace(".TW", "").replace(".TWO", "")
                
                top_c1, top_c2 = st.columns([1, 4])
                with top_c1:
                    st.markdown(f"### {name}")
                    st.caption(f"代號: {clean_id}")
                with top_c2:
                    if price:
                        color = "red" if price > cost else "green"
                        st.markdown(f"#### :test_tube: 現價: **{price:.1f}**")
                    else:
                        st.write("讀取中...")

                m1, m2, m3, m4, m5 = st.columns(5)
                m1.metric("📦 張數", f"{qty} 張")
                m2.metric("💵 成本", f"{cost}")
                m3.metric("💰 本金", f"${int(invest_cost/1000)}k") 
                m4.metric("🏦 現值", f"${int(market_value/1000)}k")
                
                color_mode = "normal" if profit > 0 else "inverse"
                m5.metric("📉 損益", f"${int(profit):,}", f"{profit_pct:.1f}%", delta_color=color_mode)

                with st.expander(f"⚙️ 設定 {name}"):
                    with st.form(key=f"edit_{i}_{sid}"):
                        new_name = st.text_input("股票名稱", value=name)
                        
                        # 調整版面：第一排張數成本
                        r1_c1, r1_c2 = st.columns(2)
                        new_qty = r1_c1.number_input("張數", value=qty, step=0.1)
                        new_cost = r1_c2.number_input("成本", value=cost, step=0.1)
                        
                        # 調整版面：第二排三個監控價 (買/賣/停損)
                        r2_c1, r2_c2, r2_c3 = st.columns(3)
                        new_buy = r2_c1.number_input("想買價", value=buy_target, step=0.1)
                        new_sell = r2_c2.number_input("想賣價", value=sell_target, step=0.1)
                        new_stop = r2_c3.number_input("🛑 停損價", value=stop_loss, step=0.1)
                        
                        b1, b2 = st.columns([1, 1])
                        if b1.form_submit_button("💾 儲存"):
                            item['name'] = new_name
                            item['qty'] = new_qty
                            item['cost_price'] = new_cost
                            item['buy_target'] = new_buy if new_buy > 0 else None
                            item['sell_target'] = new_sell if new_sell > 0 else None
                            # 儲存停損價
                            item['stop_loss'] = new_stop if new_stop > 0 else None
                            
                            save_data(current_stocks, sha)
                            st.rerun()

                        if b2.form_submit_button("🗑️ 刪除", type="primary"):
                            current_stocks.pop(i)
                            save_data(current_stocks, sha)
                            st.rerun()

        st.divider()
        st.markdown("### 🏆 總資產總覽")
        f1, f2, f3 = st.columns(3)
        f1.metric("總投入本金", f"${int(total_invest_cost):,}")
        f2.metric("目前總市值", f"${int(total_market_value):,}")
        final_color = "normal" if (total_market_value - total_invest_cost) > 0 else "inverse"
        f3.metric("總損益", f"${int(total_market_value - total_invest_cost):,}", delta_color=final_color)

# === 分頁 2: 新增 ===
with tab2:
    st.subheader("➕ 加入新股票")
    with st.form("add_stock_form"):
        col1, col2, col3 = st.columns([1, 1, 1])
        new_code = col1.text_input("股票代號", placeholder="例如 2330")
        new_name_input = col2.text_input("股票名稱", placeholder="例如 台積電")
        market_type = col3.selectbox("市場類別", ["上市 (.TW)", "上櫃 (.TWO)"])
        
        c4, c5 = st.columns(2)
        new_qty = c4.number_input("持有張數", min_value=0.1, value=1.0, step=0.1)
        new_cost = c5.number_input("平均成本", min_value=0.0, step=0.1)
        
        # 🔥 修改為三欄，加入停損價
        c6, c7, c8 = st.columns(3)
        new_buy = c6.number_input("想買價", min_value=0.0, step=0.1)
        new_sell = c7.number_input("想賣價", min_value=0.0, step=0.1)
        new_stop = c8.number_input("🛑 停損價", min_value=0.0, step=0.1)

        if st.form_submit_button("送出新增"):
            if new_code:
                suffix = ".TW" if "上市" in market_type else ".TWO"
                final_id = new_code if new_code.endswith(suffix) else f"{new_code}{suffix}"
                final_name = new_name_input if new_name_input else final_id

                exists = any(s['stock_id'] == final_id for s in current_stocks)
                if exists:
                    st.warning("這支股票已經在清單裡囉！")
                else:
                    new_data = {
                        "stock_id": final_id,
                        "name": final_name,
                        "qty": new_qty,
                        "cost_price": new_cost,
                        "buy_target": new_buy if new_buy > 0 else None,
                        "sell_target": new_sell if new_sell > 0 else None,
                        "stop_loss": new_stop if new_stop > 0 else None, # 寫入停損價
                        "last_notify": {}
                    }
                    current_stocks.append(new_data)
                    save_data(current_stocks, sha)
                    st.success(f"成功加入 {final_name}！")
                    time.sleep(1)
                    st.rerun()
            else:
                st.error("請輸入代號")

