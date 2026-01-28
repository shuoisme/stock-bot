import streamlit as st
import json
import time
import yfinance as yf
from github import Github

# --- 設定頁面 ---
st.set_page_config(page_title="股市帳本", page_icon="💰", layout="centered")

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

# --- 2. 抓取股價 (強力抓取) ---
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
st.caption("即時資產損益表")

tab1, tab2 = st.tabs(["📊 資產看板", "➕ 新增股票"])

current_stocks, sha = load_data()

# === 分頁 1: 資產看板 ===
with tab1:
    if not current_stocks:
        st.info("目前沒有股票，請去隔壁新增 👉")
    else:
        total_market_value = 0 # 總資產
        total_invest_cost = 0  # 總成本
        
        for i, item in enumerate(current_stocks):
            sid = item['stock_id']
            cost = float(item.get('cost_price', 0))
            qty = float(item.get('qty', 1.0))
            buy_target = float(item.get('buy_target', 0) or 0)
            sell_target = float(item.get('sell_target', 0) or 0)
            
            # 抓現價
            price = get_current_price(sid)
            
            # 核心計算
            # 1. 總投入成本 = 平均成本 * 張數 * 1000
            invest_cost = cost * qty * 1000
            
            # 2. 股票現值 = 現價 * 張數 * 1000
            market_value = 0
            profit = 0
            profit_pct = 0
            
            if price:
                market_value = price * qty * 1000
                if cost > 0:
                    profit = market_value - invest_cost
                    profit_pct = (profit / invest_cost) * 100
                
                # 累加到總帳戶
                total_market_value += market_value
                total_invest_cost += invest_cost

            # --- 卡片顯示 ---
            with st.container():
                # 標題與現價
                display_name = sid.replace(".TW", "").replace(".TWO", "")
                
                # 使用 columns 讓標題跟現價排在同一行
                head1, head2 = st.columns([3, 2])
                head1.subheader(f"🏷️ {display_name}")
                if price:
                    head2.markdown(f"#### 💲 現價: {price:.1f}")
                else:
                    head2.markdown("#### 💲 讀取中...")

                st.markdown("---") # 分隔線

                # 第一排：基本資料 (張數、單價)
                r1_c1, r1_c2, r1_c3 = st.columns(3)
                r1_c1.metric("📦 持有張數", f"{qty} 張")
                r1_c2.metric("💵 平均成本", f"{cost}")
                # 這裡留空或是放監控價
                r1_c3.caption(f"監控買: {buy_target or '無'}\n\n監控賣: {sell_target or '無'}")

                # 第二排：財務數據 (總成本、現值、損益) -> 這是這次改版的重點
                r2_c1, r2_c2, r2_c3 = st.columns(3)
                
                # 總成本
                r2_c1.metric("💰 總投入成本", f"${int(invest_cost):,}")
                
                # 現值
                r2_c2.metric("🏦 股票現值", f"${int(market_value):,}")
                
                # 損益 (紅賺綠賠)
                color_mode = "normal" if profit > 0 else "inverse"
                r2_c3.metric("📉 帳面損益", f"${int(profit):,}", f"{profit_pct:.1f}%", delta_color=color_mode)

                # 修改按鈕
                with st.expander(f"🛠️ 修改 {display_name} 設定"):
                    with st.form(key=f"edit_{i}_{sid}"):
                        ce1, ce2 = st.columns(2)
                        new_qty = ce1.number_input("持有張數", value=qty, step=0.1, key=f"q_{i}")
                        new_cost = ce2.number_input("平均成本", value=cost, step=0.1, key=f"c_{i}")
                        
                        ce3, ce4 = st.columns(2)
                        new_buy = ce3.number_input("監控買點", value=buy_target, step=0.1, key=f"b_{i}")
                        new_sell = ce4.number_input("監控賣點", value=sell_target, step=0.1, key=f"s_{i}")
                        
                        b1, b2 = st.columns([1, 1])
                        if b1.form_submit_button("💾 儲存修改"):
                            item['qty'] = new_qty
                            item['cost_price'] = new_cost
                            item['buy_target'] = new_buy if new_buy > 0 else None
                            item['sell_target'] = new_sell if new_sell > 0 else None
                            save_data(current_stocks, sha)
                            st.toast("✅ 更新成功")
                            time.sleep(1)
                            st.rerun()

                        if b2.form_submit_button("🗑️ 刪除", type="primary"):
                            current_stocks.pop(i)
                            save_data(current_stocks, sha)
                            st.toast("❌ 已刪除")
                            time.sleep(1)
                            st.rerun()
                st.divider()

        # 頁面最下方的總結算
        total_profit_all = total_market_value - total_invest_cost
        st.markdown("### 🏆 家族總資產結算")
        
        m1, m2, m3 = st.columns(3)
        m1.metric("總投入本金", f"${int(total_invest_cost):,}")
        m2.metric("目前總市值", f"${int(total_market_value):,}")
        
        final_color = "normal" if total_profit_all > 0 else "inverse"
        m3.metric("總損益", f"${int(total_profit_all):,}", delta_color=final_color)

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
