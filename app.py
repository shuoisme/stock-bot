import streamlit as st
import json
import time
import yfinance as yf
from github import Github

# --- 設定頁面 ---
st.set_page_config(page_title="股市帳本", page_icon="💰", layout="wide") 
# 👆 注意：我把 layout 改成 "wide" (寬螢幕)，這樣 5 個數字排一排才不會擠

# --- 1. 連接 GitHub ---
def get_repo():
    token = st.secrets["GH_TOKEN"]
    g = Github(token)
    return g.get_repo("shuoisme/stock-bot")  # ⚠️ 確認你的帳號/專案名稱

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

# --- 2. 抓取股價 ---
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
st.title("💰 股市帳本")

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
            cost = float(item.get('cost_price', 0))
            qty = float(item.get('qty', 1.0))
            buy_target = float(item.get('buy_target', 0) or 0)
            sell_target = float(item.get('sell_target', 0) or 0)
            
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

            # --- 👇 重點修改：使用 container(border=True) 把它們框在一起 ---
            with st.container(border=True):
                # 第一行：股票名稱與大大的現價
                display_name = sid.replace(".TW", "").replace(".TWO", "")
                
                # 標題區
                top_c1, top_c2 = st.columns([1, 4])
                with top_c1:
                    st.markdown(f"### 🏷️ {display_name}")
                with top_c2:
                    if price:
                        # 根據漲跌變色 (這只是裝飾，用來顯示現價)
                        color = "red" if price > cost else "green"
                        st.markdown(f"#### :test_tube: 現價: **{price:.1f}**")
                    else:
                        st.write("讀取中...")

                # 第二行：5 個關鍵數據排排站 (緊湊模式)
                # 使用 5 個欄位，讓它們擠在一起，看起來就是一組的
                m1, m2, m3, m4, m5 = st.columns(5)
                
                m1.metric("📦 持有張數", f"{qty} 張")
                m2.metric("💵 平均成本", f"{cost}")
                m3.metric("💰 總本金", f"${int(invest_cost/1000)}k", help="這是你的總投入成本") 
                # ^ 為了省空間，這裡顯示 k (千元)，例如 15.4k
                
                m4.metric("🏦 股票現值", f"${int(market_value/1000)}k")
                
                color_mode = "normal" if profit > 0 else "inverse"
                m5.metric("📉 損益", f"${int(profit):,}", f"{profit_pct:.1f}%", delta_color=color_mode)

                # 修改區 (隱藏在摺疊選單裡，保持版面乾淨)
                with st.expander(f"⚙️ 設定 {display_name}"):
                    with st.form(key=f"edit_{i}_{sid}"):
                        ce1, ce2, ce3, ce4 = st.columns(4)
                        new_qty = ce1.number_input("張數", value=qty, step=0.1)
                        new_cost = ce2.number_input("成本", value=cost, step=0.1)
                        new_buy = ce3.number_input("監控買", value=buy_target, step=0.1)
                        new_sell = ce4.number_input("監控賣", value=sell_target, step=0.1)
                        
                        b1, b2 = st.columns([1, 1])
                        if b1.form_submit_button("💾 儲存"):
                            item['qty'] = new_qty
                            item['cost_price'] = new_cost
                            item['buy_target'] = new_buy if new_buy > 0 else None
                            item['sell_target'] = new_sell if new_sell > 0 else None
                            save_data(current_stocks, sha)
                            st.rerun()

                        if b2.form_submit_button("🗑️ 刪除", type="primary"):
                            current_stocks.pop(i)
                            save_data(current_stocks, sha)
                            st.rerun()

        # 底部總結
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
        col1, col2 = st.columns([2, 1])
        new_code = col1.text_input("股票代號", placeholder="例如 2330")
        market_type = col2.selectbox("市場類別", ["上市 (.TW)", "上櫃 (.TWO)"])
        
        col3, col4 = st.columns(2)
        new_qty = col3.number_input("持有張數", min_value=0.1, value=1.0, step=0.1)
        new_cost = col4.number_input("平均成本", min_value=0.0, step=0.1)
        
        col5, col6 = st.columns(2)
        new_buy = col5.number_input("想買價", min_value=0.0, step=0.1)
        new_sell = col6.number_input("想賣價", min_value=0.0, step=0.1)

        if st.form_submit_button("送出新增"):
            if new_code:
                suffix = ".TW" if "上市" in market_type else ".TWO"
                final_id = new_code if new_code.endswith(suffix) else f"{new_code}{suffix}"

                exists = any(s['stock_id'] == final_id for s in current_stocks)
                if exists:
                    st.warning("這支股票已經在清單裡囉！")
                else:
                    new_data = {
                        "stock_id": final_id,
                        "qty": new_qty,
                        "cost_price": new_cost,
                        "buy_target": new_buy if new_buy > 0 else None,
                        "sell_target": new_sell if new_sell > 0 else None,
                        "last_notify": {}
                    }
                    current_stocks.append(new_data)
                    save_data(current_stocks, sha)
                    st.success(f"成功加入 {final_id}！")
                    time.sleep(1)
                    st.rerun()
            else:
                st.error("請輸入代號")
