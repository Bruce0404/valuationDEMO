import streamlit as st
import pandas as pd
import os
import re
import google.generativeai as genai

st.set_page_config(page_title="Porsche 估價引擎 (診斷模式)", layout="wide")

# --- CSS ---
st.markdown("""
    <style>
    .car-card { background-color: #f0f2f6; padding: 15px; border-radius: 10px; margin-bottom: 10px; text-align: center; }
    .price-tag { color: #B71C1C; font-weight: bold; font-size: 1.2em; }
    </style>
""", unsafe_allow_html=True)

st.title("🏎️ Porsche 估價引擎 (Debug Mode)")
st.info("💡 這是除錯模式，會顯示詳細的資料讀取狀態。")

# --- 輔助函式：價格清洗 ---
def try_clean_price(val):
    try:
        val_str = str(val)
        if "電洽" in val_str: return 0.0
        clean = re.sub(r'[^\d.]', '', val_str)
        return float(clean)
    except:
        return 0.0

# --- 1. 載入數據 (包含強力診斷) ---
@st.cache_data
def load_and_diagnose_data():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 定義要搜尋的路徑
    paths_to_check = [
        os.path.join(base_dir, "data"), # 優先找 data 資料夾
        base_dir # 再找根目錄
    ]
    
    # 找出所有 csv 檔案
    found_files = []
    for p in paths_to_check:
        if os.path.exists(p):
            files = [f for f in os.listdir(p) if f.endswith(".csv")]
            for f in files:
                found_files.append(os.path.join(p, f))
    
    if not found_files:
        return None, "沒有找到任何 CSV 檔案！請確認檔案是否在 data 資料夾中。"
    
    # 嘗試讀取第一個看起來像數據的檔案
    # 優先找包含 'visual' 或 'final' 的檔案
    target_file = found_files[0]
    for f in found_files:
        if "visual" in f or "final" in f:
            target_file = f
            break
            
    try:
        df = pd.read_csv(target_file)
        return df, target_file
    except Exception as e:
        return None, f"讀取檔案失敗: {e}"

# 執行載入
df_market, status_msg = load_and_diagnose_data()

# --- 2. 數據健檢 (Data Health Check) ---
with st.expander("🕵️‍♂️ 數據健檢報告 (點擊展開)", expanded=True):
    if df_market is None:
        st.error(f"❌ 嚴重錯誤：{status_msg}")
        st.stop()
    else:
        st.success(f"✅ 成功讀取檔案：{status_msg}")
        st.write(f"總筆數：{len(df_market)}")
        st.write("目前欄位：", df_market.columns.tolist())
        
        # 檢查關鍵欄位並自動修補
        if "清洗後價格" not in df_market.columns:
            st.warning("⚠️ 找不到 '清洗後價格' 欄位，正在自動從 '價格' 欄位生成...")
            if "價格" in df_market.columns:
                df_market["清洗後價格"] = df_market["價格"].apply(try_clean_price)
            else:
                st.error("❌ 無法修補：連 '價格' 欄位都沒有！請檢查 CSV。")
                st.stop()
                
        if "圖片" not in df_market.columns:
            st.warning("⚠️ 找不到 '圖片' 欄位，將使用預設圖片。")
            df_market["圖片"] = "https://placehold.co/300x200?text=No+Image"
            
        if "連結" not in df_market.columns:
            df_market["連結"] = "#"

# --- 3. 主程式邏輯 ---
options_db = {
    "性能": {"QR4": {"name": "跑車計時套件", "price": 62100, "rate": 0.6}, "1BH": {"name": "PASM懸載", "price": 66900, "rate": 0.5}},
    "外觀": {"C6X": {"name": "19吋輪圈", "price": 82800, "rate": 0.2}, "3FU": {"name": "全景天窗", "price": 102000, "rate": 0.5}},
    "內裝": {"PE5": {"name": "14向電動椅", "price": 85600, "rate": 0.4}, "9VL": {"name": "BOSE音響", "price": 75000, "rate": 0.3}}
}

col_L, col_R = st.columns([1, 1.5])

with col_L:
    st.subheader("1. 車型設定")
    # 自動抓取 CSV 裡有的車型年份，避免選到空的
    # 這裡做個簡單的年份提取
    df_market['year_str'] = df_market['車名'].astype(str).str.extract(r'(20\d{2})')
    available_years = sorted(df_market['year_str'].dropna().unique())
    
    if not available_years: available_years = ["2015", "2016", "2017", "2018", "2019"]

    target_model = st.selectbox("車型", ["Macan", "Cayenne", "911", "718"])
    target_year = st.selectbox("年份", available_years)

    # 篩選數據
    mask = (
        df_market['車名'].astype(str).str.contains(target_model, case=False) & 
        df_market['車名'].astype(str).str.contains(target_year)
    )
    filtered_df = df_market[mask].copy()

    # 計算基礎價
    base_price = 200.0
    if not filtered_df.empty:
        # 過濾掉 0 元或極端值
        valid_prices = filtered_df[filtered_df['清洗後價格'] > 10]['清洗後價格']
        if not valid_prices.empty:
            base_price = valid_prices.mean()
            st.success(f"🔍 找到 {len(valid_prices)} 筆參考資料")
        else:
            st.warning("⚠️ 雖然有資料，但價格無效，使用預設值。")
    else:
        st.warning(f"⚠️ 資料庫沒有 {target_year} {target_model} 的數據。")

    st.subheader("2. 選配")
    add_value = 0
    orig_total = 0
    for cat, items in options_db.items():
        with st.expander(cat):
            for k, v in items.items():
                if st.checkbox(f"{v['name']} (${v['price']:,})"):
                    add_value += v['price'] * v['rate']
                    orig_total += v['price']

