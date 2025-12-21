import streamlit as st
import pandas as pd
import re, os, subprocess
import google.generativeai as genai
from datetime import datetime

# --- 0. 網頁初始設定 ---
st.set_page_config(page_title="估車模型樣本診斷中心", layout="wide")

# --- 1. 補全階層式資料庫：品牌 -> 車系 -> 型號 ---
# 用於建立精確的估價特徵分類
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
CURRENT_YEAR = datetime.now().year # 自動獲取當前年份計算車齡

# --- 2. 核心清洗邏輯：修正 Benz 辨識與年份提取 ---
def extract_info(name):
    name_str = str(name).upper()
    found_brand, found_series, found_year = "其他", "不確定車系", None
    
    # 辨識品牌：解決 M-Benz 字眼導致 None 的問題
    for brand, series_dict in CAR_DATABASE.items():
        check_kw = "M-BENZ" if brand == "Benz" else brand.upper()
        if check_kw in name_str or brand.upper() in name_str:
            found_brand = brand
            for series in series_dict.keys():
                if series.upper() in name_str:
                    found_series = series
                    break
            break
            
    # 年份提取：確保樣本具備車齡特徵
    year_match = re.search(r'(20\d{2}|19\d{2})', name_str)
    year = int(year_match.group(1)) if year_match else None
    return pd.Series([found_brand, found_series, year])

# --- 3. 側邊欄：階梯式動態篩選 ---
with st.sidebar:
    st.header("🎯 樣本精確篩選")
    sel_brand = st.selectbox("1. 選擇品牌", list(CAR_DATABASE.keys()))
    
    # 連動車系選擇
    series_options = list(CAR_DATABASE[sel_brand].keys())
    sel_series = st.selectbox(f"2. 選擇 {sel_brand} 車系", series_options)
    
    # 連動具體型號選擇
    model_options = CAR_DATABASE[sel_brand][sel_series]
    sel_models = st.multiselect(f"3. 篩選型號 (選填)", model_options, default=model_options)

    st.divider()
    # 執行爬蟲更新
    if st.button("🚀 啟動爬蟲採集樣本", type="primary", use_container_width=True):
        with st.spinner("採集中..."):
            subprocess.run(["python", os.path.join(BASE_DIR, "scrape_8891.py")])
            st.rerun()

    st.header("🤖 AI 專家顧問")
    api_key = st.text_input("Gemini API Key", type="password")

# --- 4. 數據讀取與整合 (解決 ParserError 與多檔案合併) ---
def load_all_csv():
    if not os.path.exists(DATA_FOLDER): return pd.DataFrame()
    all_dfs = []
    # 掃描 data 資料夾內所有 csv
    files = [os.path.join(DATA_FOLDER, f) for f in os.listdir(DATA_FOLDER) if f.endswith('.csv')]
    for f in files:
        try:
            # 優先嘗試 utf-8-sig
            all_dfs.append(pd.read_csv(f, encoding='utf-8-sig'))
        except:
            try:
                # 失敗則嘗試 Windows 常用編碼
                all_dfs.append(pd.read_csv(f, encoding='cp950', errors='ignore'))
            except:
                continue
    return pd.concat(all_dfs, ignore_index=True) if all_dfs else pd.DataFrame()

df_raw = load_all_csv()

if not df_raw.empty:
    # 樣本去重
    df = df_raw.drop_duplicates(subset=['連結']).copy()
    
    # 價格特徵清洗
    df['價格_數值'] = df['價格'].apply(lambda x: float(re.sub(r'[^\d.]', '', str(x))) if re.sub(r'[^\d.]', '', str(x)) else 0.0)
    
    # 執行特徵提取：品牌、車系、年份
    df[['品牌', '車系', '年份']] = df['車名'].apply(extract_info)
    df = df.dropna(subset=['年份'])
    
    # 計算估車模型核心維度：車齡
    df['車齡'] = CURRENT_YEAR - df['年份']
    
    # 執行 UI 連動篩選
    mask = (df['品牌'] == sel_brand) & (df['車系'] == sel_series)
    if sel_models:
        pattern = '|'.join(sel_models)
        mask = mask & (df['車名'].str.contains(pattern, case=False, na=False))
    
    view_df = df[mask].copy()

    # --- 5. 功能展示分頁 ---
    st.title(f"🚗 {sel_brand} {sel_series} 樣本採集中心")
    st.write(f"目前有效樣本數: **{len(view_df)}** 筆")
    
    tab1, tab2, tab3 = st.tabs(["📋 樣本資料表", "📉 行情與異常檢測", "🤖 AI 診斷"])

    with tab1:
        # 手機版建議使用 data_editor 並隱藏部分欄位以優化寬度
        st.data_editor(
            view_df, 
            column_config={"圖片": st.column_config.ImageColumn("預覽"), "價格_數值": "清洗後價格(萬)"}, 
            use_container_width=True
        )

    with tab2:
        st.subheader("📊 市場行情分佈 (檢測離群值)")
        # 修正：版本檢查解決 AttributeError
        if hasattr(st, "box_chart"):
            st.box_chart(data=view_df, x='車齡', y='價格_數值')
        else:
            st.info("💡 偵測到環境版本較舊，自動切換為趨勢圖分析。")
            st.line_chart(view_df.groupby('車齡')['價格_數值'].mean())
        
        st.write("**統計摘要 (模型建模基準)**")
        st.table(view_df['價格_數值'].describe())

    with tab3:
        if api_key and st.button("生成模型樣本優化建議"):
            try:
                genai.configure(api_key=api_key)
                # 修正：改用 1.5-flash 以確保 API 相容性
                model = genai.GenerativeModel('gemini-1.5-flash')
                prompt = f"分析 {sel_brand} {sel_series} 樣本資料，平均價格 {view_df['價格_數值'].mean():.1f} 萬。建議如何剔除異常值以建立估價模型。"
                res = model.generate_content(prompt)
                st.markdown(res.text)
            except Exception as e:
                st.error(f"AI 啟動失敗: {e}")
else:
    st.info("👋 樣本庫目前為空，請點擊側邊欄按鈕開始採集數據。")
    # 終端機執行 ("streamlit run clean_data.py") 





