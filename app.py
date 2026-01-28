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

# --- 2. 抓取股價 (強力抓取核心) ---
def get_price_data(ticker):
    """
    自動切換通道：先試快速通道，不行就翻歷史紀錄
    """
    try:
        stock = yf.Ticker(ticker)
        # 1. 快速通道
        price = stock.fast_info.last_price
        
        # 2. 歷史通道 (專治上櫃抓不到的問題)
        if price is None or price == 0:
            hist = stock.history(period="1d")
            if not hist.empty:
                price = hist['Close'].iloc[-1]
        
        return price
    except:
        return None

def get_current_price(stock_id):
    # 如果代號已經有 .TW 或 .TWO，直接查
    if stock_id.endswith('.TW') or stock_id.endswith('.TWO'):
        price = get_price_data(stock_id)
        if price: return price
        return 0

    # 如果只有數字，先猜上市，再猜上櫃
    price = get_price_data(f"{stock_id}.TW")
    if price: return price

    price = get_price_data(f"{stock_id}.TWO")
    if price: return price

    return 0

# --- 3. 介面設計 ---
st.title("💰 股市帳本")
st.caption("自動更新股價")

tab1, tab2 = st.tabs(["📊 持股列表", "➕ 新增股票"])

current_stocks, sha = load_data()

# === 分頁 1: 持股卡片 ===
with tab1:
    if not current_stocks:
        st.info("目前沒有股票，請去隔壁新增 👉")
    else:
        total_profit = 0
        
        for i, item in enumerate(current_stocks):
            sid = item['stock_id']
            cost = float(item.get('cost_price', 0))
            qty = float(item.get('qty', 1.0))
            buy_target = float(item.get('buy_target', 0) or 0)
            sell_target = float(item.get('sell_target', 0) or 0)
            
            # 抓現價
            price = get_current_price(sid)
            
            # 算損益
            profit = 0
            profit_pct = 0
            if price and cost > 0:
                profit = (price - cost) * 1000 * qty
                profit_pct = ((price - cost) / cost) * 100
                total_profit += profit

            # --- 卡片顯示 ---
            with st.container():
                # 標題列
                c1, c2 = st.columns([2, 2])
                
                # 介面優化：如果是自動偵測的，不用顯示 (自動偵測) 這麼長，顯示乾淨的代號就好
                display_name = sid.replace(".TW", "").replace(".TWO", "")
                
                c1.subheader(f"🏷️ {display_name}")
                c2.markdown(f"### 💲 {price:.1f}" if price else "💲 讀取中...")

                # 數據列
                k1, k2, k3 = st.columns(3)
                k1.metric("張數/成本", f"{qty} 張", f"{cost}")
                
                color_mode = "normal" if profit > 0 else "inverse"
                k2.metric("總損益", f"{int(profit):,}", f"{profit_pct:.1f}%", delta_color=color_mode)
                
                k3.caption(f"買點: {buy_target or '無'}")
                k3.caption(f"賣點: {sell_target or '無'}")

                # 修改選單 (極簡化：只留真正會用到的)
                with st.expander(f"🛠️ 修改設定"):
                    with st.form(key=f"edit_{i}_{sid}"):
                        ce1, ce2 = st.columns(2)
                        new_qty = ce1.number_input("持有張數", value=qty, step=0.1, key=f"q_{i}")
                        new_cost = ce2.number_input("平均成本", value=cost, step=0.1, key=f"c_{i}")
                        
                        ce3, ce4 = st.columns(2)
                        new_buy = ce3.number_input("監控買點", value=buy_target, step=0.1, key=f"b_{i}")
                        new_sell = ce4.number_input("監控賣點", value=sell_target, step=0.1, key=f"s_{i}")

                        # 那些複雜的「強制修改市場」按鈕都拿掉了！
                        
                        b1, b2 = st.columns([1, 1])
                        
                        if b1.form_submit_button("💾 儲存修改"):
                            item['qty'] = new_qty
                            item['cost_price'] = new_cost
                            item['buy_target'] = new_buy if new_buy > 0 else None
                            item['sell_target'] = new_sell if new_sell > 0 else None
                            
                            save_data(current_stocks, sha)
                            st.toast("✅ 資料已更新！")
                            time.sleep(1)
                            st.rerun()

                        if b2.form_submit_button("🗑️ 刪除", type="primary"):
                            current_stocks.pop(i)
                            save_data(current_stocks, sha)
                            st.toast("❌ 已刪除")
                            time.sleep(1)
                            st.rerun()
                st.divider()

        # 總結
        st.markdown("### 🏦 帳戶總損益")
        if total_profit > 0:
            st.success(f"💰 目前共賺：NT$ {int(total_profit):,}")
        else:
            st.error(f"💸 目前共賠：NT$ {int(total_profit):,}")

# === 分頁 2: 新增 ===
with tab2:
    st.subheader("➕ 加入新股票")
    with st.form("add_stock_form"):
        col1, col2 = st.columns([2, 1])
        new_code = col1.text_input("股票代號", placeholder="例如 3071")
        # 這裡保留下拉選單，因為新增時選對市場可以加快讀取速度
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
