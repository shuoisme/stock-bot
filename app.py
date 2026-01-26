import streamlit as st
import pandas as pd
import yfinance as yf
import mplfinance as mpf
import json
import os
from github import Github, Auth
import time

# --- 1. 設定區 ---
# ⚠️ 請再次確認這裡填對！格式: "你的帳號/專案名稱"
GITHUB_REPO_NAME = "shuoisme/stock-bot" 
DATA_FILE_PATH = "stocks.json"

st.set_page_config(page_title="我的股市戰情室", layout="wide", page_icon="💰")

# --- 2. 雲端連線區 ---
@st.cache_resource(ttl=600)
def get_github_connection():
    token = os.environ.get("GH_TOKEN")
    if not token: return None
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
        df = pd.DataFrame(data)
        if 'cost_price' not in df.columns:
            df['cost_price'] = 0.0
        return df
    else:
        return pd.DataFrame(columns=['stock_id', 'buy_target', 'sell_target', 'cost_price'])

def save_watchlist(df):
    repo, contents = get_github_content(GITHUB_REPO_NAME, DATA_FILE_PATH)
    if not repo:
        st.error("GitHub 連線失敗")
        st.stop()
        
    df = df.astype({'stock_id': str})
    json_str = df.to_json(orient='records', indent=2)
    
    if contents:
        repo.update_file(contents.path, "Update data", json_str, contents.sha)
    else:
        repo.create_file(DATA_FILE_PATH, "Init data", json_str)
    
    st.toast("✅ 資料已更新！", icon="💾")
    st.cache_data.clear()
    time.sleep(1)
    st.rerun()

@st.cache_data(ttl=300)
def fetch_stock_data(symbol):
    try:
        stock = yf.Ticker(symbol)
        time.sleep(0.1)
        return stock.info, stock.history(period="1mo"), stock.major_holders, stock.institutional_holders
    except:
        return None, None, None, None

# --- 3. 介面邏輯 ---
st.title("💰 我的資產戰情室")

try:
    df_stocks = load_watchlist()
except:
    df_stocks = pd.DataFrame(columns=['stock_id', 'buy_target', 'sell_target', 'cost_price'])

with st.sidebar:
    st.header("⚙️ 庫存管理")
    
    if not df_stocks.empty:
        stock_list = df_stocks['stock_id'].tolist()
        selected_stock_id = st.selectbox("選擇要查看/編輯的股票：", stock_list)
    else:
        selected_stock_id = None
        st.info("目前沒有庫存，請新增股票。")

    st.divider()
    
    with st.expander("➕ 新增 / 編輯持股"):
        edit_id = st.text_input("股票代號", value=selected_stock_id if selected_stock_id else "")
        
        curr_cost = 0.0
        curr_buy = 0.0
        curr_sell = 0.0
        
        if edit_id and not df_stocks.empty and edit_id in df_stocks['stock_id'].values:
            row = df_stocks[df_stocks['stock_id'] == edit_id].iloc[0]
            curr_cost = float(row.get('cost_price', 0))
            curr_buy = float(row.get('buy_target', 0) or 0)
            curr_sell = float(row.get('sell_target', 0) or 0)

        new_cost = st.number_input("原始買進成本 (Cost)", value=curr_cost, min_value=0.0)
        c1, c2 = st.columns(2)
        new_buy = c1.number_input("預期加碼價 (Buy)", value=curr_buy, min_value=0.0)
        new_sell = c2.number_input("預期獲利價 (Sell)", value=curr_sell, min_value=0.0)
        
        if st.button("💾 儲存 / 新增"):
            if edit_id:
                new_data = {
                    'stock_id': edit_id,
                    'cost_price': new_cost,
                    'buy_target': new_buy if new_buy > 0 else None,
                    'sell_target': new_sell if new_sell > 0 else None
                }
                
                if edit_id in df_stocks['stock_id'].values:
                    df_stocks = df_stocks[df_stocks['stock_id'] != edit_id]
                
                df_new = pd.concat([df_stocks, pd.DataFrame([new_data])], ignore_index=True)
                save_watchlist(df_new)
            else:
                st.warning("請輸入代號")

    if not df_stocks.empty:
        with st.expander("🗑️ 刪除股票"):
            if st.button(f"刪除 {selected_stock_id}"):
                save_watchlist(df_stocks[df_stocks['stock_id'] != selected_stock_id])

