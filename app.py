import streamlit as st
import json
import time
import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import yfinance as yf
from github import Github

# --- 設定頁面 ---
st.set_page_config(page_title="家族股市戰情室", page_icon="💰", layout="wide")

# --- 設定區 ---
REPO_NAME = "shuoisme/stock-bot"  # ⚠️ 確認你的 GitHub 帳號/專案名稱
WORKFLOW_FILE = "main.yml"
BRANCH_NAME = "main"

# --- 1. 連接 GitHub ---
def get_repo():
    try:
        token = st.secrets["GH_TOKEN"]
        g = Github(token)
        return g.get_repo(REPO_NAME)
    except Exception as e:
        st.error(f"GitHub 連線失敗: {e}")
        return None

def load_data():
    try:
        repo = get_repo()
        if not repo: return [], None
        content = repo.get_contents("stocks.json")
        decoded = content.decoded_content.decode()
        if not decoded: return [], content.sha
        return json.loads(decoded), content.sha
    except:
        return [], None

def save_data(data, sha):
    repo = get_repo()
    if not repo: return
    content = repo.get_contents("stocks.json")
    repo.update_file("stocks.json", "Update from App", json.dumps(data, indent=2, ensure_ascii=False), content.sha)

# --- 🚀 呼叫機器人 ---
def trigger_bot():
    token = st.secrets["GH_TOKEN"]
    url = f"https://api.github.com/repos/{REPO_NAME}/actions/workflows/{WORKFLOW_FILE}/dispatches"
    
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    data = {"ref": BRANCH_NAME}
    
    try:
        response = requests.post(url, json=data, headers=headers)
        if response.status_code == 204:
            return True, "🚀 指令已發送！機器人約 30 秒後會回報。"
        else:
            return False, f"❌ 發送失敗 (代碼 {response.status_code})：{response.text}"
    except Exception as e:
        return False, f"❌ 連線錯誤：{str(e)}"

# --- 2. 抓價與畫圖功能 ---
def get_stock_history(ticker, period="1mo"):
    """抓取歷史股價畫圖用"""
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period=period)
        return hist
    except:
        return pd.DataFrame()

def get_current_price(stock_id):
    """抓取最新價格"""
    # 嘗試各種後綴
    suffixes = [stock_id, f"{stock_id}.TW", f"{stock_id}.TWO"]
    # 如果原本就有後綴，就不用亂試
    if stock_id.endswith('.TW') or stock_id.endswith('.TWO'):
        suffixes = [stock_id]
        
    for sym in suffixes:
        try:
            stock = yf.Ticker(sym)
            price = stock.fast_info.last_price
            if price and price > 0: return price, sym
        except:
            continue
    return 0, stock_id

# --- 3. 介面設計 ---
st.title("💰 家族股市戰情室")

# 👇 側邊欄
with st.sidebar:
    st.header("🎮 機器人遙控器")
    if st.button("📣 立即 LINE 回報", type="primary", use_container_width=True):
        with st.spinner("呼叫機器人中..."):
            success, msg = trigger_bot()
            if success: st.success(msg)
            else: st.error(msg)
    st.divider()
    st.info("💡 提示：走勢圖需要下載數據，若載入較慢請見諒。")

# 🔥 新增 Tab 3: 攤平試算機
tab1, tab2, tab3 = st.tabs(["📊 資產看板", "➕ 新增股票", "🧮 攤平試算機"])

current_stocks, sha = load_data()

