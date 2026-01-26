import streamlit as st
import pandas as pd
import yfinance as yf
import mplfinance as mpf
import json
import os
from github import Github
import time

# --- 1. 設定區 ---
# ⚠️ 請務必確認這裡填寫正確！格式: "你的帳號/專案名稱"
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
        return None, None

def load_watchlist():
    repo, contents = get_github_file()
    if contents:
        data = json.loads(contents.decoded_content.decode())
        return pd.DataFrame(data)
    else:
        return pd.DataFrame(columns=['stock_id', 'buy_target', 'sell_target'])

def save_watchlist(df):
    repo, contents = get_github_file()
    df = df.astype({'stock_id': str})
    json_str = df.to_json(orient='records', indent=2)
    
    if contents:
        repo.update_file(contents.path, "Update from App", json_str, contents.sha)
    else:
        # 如果檔案不存在，建立新檔案
        if repo:
            repo.create_file(DATA_FILE_PATH, "Init watchlist", json_str)
        else:
            st.error("無法存取 GitHub 專案，請檢查名稱設定。")
            st.stop()
    
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
    # 處理台股代號 (Yahoo Finance 需要 .TW 後綴)
    yf_symbol = selected_stock_id
    if selected_stock_id.isdigit(): # 如果是純數字(台股)，加上 .TW
        yf_symbol = f"{selected_stock_id}.TW"

    # 讀取設定
    current_setting = df_stocks[df_stocks['stock_id'] == selected_stock_id].iloc[0]
    
    try:
        # 改用 yfinance 抓資料
        stock = yf.Ticker(yf_symbol)
        # 取得即時資訊 (有些股票可能在 info，有些在 fast_info)
        info = stock.info
        
        # 嘗試取得價格
        current_price = info.get('currentPrice') or info.get('regularMarketPrice')
        previous_close = info.get('previousClose') or info.get('regularMarketPreviousClose')
        
        if current_price:
            # --- 看板區 ---
            st.title(f"{info.get('shortName', yf_symbol)} ({selected_stock_id})")
            
            # 計算漲跌幅
            change = current_price - previous_close
            pct_change = (change / previous_close) * 100
            
            c1, c2, c3 = st.columns(3)
            c1.metric("目前股價", f"{current_price}", f"{pct_change:.2f}%")
            c2.metric("買入目標", current_setting['buy_target'] or "未設")
            c3.metric("賣出目標", current_setting['sell_target'] or "未設")

            # --- 分頁區 ---
            tab1, tab2, tab3 = st.tabs(["📊 K線圖", "📋 詳細數據", "⚙️ 設定警報"])

            with tab1:
                st.subheader("日 K 線圖 (近 1 個月)")
                # 抓取歷史資料
                hist_data = stock.history(period="1mo")
                
                if not hist_data.empty:
                    # 畫圖
                    fig, ax = mpf.plot(
                        hist_data, 
                        type='candle', 
                        style='yahoo', 
                        volume=True, 
                        mav=(5,10), 
                        returnfig=True
                    )
                    st.pyplot(fig)
                else:
                    st.warning("暫無歷史資料")

            with tab2:
                if not hist_data.empty:
                    # 整理表格顯示 (反序)
                    display_df = hist_data[['Open', 'High', 'Low', 'Close', 'Volume']].sort_index(ascending=False).head(5)
                    st.dataframe(display_df, use_container_width=True)

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
            st.warning(f"無法取得 {yf_symbol} 的即時價格，請確認代號是否正確。")
            
    except Exception as e:
        st.error(f"發生錯誤: {e}")
else:
    st.info("👈 請從左側選擇或新增股票 (台股請輸入代號，如 2330)。")

# --- 新增/刪除 ---
st.sidebar.divider()
with st.sidebar.expander("➕ 新增股票"):
    new_id = st.text_input("輸入代號 (如 2330)")
    if st.button("加入") and new_id:
        # 檢查是否重複
        if new_id not in df_stocks['stock_id'].values:
            new_row = pd.DataFrame([{'stock_id': new_id, 'buy_target': None, 'sell_target': None}])
            # 使用 pd.concat 替代 append (新版 pandas 語法)
            df_new = pd.concat([df_stocks, new_row], ignore_index=True)
            save_watchlist(df_new)
        else:
            st.warning("這支股票已經在清單裡囉！")

with st.sidebar.expander("🗑️ 刪除股票"):
    if not df_stocks.empty:
        d_id = st.selectbox("移除", df_stocks['stock_id'])
        if st.button("確認移除"):
            save_watchlist(df_stocks[df_stocks['stock_id'] != d_id])
