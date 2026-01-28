import streamlit as st
import json
import pandas as pd
import yfinance as yf
from github import Github

# --- 設定頁面資訊 (手機上看起來像 App) ---
st.set_page_config(page_title="家族股市帳本", page_icon="💰", layout="centered")

# --- 1. 連接 GitHub ---
# 這是為了讀取和儲存 stocks.json
def get_repo():
    token = st.secrets["GH_TOKEN"]
    g = Github(token)
    return g.get_repo("shuoisme/stock-bot") # ⚠️ 記得改成你的 "帳號/專案名"

def load_data():
    try:
        repo = get_repo()
        content = repo.get_contents("stocks.json")
        return json.loads(content.decoded_content.decode()), content.sha
    except:
        return [], None

def save_data(data, sha):
    repo = get_repo()
    content = repo.get_contents("stocks.json")
    repo.update_file("stocks.json", "Update from App", json.dumps(data, indent=2, ensure_ascii=False), content.sha)

# --- 2. 抓取即時股價 (為了顯示給家人看) ---
def get_current_price(stock_id):
    try:
        # 自動嘗試 .TW 或 .TWO
        sid = stock_id
        if not sid.endswith('.TW') and not sid.endswith('.TWO'):
            sid = f"{stock_id}.TW"
        
        stock = yf.Ticker(sid)
        price = stock.fast_info.last_price
        # 嘗試抓 .TWO 如果 .TW 失敗 (雖不精確但堪用)
        if price is None: 
            stock = yf.Ticker(f"{stock_id}.TWO")
            price = stock.fast_info.last_price
            
        return price
    except:
        return 0

# --- 3. 介面設計開始 ---

st.title("💰 家族股市帳本")
st.caption("自動監控中，價格到了會通知 LINE")

# 建立兩個分頁
tab1, tab2 = st.tabs(["📊 目前持股", "⚙️ 新增/刪除"])

# 載入目前的清單
current_stocks, sha = load_data()

# === 分頁 1: 看盤介面 (大字體、顏色鮮明) ===
with tab1:
    if not current_stocks:
        st.info("目前沒有監控中的股票，請去隔壁新增 👉")
    else:
        # 總損益計算
        total_profit = 0
        
        for item in current_stocks:
            # 準備資料
            sid = item['stock_id']
            cost = float(item.get('cost_price', 0))
            price = get_current_price(sid)
            
            # 計算損益
            profit = 0
            profit_pct = 0
            if price and cost > 0:
                profit = (price - cost) * 1000 # 一張 1000 股
                profit_pct = ((price - cost) / cost) * 100
                total_profit += profit

            # 卡片式顯示
            with st.container():
                # 標題列：股票代號
                c1, c2 = st.columns([2, 2])
                c1.subheader(f"🏷️ {sid}")
                c2.write(f"現價: **{price:.1f}**")
                
                # 數據列
                c3, c4, c5 = st.columns(3)
                c3.metric("成本", f"{cost}")
                
                # 台股邏輯：賺錢顯示紅色(normal)，賠錢顯示綠色(inverse)
                color_mode = "normal" if profit > 0 else "inverse"
                c4.metric("預估損益", f"{int(profit)}", f"{profit_pct:.1f}%", delta_color=color_mode)
                
                # 設定列
                buy = item.get('buy_target', '無')
                sell = item.get('sell_target', '無')
                c5.caption(f"🎯 買:{buy} / 賣:{sell}")
                
                st.divider() # 分隔線
        
        # 顯示總資產損益
        st.markdown("### 🏦 總帳戶損益")
        if total_profit > 0:
            st.success(f"目前共賺：NT$ {int(total_profit):,}")
        else:
            st.error(f"目前共賠：NT$ {int(total_profit):,}")

# === 分頁 2: 管理介面 (簡單表單) ===
with tab2:
    st.subheader("➕ 新增監控股票")
    
    with st.form("add_stock_form"):
        col1, col2 = st.columns(2)
        new_id = col1.text_input("股票代號 (例如 2330)", placeholder="輸入代號")
        new_cost = col2.number_input("你的成本價 (沒買填 0)", min_value=0.0, step=0.1)
        
        col3, col4 = st.columns(2)
        new_buy = col3.number_input("想買的價格 (選填)", min_value=0.0, step=0.1)
        new_sell = col4.number_input("想賣的價格 (選填)", min_value=0.0, step=0.1)
        
        submit = st.form_submit_button("💾 儲存加入")
        
        if submit and new_id:
            # 建立新資料物件
            new_data = {
                "stock_id": new_id,
                "cost_price": new_cost,
                "buy_target": new_buy if new_buy > 0 else None,
                "sell_target": new_sell if new_sell > 0 else None,
                "last_notify": {} # 初始化通知紀錄
            }
            # 加入清單並存檔
            current_stocks.append(new_data)
            save_data(current_stocks, sha)
            st.success(f"成功加入 {new_id}！請重新整理頁面。")
            st.rerun()

    st.markdown("---")
    st.subheader("🗑️ 刪除股票")
    
    # 刪除選單
    if current_stocks:
        # 製作一個選單列表: "2330 (成本: 500)"
        options = [f"{s['stock_id']} (成本: {s.get('cost_price', 0)})" for s in current_stocks]
        selected_option = st.selectbox("選擇要刪除的股票", options)
        
        if st.button("確認刪除 ❌"):
            # 找出選了第幾個，把它刪掉
            idx = options.index(selected_option)
            del current_stocks[idx]
            save_data(current_stocks, sha)
            st.warning("已刪除！")
            time.sleep(1)
            st.rerun()
