import time
import csv
import datetime
import re
import os
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
from webdriver_manager.chrome import ChromeDriverManager

# --- 1. 路徑與初始化設定 ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SAVE_DIRECTORY = os.path.join(BASE_DIR, "data")

def clean_price(price_text):
    """提取純數字價格"""
    if not price_text or "電洽" in price_text:
        return 0, False
    clean_str = re.sub(r'[^\d.]', '', price_text)
    try:
        val = float(clean_str)
        return val, True
    except:
        return 0, False

def scrape_8891_v12_portable():
    print(f"🚀 啟動全品牌通用版採集引擎...")
    print(f"📂 資料儲存路徑: {SAVE_DIRECTORY}")
    
    TARGET_COUNT = 50 
    
    # --- 2. 瀏覽器環境設定 (增加雲端相容模式) ---
    options = Options()
    # 手機展示或雲端部署必備：無頭模式
    options.add_argument("--headless") 
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled") 
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_argument("--start-maximized") 
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    valid_data = []
    seen_links = set()
    
    try:
        driver.get("https://auto.8891.com.tw/")
        
        # 提示：若在本地執行可取消註解 input，雲端環境則靠自動載入
        print("\n⏳ 正在載入頁面 (Headless 模式中)...")
        time.sleep(5) 
        
        while len(valid_data) < TARGET_COUNT:
            # 模擬人類捲動
            driver.execute_script("window.scrollBy(0, 1000);")
            time.sleep(2)
            
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            items = soup.select("a[href*='usedauto-infos']")
            
            if not items:
                print("⚠️ 找不到車輛物件，停止抓取。")
                break

            for item in items:
                try:
                    href = item.get('href', '')
                    full_link = "https://auto.8891.com.tw" + href if not href.startswith("http") else href
                    
                    if full_link in seen_links: continue
                    seen_links.add(full_link)

                    # --- 核心修正：先提取 text 賦值給 full_text ---
                    full_text = item.get_text(separator=" ", strip=True) 
                    
                    # 提取圖片
                    img_tag = item.find("img")
                    img_url = "https://placehold.co/100x75?text=No+Image"
                    if img_tag:
                        img_url = img_tag.get("data-original") or img_tag.get("src") or img_url

                    # 識別品牌與標題 (增加 Benz/M-Benz 支援)
                    title = "N/A"
                    brand_keywords = ["Porsche", "Benz", "賓士", "M-Benz", "BMW", "Tesla"]
                    for kw in brand_keywords:
                        if kw.upper() in full_text.upper():
                            start = full_text.upper().find(kw.upper())
                            title = full_text[start:start+50].split("萬")[0].strip()
                            break
                    if title == "N/A": title = full_text[:40].split("萬")[0].strip()

                    # 提取價格
                    price_match = re.search(r'(\d{1,4}[,\d]*\.?\d*)\s*萬', full_text)
                    if price_match:
                        price_val, success = clean_price(price_match.group(1))
                        if success:
                            valid_data.append({
                                "圖片": img_url,
                                "車名": title,
                                "價格": price_val,
                                "連結": full_link
                            })
                            print(f" ✅ 收錄樣本: {title[:15]}... | 💰 {price_val}萬")
                except Exception as e:
                    continue

            if len(valid_data) >= TARGET_COUNT: break
            # 簡易翻頁邏輯：此處僅抓取滾動後的內容，完整翻頁可按需求擴充
            break 

    except Exception as e:
        print(f"❌ 錯誤: {e}")

    finally:
        # --- 3. 存檔邏輯 (自動判斷品牌並動態命名) ---
        if valid_data:
            if not os.path.exists(SAVE_DIRECTORY):
                os.makedirs(SAVE_DIRECTORY)
            
            # 根據樣本內容決定檔名標籤
            brand_tag = "car"
            first_car_name = valid_data[0]['車名'].upper()
            for b in ["PORSCHE", "BENZ", "BMW", "TESLA"]:
                if b in first_car_name or ("賓士" in first_car_name and b == "BENZ"):
                    brand_tag = b.lower()
                    break

            now_str = datetime.datetime.now().strftime("%m%d_%H%M")
            fname = f'8891_{brand_tag}_samples_{now_str}.csv'
            full_path = os.path.join(SAVE_DIRECTORY, fname)

            with open(full_path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=["圖片", "車名", "價格", "連結"])
                writer.writeheader()
                writer.writerows(valid_data)
            
            print(f"\n🏁 採集結束！共獲取 {len(valid_data)} 筆樣本")
            print(f"✅ 檔案已完美存入: {full_path}")
        
        driver.quit()

if __name__ == "__main__":
    scrape_8891_v12_portable()