with col_R:
    st.subheader("📊 市場佐證")
    st.metric("平均行情", f"{base_price:.1f} 萬")
    
    if not filtered_df.empty:
        # 顯示前 3 筆
        filtered_df['diff'] = abs(filtered_df['清洗後價格'] - base_price)
        show_df = filtered_df.sort_values('diff').head(3)
        
        cols = st.columns(3)
        for i, row in enumerate(show_df.itertuples()):
            with cols[i % 3]:
                img = row.圖片 if pd.notna(row.圖片) else "https://placehold.co/300x200?text=No+Image"
                st.markdown(f"""
                <div class="car-card">
                    <img src="{img}" style="width:100%; border-radius:5px;">
                    <div style="font-size:0.8em; margin-top:5px;">{str(row.車名)[:15]}...</div>
                    <div class="price-tag">{row.清洗後價格} 萬</div>
                </div>
                """, unsafe_allow_html=True)

    st.subheader("💰 最終估價")
    # --- 在檔案最下方加入 AI 決策顧問區塊 ---
    st.markdown("---")
    st.header("🤖 AI 智能決策顧問 (Gemini 版)")

# --- 🚑 緊急修補：如果上面沒算到價格，這裡先給個預設值 ---
if 'final_price' not in locals():
    final_price = 158.0  # 預設值，避免報錯
if 'base_price' not in locals():
    base_price = 150.0   # 預設值
if 'target_year' not in locals():
    target_year = "2019" # 預設值
if 'target_model' not in locals():
    target_model = "Porsche" # 預設值

# 1. 模擬維修數據
repair_cost = st.slider("預估維修成本 (模擬 IoT/板金數據)", 
                        min_value=0, max_value=200000, value=5000, step=1000, format="$%d")

# 2. 輸入 Google API Key
user_api_key = st.text_input("請輸入 Google Gemini API Key", type="password")
if user_api_key:
    try:
        genai.configure(api_key=user_api_key)
        with st.expander("🔍 點擊查看雲端可用的模型清單 (除錯用)"):
            st.write("正在掃描雲端伺服器支援的模型...")
            models = []
            for m in genai.list_models():
                if 'generateContent' in m.supported_generation_methods:
                    models.append(m.name)
            st.write(models) # 這裡會直接印出所有可用的名字
    except Exception as e:
        st.error(f"API Key 可能有誤或無法連線: {e}")
st.caption("還沒有 Key？[點此免費申請](https://aistudio.google.com/app/apikey)")

if st.button("📝 生成專業收購評估報告"):
    if not user_api_key:
        st.warning("請先輸入 API Key 才能啟動 AI 大腦！")
    else:
        try:
            with st.spinner("Gemini 正在分析市場數據與車況..."):
                # A. 設定 API Key
                genai.configure(api_key=user_api_key)
                
                # B. 設定模型 (使用 Gemini 1.5 Flas，速度快且免費額度高)
                model = genai.GenerativeModel('gemini-pro')

                # C. 準備提示詞 (Prompt)
                car_info = f"{target_year} {target_model}"
                market_price = f"{base_price:.1f}"
                final_estimate = f"{final_price:.1f}"
                
                prompt = f"""
                你是一位擁有 20 年經驗的 Porsche 中古車鑑價專家。
                請根據以下數據，為車商撰寫一份簡短的「收購決策報告」：
                
                [車輛資訊]
                - 車型：{car_info}
                - 目前市場行情：{market_price} 萬
                - 選配後估值：{final_estimate} 萬
                - 發現的待修項目成本：{repair_cost} 元
                
                [你的任務]
                1. 分析此車的價格是否具備收購優勢（考慮維修成本）。
                2. 若維修成本低於車價的 5%，請強烈建議收購。
                3. 用條列式列出 3 個風險與機會點。
                4. 語氣要專業、果斷，像在對老闆做簡報。
                請直接輸出報告內容，不要有開場白。
                """

                # D. 發送請求
                response = model.generate_content(prompt)
                
                # E. 顯示結果
                st.success("分析完成！")
                st.markdown(response.text)
                
        except Exception as e:
            st.error(f"連線失敗，請檢查 API Key 是否正確。\n錯誤訊息：{e}")

#終端機執行>>>("streamlit run valuation.py")