# === 分頁 1: 資產看板 (含圓餅圖 & K線圖) ===
with tab1:
    if not current_stocks:
        st.info("目前沒有股票，請去隔壁新增 👉")
    else:
        total_market_value = 0 
        total_invest_cost = 0
        pie_data_list = [] # 用來存圓餅圖資料
        
        # 先計算總資產與準備資料
        # 為了效率，這裡先做一次迴圈處理數據
        display_data = []
        
        for i, item in enumerate(current_stocks):
            sid = item['stock_id']
            name = item.get('name', sid)
            cost = float(item.get('cost_price') or 0)
            qty = float(item.get('qty') or 1.0)
            buy_target = float(item.get('buy_target') or 0)
            sell_target = float(item.get('sell_target') or 0)
            stop_loss = float(item.get('stop_loss') or 0)
            
            # 抓價
            price, valid_symbol = get_current_price(sid)
            
            invest_cost = cost * qty * 1000
            market_value = 0
            profit = 0
            profit_pct = 0
            
            if price > 0:
                market_value = price * qty * 1000
                if cost > 0:
                    profit = market_value - invest_cost
                    profit_pct = (profit / invest_cost) * 100
                
                total_market_value += market_value
                total_invest_cost += invest_cost
                
                # 加入圓餅圖數據
                pie_data_list.append({"股票": name, "市值": market_value})
            
            display_data.append({
                "i": i, "item": item, "price": price, "symbol": valid_symbol,
                "cost": cost, "qty": qty, "profit": profit, "profit_pct": profit_pct,
                "invest_cost": invest_cost, "market_value": market_value,
                "buy": buy_target, "sell": sell_target, "stop": stop_loss
            })

        # --- 📊 1. 資產分布圓餅圖 ---
        if total_market_value > 0:
            st.markdown("### 🍰 資產配置圖")
            df_pie = pd.DataFrame(pie_data_list)
            fig_pie = px.pie(df_pie, values='市值', names='股票', hole=0.4, 
                             color_discrete_sequence=px.colors.sequential.RdBu)
            fig_pie.update_traces(textposition='inside', textinfo='percent+label')
            st.plotly_chart(fig_pie, use_container_width=True)
            st.divider()

        # --- 2. 總資產數據 ---
        st.markdown("### 🏆 總資產總覽")
        f1, f2, f3 = st.columns(3)
        f1.metric("總投入本金", f"${int(total_invest_cost):,}")
        f2.metric("目前總市值", f"${int(total_market_value):,}")
        final_color = "normal" if (total_market_value - total_invest_cost) > 0 else "inverse"
        f3.metric("總損益", f"${int(total_market_value - total_invest_cost):,}", delta_color=final_color)
        st.divider()

        # --- 3. 個股詳細卡片 ---
        st.markdown("### 📝 持股明細")
        for d in display_data:
            price = d['price']
            item = d['item']
            name = item.get('name')
            sid = item.get('stock_id')
            
            with st.container(border=True):
                clean_id = sid.replace(".TW", "").replace(".TWO", "")
                
                top_c1, top_c2 = st.columns([1, 4])
                with top_c1:
                    st.markdown(f"### {name}")
                    st.caption(f"代號: {clean_id}")
                with top_c2:
                    if price > 0:
                        color = "red" if price > d['cost'] else "green"
                        st.markdown(f"#### :test_tube: 現價: **{price:.2f}**")
                    else:
                        st.warning("⚠️ 無法讀取股價")

                m1, m2, m3, m4, m5 = st.columns(5)
                m1.metric("📦 張數", f"{d['qty']} 張")
                m2.metric("💵 成本", f"{d['cost']}")
                m3.metric("💰 本金", f"${int(d['invest_cost']/1000)}k") 
                m4.metric("🏦 現值", f"${int(d['market_value']/1000)}k")
                
                color_mode = "normal" if d['profit'] > 0 else "inverse"
                m5.metric("📉 損益", f"${int(d['profit']):,}", f"{d['profit_pct']:.1f}%", delta_color=color_mode)

                # --- ⚙️ 設定與走勢圖區域 ---
                with st.expander(f"⚙️ 設定 & 走勢圖 - {name}"):
                    
                    # 🔥 [新增] K線圖 / 走勢圖
                    st.markdown("##### 📈 最近 1 個月走勢")
                    if d['symbol']:
                        try:
                            hist_data = get_stock_history(d['symbol'])
                            if not hist_data.empty:
                                # 畫 K 線圖
                                fig_k = go.Figure(data=[go.Candlestick(x=hist_data.index,
                                                open=hist_data['Open'],
                                                high=hist_data['High'],
                                                low=hist_data['Low'],
                                                close=hist_data['Close'])])
                                fig_k.update_layout(xaxis_rangeslider_visible=False, margin=dict(l=0, r=0, t=0, b=0), height=300)
                                st.plotly_chart(fig_k, use_container_width=True)
                            else:
                                st.write("無歷史數據")
                        except:
                            st.write("圖表載入失敗")

                    st.divider()
                    st.markdown("##### ⚙️ 參數設定")
                    with st.form(key=f"edit_{d['i']}_{sid}"):
                        new_name = st.text_input("股票名稱", value=name)
                        r1_c1, r1_c2 = st.columns(2)
                        new_qty = r1_c1.number_input("張數", value=d['qty'], step=0.1)
                        new_cost = r1_c2.number_input("成本", value=d['cost'], step=0.1)
                        
                        r2_c1, r2_c2, r2_c3 = st.columns(3)
                        new_buy = r2_c1.number_input("監控買", value=d['buy'], step=0.1)
                        new_sell = r2_c2.number_input("監控賣", value=d['sell'], step=0.1)
                        new_stop = r2_c3.number_input("🛑 停損價", value=d['stop'], step=0.1)
                        
                        b1, b2 = st.columns([1, 1])
                        if b1.form_submit_button("💾 儲存修改"):
                            item['name'] = new_name
                            item['qty'] = new_qty
                            item['cost_price'] = new_cost
                            item['buy_target'] = new_buy if new_buy > 0 else None
                            item['sell_target'] = new_sell if new_sell > 0 else None
                            item['stop_loss'] = new_stop if new_stop > 0 else None
                            save_data(current_stocks, sha)
                            st.rerun()

                        if b2.form_submit_button("🗑️ 刪除股票", type="primary"):
                            current_stocks.pop(d['i'])
                            save_data(current_stocks, sha)
                            st.rerun()

