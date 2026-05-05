#!/usr/bin/env python3
import requests
from bs4 import BeautifulSoup
import json
import re
import time
from urllib.parse import urljoin
from datetime import datetime
import logging

# کتابخانه جدید برای مدیریت تاریخ شمسی
import jdatetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class Scraper:
    BASE_URL = "https://iranintl.com"
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept-Language': 'en-US,en;q=0.5',
        })

    def get_page(self, url):
        try:
            r = self.session.get(url, timeout=30)
            r.raise_for_status()
            return BeautifulSoup(r.content, 'html.parser')
        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
            return None

    def parse_date(self, date_str):
        """
        تبدیل رشته تاریخ (فارسی یا انگلیسی) به آبجکت jdatetime برای مرتب‌سازی دقیق
        """
        if not date_str:
            return None

        try:
            # پاکسازی کاراکترهای اضافی مثل "منتشر شده در" یا فاصله‌های اضافی
            clean_date = re.sub(r'[^\d\-/\u06F0-\u06F9]', '', date_str)
            
            # اگر تاریخ خالی شد
            if not clean_date:
                return None

            # تشخیص جداکننده
            if '/' in clean_date:
                parts = clean_date.split('/')
            elif '-' in clean_date:
                parts = clean_date.split('-')
            else:
                # اگر عدد پیوسته است (مثلا 14020512)
                if len(clean_date) == 8:
                    parts = [clean_date[:4], clean_date[4:6], clean_date[6:8]]
                else:
                    return None

            if len(parts) != 3:
                return None

            # تبدیل اعداد فارسی به انگلیسی اگر لازم باشد (jdatetime خودکار هندل می‌کند اما برای اطمینان)
            # جداول اعداد فارسی
            farsi_digits = '۰۱۲۳۴۵۶۷۸۹'
            eng_digits = '0123456789'
            
            # تبدیل دستی اگر رشته شامل اعداد فارسی باشد
            # اما jdatetime.fromgregorian یا constructor معمولا اعداد فارسی را هم می‌پذیرند؟
            # بهتر است مطمئن شویم اعداد انگلیسی هستند یا از try-except استفاده کنیم.
            
            # روش امن: تلاش برای ساخت آبجکت جالویشی
            # ما فرض می‌کنیم فرمت شمسی است چون سایت فارسی است.
            # اگر اعداد فارسی باشند، jdatetime از آن‌ها پشتیبانی می‌کند.
            
            year = int(parts[0])
            month = int(parts[1])
            day = int(parts[2])

            # اعتبارسنجی ساده
            if 1300 <= year <= 1500 and 1 <= month <= 12 and 1 <= day <= 31:
                return jdatetime.datetime(year, month, day)
            
            # اگر فرمت میلادی بود (احتمال کم در این سایت، اما برای اطمینان)
            # اگر سال کمتر از 1300 بود، احتمالا میلادی است
            elif year < 1300:
                return datetime(year, month, day)
                
        except (ValueError, IndexError) as e:
            logger.debug(f"Could not parse date: {date_str}, Error: {e}")
            return None
            
        return None

    def get_article_meta(self, soup):
        """استخراج تاریخ و تصویر از هدر خبر"""
        date_obj = None
        image = None
        
        # ۱. جستجو برای تصویر
        og_image = soup.find('meta', property='og:image')
        if og_image and og_image.get('content'):
            image = og_image['content']
        else:
            img_tag = soup.find('article') or soup
            img = img_tag.find('img')
            if img and img.get('src'):
                image = img['src']

        # ۲. جستجو برای تاریخ
        date_text = ""
        time_tag = soup.find('time')
        if time_tag:
            # اول datetime را چک کن، اگر نبود متن را بگیر
            date_text = time_tag.get('datetime') or time_tag.get_text(strip=True)
        
        if not date_text:
            date_classes = ['date', 'published', 'timestamp', 'post-date', 'entry-date', 'pubdate']
            for cls in date_classes:
                date_el = soup.find(class_=re.compile(cls, re.I))
                if date_el:
                    date_text = date_el.get_text(strip=True)
                    break
        
        # تبدیل به آبجکت تاریخ برای مرتب‌سازی
        parsed_date = self.parse_date(date_text)
        
        return parsed_date, date_text, image

    def get_article_text(self, url):
        """استخراج متن کامل خبر"""
        soup = self.get_page(url)
        if not soup:
            return [], None, None, None
        
        parsed_date, date_text, image = self.get_article_meta(soup)
        
        content_div = soup.find('div', class_=re.compile(r'article-body|story-content|post-content|entry-content', re.I))
        if not content_div:
            content_div = soup.find('article') or soup
        
        if not content_div:
            return [], None, None, None

        paragraphs = []
        for p in content_div.find_all('p'):
            text = p.get_text(strip=True)
            if text and len(text) > 50: # کمی کاهش حداقل طول برای گرفتن جملات کوتاه‌تر
                paragraphs.append(text)
        
        return paragraphs[:10], parsed_date, date_text, image

    def run(self):
        logger.info("Fetching homepage...")
        soup = self.get_page(self.BASE_URL)
        if not soup:
            logger.error("Failed to fetch homepage")
            return []

        articles = []
        seen = set()
        
        # ۱. استخراج لینک‌ها از صفحه اصلی
        raw_links = []
        for a in soup.find_all('a', href=True):
            href = a.get('href', '')
            if 'iranintl' not in href:
                continue
            url = urljoin(self.BASE_URL, href) if href.startswith('/') else href
            if url in seen:
                continue
            if any(skip in url for skip in ['/category/', '/tag/', '/author/', '#']):
                continue
            
            seen.add(url)
            parent = a.parent
            
            # پیدا کردن عنوان در تگ‌های والد
            title = ""
            # گاهی لینک مستقیماً داخل h2 است
            if a.name in ['h2', 'h3', 'h4']:
                title = a.get_text(strip=True)
            else:
                for tag in ['h2', 'h3', 'h4', 'h5']:
                    t = parent.find(tag)
                    if t:
                        title = t.get_text(strip=True)
                        break
            
            if not title:
                title = a.get_text(strip=True)
            
            if not title:
                continue
                
            raw_links.append({
                "url": url,
                "title": title
            })
            if len(raw_links) >= 10:
                break

        # ۲. پردازش هر لینک
        for item in raw_links:
            url = item['url']
            logger.info(f"Processing: {item['title'][:50]}...")
            
            summary, parsed_date, date_text, image = self.get_article_text(url)
            
            if not summary:
                continue

            # تحلیل سنجیمنت (ساده)
            full_text = " ".join(summary).lower()
            positive_words = ['موفق', 'پیشرفت', 'امید', 'خوب', 'بهبود', 'success', 'hope', 'رشد', 'افتتاح']
            negative_words = ['جنگ', 'بحران', 'تنش', 'خشونت', 'تهدید', 'war', 'crisis', 'tension', 'حمله', 'کشته']
            
            pos = sum(1 for w in positive_words if w in full_text)
            neg = sum(1 for w in negative_words if w in full_text)
            total = pos + neg
            sentiment = round((pos - neg) / total, 2) if total > 0 else 0.0
            
            urgency = 5
            high = ['فوری', 'خبر مهم', 'breaking', 'urgent', 'جنگ', 'حمله', 'هشدار']
            for w in high:
                if w in full_text:
                    urgency = 8
                    break
            
            impact = ""
            if sentiment < -0.3 and urgency > 6:
                impact = "این رویداد می‌تواند تأثیرات جدی بر وضعیت امنیتی و سیاسی منطقه داشته باشد."
            elif sentiment < 0:
                impact = "این خبر می‌تواند بر فضای عمومی و افکار عمومی تأثیرگذار باشد."
            elif sentiment > 0.3:
                impact = "این خبر می‌تواند تأثیر مثبتی بر فضای عمومی داشته باشد."
            else:
                impact = "این خبر در حال حاضر تأثیر قابل توجهی بر وضعیت کلی ندارد."

            # فرمت‌دهی تاریخ برای نمایش
            # اگر تاریخ شمسی استخراج شد، آن را به رشته زیبای فارسی تبدیل می‌کنیم
            date_display = ""
            if parsed_date:
                if isinstance(parsed_date, jdatetime.datetime):
                    date_display = parsed_date.strftime('%Y/%m/%d') # فرمت شمسی
                elif isinstance(parsed_date, datetime):
                    date_display = parsed_date.strftime('%Y-%m-%d') # فرمت میلادی
            
            article = {
                "title_fa": item['title'],
                "title_en": "",
                "summary": summary,
                "impact": impact,
                "tag": "عمومی",
                "urgency": urgency,
                "sentiment": sentiment,
                "source": "Iran International",
                "url": url,
                "clean_url": url,
                "image": image,
                "date_raw": date_text if date_text else "",
                "date_formatted": date_display, # تاریخ خوانا برای کاربر
                # برای مرتب‌سازی داخلی، از timestamp یونیکس یا خود آبجکت تاریخ استفاده می‌کنیم
                # اما چون jdatetime قابل مقایسه مستقیم در JSON نیست، ما از یک عدد یونیکس استفاده می‌کنیم
                "sort_timestamp": parsed_date.toordinal() if parsed_date else 0 
            }
            articles.append(article)
            time.sleep(1)

        # ۳. مرتب‌سازی از جدید به قدیم
        # استفاده از sort_timestamp که بر اساس تاریخ شمسی یا میلادی محاسبه شده است
        # toordinal() یک عدد صحیح یکتا برای هر روز می‌دهد که برای مقایسه عالی است
        articles.sort(key=lambda x: x['sort_timestamp'], reverse=True)
        
        # حذف فیلد کمکی sort_timestamp از خروجی نهایی (اختیاری)
        for art in articles:
            del art['sort_timestamp']

        logger.info(f"Final count: {len(articles)} articles")
        return articles

if __name__ == "__main__":
    scraper = Scraper()
    articles = scraper.run()
    if articles:
        with open("news.json", "w", encoding="utf-8") as f:
            json.dump(articles, f, ensure_ascii=False, indent=4)
        print(f"✅ Saved {len(articles)} articles to news.json")
        # نمایش تاریخ اولین خبر برای تست
        if articles:
            print(f"📅 First article date (Shamsi): {articles[0].get('date_formatted', 'N/A')}")
    else:
        print("❌ No articles found")
