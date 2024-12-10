import feedparser
from datetime import datetime, timezone
import json
import os
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

class RSSService:
    def __init__(self, line_bot_api):
        self.line_bot_api = line_bot_api
        self.feeds_file = 'rss_feeds.json'
        self.last_check_file = 'last_check.json'
        self.feeds = self.load_feeds()
        self.last_check = self.load_last_check()
        self.scheduler = BackgroundScheduler()
        self.setup_scheduler()

    def load_feeds(self):
        """載入訂閱的 RSS feeds"""
        if os.path.exists(self.feeds_file):
            with open(self.feeds_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}  # 格式: {user_id/group_id: [{'url': url, 'name': name}, ...]}

    def save_feeds(self):
        """儲存 RSS feeds"""
        with open(self.feeds_file, 'w', encoding='utf-8') as f:
            json.dump(self.feeds, f, ensure_ascii=False, indent=2)

    def load_last_check(self):
        """載入上次檢查時間"""
        if os.path.exists(self.last_check_file):
            with open(self.last_check_file, 'r') as f:
                return json.load(f)
        return {}  # 格式: {url: timestamp}

    def save_last_check(self):
        """儲存檢查時間"""
        with open(self.last_check_file, 'w') as f:
            json.dump(self.last_check, f)

    def add_feed(self, user_id, url, name=None):
        """添加新的 RSS 訂閱"""
        try:
            # 驗證 RSS feed
            feed = feedparser.parse(url)
            if feed.get('bozo', 1):  # bozo=1 表示解析出錯
                return False, "無效的 RSS feed"

            # 如果沒有提供名稱，使用 feed 標題
            if not name:
                name = feed.feed.get('title', url)

            # 初始化用戶的訂閱列表
            if user_id not in self.feeds:
                self.feeds[user_id] = []

            # 檢查是否已經訂閱
            for feed in self.feeds[user_id]:
                if feed['url'] == url:
                    return False, "已經訂閱過這個 RSS feed"

            # 添加新訂閱
            self.feeds[user_id].append({
                'url': url,
                'name': name
            })
            self.save_feeds()
            
            # 初始化最後檢查時間
            self.last_check[url] = datetime.now(timezone.utc).timestamp()
            self.save_last_check()

            return True, f"成功訂閱 {name}"
        except Exception as e:
            return False, f"訂閱失敗：{str(e)}"

    def remove_feed(self, user_id, feed_index):
        """移除 RSS 訂閱"""
        try:
            if user_id not in self.feeds or feed_index >= len(self.feeds[user_id]):
                return False, "找不到指定的訂閱"

            removed_feed = self.feeds[user_id].pop(feed_index)
            self.save_feeds()
            return True, f"已取消訂閱 {removed_feed['name']}"
        except Exception as e:
            return False, f"取消訂閱失敗：{str(e)}"

    def list_feeds(self, user_id):
        """列出用戶的所有訂閱"""
        if user_id not in self.feeds or not self.feeds[user_id]:
            return "目前沒有訂閱的 RSS feed"

        message = "您目前訂閱的 RSS feeds：\n"
        for i, feed in enumerate(self.feeds[user_id]):
            message += f"{i+1}. {feed['name']}\n"
        return message

    def check_updates(self):
        """檢查所有訂閱的更新"""
        for user_id, feeds in self.feeds.items():
            for feed in feeds:
                url = feed['url']
                name = feed['name']
                last_check = self.last_check.get(url, 0)

                parsed = feedparser.parse(url)
                if parsed.get('bozo', 1):
                    continue

                new_entries = []
                for entry in parsed.entries:
                    # 取得文章發布時間
                    published = entry.get('published_parsed', None)
                    if published:
                        published_time = datetime(*published[:6], tzinfo=timezone.utc).timestamp()
                        if published_time > last_check:
                            new_entries.append(entry)

                # 發送新文章通知
                if new_entries:
                    message = f"【{name}】有新文章：\n\n"
                    for entry in new_entries[:5]:  # 最多顯示5篇
                        message += f"📰 {entry.get('title', '無標題')}\n"
                        message += f"🔗 {entry.get('link', '#')}\n\n"
                    
                    try:
                        self.line_bot_api.push_message(user_id, TextSendMessage(text=message))
                    except Exception as e:
                        print(f"發送更新通知失敗：{str(e)}")

                # 更新最後檢查時間
                self.last_check[url] = datetime.now(timezone.utc).timestamp()
                self.save_last_check()

    def setup_scheduler(self):
        """設定定時檢查"""
        # 每小時檢查一次更新
        self.scheduler.add_job(
            self.check_updates,
            CronTrigger(minute=0),  # 每小時整點執行
            id='check_rss_updates'
        )
        self.scheduler.start()
