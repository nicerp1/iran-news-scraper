#!/usr/bin/env python3
import requests
from bs4 import BeautifulSoup
import json
import re
import time
from urllib.parse import urljoin
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
    
    def get_article_text(self, url):
        """استخراج متن کامل خبر از صفحه داخلی"""
        soup = self.get_page(url)
        if not soup:
            return []
        
        # تلاش برای پیدا کردن بدنه اصلی خبر
        # معمولاً کلاس‌هایی مثل article-body, story-content, post-content دارند
        content_div = soup.find('div', class_=re.compile(r'article-body|story-content|post-content|entry-content', re.I))
        
        if not content_div:
            # اگر پیدا نشد، کل div اصلی را بگیر
            content_div = soup.find('article') or soup
        
        if not content_div:
            return []
        
        paragraphs = []
        for p in content_div.find_all('p'):
            text = p.get_text(strip=True)
            # پاراگراف‌های کوتاه (مثل کپشن عکس یا لینک) را حذف کن
            if text and len(text) > 100:
                paragraphs.append(text)
        
        return paragraphs[:10]  # حداکثر ۱۰ پاراگراف برای جلوگیری از حجم زیاد
    
    def run(self):
        logger.info("Fetching homepage...")
        soup = self.get_page(self.BASE_URL)
        if not soup:
            logger.error("Failed to fetch homepage")
            return []
        
        articles = []
        seen = set()
        
        # ۱. استخراج لینک‌های خبر از صفحه اصلی
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
            
            # استخراج عنوان و اطلاعات اولیه
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
            
            img = parent.find('img')
            image = img.get('src') or img.get('data-src') if img else None
            
            cat = parent.find(class_=re.compile(r'category|tag', re.I))
            tag = cat.get_text(strip=True) if cat else "عمومی"
            
            raw_links.append({
                "url": url,
                "title": title,
                "image": image,
                "tag": tag
            })
            
            if len(raw_links) >= 10: # فقط ۱۰ خبر اول را پردازش کن تا سریع باشد
                break
        
        # ۲. برای هر لینک، برو داخل صفحه و متن را بگیر
        for item in raw_links:
            url = item['url']
            logger.info(f"Processing: {item['title'][:50]}...")
            
            # استخراج متن کامل
            summary = self.get_article_text(url)
            
            # تحلیل ساده سنجیمنت (احساس متن)
            full_text = " ".join(summary).lower()
            positive_words = ['موفق', 'پیشرفت', 'امید', 'خوب', 'بهبود', 'success', 'hope']
            negative_words = ['جنگ', 'بحران', 'تنش', 'خشونت', 'تهدید', 'war', 'crisis', 'tension']
            
            pos = sum(1 for w in positive_words if w in full_text)
            neg = sum(1 for w in negative_words if w in full_text)
            total = pos + neg
            
            sentiment = round((pos - neg) / total, 2) if total > 0 else 0.0
            
            # تعیین فوریت
            urgency = 5
            high = ['فوری', 'خبر مهم', 'breaking', 'urgent', 'جنگ', 'حمله']
            for w in high:
                if w in full_text:
                    urgency = 8
                    break
            
            # تولید پیام تأثیر
            impact = ""
            if sentiment < -0.3 and urgency > 6:
                impact = "این رویداد می‌تواند تأثیرات جدی بر وضعیت امنیتی و سیاسی منطقه داشته باشد."
            elif sentiment < 0:
                impact = "این خبر می‌تواند بر فضای عمومی و افکار عمومی تأثیرگذار باشد."
            elif sentiment > 0.3:
                impact = "این خبر می‌تواند تأثیر مثبتی بر فضای عمومی داشته باشد."
            else:
                impact = "این خبر در حال حاضر تأثیر قابل توجهی بر وضعیت کلی ندارد."
            
            article = {
                "title_fa": item['title'],
                "title_en": "",
                "summary": summary,
                "impact": impact,
                "tag": item['tag'],
                "urgency": urgency,
                "sentiment": sentiment,
                "source": "Iran International",
                "url": url,
                "clean_url": url,
                "image": item['image'],
                "timestamp": time.time()
            }
            articles.append(article)
            
            # استراحت کوتاه بین درخواست‌ها
            time.sleep(1)
        
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
