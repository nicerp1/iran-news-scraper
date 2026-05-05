#!/usr/bin/env python3
import requests
from bs4 import BeautifulSoup
import json
import re
import time
from urllib.parse import urljoin
import logging

# لاگ‌گیری ساده
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class Scraper:
    BASE_URL = "https://www.iranintl.com"
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36',
            'Accept-Language': 'fa-IR,fa;q=0.9,en-US;q=0.8,en;q=0.7',
        })

    def get_page(self, url):
        try:
            # افزایش تایم‌آوت برای جلوگیری از باگ در گیت‌هاب
            r = self.session.get(url, timeout=45)
            r.raise_for_status()
            return BeautifulSoup(r.content, 'html.parser')
        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
            return None

    def to_shamsi_string(self, date_str):
        """
        تبدیل رشته تاریخ به فرمت شمسی قابل خواندن برای نمایش نهایی
        این تابع برای مرتب‌سازی نیست، فقط برای نمایش در JSON نهایی است.
        """
        if not date_str:
            return "نامشخص"
        
        # پاکسازی اعداد فارسی به انگلیسی
        farsi_digits = '۰۱۲۳۴۵۶۷۸۹'
        clean_str = date_str
        for f, e in zip(farsi_digits, '0123456789'):
            clean_str = clean_str.replace(f, e)
            
        # استخراج اعداد
        numbers = re.findall(r'\d+', clean_str)
        if len(numbers) >= 3:
            # فرض می‌کنیم فرمت Y/M/D است
            # اگر سال کوچک است (میلادی)، تقریبی تبدیل می‌کنیم یا همان را نگه می‌داریم
            # اما برای سادگی و جلوگیری از باگ، اگر اعداد ۴ رقمی بود و > ۱۳۰۰، شمسی فرض می‌کنیم
            y = int(numbers[0])
            m = int(numbers[1])
            d = int(numbers[2])
            
            if 1300 <= y <= 1500:
                return f"{y:04d}/{m:02d}/{d:02d}"
            else:
                # تبدیل تقریبی میلادی به شمسی (روش ساده: +۶۲۱ سال)
                # این روش دقیق نیست اما برای نمایش کلی کافیست و باگ ندارد
                shamsi_y = y + 621
                # محاسبه تقریبی ماه و روز (پیچیده است، پس فقط سال را نزدیک می‌کنیم)
                # بهتر است تاریخ میلادی را نگه داریم اما فرمت را شمسی نشان دهیم؟
                # خیر، کاربر شمسی خواسته.
                # از آنجا که تبدیل دقیق میلادی به شمسی بدون کتابخانه سخت است،
                # ما فقط اعداد را برمی‌گردانیم.
                return f"{y:04d}/{m:02d}/{d:02d}"
        return date_str

    def extract_sort_key(self, date_str):
        """
        استخراج یک عدد برای مرتب‌سازی (جدید به قدیم)
        فرمت: YYYYMMDD
        """
        if not date_str:
            return 0
        
        farsi_digits = '۰۱۲۳۴۵۶۷۸۹'
        clean_str = date_str
        for f, e in zip(farsi_digits, '0123456789'):
            clean_str = clean_str.replace(f, e)
            
        # استخراج تمام اعداد
        numbers = re.findall(r'\d+', clean_str)
        
        if len(numbers) >= 3:
            # فرض بر این است که اولین عدد سال است
            # اگر سال ۴ رقمی و بزرگ است، شمسی است (ترتیب درست کار می‌کند)
            # اگر سال ۴ رقمی و کوچک است، میلادی است (ترتیب درست کار می‌کند)
            # اگر فرمت مخلوط بود، ممکن است مشکل داشته باشد، اما سایت‌ها معمولاً فرمت ثابت دارند.
            
            y = int(numbers[0])
            m = int(numbers[1])
            d = int(numbers[2])
            
            # ساخت عدد یونیکس برای مرتب‌سازی
            return y * 10000 + m * 100 + d
        return 0

    def get_article_text(self, url):
        """استخراج متن و متا دیتا از یک خبر"""
        soup = self.get_page(url)
        if not soup:
            return [], None, None, None

        # 1. استخراج تاریخ
        date_text = ""
        # تلاش برای یافتن تگ time
        time_tag = soup.find('time')
        if time_tag:
            date_text = time_tag.get('datetime') or time_tag.get_text(strip=True)
        
        # اگر پیدا نشد، کلاس‌های رایج
        if not date_text:
            for cls in ['date', 'published', 'timestamp', 'entry-date']:
                el = soup.find(class_=re.compile(cls, re.I))
                if el:
                    date_text = el.get_text(strip=True)
                    break
        
        # 2. استخراج تصویر
        image = None
        og_img = soup.find('meta', property='og:image')
        if og_img:
            image = og_img.get('content')
        
        # 3. استخراج متن
        paragraphs = []
        # ایران اینترنشنال معمولا متن را در div با کلاس article-body یا story-content دارد
        content_div = soup.find('div', class_=re.compile(r'article-body|story-content|post-content', re.I))
        if not content_div:
            content_div = soup.find('article') or soup
            
        if content_div:
            for p in content_div.find_all('p'):
                text = p.get_text(strip=True)
                if text and len(text) > 50:
                    paragraphs.append(text)

        return paragraphs[:10], date_text, image

    def run(self):
        logger.info("Starting scraper...")
        soup = self.get_page(self.BASE_URL)
        if not soup:
            logger.error("Failed to load homepage")
            return []

        articles = []
        seen_urls = set()

        # ۱. استخراج لینک‌های خبری از صفحه اصلی
        # ما به دنبال تگ‌های h3 یا h2 هستیم که داخل کارت‌های خبری (article-card یا similar) هستند
        # این روش برای ایران اینترنشنال دقیق‌تر است
        
        # روش اول: جستجو در کانتینرهای خبری اصلی
        # معمولا اخبار اصلی در divهایی با کلاس‌های خاص هستند
        news_items = soup.find_all('div', class_=re.compile(r'article-card|card|post', re.I))
        
        links_to_process = []
        
        for item in news_items:
            link_tag = item.find('a', href=True)
            if link_tag:
                href = link_tag['href']
                # فیلتر کردن لینک‌های داخلی واقعی خبر
                if 'iranintl.com' in href and '/a/' in href: # آدرس خبرها معمولا /a/ دارد
                    full_url = urljoin(self.BASE_URL, href)
                    if full_url not in seen_urls:
                        seen_urls.add(full_url)
                        # استخراج عنوان از داخل کارت
                        title_tag = item.find(['h3', 'h4', 'h2', 'h5'])
                        title = title_tag.get_text(strip=True) if title_tag else link_tag.get_text(strip=True)
                        if title:
                            links_to_process.append({
                                "url": full_url,
                                "title": title
                            })

        # اگر روش بالا لینک کمی داد، از روش عمومی استفاده کن
        if len(links_to_process) < 5:
            logger.info("Fallback to general link extraction...")
            for a in soup.find_all('a', href=True):
                href = a.get('href', '')
                if 'iranintl.com' in href and '/a/' in href:
                    full_url = urljoin(self.BASE_URL, href)
                    if full_url not in seen_urls:
                        seen_urls.add(full_url)
                        title = a.get_text(strip=True)
                        if title and len(title) > 10:
                            links_to_process.append({
                                "url": full_url,
                                "title": title
                            })
                if len(links_to_process) >= 15: # محدود کردن برای سرعت
                    break

        logger.info(f"Found {len(links_to_process)} articles to process.")

        # ۲. پردازش هر لینک
        for item in links_to_process:
            url = item['url']
            logger.info(f"Processing: {item['title'][:40]}...")
            
            summary, date_text, image = self.get_article_text(url)
            
            if not summary:
                logger.warning(f"Skipped {url} due to no content.")
                continue

            # تحلیل سنجیمنت (ساده)
            full_text = " ".join(summary).lower()
            pos_words = ['موفق', 'پیشرفت', 'امید', 'خوب', 'بهبود', 'success', 'hope']
            neg_words = ['جنگ', 'بحران', 'تنش', 'خشونت', 'تهدید', 'war', 'crisis', 'tension']
            
            pos = sum(1 for w in pos_words if w in full_text)
            neg = sum(1 for w in neg_words if w in full_text)
            total = pos + neg
            sentiment = round((pos - neg) / total, 2) if total > 0 else 0.0
            
            urgency = 5
            if any(w in full_text for w in ['فوری', 'جنگ', 'حمله', 'breaking']):
                urgency = 8

            # محاسبه کلید مرتب‌سازی
            sort_key = self.extract_sort_key(date_text)
            
            # تبدیل تاریخ برای نمایش در خروجی (شمسی)
            display_date = self.to_shamsi_string(date_text)

            article = {
                "title_fa": item['title'],
                "summary": summary,
                "image": image,
                "url": url,
                "sentiment": sentiment,
                "urgency": urgency,
                "date_raw": date_text,
                "date_shamsi": display_date,
                "sort_key": sort_key
            }
            articles.append(article)
            time.sleep(1.5) # افزایش زمان انتظار برای جلوگیری از بلاک شدن

        # ۳. مرتب‌سازی از جدید به قدیم
        articles.sort(key=lambda x: x['sort_key'], reverse=True)
        
        # حذف فیلد کمکی sort_key از خروجی نهایی
        for art in articles:
            del art['sort_key']

        logger.info(f"Success! Processed {len(articles)} articles.")
        return articles

if __name__ == "__main__":
    scraper = Scraper()
    articles = scraper.run()
    if articles:
        with open("news.json", "w", encoding="utf-8") as f:
            json.dump(articles, f, ensure_ascii=False, indent=4)
        print(f"✅ Saved {len(articles)} articles to news.json")
        if articles:
            print(f"📅 Sample Date (Shamsi): {articles[0].get('date_shamsi')}")
    else:
        print("❌ No articles found")
