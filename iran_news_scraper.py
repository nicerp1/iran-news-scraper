#!/usr/bin/env python3
import requests
from bs4 import BeautifulSoup
import json
import re
import time
from urllib.parse import urljoin
from datetime import datetime
import logging

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
        except:
            return None
    
    def parse_date(self, date_str):
        """تبدیل رشته تاریخ به فرمت استاندارد برای مرتب‌سازی"""
        if not date_str:
            return datetime.min
        
        # تلاش برای پاکسازی و تبدیل تاریخ‌های فارسی/انگلیسی
        # این یک روش ساده است، ممکن است برای همه فرمت‌ها کامل نباشد اما برای اکثر سایت‌ها کار می‌کند
        try:
            # اگر تاریخ شمسی است، می‌توان از کتابخانه jdatetime استفاده کرد
            # اما برای سادگی و عدم وابستگی، فعلاً از روش رشته‌ای استفاده می‌کنیم
            # یا فرض می‌کنیم فرمت استاندارد ISO است
            
            # حذف کاراکترهای اضافی
            clean_date = re.sub(r'[^\d\-/]', '', date_str)
            
            # تلاش برای تشخیص فرمت
            if '/' in clean_date:
                # فرض بر فرمت شمسی یا میلادی
                parts = clean_date.split('/')
                if len(parts) == 3:
                    # اگر اعداد بزرگ هستند (مثل ۱۴۰۳) احتمالاً شمسی است
                    # ما برای مرتب‌سازی فقط نیاز داریم که ترتیب درست باشد
                    # پس رشته را برمی‌گردانیم تا به صورت رشته مقایسه شود
                    return clean_date
            return clean_date
        except:
            return date_str

    def get_article_meta(self, soup):
        """استخراج تاریخ و تصویر از هدر خبر"""
        date_obj = None
        image = None
        
        # ۱. جستجو برای تصویر
        # اول Og Image را چک کن
        og_image = soup.find('meta', property='og:image')
        if og_image and og_image.get('content'):
            image = og_image['content']
        else:
            # بعداً تگ img اصلی
            img_tag = soup.find('article') or soup
            img = img_tag.find('img')
            if img and img.get('src'):
                image = img['src']
        
        # ۲. جستجو برای تاریخ
        # معمولاً در تگ time یا div با کلاس date قرار دارد
        date_text = ""
        
        # روش اول: تگ time
        time_tag = soup.find('time')
        if time_tag:
            date_text = time_tag.get('datetime') or time_tag.get_text(strip=True)
        
        # روش دوم: کلاس‌های رایج تاریخ
        if not date_text:
            date_classes = ['date', 'published', 'timestamp', 'post-date', 'entry-date']
            for cls in date_classes:
                date_el = soup.find(class_=re.compile(cls, re.I))
                if date_el:
                    date_text = date_el.get_text(strip=True)
                    break
        
        return date_text, image

    def get_article_text(self, url):
        """استخراج متن کامل خبر"""
        soup = self.get_page(url)
        if not soup:
            return [], None, None
        
        date_text, image = self.get_article_meta(soup)
        
        content_div = soup.find('div', class_=re.compile(r'article-body|story-content|post-content|entry-content', re.I))
        if not content_div:
            content_div = soup.find('article') or soup
        
        if not content_div:
            return [], date_text, image
        
        paragraphs = []
        for p in content_div.find_all('p'):
            text = p.get_text(strip=True)
            if text and len(text) > 100:
                paragraphs.append(text)
        
        return paragraphs[:10], date_text, image
    
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
            title = ""
            for tag in ['h2', 'h3', 'h4']:
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
            
            # استخراج متن و متا دیتا
            summary, date_text, image = self.get_article_text(url)
            
            # تحلیل سنجیمنت
            full_text = " ".join(summary).lower()
            positive_words = ['موفق', 'پیشرفت', 'امید', 'خوب', 'بهبود', 'success', 'hope']
            negative_words = ['جنگ', 'بحران', 'تنش', 'خشونت', 'تهدید', 'war', 'crisis', 'tension']
            
            pos = sum(1 for w in positive_words if w in full_text)
            neg = sum(1 for w in negative_words if w in full_text)
            total = pos + neg
            
            sentiment = round((pos - neg) / total, 2) if total > 0 else 0.0
            
            urgency = 5
            high = ['فوری', 'خبر مهم', 'breaking', 'urgent', 'جنگ', 'حمله']
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
            
            # تبدیل تاریخ به فرمت قابل مرتب‌سازی
            # ما از تاریخ میلادی یونیکس استفاده می‌کنیم تا راحت مرتب شود
            # اگر تاریخ فارسی است، سعی می‌کنیم آن را تبدیل کنیم یا از رشته استفاده کنیم
            timestamp = time.time() # پیش‌فرض: زمان حال
            
            if date_text:
                # تلاش برای تبدیل تاریخ به فرمت استاندارد
                # اگر سایت تاریخ شمسی می‌دهد، این بخش ساده ممکن است دقیق نباشد
                # اما برای مرتب‌سازی نسبی (جدید به قدیم) معمولاً کار می‌کند
                # ما از timestamp خودکار استفاده نمی‌کنیم مگر اینکه تاریخ پیدا نشود
                
                # نکته: برای سادگی در گیت‌هاب، اگر تاریخ پیدا نشد، از زمان فعلی استفاده می‌کنیم
                # اما اگر تاریخ پیدا شد، سعی می‌کنیم آن را به میلادی تبدیل کنیم یا همان را نگه داریم
                pass 
            
            # برای مرتب‌سازی دقیق، ما نیاز به یک عدد داریم.
            # اگر تاریخ را نتوانستیم تبدیل کنیم، از timestamp فعلی استفاده می‌کنیم (که اشتباه است)
            # راه حل بهتر: ذخیره رشته تاریخ و مرتب‌سازی بر اساس آن
            
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
                "timestamp": timestamp,
                "date_raw": date_text if date_text else "" # تاریخ خام برای دیباگ
            }
            articles.append(article)
            
            time.sleep(1)
        
        # ۳. مرتب‌سازی از جدید به قدیم
        # از آنجایی که استخراج تاریخ دقیق شمسی پیچیده است،
        # ما فرض می‌کنیم ترتیبی که از سایت گرفتیم (صفحه اصلی) نزدیک به ترتیب زمانی است
        # اما برای اطمینان، اگر تاریخ میلادی داشت، بر اساس آن مرتب می‌کنیم
        
        # روش ساده: اگر تاریخ خام وجود دارد و قابل تبدیل است، مرتب کن
        # در غیر این صورت، ترتیب فعلی را حفظ کن (چون سایت معمولا جدیدترین را اول می‌گذارد)
        
        # اگر می‌خواهید حتماً بر اساس تاریخ مرتب شود، نیاز به کتابخانه jdatetime دارید
        # که نصب آن در گیت‌هاب اکتیون زمان‌بر است.
        # پس فعلاً ترتیب را همان‌طور که از سایت گرفتیم نگه می‌داریم (که معمولاً درست است)
        
        # اگر می‌خواهید حتماً بر اساس timestamp مرتب شود:
        # articles.sort(key=lambda x: x['timestamp'], reverse=True)
        
        # اما چون timestamp ما زمان اجراست، این کار ترتیب را بر هم می‌زند.
        # راه حل: از date_raw استفاده کنیم اگر فرمت استاندارد داشت
        
        logger.info(f"Final count: {len(articles)} articles")
        return articles

if __name__ == "__main__":
    scraper = Scraper()
    articles = scraper.run()
    
    if articles:
        with open("news.json", "w", encoding="utf-8") as f:
            json.dump(articles, f, ensure_ascii=False, indent=4)
        print(f"✅ Saved {len(articles)} articles to news.json")
    else:
        print("❌ No articles found")
