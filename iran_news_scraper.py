#!/usr/bin/env python3
import requests
from bs4 import BeautifulSoup
import json
import re
import time
from urllib.parse import urljoin
from datetime import datetime
import logging
import jdatetime # کتابخانه تاریخ شمسی

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class Scraper:
    BASE_URL = "https://iranintl.com"
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept-Language': 'fa-IR,fa;q=0.9,en-US;q=0.8,en;q=0.7',
        })

    def get_page(self, url):
        try:
            r = self.session.get(url, timeout=30)
            r.raise_for_status()
            return BeautifulSoup(r.content, 'html.parser')
        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
            return None

    def convert_to_shamsi(self, date_obj):
        """
        تبدیل هر نوع تاریخ (میلادی یا شمسی) به تاریخ شمسی زیبا
        """
        if not date_obj:
            return "تاریخ نامشخص"
        
        try:
            # اگر آبجکت jdatetime باشد (یعنی قبلاً شمسی بوده)
            if isinstance(date_obj, jdatetime.datetime):
                return date_obj.strftime('%Y/%m/%d')
            
            # اگر آبجکت datetime معمولی باشد (میلادی)
            if isinstance(date_obj, datetime):
                # تبدیل میلادی به شمسی
                shamsi_date = jdatetime.datetime.fromgregorian(datetime=date_obj)
                return shamsi_date.strftime('%Y/%m/%d')
                
            # اگر رشته بود، سعی در تشخیص می‌کنیم
            if isinstance(date_obj, str):
                # تلاش برای تبدیل اعداد فارسی به انگلیسی
                clean_str = re.sub(r'[^\d\-/\u06F0-\u06F9]', '', date_obj)
                if not clean_str:
                    return date_obj
                
                # اگر اعداد فارسی هستند
                farsi_digits = '۰۱۲۳۴۵۶۷۸۹'
                eng_digits = '0123456789'
                for f, e in zip(farsi_digits, eng_digits):
                    clean_str = clean_str.replace(f, e)
                
                parts = re.split(r'[-/]', clean_str)
                if len(parts) == 3:
                    y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
                    # تشخیص شمسی یا میلادی بر اساس سال
                    # اگر سال بین 1300 تا 1500 است، شمسی فرض می‌کنیم
                    if 1300 <= y <= 1500:
                        try:
                            shamsi_dt = jdatetime.datetime(y, m, d)
                            return shamsi_dt.strftime('%Y/%m/%d')
                        except:
                            pass # اگر خطا داشت، احتمالا میلادی است
                    # اگر سال کوچک است (مثلا 2023)، میلادی است و باید تبدیل شود
                    if y < 1300:
                        try:
                            gregorian_dt = datetime(y, m, d)
                            shamsi_dt = jdatetime.datetime.fromgregorian(datetime=gregorian_dt)
                            return shamsi_dt.strftime('%Y/%m/%d')
                        except:
                            pass
        except Exception as e:
            logger.debug(f"Date conversion error: {e}")
            return date_obj

    def get_article_meta(self, soup):
        """استخراج تاریخ و تصویر"""
        image = None
        
        # 1. تصویر
        og_image = soup.find('meta', property='og:image')
        if og_image and og_image.get('content'):
            image = og_image['content']
        else:
            img_tag = soup.find('article') or soup
            img = img_tag.find('img')
            if img and img.get('src'):
                image = img['src']

        # 2. تاریخ
        date_obj = None
        date_text = ""
        
        # روش اول: تگ time
        time_tag = soup.find('time')
        if time_tag:
            # datetime attribute معمولاً استاندارد است
            dt_attr = time_tag.get('datetime')
            if dt_attr:
                date_text = dt_attr
            else:
                date_text = time_tag.get_text(strip=True)
        
        # روش دوم: کلاس‌های رایج
        if not date_text:
            date_classes = ['date', 'published', 'timestamp', 'post-date', 'entry-date']
            for cls in date_classes:
                date_el = soup.find(class_=re.compile(cls, re.I))
                if date_el:
                    date_text = date_el.get_text(strip=True)
                    break
        
        # تبدیل رشته تاریخ به آبجکت قابل تبدیل
        if date_text:
            # تلاش برای ساخت آبجکت datetime
            try:
                # اگر فرمت استاندارد میلادی باشد (مثلا 2023-05-12)
                if re.match(r'^\d{4}[-/]\d{1,2}[-/]\d{1,2}$', date_text):
                    date_obj = datetime.strptime(date_text, '%Y-%m-%d')
                elif re.match(r'^\d{4}[-/]\d{1,2}[-/]\d{1,2}$', date_text): # فرمت دیگر
                    date_obj = datetime.strptime(date_text, '%Y/%m/%d')
                else:
                    # اگر فرمت نامشخص است، فرض می‌کنیم رشته است و convert_to_shamsi خودش مدیریت می‌کند
                    date_obj = date_text 
            except:
                date_obj = date_text # اگر پارس نشد، خود تابع تبدیل بعداً مدیریت می‌کند

        return date_obj, date_text, image

    def get_article_text(self, url):
        """استخراج متن کامل خبر"""
        soup = self.get_page(url)
        if not soup:
            return [], None, None, None
        
        date_obj, date_text, image = self.get_article_meta(soup)
        
        # استخراج بدنه خبر
        # الگوی کلاس در ایران اینترنشنال معمولا article-body یا story-content است
        content_div = soup.find('div', class_=re.compile(r'article-body|story-content|post-content|entry-content', re.I))
        if not content_div:
            content_div = soup.find('article') or soup
        
        if not content_div:
            return [], None, None, None

        paragraphs = []
        for p in content_div.find_all('p'):
            text = p.get_text(strip=True)
            # حذف پاراگراف‌های خیلی کوتاه یا تکراری
            if text and len(text) > 50:
                paragraphs.append(text)
        
        return paragraphs[:10], date_obj, date_text, image

    def run(self):
        logger.info("Fetching homepage...")
        soup = self.get_page(self.BASE_URL)
        if not soup:
            logger.error("Failed to fetch homepage")
            return []

        articles = []
        seen_urls = set()
        
        # ۱. استخراج لینک‌های خبر از صفحه اصلی
        # ما به دنبال تگ‌های h2, h3, h4 هستیم که داخل لینک هستند یا لینک والدشان هستند
        news_links = []
        
        # روش مطمئن: پیدا کردن تمام تگ‌های h2/h3 که لینک دارند
        for header in soup.find_all(['h2', 'h3', 'h4']):
            link = header.find('a', href=True)
            if link:
                href = link['href']
                if 'iranintl' in href and not any(skip in href for skip in ['/category/', '/tag/', '/author/', '#']):
                    url = urljoin(self.BASE_URL, href)
                    if url not in seen_urls:
                        seen_urls.add(url)
                        title = header.get_text(strip=True)
                        news_links.append({
                            "url": url,
                            "title": title
                        })
        
        # اگر لینک‌های هدر پیدا نشد، از روش عمومی استفاده کن (اما فیلتر دقیق‌تر)
        if not news_links:
            for a in soup.find_all('a', href=True):
                href = a.get('href', '')
                if 'iranintl' in href and not any(skip in href for skip in ['/category/', '/tag/', '/author/', '#']):
                    url = urljoin(self.BASE_URL, href)
                    if url not in seen_urls:
                        seen_urls.add(url)
                        # پیدا کردن عنوان نزدیک به لینک
                        parent = a.parent
                        title = ""
                        for tag in ['h2', 'h3', 'h4', 'strong', 'span']:
                            t = parent.find(tag)
                            if t:
                                title = t.get_text(strip=True)
                                break
                        if not title:
                            title = a.get_text(strip=True)
                        
                        if title and len(title) > 10: # عنوان باید معنادار باشد
                            news_links.append({
                                "url": url,
                                "title": title
                            })
        
        # محدود کردن تعداد لینک‌های ورودی برای پردازش (مثلا 20 تا)
        # اما نه کمتر از 10 تا
        limit = max(10, min(len(news_links), 20))
        raw_links = news_links[:limit]

        logger.info(f"Found {len(raw_links)} potential news links.")

        # ۲. پردازش هر لینک
        for item in raw_links:
            url = item['url']
            logger.info(f"Processing: {item['title'][:40]}...")
            
            summary, date_obj, date_text, image = self.get_article_text(url)
            
            # اگر خبری در صفحه نبود، رد شو
            if not summary:
                logger.warning(f"No content found in {url}")
                continue

            # تحلیل سنجیمنت (ساده)
            full_text = " ".join(summary).lower()
            positive_words = ['موفق', 'پیشرفت', 'امید', 'خوب', 'بهبود', 'success', 'hope', 'رشد', 'افتتاح', 'صلح']
            negative_words = ['جنگ', 'بحران', 'تنش', 'خشونت', 'تهدید', 'war', 'crisis', 'tension', 'حمله', 'کشته', 'ترور']
            
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

            # تبدیل تاریخ به شمسی برای نمایش
            shamsi_date_str = self.convert_to_shamsi(date_obj)
            
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
                "date_shamsi": shamsi_date_str, # تاریخ شمسی تبدیل شده
                # برای مرتب‌سازی، از یک عدد یونیکس استفاده می‌کنیم
                # اگر تاریخ شمسی داشتیم، آن را به میلادی تبدیل کن تا قابل مقایسه باشد
                sort_key = 0
                if isinstance(date_obj, jdatetime.datetime):
                    sort_key = date_obj.toordinal()
                elif isinstance(date_obj, datetime):
                    sort_key = date_obj.toordinal()
                elif isinstance(date_obj, str):
                    # اگر رشته بود، سعی کن پارس کنی
                    # این بخش پیشرفته است، فعلا صفر در نظر می‌گیریم
                    pass
                article["sort_key"] = sort_key

            articles.append(article)
            time.sleep(1)

        # ۳. مرتب‌سازی از جدید به قدیم
        # بر اساس sort_key مرتب می‌کنیم
        articles.sort(key=lambda x: x['sort_key'], reverse=True)
        
        # حذف فیلد کمکی از خروجی نهایی
        for art in articles:
            del art['sort_key']

        logger.info(f"Final count: {len(articles)} articles processed successfully.")
        return articles

if __name__ == "__main__":
    scraper = Scraper()
    articles = scraper.run()
    if articles:
        with open("news.json", "w", encoding="utf-8") as f:
            json.dump(articles, f, ensure_ascii=False, indent=4)
        print(f"✅ Saved {len(articles)} articles to news.json")
        # نمایش اولین خبر برای تست تاریخ
        if articles:
            print(f"📅 First article date (Shamsi): {articles[0].get('date_shamsi', 'N/A')}")
            print(f"📰 First article title: {articles[0].get('title_fa', 'N/A')}")
    else:
        print("❌ No articles found")
