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
        # 處理空的 JSON 檔案
        if not decoded:
            return [], content.sha
        return json.loads(decoded), content.sha
    except Exception as e:
        # 如果檔案不存在或格式錯誤，回傳空列表
        return [], None

def save_data(data, sha):
    repo = get_repo()
    content = repo.get_contents("stocks.json")
    repo.update_file("stocks.json", "Update from App", json.dumps(data, indent=2, ensure_ascii=False), content.sha)

# --- 2. 抓取股價 ---
def get_current_price(stock_id):
    try:
        sid = stock_id
        if not sid.endswith('.TW') and not sid.endswith('.TWO'):
            sid = f"{stock_id}.TW"
        
        stock = yf.Ticker(sid)
        price = stock.fast_info.last_price
        if price is None: 
            stock = yf.Ticker(f"{stock_id}.TWO")
            price = stock.fast_info.last_price
        return price
    except:
        return 0

# --- 3. 介面設計 ---
st.title("💰 股市帳本")
st.caption("即時監控與損益試算")

tab1, tab2 = st.tabs(["📊 持股管理 (修改/刪除)", "➕ 新增股票"])

current_stocks, sha = load_data()

# === 分頁 1: 持股卡片 (含編輯功能) ===
with tab1:
    if not current_stocks:
        st.info("目前沒有股票，請去隔壁新增 👉")
    else:
        total_profit = 0
        
        # 為了安全，我們複製一份清單來顯示，避免迴圈中修改出錯
        for i, item in enumerate(current_stocks):
            sid = item['stock_id']
            cost = float(item.get('cost_price', 0))
            buy_target = float(item.get('buy_target', 0) or 0)
            sell_target = float(item.get('sell_target', 0) or 0)
            
            # 抓現價
            price = get_current_price(sid)
            
            # 算損益
            profit = 0
            profit_pct = 0
            if price and cost > 0:
                profit = (price - cost) * 1000
                profit_pct = ((price - cost) / cost) * 100
                total_profit += profit

            # --- 卡片顯示區 ---
            with st.container():
                # 1. 標題與現價
                c1, c2 = st.columns([2, 2])
                c1.subheader(f"🏷️ {sid}")
                c2.markdown(f"### 💲 {price:.1f}" if price else "💲 讀取中...")

                # 2. 數據呈現
                k1, k2, k3 = st.columns(3)
                k1.metric("持有成本", f"{cost}")
                
                # 顏色邏輯：賺錢紅色，賠錢綠色
                color_mode = "normal" if profit > 0 else "inverse"
                k2.metric("預估損益", f"{int(profit)}", f"{profit_pct:.1f}%", delta_color=color_mode)
                
                k3.caption(f"監控買點: {buy_target if buy_target else '無'}")
                k3.caption(f"監控賣點: {sell_target if sell_target else '無'}")

                # 3. 👇 重點：編輯/刪除功能 (用 Expander 收起來)
                with st.expander(f"🛠️ 修改/刪除 {sid}"):
                    with st.form(key=f"edit_{i}_{sid}"):
                        st.write("修改設定：")
                        col_e1, col_e2, col_e3 = st.columns(3)
                        new_cost = col_e1.number_input("成本價", value=cost, step=0.1, key=f"c_{i}")
                        new_buy = col_e2.number_input("想買價", value=buy_target, step=0.1, key=f"b_{i}")
                        new_sell = col_e3.number_input("想賣價", value=sell_target, step=0.1, key=f"s_{i}")
                        
                        col_btn1, col_btn2 = st.columns([1, 1])
                        
                        # 修改按鈕
                        if col_btn1.form_submit_button("💾 儲存修改"):
                            item['cost_price'] = new_cost
                            item['buy_target'] = new_buy if new_buy > 0 else None
                            item['sell_target'] = new_sell if new_sell > 0 else None
                            
                            save_data(current_stocks, sha)
                            st.toast(f"✅ {sid} 資料已更新！")
                            time.sleep(1)
                            st.rerun()

                        # 刪除按鈕 (紅色)
                        if col_btn2.form_submit_button("🗑️ 刪除此股", type="primary"):
                            current_stocks.pop(i) # 移除這個項目
                            save_data(current_stocks, sha)
                            st.toast(f"❌ 已刪除 {sid}")
                            time.sleep(1)
                            st.rerun()

                st.divider()

        # 總結
        st.markdown("### 🏦 帳戶總損益")
        if total_profit > 0:
            st.success(f"💰 目前共賺：NT$ {int(total_profit):,}")
        else:
            st.error(f"💸 目前共賠：NT$ {int(total_profit):,}")

# === 分頁 2: 純新增 ===
with tab2:
    st.subheader("➕ 加入新股票")
    with st.form("add_stock_form"):
        c1, c2 = st.columns(2)
        new_id = c1.text_input("股票代號", placeholder="例如 2330")
        new_cost = c2.number_input("成本價 (沒買填0)", min_value=0.0, step=0.1)
        
        c3, c4 = st.columns(2)
        new_buy = c3.number_input("想買價 (選填)", min_value=0.0, step=0.1)
        new_sell = c4.number_input("想賣價 (選填)", min_value=0.0, step=0.1)

        if st.form_submit_button("送出新增"):
            if new_id:
                # 檢查是否已經存在
                exists = any(s['stock_id'] == new_id for s in current_stocks)
                if exists:
                    st.warning("這支股票已經在清單裡囉！請去隔壁分頁修改。")
                else:
                    new_data = {
                        "stock_id": new_id,
                        "cost_price": new_cost,
                        "buy_target": new_buy if new_buy > 0 else None,
                        "sell_target": new_sell if new_sell > 0 else None,
                        "last_notify": {}
                    }
                    current_stocks.append(new_data)
                    save_data(current_stocks, sha)
                    st.success(f"成功加入 {new_id}！")
                    time.sleep(1)
                    st.rerun()
            else:
                st.error("請輸入股票代號")

