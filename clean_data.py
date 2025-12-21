import streamlit as st
import pandas as pd
import re, os, subprocess
import google.generativeai as genai
from datetime import datetime

st.set_page_config(page_title="估車模型樣本診斷中心", layout="wide")

# --- 1. 補全階層式資料庫 ---
# 建立層級關係以利於模型特徵分類
CAR_DATABASE = {
    "Porsche": {
        "911": ["991", "992", "Carrera", "GT3", "Turbo S"],
        "Cayenne": ["SUV", "Coupe", "E-Hybrid"],
        "Macan": ["Base", "S", "GTS", "T"],
        "Panamera": ["Sedan", "Sport Turismo"],
        "718": ["Cayman", "Boxster", "GT4"]
    },
    "Benz": {
        "C-Class": ["W205", "W206", "Sedan", "Coupe", "Estate"],
        "E-Class": ["W213", "W214", "Sedan", "Coupe"],
        "GLC": ["SUV", "Coupe", "X253", "X254"],
        "GLE": ["SUV", "Coupe"],
        "CLA": ["Sedan", "Shooting Brake"],
        "A-Class": ["W177", "A180", "A250"]
    },
    "BMW": {
        "3 Series": ["F30", "G20", "Touring"],
        "5 Series": ["G30", "G60", "Touring"],
        "X3": ["G01", "SUV"],
        "X5": ["G05", "SUV"],
        "M Power": ["M2", "M3", "M4", "M5"]
    }
}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FOLDER = os.path.join(BASE_DIR, "data")
CURRENT_YEAR = 2025 # 依據當前時間設定 [cite: 2025-12-21]

# --- 2. 核心清洗邏輯 (解決 Benz 與年份 None 問題) ---
def extract_info(name):
    name_str = str(name).upper()
    found_brand, found_series, found_year = "其他", "不確定車系", None
    
    for brand, series_dict in CAR_DATABASE.items():
        # 處理 M-Benz 字眼識別問題
        check_kw = "M-BENZ" if brand == "Benz" else brand.upper()
        if check_kw in name_str or brand.upper() in name_str:
            found_brand = brand
            for series in series_dict.keys():
                if series.upper() in name_str:
                    found_series = series
                    break
            break
            
    # 強力提取 4 位數年份
    year_match = re.search(r'(20\d{2}|19\d{2})', name_str)
    year = int(year_match.group(1)) if year_match else None
    return pd.Series([found_brand, found_series, year])

# --- 3. 側邊欄：階梯式動態篩選 ---
with st.sidebar:
    st.header("🎯 樣本精確篩選")
    sel_brand = st.selectbox("1. 選擇品牌", list(CAR_DATABASE.keys()))
    series_options = list(CAR_DATABASE[sel_brand].keys())
    sel_series = st.selectbox(f"2. 選擇 {sel_brand} 車系", series_options)
    
    model_options = CAR_DATABASE[sel_brand][sel_series]
    sel_models = st.multiselect(f"3. 篩選具體型號 (選填)", model_options, default=model_options)

    st.divider()
    if st.button("🚀 啟動爬蟲採集樣本", type="primary", use_container_width=True):
        subprocess.run(["python", os.path.join(BASE_DIR, "scrape_8891.py")])
        st.rerun()

    st.header("🤖 AI 專家顧問")
    api_key = st.text_input("Gemini API Key", type="password")

# --- 4. 數據整合流程 (解決 ParserError) ---
def load_all_csv():
    if not os.path.exists(DATA_FOLDER): return pd.DataFrame()
    all_dfs = []
    files = [os.path.join(DATA_FOLDER, f) for f in os.listdir(DATA_FOLDER) if f.endswith('.csv')]
    for f in files:
        try: # 優先 UTF-8
            all_dfs.append(pd.read_csv(f, encoding='utf-8-sig'))
        except: # 失敗則 CP950
            try: all_dfs.append(pd.read_csv(f, encoding='cp950', errors='ignore'))
            except: continue
    return pd.concat(all_dfs, ignore_index=True) if all_dfs else pd.DataFrame()

df_raw = load_all_csv()

if not df_raw.empty:
    df = df_raw.drop_duplicates(subset=['連結']).copy()
    # 清洗價格
    df['清洗後價格'] = df['價格'].apply(lambda x: float(re.sub(r'[^\d.]', '', str(x))) if re.sub(r'[^\d.]', '', str(x)) else 0.0)
    # 執行特徵提取
    df[['品牌', '車系', '年份']] = df['車名'].apply(extract_info)
    df = df.dropna(subset=['年份'])
    # 計算模型核心維度：車齡
    # $Age = CURRENT\_YEAR - Year$
    df['車齡'] = CURRENT_YEAR - df['年份']
    
    # 執行 UI 篩選
    mask = (df['品牌'] == sel_brand) & (df['車系'] == sel_series)
    if sel_models:
        pattern = '|'.join(sel_models)
        mask = mask & (df['車名'].str.contains(pattern, case=False, na=False))
    view_df = df[mask].copy()

    # --- 5. 分頁展示 ---
    st.title(f"🚗 {sel_brand} {sel_series} 樣本庫 (樣本數: {len(view_df)})")
    t1, t2, t3 = st.tabs(["📋 樣本資料表", "📉 行情與異常檢測", "🤖 AI 模型建議"])

    with t1:
        st.data_editor(view_df, column_config={"圖片": st.column_config.ImageColumn("預覽")}, use_container_width=True)

    with t2:
        st.subheader("📊 市場行情分佈")
        # 修正 AttributeError: box_chart 報錯
        if hasattr(st, "box_chart"):
            st.box_chart(data=view_df, x='車齡', y='清洗後價格')
        else:
            st.info("💡 偵測到舊版環境，自動切換為柱狀圖。")
            st.bar_chart(view_df.groupby('車齡')['清洗後價格'].mean())
        
        st.write("**統計摘要 (用於估價模型基準)**")
        st.table(view_df['清洗後價格'].describe())

    with t3:
        if api_key and st.button("生成模型樣本優化建議"):
            try:
                genai.configure(api_key=api_key)
                # --- 修正 404 錯誤：改用 1.5-flash 模型 ---
                model = genai.GenerativeModel('gemini-flash-latest')
                prompt = f"分析 {sel_brand} {sel_series} 樣本資料，平均價格 {view_df['清洗後價格'].mean():.1f} 萬。建議如何剔除異常值以建立估價模型。"
                res = model.generate_content(prompt)
                st.markdown(res.text)
            except Exception as e:
                st.error(f"AI 啟動失敗: {e}")
else:
    st.info("👋 樣本庫目前為空，請點擊側邊欄按鈕採集數據。")
    # 終端機執行 ("streamlit run clean_data.py") 




