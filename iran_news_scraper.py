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
    
    def run(self):
        logger.info("Fetching homepage...")
        soup = self.get_page(self.BASE_URL)
        if not soup:
            logger.error("Failed to fetch")
            return []
        
        articles = []
        seen = set()
        
        # استخراج لینک‌های خبر
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
            
            # استخراج عنوان
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
            
            # استخراج عکس
            img = parent.find('img')
            image = img.get('src') or img.get('data-src') if img else None
            
            # استخراج دسته‌بندی
            cat = parent.find(class_=re.compile(r'category|tag', re.I))
            tag = cat.get_text(strip=True) if cat else "عمومی"
            
            article = {
                "title_fa": title,
                "title_en": "",
                "summary": [],
                "impact": "",
                "tag": tag,
                "urgency": 5,
                "sentiment": 0.0,
                "source": "Iran International",
                "url": url,
                "clean_url": url,
                "image": image,
                "timestamp": time.time()
            }
            articles.append(article)
            
            if len(articles) >= 30:
                break
        
        # اگر از RSS توانستیم بگیریم بهتره
        if not articles:
            for rss_url in [f"{self.BASE_URL}/rss.xml", f"{self.BASE_URL}/fa/rss"]:
                try:
                    r = self.session.get(rss_url, timeout=10)
                    if r.status_code == 200:
                        rss_soup = BeautifulSoup(r.content, 'xml')
                        for item in rss_soup.find_all('item')[:20]:
                            title_el = item.find('title')
                            link_el = item.find('link')
                            desc_el = item.find('description')
                            
                            if link_el and link_el.get_text(strip=True):
                                articles.append({
                                    "title_fa": title_el.get_text(strip=True) if title_el else "",
                                    "title_en": "",
                                    "summary": [desc_el.get_text(strip=True)] if desc_el else [],
                                    "impact": "",
                                    "tag": "عمومی",
                                    "urgency": 5,
                                    "sentiment": 0.0,
                                    "source": "Iran International",
                                    "url": link_el.get_text(strip=True),
                                    "clean_url": link_el.get_text(strip=True),
                                    "image": None,
                                    "timestamp": time.time()
                                })
                except:
                    pass
        
        logger.info(f"Found {len(articles)} articles")
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
