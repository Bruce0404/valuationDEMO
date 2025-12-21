import time, csv, datetime, re, os
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
from webdriver_manager.chrome import ChromeDriverManager

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SAVE_DIRECTORY = os.path.join(BASE_DIR, "data")

def scrape_8891_v12_portable():
    print(f"🚀 啟動全品牌通用版採集引擎...")
    options = Options()
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--start-maximized") 
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    valid_data = []
    seen_links = set()
    
    try:
        driver.get("https://auto.8891.com.tw/")
        input("\n🛑 請在瀏覽器篩選完畢後，回到此處按 [Enter] 開始...")
        
        while len(valid_data) < 100:
            driver.execute_script("window.scrollBy(0, 1000);")
            time.sleep(2)
            
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            items = soup.select("a[href*='usedauto-infos']")
            
            for item in items:
                href = item.get('href', '')
                full_link = "https://auto.8891.com.tw" + href if not href.startswith("http") else href
                if full_link in seen_links: continue
                seen_links.add(full_link)

                # --- 核心修正：先定義 text，解決 NameError ---
                full_text = item.get_text(separator=" ", strip=True) 
                
                # 識別標題與品牌 (支援 M-Benz)
                title = "N/A"
                brand_list = ["Porsche", "Benz", "M-Benz", "BMW", "Tesla", "Toyota"]
                for b in brand_list:
                    if b.upper() in full_text.upper():
                        start = full_text.upper().find(b.upper())
                        title = full_text[start:start+50].split("萬")[0].strip()
                        break
                if title == "N/A": title = full_text[:40].split("萬")[0].strip()

                price_match = re.search(r'(\d+[,\d]*\.?\d*)\s*萬', full_text)
                if price_match:
                    img_tag = item.find("img")
                    img_url = img_tag.get("data-original") or img_tag.get("src") if img_tag else "No Image"
                    valid_data.append({"圖片": img_url, "車名": title, "價格": price_match.group(1), "連結": full_link})
                    print(f" ✅ 樣本入庫: {title[:15]}...")
            if len(valid_data) >= 100: break
            break 
    finally:
        if valid_data:
            if not os.path.exists(SAVE_DIRECTORY): os.makedirs(SAVE_DIRECTORY)
            now_str = datetime.datetime.now().strftime("%m%d_%H%M")
            fname = f'8891_raw_samples_{now_str}.csv'
            full_path = os.path.join(SAVE_DIRECTORY, fname)
            with open(full_path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=["圖片", "車名", "價格", "連結"])
                writer.writeheader(); writer.writerows(valid_data)
            print(f"✅ 樣本已存至: {full_path}")
        driver.quit()

if __name__ == "__main__":
    scrape_8891_v12_portable()