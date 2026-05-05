name: News Scraper

on:
  schedule:
    # اجرای هر ساعت در دقیقه ۰ (مثلاً ۱۰:۰۰، ۱۱:۰۰)
    - cron: '0 * * * *'
  workflow_dispatch: # امکان اجرای دستی

jobs:
  scrape:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout code
        uses: actions/checkout@v4
        with:
          token: ${{ secrets.GH_TOKEN }}

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt

      - name: Run scraper
        run: |
          python iran_news_scraper.py

      - name: Commit and push if changed
        if: success()
        run: |
          git config --local user.email "action@github.com"
          git config --local user.name "GitHub Action"
          
          git add .
          git diff --quiet && git diff --staged --quiet || git commit -m "Update news data" -a
          
          git push
