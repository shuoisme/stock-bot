import streamlit as st
import pandas as pd
import yfinance as yf
import mplfinance as mpf
import json
import os
from github import Github, Auth  # 修正警告：引入 Auth
import time

# --- 1. 設定區 ---
# ⚠️ 請再次確認這裡填對！格式: "你的帳號/專案名稱"
GITHUB_REPO_NAME = "shuoisme/stock-bot" 
DATA_FILE_PATH = "stocks.json"

st.set_page_config(page_title="股市戰情室", layout="wide", page_icon="📈")

# --- 2. 功能函數區 ---

# 加入快取：讓 GitHub 連線記住 10 分鐘，不用一直重連
@st.cache_resource(ttl=600)
def get_github_connection():
    token = os.environ.get("GH_TOKEN")
    if not token:
        return None
    # 修正警告：使用新版驗證方式
    auth = Auth.Token(token)
    return Github(auth=auth)

def get_github_content(repo_name, file_path):
    g = get_github_connection()
    if not g: return None, None
    try:
        repo = g.get_repo(repo_name)
        contents = repo.get_contents(file_path)
        return repo, contents
    except:
        return None, None

def load_watchlist():
    repo, contents = get_github_content(GITHUB_REPO_NAME, DATA_FILE_PATH)
    if contents:
        data = json.loads(contents.decoded_content.decode())
        return pd.DataFrame(data)
    else:
        return pd.DataFrame(columns=['stock_id', 'buy_target', 'sell_target'])

def save_watchlist(df):
    repo, contents = get_github_content(GITHUB_REPO_NAME, DATA_FILE_PATH)
    if not repo:
        st.error("GitHub 連線失敗，請檢查 Token 或專案名稱")
        st.stop()
        
    df = df.astype({'stock_id': str})
    json_str = df.to_json(orient='records', indent=2)
    
    if contents:
        repo.update_file(contents.path, "Update from App", json_str, contents.sha)
    else:
        repo.create_file(DATA_FILE_PATH, "Init watchlist", json_str)
    
    st.toast("✅ 設定已儲存到雲端！", icon="☁️")
    # 清除快取，確保下次讀到最新的
    st.cache_data.clear()
    time.sleep(1)
    st.rerun()

# 加入快取：股價資料記住 5 分鐘 (300秒)
# 這樣你切換分頁時，就不會重新跟 Yahoo 要資料，避免被鎖 IP
@st.cache_data(ttl=300)
def fetch_stock_data(symbol):
    try:
        stock = yf.Ticker(symbol)
        # 讓它強制休息一下，避免請求太快
        time.sleep(0.1)
        info = stock.info
        hist = stock.history(period="1mo")
        return info, hist
    except Exception as e:
        print(f"Error fetching {symbol}: {e}")
        return None, None

# --- 3. 主畫面邏輯 ---
st.sidebar.title("🔍 自選股清單")

# 讀取資料
try:
    df_stocks = load_watchlist()
except Exception as e:
    st.error(f"讀取清單失敗，請稍後再試。錯誤: {e}")
    df_stocks = pd.DataFrame(columns=['stock_id', 'buy_target', 'sell_target'])

selected_stock_id = None
if not df_stocks.empty:
    stock_options = df_stocks['stock_id'].tolist()
    selected_stock_id = st.sidebar.radio("點擊查看個股：", stock_options)
    st.sidebar.caption(f"監控中：{len(stock_options)} 檔")

if selected_stock_id:
    yf_symbol = selected_stock_id
    if selected_stock_id.isdigit(): 
        yf_symbol = f"{selected_stock_id}.TW"

    # 取得設定
    current_setting = df_stocks[df_stocks['stock_id'] == selected_stock_id].iloc[0]
    
    # 呼叫有快取功能的抓取函式
    info, hist_data = fetch_stock_data(yf_symbol)
    
    if info:
        current_price = info.get('currentPrice') or info.get('regularMarketPrice')
        previous_close = info.get('previousClose') or info.get('regularMarketPreviousClose')
        
        if current_price:
            # 顯示看板
            st.title(f"{info.get('shortName', yf_symbol)} ({selected_stock_id})")
            
            change = current_price - previous_close
            pct_change = (change / previous_close) * 100
            
            c1, c2, c3 = st.columns(3)
            c1.metric("目前股價", f"{current_price}", f"{pct_change:.2f}%")
            c2.metric("買入目標", current_setting['buy_target'] or "未設")
            c3.metric("賣出目標", current_setting['sell_target'] or "未設")

            tab1, tab2, tab3 = st.tabs(["📊 K線圖", "📋 詳細數據", "⚙️ 設定警報"])

            with tab1:
                st.subheader("日 K 線圖 (近 1 個月)")
                if not hist_data.empty:
                    fig, ax = mpf.plot(hist_data, type='candle', style='yahoo', volume=True, mav=(5,10), returnfig=True)
                    st.pyplot(fig)
                else:
                    st.warning("暫無歷史資料")

            with tab2:
                if not hist_data.empty:
                    display_df = hist_data[['Open', 'High', 'Low', 'Close', 'Volume']].sort_index(ascending=False).head(5)
                    st.dataframe(display_df, use_container_width=True)

            with tab3:
                st.write("設定機器人通知你的價格：")
                with st.form("setting"):
                    nb = st.number_input("買入價", value=float(current_setting['buy_target'] or 0))
                    ns = st.number_input("賣出價", value=float(current_setting['sell_target'] or 0))
                    if st.form_submit_button("💾 儲存設定"):
                        df_stocks.loc[df_stocks['stock_id'] == selected_stock_id, 'buy_target'] = nb if nb>0 else None
                        df_stocks.loc[df_stocks['stock_id'] == selected_stock_id, 'sell_target'] = ns if ns>0 else None
                        save_watchlist(df_stocks)
        else:
            st.warning("無法取得即時價格，可能盤中資料延遲或被限制，請稍候再試。")
    else:
        st.error("⚠️ 抓取資料過於頻繁，已被暫時限制 (Rate Limited)。\n\n請等待約 1~5 分鐘後再重新整理網頁。")

else:
    st.info("👈 請從左側選擇或新增股票。")

# 新增/刪除功能
st.sidebar.divider()
with st.sidebar.expander("➕ 新增股票"):
    new_id = st.text_input("輸入代號")
    if st.button("加入") and new_id:
        if new_id not in df_stocks['stock_id'].values:
            new_row = pd.DataFrame([{'stock_id': new_id, 'buy_target': None, 'sell_target': None}])
            df_new = pd.concat([df_stocks, new_row], ignore_index=True)
            save_watchlist(df_new)
        else:
            st.warning("已在清單中")

with st.sidebar.expander("🗑️ 刪除股票"):
    if not df_stocks.empty:
        d_id = st.selectbox("移除", df_stocks['stock_id'])
        if st.button("確認移除"):
            save_watchlist(df_stocks[df_stocks['stock_id'] != d_id])