if selected_stock_id:
    yf_symbol = selected_stock_id
    if selected_stock_id.isdigit(): yf_symbol = f"{selected_stock_id}.TW"

    info, hist, major, inst = fetch_stock_data(yf_symbol)
    
    if info:
        price = info.get('currentPrice') or info.get('regularMarketPrice')
        prev_close = info.get('previousClose')
        
        user_row = df_stocks[df_stocks['stock_id'] == selected_stock_id].iloc[0]
        cost = float(user_row.get('cost_price', 0))
        
        change = price - prev_close
        pct_change = (change / prev_close) * 100
        
        profit = 0
        if cost > 0:
            profit = (price - cost)
            
        st.subheader(f"{info.get('shortName', yf_symbol)} ({selected_stock_id})")
        
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("現價", f"{price}", f"{pct_change:.2f}%")
        m2.metric("原始成本", f"{cost}", delta=f"{profit:.1f} (損益)" if cost>0 else "未設定", delta_color="normal")
        m3.metric("預期獲利價", user_row['sell_target'] or "-")
        m4.metric("預期加碼價", user_row['buy_target'] or "-")

        tab1, tab2, tab3 = st.tabs(["📊 K線與走勢", "📑 基本面與法人", "📋 詳細報價表"])

        with tab1:
            if not hist.empty:
                fig, ax = mpf.plot(
                    hist, 
                    type='candle', 
                    style='yahoo', 
                    volume=True, 
                    mav=(5, 10, 20),
                    title=f"{selected_stock_id} Daily K",
                    returnfig=True
                )
                st.pyplot(fig)
            else:
                st.warning("無歷史資料")

        with tab2:
            c_a, c_b = st.columns(2)
            with c_a:
                st.info("📊 **基本面數據**")
                # 取得資料並安全處理
                pe = info.get('trailingPE', 'N/A')
                eps = info.get('trailingEps', 'N/A')
                dy = info.get('dividendYield')
                dy_str = f"{dy*100:.2f}%" if dy else "N/A"
                
                fund_data = {
                    "項目": ["本益比 (PE)", "每股盈餘 (EPS)", "股息殖利率", "52週最高", "52週最低"],
                    "數值": [
                        str(pe), # 強制轉文字，避免 Crash
                        str(eps), 
                        str(dy_str), 
                        str(info.get('fiftyTwoWeekHigh', 'N/A')),
                        str(info.get('fiftyTwoWeekLow', 'N/A'))
                    ]
                }
                # 這裡強制轉型成字串 (astype(str)) 是關鍵
                st.dataframe(pd.DataFrame(fund_data).astype(str), use_container_width=True)

            with c_b:
                st.info("🏢 **機構與大股東持股**")
                if major is not None and not major.empty:
                    st.dataframe(major.astype(str), use_container_width=True)
                elif inst is not None and not inst.empty:
                    st.dataframe(inst.astype(str), use_container_width=True)
                else:
                    st.write("查無公開機構持股資料")

        with tab3:
            st.caption("近 5 日詳細交易數據")
            if not hist.empty:
                display_df = hist[['Open', 'High', 'Low', 'Close', 'Volume']].sort_index(ascending=False).head(5)
                
                st.dataframe(
                    display_df,
                    use_container_width=True,
                    column_config={
                        "Open": st.column_config.NumberColumn("開盤", format="$%.2f"),
                        "High": st.column_config.NumberColumn("最高", format="$%.2f"),
                        "Low": st.column_config.NumberColumn("最低", format="$%.2f"),
                        "Close": st.column_config.NumberColumn("收盤", format="$%.2f"),
                        "Volume": st.column_config.ProgressColumn(
                            "成交量", 
                            format="%d", 
                            min_value=0, 
                            max_value=int(hist['Volume'].max())
                        ),
                    }
                )
    else:
        st.error("無法讀取資料，請稍後再試。")

else:
    st.info("👈 請從左側選單選擇一支股票，開始管理你的資產！")
