import streamlit as st
import pandas as pd
import twstock
import mplfinance as mpf
import json
import os
from github import Github
import time

# --- 1. 設定區 ---
# ⚠️ 這裡一定要改！格式: "你的帳號/專案名稱"
GITHUB_REPO_NAME = "shuoisme/stock-bot" 
DATA_FILE_PATH = "stocks.json"

st.set_page_config(page_title="股市戰情室", layout="wide", page_icon="📈")

# --- 2. GitHub 連線功能 ---
def get_github_file():
    token = os.environ.get("GH_TOKEN")
    if not token:
        st.error("❌ 錯誤：未偵測到 GH_TOKEN，請檢查 Streamlit Secrets。")
        st.stop()
    g = Github(token)
    try:
        repo = g.get_repo(GITHUB_REPO_NAME)
        contents = repo.get_contents(DATA_FILE_PATH)
        return repo, contents
    except:
        st.error(f"找不到專案或檔案！請確認 GITHUB_REPO_NAME 是否為 '{GITHUB_REPO_NAME}' 且檔案存在。")
        st.stop()

def load_watchlist():
    repo, contents = get_github_file()
    data = json.loads(contents.decoded_content.decode())
    return pd.DataFrame(data)

def save_watchlist(df):
    repo, contents = get_github_file()
    df = df.astype({'stock_id': str})
    json_str = df.to_json(orient='records', indent=2)
    repo.update_file(contents.path, "Update from App", json_str, contents.sha)
    st.toast("✅ 設定已儲存到雲端！", icon="☁️")
    time.sleep(1)
    st.rerun()

# --- 3. 畫面開始 ---
st.sidebar.title("🔍 自選股清單")
try:
    df_stocks = load_watchlist()
except:
    df_stocks = pd.DataFrame(columns=['stock_id', 'buy_target', 'sell_target'])

selected_stock_id = None
if not df_stocks.empty:
    stock_options = df_stocks['stock_id'].tolist()
    selected_stock_id = st.sidebar.radio("點擊查看個股：", stock_options)
    st.sidebar.caption(f"監控中：{len(stock_options)} 檔")

if selected_stock_id:
    # 讀取設定
    current_setting = df_stocks[df_stocks['stock_id'] == selected_stock_id].iloc[0]
    
    try:
        # 抓取資料
        stock = twstock.Stock(selected_stock_id)
        real = twstock.realtime.get(selected_stock_id)
        
        if real['success']:
            info = real['info']
            rt = real['realtime']
            price = float(rt['latest_trade_price'])
            
            # --- 看板區 ---
            st.title(f"{info['name']} ({selected_stock_id})")
            c1, c2, c3 = st.columns(3)
            c1.metric("目前股價", price)
            c2.metric("買入目標", current_setting['buy_target'] or "未設")
            c3.metric("賣出目標", current_setting['sell_target'] or "未設")

            # --- 分頁區 ---
            tab1, tab2, tab3 = st.tabs(["📊 K線圖", "📋 詳細數據", "⚙️ 設定警報"])

            with tab1:
                st.subheader("日 K 線圖 (近 31 日)")
                hist_data = stock.fetch_31()
                df_hist = pd.DataFrame(hist_data)
                df_hist['Date'] = pd.to_datetime(df_hist['date'])
                df_hist.set_index('Date', inplace=True)
                for col in ['open', 'high', 'low', 'close', 'capacity']:
                    df_hist[col] = pd.to_numeric(df_hist[col])
                
                fig, ax = mpf.plot(df_hist, type='candle', style='yahoo', volume=True, mav=(5,10), returnfig=True)
                st.pyplot(fig)

            with tab2:
                st.dataframe(df_hist.sort_index(ascending=False).head(5), use_container_width=True)

            with tab3:
                st.write("設定機器人通知你的價格：")
                with st.form("setting"):
                    nb = st.number_input("買入價 (低於通知)", value=float(current_setting['buy_target'] or 0))
                    ns = st.number_input("賣出價 (高於通知)", value=float(current_setting['sell_target'] or 0))
                    if st.form_submit_button("💾 儲存設定"):
                        df_stocks.loc[df_stocks['stock_id'] == selected_stock_id, 'buy_target'] = nb if nb>0 else None
                        df_stocks.loc[df_stocks['stock_id'] == selected_stock_id, 'sell_target'] = ns if ns>0 else None
                        save_watchlist(df_stocks)
        else:
            st.warning("盤中資料讀取失敗，請稍候。")
    except Exception as e:
        st.error(f"發生錯誤: {e}")
else:
    st.info("👈 請從左側選擇或新增股票。")

# --- 新增/刪除 ---
st.sidebar.divider()
with st.sidebar.expander("➕ 新增股票"):
    new_id = st.text_input("代號")
    if st.button("加入") and new_id:
        if new_id not in df_stocks['stock_id'].values:
            new_row = pd.DataFrame([{'stock_id': new_id, 'buy_target': None, 'sell_target': None}])
            save_watchlist(pd.concat([df_stocks, new_row], ignore_index=True))

with st.sidebar.expander("🗑️ 刪除股票"):
    if not df_stocks.empty:
        d_id = st.selectbox("移除", df_stocks['stock_id'])
        if st.button("確認移除"):
            save_watchlist(df_stocks[df_stocks['stock_id'] != d_id])