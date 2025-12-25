import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import time
from datetime import datetime

# Настройка страницы в стиле Dark Mode
st.set_page_config(page_title="PolyMaker Pro Terminal", layout="wide", initial_sidebar_state="expanded")

# Кастомный CSS для соответствия скриншотам (цвета, отступы, карточки)
st.markdown("""
    <style>
    .stApp { background-color: #0e1117; color: #e0e0e0; }
    .stButton>button { width: 100%; border-radius: 5px; height: 3em; background-color: #2e3440; color: white; border: none; }
    .stButton>button:hover { background-color: #3b4252; border: 1px solid #4c566a; }
    div[data-testid="stMetricValue"] { color: #00ffcc; font-size: 1.8rem; }
    .bot-card { background-color: #1b212c; padding: 20px; border-radius: 10px; border-left: 5px solid #ffa500; margin-bottom: 10px; }
    .log-container { background-color: #000000; color: #00ff00; font-family: 'Courier New', monospace; padding: 10px; border-radius: 5px; font-size: 0.8rem; }
    </style>
    """, unsafe_allow_html=True)

# --- SIDEBAR: BOT SETTINGS ---
with st.sidebar:
    st.header("⚙️ Bot Settings")
    st.info("Market: Russia x Ukraine ceasefire 2025?")
    
    mode = st.radio("MODE", ["Market Making", "Flip Trading"], horizontal=True)
    side = st.radio("SIDE", ["BUY", "SELL", "BOTH"], horizontal=True)
    outcome = st.radio("OUTCOME", ["YES", "NO"], horizontal=True)
    
    amount = st.number_input("AMOUNT (USDT)", min_value=1.0, value=5.0, step=1.0)
    position = st.selectbox("POSITION", ["1st", "2nd", "3rd", "Top of Book"])
    
    check_interval = st.select_slider("CHECK INTERVAL", options=["5 sec", "30 sec", "1 min", "5 min", "30 min"])
    
    use_pct = st.checkbox("Use % of balance")
    
    if st.button("🚀 Start Bot", type="primary"):
        st.toast("Бот запускается...")

    st.markdown("---")
    st.subheader("📊 Orderbook")
    # Эмуляция стакана со скриншота
    ob_data = {
        "Bids": ["6.1¢", "6.1¢", "6.0¢", "5.9¢"],
        "Asks": ["6.2¢", "6.2¢", "6.5¢", "7.0¢"],
        "Size": [32, 407, 362, 1285]
    }
    st.table(pd.DataFrame(ob_data))

# --- MAIN CONTENT ---
col_main, col_logs = st.columns([2, 1])

with col_main:
    st.subheader("🤖 Active Trading Bots")
    
    # Карточка бота (как на фото)
    st.markdown(f"""
    <div class="bot-card">
        <div style="display: flex; justify-content: space-between;">
            <b>Russia x Ukraine ceasefire in 2025?</b>
            <span style="color: #ff4b4b; cursor: pointer;">Stop</span>
        </div>
        <div style="color: #00ffcc; margin: 10px 0;">YES | Buy: 5.20¢ | Sell: 6.90¢ | $2.70</div>
        <div style="font-size: 0.8rem; color: #888;">⏳ Waiting: SELL | Cycles: 0 | PnL: <span style="color: #00ffcc;">+$0.0000</span></div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")
    
    # Секция открытых ордеров и позиций
    tab1, tab2 = st.tabs(["📋 Open Orders", "💼 Positions"])
    
    with tab1:
        orders = [
            {"Type": "SELL", "Price": "6.90¢", "Size": "$39.00", "Market": "Russia x Ukraine"},
            {"Type": "SELL", "Price": "5.40¢", "Size": "$92.00", "Market": "CZ return to Binance"}
        ]
        for order in orders:
            c1, c2, c3, c4 = st.columns([1, 1, 1, 2])
            c1.error(order["Type"])
            c2.write(order["Price"])
            c3.write(order["Size"])
            if c4.button("Cancel", key=order["Market"]): pass

    with tab2:
        st.write("Активные позиции...")
        st.dataframe(pd.DataFrame([{"Asset": "YES", "Value": "$5.13", "PnL": "+0.00%"}]))

with col_logs:
    st.subheader("🗒 Bot Logs")
    st.markdown(f"""
    <div class="log-container">
        [{datetime.now().strftime('%H:%M:%S')}] 💤 [Russia x Ukraine] Следующая проверка через 60 сек...<br>
        [{datetime.now().strftime('%H:%M:%S')}] 👨‍💻 [Russia x Ukraine] Ордер SELL @ 6.9¢ активен. Ждём...<br>
        [{datetime.now().strftime('%H:%M:%S')}] 🔍 Проверка #7: ждём SELL | Bid: 5.3¢ Ask: 5.4¢<br>
        <hr style="border-color: #333;">
        [{datetime.now().strftime('%H:%M:%S')}] 🚀 Бот запущен. Ожидание ликвидности...
    </div>
    """, unsafe_allow_html=True)
    if st.button("Clear Logs"): pass

# Авто-обновление
time.sleep(2)
st.rerun()