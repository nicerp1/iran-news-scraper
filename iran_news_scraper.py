#!/usr/bin/env python3
import requests
from bs4 import BeautifulSoup
import json
import re
import time
from urllib.parse import urljoin
import logging
import sys
import os

# تنظیم لاگ‌گیری برای مشاهده خطاها در گیت‌هاب
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

class NewsScraper:
    BASE_URL = "https://www.iranintl.com"
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36',
            'Accept-Language': 'fa-IR,fa;q=0.9,en-US;q=0.8,en;q=0.7',
        })

    def get_page(self, url):
        try:
            r = self.session.get(url, timeout=45)
            r.raise_for_status()
            return BeautifulSoup(r.content, 'html.parser')
        except Exception as e:
            logger.error(f"Network error fetching {url}: {e}")
            return None

    def to_shamsi_string(self, date_str):
        """تبدیل رشته تاریخ به فرمت شمسی قابل خواندن"""
        if not date_str:
            return "نامشخص"
        
        farsi_digits = '۰۱۲۳۴۵۶۷۸۹'
        clean_str = date_str
        for f, e in zip(farsi_digits, '0123456789'):
            clean_str = clean_str.replace(f, e)
            
        numbers = re.findall(r'\d+', clean_str)
        if len(numbers) >= 3:
            try:
                y = int(numbers[0])
                m = int(numbers[1])
                d = int(numbers[2])
                
                if 1300 <= y <= 1500:
                    return f"{y:04d}/{m:02d}/{d:02d}"
                else:
                    shamsi_y = y + 621
                    return f"{shamsi_y:04d}/{m:02d}/{d:02d}"
            except ValueError:
                return date_str
        return date_str

    def extract_sort_key(self, date_str):
        """استخراج کلید عددی برای مرتب‌سازی"""
        if not date_str:
            return 0
        
        farsi_digits = '۰۱۲۳۴۵۶۷۸۹'
        clean_str = date_str
        for f, e in zip(farsi_digits, '0123456789'):
            clean_str = clean_str.replace(f, e)
            
        numbers = re.findall(r'\d+', clean_str)
        
        if len(numbers) >= 3:
            try:
                y = int(numbers[0])
                m = int(numbers[1])
                d = int(numbers[2])
                return y * 10000 + m * 100 + d
            except ValueError:
                return 0
        return 0

    def get_article_content(self, url):
        """استخراج متن، تاریخ و تصویر از صفحه خبر"""
        try:
            soup = self.get_page(url)
            if not soup:
                return [], None, None, None

            date_text = ""
            time_tag = soup.find('time')
            if time_tag:
                date_text = time_tag.get('datetime') or time_tag.get_text(strip=True)
            
            if not date_text:
                for cls in ['date', 'published', 'timestamp', 'entry-date']:
                    el = soup.find(class_=re.compile(cls, re.I))
                    if el:
                        date_text = el.get_text(strip=True)
                        break
            
            image = None
            og_img = soup.find('meta', property='og:image')
            if og_img:
                image = og_img.get('content')
            
            paragraphs = []
            content_div = soup.find('div', class_=re.compile(r'article-body|story-content|post-content', re.I))
            if not content_div:
                content_div = soup.find('article') or soup
                
            if content_div:
                for p in content_div.find_all('p'):
                    text = p.get_text(strip=True)
                    if text and len(text) > 50:
                        paragraphs.append(text)

            return paragraphs[:10], date_text, image
        except Exception as e:
            logger.error(f"Error parsing article {url}: {e}")
            return [], None, None

    def run(self):
        logger.info("Starting news scraper...")
        try:
            soup = self.get_page(self.BASE_URL)
            if not soup:
                logger.error("Failed to load homepage")
                return []

            articles = []
            seen_urls = set()

            # استخراج لینک‌های خبری
            news_items = soup.find_all('div', class_=re.compile(r'article-card|card|post', re.I))
            links_to_process = []
            
            for item in news_items:
                link_tag = item.find('a', href=True)
                if link_tag:
                    href = link_tag['href']
                    if 'iranintl.com' in href and '/a/' in href:
                        full_url = urljoin(self.BASE_URL, href)
                        if full_url not in seen_urls:
                            seen_urls.add(full_url)
                            title_tag = item.find(['h3', 'h4', 'h2', 'h5'])
                            title = title_tag.get_text(strip=True) if title_tag else link_tag.get_text(strip=True)
                            if title:
                                links_to_process.append({
                                    "url": full_url,
                                    "title": title
                                })

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
                    if len(links_to_process) >= 15:
                        break

            logger.info(f"Found {len(links_to_process)} articles to process.")

            for item in links_to_process:
                url = item['url']
                logger.info(f"Processing: {item['title'][:40]}...")
                
                try:
                    summary, date_text, image = self.get_article_content(url)
                    
                    if not summary:
                        logger.warning(f"Skipped {url} due to no content.")
                        continue

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

                    sort_key = self.extract_sort_key(date_text)
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
                    time.sleep(1.5)
                except Exception as e:
                    logger.error(f"Error processing article {url}: {e}")
                    continue

            articles.sort(key=lambda x: x['sort_key'], reverse=True)
            
            for art in articles:
                del art['sort_key']

            logger.info(f"Success! Processed {len(articles)} articles.")
            return articles
        except Exception as e:
            logger.error(f"Critical error in run method: {e}")
            return []

if __name__ == "__main__":
    try:
        scraper = NewsScraper()
        articles = scraper.run()
        
        # همیشه فایل را می‌نویسیم، حتی اگر لیست خالی باشد
        with open("news.json", "w", encoding="utf-8") as f:
            json.dump(articles, f, ensure_ascii=False, indent=4)
            
        print(f"✅ Saved {len(articles)} articles to news.json")
        if articles:
            print(f"📅 Sample Date (Shamsi): {articles[0].get('date_shamsi')}")
        else:
            print("⚠️ No articles found. Check logs for details.")
            
    except Exception as e:
        logger.critical(f"Fatal error: {e}")
        # حتی در صورت خطای کشیده، سعی می‌کنیم یک فایل خالی بسازیم تا گیت‌هاب اکشن متوقف نشود
        try:
            with open("news.json", "w", encoding="utf-8") as f:
                json.dump([], f)
        except:
            pass
        sys.exit(1)