# === 分頁 2: 新增 ===
with tab2:
    st.subheader("➕ 加入新股票")
    with st.form("add_stock_form"):
        col1, col2, col3 = st.columns([1, 1, 1])
        new_code = col1.text_input("股票代號", placeholder="例如 2330")
        new_name_input = col2.text_input("股票名稱", placeholder="例如 台積電")
        market_type = col3.selectbox("市場類別", ["上市 (.TW)", "上櫃 (.TWO)"])
        
        c4, c5 = st.columns(2)
        new_qty = c4.number_input("持有張數", min_value=0.1, value=1.0, step=0.1)
        new_cost = c5.number_input("平均成本", min_value=0.0, step=0.1)
        
        c6, c7, c8 = st.columns(3)
        new_buy = c6.number_input("想買價", min_value=0.0, step=0.1)
        new_sell = c7.number_input("想賣價", min_value=0.0, step=0.1)
        new_stop = c8.number_input("🛑 停損價", min_value=0.0, step=0.1)

        if st.form_submit_button("送出新增"):
            if new_code:
                suffix = ".TW" if "上市" in market_type else ".TWO"
                final_id = new_code if new_code.endswith(suffix) else f"{new_code}{suffix}"
                final_name = new_name_input if new_name_input else final_id

                exists = any(s['stock_id'] == final_id for s in current_stocks)
                if exists:
                    st.warning("這支股票已經在清單裡囉！")
                else:
                    new_data = {
                        "stock_id": final_id, "name": final_name, "qty": new_qty, "cost_price": new_cost,
                        "buy_target": new_buy if new_buy > 0 else None,
                        "sell_target": new_sell if new_sell > 0 else None,
                        "stop_loss": new_stop if new_stop > 0 else None,
                        "last_notify": {}
                    }
                    current_stocks.append(new_data)
                    save_data(current_stocks, sha)
                    st.success(f"成功加入 {final_name}！")
                    time.sleep(1)
                    st.rerun()
            else:
                st.error("請輸入代號")

# === 分頁 3: 攤平試算機 (New!) ===
with tab3:
    st.subheader("🧮 攤平計算機 (Average Down Calculator)")
    st.write("如果你現在加碼買進，你的平均成本會變成多少？")
    
    with st.container(border=True):
        c1, c2 = st.columns(2)
        cur_qty = c1.number_input("目前持有張數 (張)", value=1.0, step=0.1)
        cur_cost = c2.number_input("目前平均成本", value=100.0, step=0.5)
        
        st.divider()
        
        c3, c4 = st.columns(2)
        add_qty = c3.number_input("預計加碼張數 (張)", value=0.5, step=0.1)
        add_price = c4.number_input("預計加碼價格 (現價)", value=90.0, step=0.5)
        
        # 計算邏輯
        total_old_cost = cur_qty * cur_cost
        total_new_cost = add_qty * add_price
        total_qty = cur_qty + add_qty
        
        new_avg_cost = 0
        if total_qty > 0:
            new_avg_cost = (total_old_cost + total_new_cost) / total_qty
            
        diff_pct = 0
        if cur_cost > 0:
            diff_pct = ((new_avg_cost - cur_cost) / cur_cost) * 100
            
        st.markdown(f"### 🎯 試算結果")
        r1, r2, r3 = st.columns(3)
        r1.metric("加碼後總張數", f"{total_qty} 張")
        r2.metric("加碼後新成本", f"{new_avg_cost:.2f}", f"{diff_pct:.2f}% (成本降幅)", delta_color="inverse")
        r3.metric("需準備資金", f"${int(total_new_cost * 1000):,}")
        
        st.info(f"💡 小撇步：如果你的目標是把成本降到 {add_price} 元，你還需要買非常多張... 投資請量力而為！")
