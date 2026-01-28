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

# --- 2. 抓取股價 (支援上市上櫃) ---
def get_current_price(stock_id):
    try:
        # 如果 stock_id 已經包含 .TW 或 .TWO，直接用
        # 如果是舊資料只有數字，先試 .TW 再試 .TWO
        ticker = stock_id
        if not (ticker.endswith('.TW') or ticker.endswith('.TWO')):
            ticker = f"{stock_id}.TW"
        
        stock = yf.Ticker(ticker)
        price = stock.fast_info.last_price
        
        # 如果舊資料抓不到上市，試試上櫃
        if price is None and not (stock_id.endswith('.TW') or stock_id.endswith('.TWO')):
             stock = yf.Ticker(f"{stock_id}.TWO")
             price = stock.fast_info.last_price
             
        return price
    except:
        return 0

# --- 3. 介面設計 ---
st.title("💰 股市帳本")
st.caption("支援上市/上櫃與張數計算")

tab1, tab2 = st.tabs(["📊 持股管理 (修改/刪除)", "➕ 新增股票"])

current_stocks, sha = load_data()

# === 分頁 1: 持股卡片 ===
with tab1:
    if not current_stocks:
        st.info("目前沒有股票，請去隔壁新增 👉")
    else:
        total_profit = 0
        
        for i, item in enumerate(current_stocks):
            # 讀取資料 (容錯處理：如果舊資料沒有 qty，預設為 1)
            sid = item['stock_id']
            cost = float(item.get('cost_price', 0))
            qty = float(item.get('qty', 1.0))  # 👈 新增：張數
            
            buy_target = float(item.get('buy_target', 0) or 0)
            sell_target = float(item.get('sell_target', 0) or 0)
            
            # 抓現價
            price = get_current_price(sid)
            
            # 算損益 ( (現價 - 成本) * 1000股 * 張數 )
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
                c1.subheader(f"🏷️ {sid}")
                c2.markdown(f"### 💲 {price:.1f}" if price else "💲 讀取中...")

                # 數據列
                k1, k2, k3 = st.columns(3)
                k1.metric("持有張數", f"{qty} 張", f"成本 {cost}")
                
                # 損益顯示
                color_mode = "normal" if profit > 0 else "inverse"
                k2.metric("總損益", f"{int(profit):,}", f"{profit_pct:.1f}%", delta_color=color_mode)
                
                k3.caption(f"監控買: {buy_target or '無'}")
                k3.caption(f"監控賣: {sell_target or '無'}")

                # 修改選單
                with st.expander(f"🛠️ 修改/刪除 {sid}"):
                    with st.form(key=f"edit_{i}_{sid}"):
                        st.write("修改設定：")
                        # 第一排：張數與成本
                        ce1, ce2 = st.columns(2)
                        new_qty = ce1.number_input("張數", value=qty, step=0.1, key=f"q_{i}")
                        new_cost = ce2.number_input("成本", value=cost, step=0.1, key=f"c_{i}")
                        
                        # 第二排：監控價
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

# === 分頁 2: 新增 (含市場選擇) ===
with tab2:
    st.subheader("➕ 加入新股票")
    with st.form("add_stock_form"):
        col1, col2 = st.columns([2, 1])
        new_code = col1.text_input("股票代號", placeholder="例如 2330")
        market_type = col2.selectbox("市場類別", ["上市 (.TW)", "上櫃 (.TWO)"])
        
        col3, col4 = st.columns(2)
        new_qty = col3.number_input("持有張數", min_value=0.1, value=1.0, step=0.1)
        new_cost = col4.number_input("平均成本", min_value=0.0, step=0.1)
        
        st.markdown("---")
        st.write("設定通知 (選填)")
        col5, col6 = st.columns(2)
        new_buy = col5.number_input("想買價", min_value=0.0, step=0.1)
        new_sell = col6.number_input("想賣價", min_value=0.0, step=0.1)

        if st.form_submit_button("送出新增"):
            if new_code:
                # 處理代號後綴
                suffix = ".TW" if "上市" in market_type else ".TWO"
                # 如果使用者沒自己打後綴，幫他加上去
                if not new_code.endswith(suffix):
                    final_id = f"{new_code}{suffix}"
                else:
                    final_id = new_code

                # 檢查重複
                exists = any(s['stock_id'] == final_id for s in current_stocks)
                if exists:
                    st.warning("這支股票已經在清單裡囉！")
                else:
                    new_data = {
                        "stock_id": final_id,
                        "qty": new_qty,  # 👈 存入張數
                        "cost_price": new_cost,
                        "buy_target": new_buy if new_buy > 0 else None,
                        "sell_target": new_sell if new_sell > 0 else None,
                        "last_notify": {}
                    }
                    current_stocks.append(new_data)
                    save_data(current_stocks, sha)
                    st.success(f"成功加入 {final_id} ({new_qty}張)！")
                    time.sleep(1)
                    st.rerun()
            else:
                st.error("請輸入代號")

