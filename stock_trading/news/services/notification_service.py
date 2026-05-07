from __future__ import annotations

from datetime import time
import os

from django.core.mail import EmailMultiAlternatives
from django.utils import timezone

from news.models import NewsItem, NotificationLog
from trades.models import TradeRecord


class NotificationService:
    IMPORTANT_SENTIMENT_KEYWORDS = ("停牌", "减持", "增持", "预警", "调查", "业绩", "盈喜", "盈警")
    HIGH_PRIORITY_ANNOUNCEMENT_KEYWORDS = (
        "停牌",
        "复牌",
        "回购",
        "减持",
        "增持",
        "分红",
        "派息",
        "配股",
        "增发",
        "重组",
        "诉讼",
        "调查",
        "风险提示",
        "盈喜",
        "盈警",
        "业绩预告",
    )
    NOISE_KEYWORDS = (
        "精彩亮相",
        "市场热议",
        "再迎催化",
        "机构看好",
        "板块活跃",
        "概念走强",
        "震荡上涨",
        "资金关注",
    )
    CATEGORY_SCORES = {
        NewsItem.Category.ANNOUNCEMENT: 60,
        NewsItem.Category.RESEARCH: 35,
        NewsItem.Category.SENTIMENT: 20,
        NewsItem.Category.INDUSTRY: 10,
    }
    SOURCE_SCORES = {
        "东方财富": 30,
        "披露易": 30,
        "港交所": 30,
        "新浪财经": 10,
        "AASTOCKS": 10,
    }

    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self.sender = self.config.get("sender")
        self.channel = (
            self.config["channel"]
            if "channel" in self.config
            else os.getenv("NEWS_NOTIFY_CHANNEL", NotificationLog.Channel.EMAIL)
        )
        recipients_source = (
            self.config["recipients"] if "recipients" in self.config else os.getenv("NEWS_NOTIFY_EMAIL_TO", "")
        )
        self.recipients = self._split_list(recipients_source)
        self.from_email = (
            self.config["from_email"] if "from_email" in self.config else os.getenv("DEFAULT_FROM_EMAIL", "")
        )

    def score_news(self, news):
        score = self.CATEGORY_SCORES.get(news.category, 0)
        matched_rules: list[str] = [f"category:{news.category}:{score}"]

        source_score = self.SOURCE_SCORES.get(news.source, 0)
        if news.category != NewsItem.Category.INDUSTRY:
            score += source_score
            if source_score:
                matched_rules.append(f"source:{news.source}:{source_score}")

        haystack = f"{news.title} {news.summary}".lower()

        if news.category == NewsItem.Category.ANNOUNCEMENT:
            for keyword in self.HIGH_PRIORITY_ANNOUNCEMENT_KEYWORDS:
                if keyword.lower() in haystack:
                    score += 25
                    matched_rules.append(f"keyword:{keyword}:+25")

        if news.category == NewsItem.Category.SENTIMENT:
            for keyword in self.IMPORTANT_SENTIMENT_KEYWORDS:
                if keyword.lower() in haystack:
                    score += 60
                    matched_rules.append(f"sentiment:{keyword}:+60")

        for keyword in self.NOISE_KEYWORDS:
            if keyword.lower() in haystack:
                score -= 20
                matched_rules.append(f"noise:{keyword}:-20")

        if score >= 80:
            level = "P1"
        elif score >= 40:
            level = "P2"
        else:
            level = "P3"

        return {
            "priority_score": score,
            "priority_level": level,
            "matched_rules": matched_rules,
        }

    def should_push(self, news):
        return self.score_news(news)["priority_level"] == "P1"

    def should_digest(self, news):
        return self.score_news(news)["priority_level"] == "P2"

    def push(self, news):
        decision = self.score_news(news)
        message = self._format_message(news)
        sender = self.sender

        if sender is None and self.channel == NotificationLog.Channel.EMAIL and self.recipients:
            sender = self._send_email_notification

        if decision["priority_level"] != "P1":
            self._log_pending(news)
            return False

        if not callable(sender):
            self._log_pending(news)
            return False

        success = bool(sender(message, news, self.channel))
        self._log_delivery(news, success)
        return success

    def push_digest(self, items):
        digest_items = [item for item in items if self.should_digest(item) and not item.pushed]
        if not digest_items:
            return False

        lines = ["News summary"]
        for item in digest_items:
            lines.append(f"- {item.stock_code} | {item.title} | {item.source}")
        message = "\n".join(lines)

        sender = self.sender
        if sender is None and self.channel == NotificationLog.Channel.EMAIL and self.recipients:
            sender = self._send_email_summary
        if not callable(sender):
            for item in digest_items:
                self._log_pending(item)
            return False

        success = bool(sender(message, digest_items, self.channel))
        for item in digest_items:
            self._log_delivery(item, success)
        return success

    def batch_push_summary(self, items):
        return self.push_digest(items)

    def is_trading_hours(self, market: str) -> bool:
        now = timezone.localtime().time()
        if market == TradeRecord.Market.A_STOCK:
            return time(9, 15) <= now <= time(15, 0)
        if market == TradeRecord.Market.HK_STOCK:
            return time(9, 15) <= now <= time(16, 15)
        return False

    def _format_message(self, news):
        return "\n".join(
            [
                news.title,
                f"Source: {news.source}",
                f"Summary: {news.summary or 'N/A'}",
                f"Link: {news.url}",
            ]
        )

    def _send_email_notification(self, message, news, channel):
        if not self.recipients:
            return False
        subject = f"[StockAgent][{news.stock_code}] {news.title}"
        email = EmailMultiAlternatives(
            subject=subject,
            body=message,
            from_email=self.from_email or None,
            to=self.recipients,
        )
        return email.send(fail_silently=False) > 0

    def _send_email_summary(self, message, items, channel):
        if not self.recipients:
            return False
        subject = f"[StockAgent] News Summary ({len(items)})"
        email = EmailMultiAlternatives(
            subject=subject,
            body=message,
            from_email=self.from_email or None,
            to=self.recipients,
        )
        return email.send(fail_silently=False) > 0

    def _log_pending(self, news):
        NotificationLog.objects.create(
            news_item=news,
            channel=self.channel,
            status=NotificationLog.Status.PENDING,
            retry_count=0,
        )

    def _log_delivery(self, news, success: bool):
        NotificationLog.objects.create(
            news_item=news,
            channel=self.channel,
            status=NotificationLog.Status.SUCCESS if success else NotificationLog.Status.FAILED,
            retry_count=0 if success else 1,
            sent_at=timezone.now() if success else None,
        )
        if success:
            news.pushed = True
            news.save(update_fields=["pushed"])

    def _split_list(self, value: str | list[str] | None):
        if not value:
            return []
        if isinstance(value, list):
            return [item.strip() for item in value if item and item.strip()]
        return [item.strip() for item in str(value).split(",") if item.strip()]
