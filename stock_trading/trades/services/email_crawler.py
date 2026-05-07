from __future__ import annotations

from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime
from datetime import datetime
from decimal import Decimal
from email import message_from_bytes
from email.message import Message
import imaplib
import re

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from trades.models import TradeRecord


class EmailCrawler:
    EXECUTED_STATUSES = {"全部執行", "全部执行", "FULLY EXECUTED"}
    CANCELLED_STATUSES = {"全部取消", "FULLY CANCELLED", "已取消"}
    LABEL_PATTERNS = {
        "stock_code": [r"(?:Stock\s*Code|证券代码)\s*[:：]\s*(?P<value>[A-Z0-9.\-]+)"],
        "stock_name": [r"(?:Stock\s*Name|证券名称)\s*[:：]\s*(?P<value>.+)"],
        "direction": [r"(?:Side|Direction|买卖方向)\s*[:：]\s*(?P<value>BUY|SELL|Buy|Sell|买入|卖出)"],
        "price": [r"(?:Price|成交价格|成交價|价格)\s*[:：]\s*(?P<value>[A-Z$HKDUSD￥¥\s]*[\d,]+(?:\.\d+)?)"],
        "quantity": [r"(?:Quantity|已成交數量\(股/單位\)|已成交数量\(股/单位\)|成交数量|數量|数量)\s*[:：]\s*(?P<value>[\d,]+)"],
        "trade_time": [r"(?:Trade\s*Time|成交时间|交易时间)\s*[:：]\s*(?P<value>[0-9T:\-\/\s\+]+)"],
        "commission": [r"(?:Commission|佣金)\s*[:：]\s*(?P<value>[A-Z$HKDUSD￥¥\s]*[\d,]+(?:\.\d+)?)"],
        "stamp_duty": [r"(?:Stamp\s*Duty|印花税|印花稅)\s*[:：]\s*(?P<value>[A-Z$HKDUSD￥¥\s]*[\d,]+(?:\.\d+)?)"],
        "other_fees": [r"(?:Other\s*Fees|其他费用|其他費用)\s*[:：]\s*(?P<value>[A-Z$HKDUSD￥¥\s]*[\d,]+(?:\.\d+)?)"],
        "market": [r"(?:Market|市场)\s*[:：]\s*(?P<value>A_STOCK|HK_STOCK|A股|港股)"],
        "status": [r"(?:交易狀況|交易状态|Status)\s*[:：]\s*(?P<value>.+)"],
        "trade_id": [r"(?:交易編號|交易编号|Trade\s*ID)\s*[:：]\s*(?P<value>[A-Z]\d+)"],
        "stock_line": [r"(?:股票名稱/\s*股票編號|股票名称/\s*股票编号)\s*[:：]\s*(?P<value>.+)"],
    }
    SUBJECT_PATTERN = re.compile(
        r"(?P<status>全部執行|全部执行|全部取消|Fully Executed|Fully Cancelled)\s*[:：]\s*"
        r"(?P<direction>買入|买入|沽出|卖出|BUY|SELL)"
        r"\s*(?P<stock_code>\d{5})\s*[:：]\s*"
        r"(?P<stock_name>.+?)\s*的股/單位"
        r"\(交易編號\s*[:：]\s*(?P<trade_id>[A-Z]\d+)\)",
        re.IGNORECASE,
    )

    def __init__(self, config: dict):
        self.config = config
        self._client = None

    def connect(self) -> None:
        host = self.config.get("host")
        username = self.config.get("username")
        password = self.config.get("password")
        port = self.config.get("port", 993)

        if not all([host, username, password]):
            raise ValueError("IMAP host, username and password are required.")

        client = imaplib.IMAP4_SSL(host, port)
        client.login(username, password)
        mailbox = self.config.get("mailbox", "INBOX")
        client.select(mailbox)
        self._client = client

    def test_connection(self) -> bool:
        self.connect()
        return self._client is not None

    def close(self) -> None:
        if self._client is None:
            return
        try:
            self._client.logout()
        finally:
            self._client = None

    def fetch_hsbc_emails(self, since_date):
        if "emails" in self.config:
            return list(self.config["emails"])

        if self._client is None:
            self.connect()

        sender_filters = self._split_filters(
            self.config.get("sender_filters") or self.config.get("sender_keyword") or "hsbc"
        )
        subject_include_keywords = self._split_filters(
            self.config.get("subject_include_keywords")
            or "全部執行,全部执行,全部取消"
        )
        subject_exclude_keywords = self._split_filters(
            self.config.get("subject_exclude_keywords") or "登入通知,login notification"
        )
        subject_search_terms = self._split_filters(self.config.get("subject_search_terms"))
        header_fetch_batch_size = int(self.config.get("header_fetch_batch_size", 100))

        candidate_ids: list[bytes] = []
        if sender_filters:
            seen_ids = set()
            for sender in sender_filters:
                criteria = f'(SINCE "{since_date.strftime("%d-%b-%Y")}" FROM "{sender}")'
                status, data = self._client.search(None, criteria)
                if status != "OK":
                    continue
                ids = data[0].split() if data and data[0] else []
                for email_id in ids:
                    if email_id not in seen_ids:
                        candidate_ids.append(email_id)
                        seen_ids.add(email_id)
        else:
            criteria = f'(SINCE "{since_date.strftime("%d-%b-%Y")}")'
            status, data = self._client.search(None, criteria)
            if status != "OK":
                raise RuntimeError("Failed to search emails from IMAP server.")
            candidate_ids = data[0].split() if data and data[0] else []

        messages = []
        for email_id, header_message in self._iter_header_messages(candidate_ids, header_fetch_batch_size):
            sender_value = self._decode_mime_header(header_message.get("From", ""))
            subject_value = self._decode_mime_header(header_message.get("Subject", ""))

            if sender_filters and not any(keyword.lower() in sender_value.lower() for keyword in sender_filters):
                continue
            if subject_search_terms and not any(
                keyword.lower() in subject_value.lower() for keyword in subject_search_terms
            ):
                continue
            if subject_exclude_keywords and any(
                keyword.lower() in subject_value.lower() for keyword in subject_exclude_keywords
            ):
                continue
            if subject_include_keywords and not any(
                keyword.lower() in subject_value.lower() for keyword in subject_include_keywords
            ):
                continue

            status, payload = self._client.fetch(email_id, "(RFC822)")
            if status != "OK" or not payload or not payload[0]:
                continue
            raw_bytes = payload[0][1]
            messages.append(message_from_bytes(raw_bytes))
        return messages

    def parse_trade_email(self, email):
        subject = self._extract_subject(email)
        text = self._extract_text(email)
        metadata = self._extract_metadata(subject, text, email)
        status = self._normalize_status(metadata["status"])
        if status in self.CANCELLED_STATUSES:
            raise ValueError("Cancelled trade email should not be recorded.")
        if status not in self.EXECUTED_STATUSES:
            raise ValueError(f"Unsupported trade status: {status}")

        parsed = {
            "stock_code": metadata["stock_code"],
            "stock_name": metadata["stock_name"],
            "direction": metadata["direction"],
            "price": self._parse_decimal(self._extract_value("price", text)),
            "quantity": int(self._clean_numeric(self._extract_value("quantity", text))),
            "trade_time": metadata["trade_time"],
            "commission": self._parse_decimal(self._extract_value("commission", text, default="0")),
            "stamp_duty": self._parse_decimal(self._extract_value("stamp_duty", text, default="0")),
            "other_fees": self._parse_decimal(self._extract_value("other_fees", text, default="0")),
            "market": metadata.get("market", TradeRecord.Market.HK_STOCK),
            "source": TradeRecord.Source.HSBC_EMAIL,
        }
        return parsed

    def format_trade_record(self, record) -> str:
        data = dict(record)
        trade_time = data["trade_time"]
        if hasattr(trade_time, "astimezone"):
            trade_time_text = trade_time.astimezone(timezone.get_current_timezone()).isoformat()
        else:
            trade_time_text = str(trade_time)

        lines = [
            f"Market: {data.get('market', TradeRecord.Market.HK_STOCK)}",
            f"Stock Code: {str(data['stock_code']).strip().upper()}",
            f"Stock Name: {str(data['stock_name']).strip()}",
            "Status: 全部執行",
            f"Side: {data['direction']}",
            f"Price: {self._format_decimal(data['price'])}",
            f"Quantity: {int(data['quantity'])}",
            f"Trade Time: {trade_time_text}",
            f"Commission: {self._format_decimal(data.get('commission', 0))}",
            f"Stamp Duty: {self._format_decimal(data.get('stamp_duty', 0))}",
            f"Other Fees: {self._format_decimal(data.get('other_fees', 0))}",
        ]
        return "\n".join(lines)

    def _extract_text(self, email) -> str:
        if isinstance(email, dict):
            return str(email.get("body", ""))
        if isinstance(email, str):
            return email
        if isinstance(email, bytes):
            return email.decode("utf-8", errors="ignore")
        if isinstance(email, Message):
            parts = []
            if email.is_multipart():
                for part in email.walk():
                    if part.get_content_maintype() == "multipart":
                        continue
                    if "attachment" in (part.get("Content-Disposition") or ""):
                        continue
                    payload = part.get_payload(decode=True)
                    if payload is None:
                        continue
                    charset = part.get_content_charset() or "utf-8"
                    parts.append(payload.decode(charset, errors="ignore"))
            else:
                payload = email.get_payload(decode=True)
                if payload is not None:
                    charset = email.get_content_charset() or "utf-8"
                    parts.append(payload.decode(charset, errors="ignore"))
                else:
                    parts.append(email.get_payload())
            return "\n".join(parts)
        raise TypeError(f"Unsupported email type: {type(email)!r}")

    def _extract_subject(self, email) -> str:
        if isinstance(email, dict):
            return str(email.get("subject", ""))
        if isinstance(email, Message):
            return self._decode_mime_header(str(email.get("Subject", "")))
        return ""

    def _extract_metadata(self, subject: str, text: str, email) -> dict:
        subject_data = self._parse_subject(subject)
        status = subject_data.get("status") or self._extract_value("status", text, default="全部執行")
        direction = subject_data.get("direction") or self._normalize_direction(self._extract_value("direction", text))
        stock_code = subject_data.get("stock_code")
        stock_name = subject_data.get("stock_name")

        if not stock_code or not stock_name:
            stock_line = self._extract_value("stock_line", text, default="")
            if stock_line:
                stock_name, stock_code = self._parse_stock_line(stock_line)
            else:
                stock_code = self._extract_value("stock_code", text)
                stock_name = self._extract_value("stock_name", text)

        market_value = self._extract_value("market", text, default="HK_STOCK")
        trade_time_value = self._extract_value("trade_time", text, default="")
        trade_time = self._parse_trade_time(trade_time_value, email)

        return {
            "status": status,
            "direction": direction,
            "stock_code": str(stock_code).strip().upper(),
            "stock_name": str(stock_name).strip(),
            "market": self._normalize_market(market_value),
            "trade_time": trade_time,
            "trade_id": subject_data.get("trade_id") or self._extract_value("trade_id", text, default=""),
        }

    def _parse_subject(self, subject: str) -> dict:
        if not subject:
            return {}
        match = self.SUBJECT_PATTERN.search(subject.strip())
        if not match:
            return {}
        return {
            "status": match.group("status").strip(),
            "direction": self._normalize_direction(match.group("direction")),
            "stock_code": match.group("stock_code").strip(),
            "stock_name": match.group("stock_name").strip(),
            "trade_id": match.group("trade_id").strip(),
        }

    def _parse_stock_line(self, stock_line: str):
        match = re.search(r"(?P<name>.+?)\s*\((?P<code>\d{5})\)", stock_line.strip())
        if not match:
            raise ValueError(f"Could not parse stock line: {stock_line}")
        return match.group("name").strip(), match.group("code").strip()

    def _extract_value(self, field: str, text: str, default=None) -> str:
        for pattern in self.LABEL_PATTERNS[field]:
            match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if match:
                return match.group("value").strip()
        if default is not None:
            return default
        raise ValueError(f"Could not parse {field} from email content.")

    def _normalize_direction(self, value: str) -> str:
        normalized = value.strip().upper()
        if normalized in {"BUY", "买入", "買入"}:
            return TradeRecord.Direction.BUY
        if normalized in {"SELL", "卖出", "沽出"}:
            return TradeRecord.Direction.SELL
        raise ValueError(f"Unsupported direction value: {value}")

    def _normalize_market(self, value: str) -> str:
        normalized = value.strip().upper()
        if normalized in {"HK_STOCK", "港股"}:
            return TradeRecord.Market.HK_STOCK
        if normalized in {"A_STOCK", "A股"}:
            return TradeRecord.Market.A_STOCK
        raise ValueError(f"Unsupported market value: {value}")

    def _normalize_status(self, value: str) -> str:
        return value.strip().upper().replace("執", "执")

    def _parse_decimal(self, value: str) -> Decimal:
        return Decimal(self._clean_numeric(value))

    def _clean_numeric(self, value: str) -> str:
        return re.sub(r"[^\d.\-]", "", value)

    def _parse_trade_time(self, value: str, email=None):
        if value:
            parsed = parse_datetime(value.strip())
            if parsed is None:
                parsed = datetime.fromisoformat(value.strip().replace("/", "-"))
        else:
            parsed = self._extract_email_date(email)

        if timezone.is_naive(parsed):
            parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
        return parsed.astimezone(timezone.get_current_timezone())

    def _extract_email_date(self, email):
        if isinstance(email, dict) and email.get("date"):
            parsed = parse_datetime(str(email["date"]).strip())
            if parsed is None:
                parsed = parsedate_to_datetime(str(email["date"]).strip())
            return parsed

        if isinstance(email, Message) and email.get("Date"):
            return parsedate_to_datetime(email.get("Date"))

        raise ValueError("Trade time is missing and no email Date header was provided.")

    def _decode_mime_header(self, value: str) -> str:
        if not value:
            return ""
        return str(make_header(decode_header(value)))

    def _iter_header_messages(self, candidate_ids: list[bytes], batch_size: int):
        for offset in range(0, len(candidate_ids), batch_size):
            chunk = candidate_ids[offset : offset + batch_size]
            fetch_ids = b",".join(chunk)
            status, payload = self._client.fetch(fetch_ids, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
            if status != "OK" or not payload:
                continue

            current_id = None
            for item in payload:
                if isinstance(item, tuple) and len(item) == 2:
                    meta = item[0]
                    match = re.match(rb"(\d+)\s", meta)
                    if match:
                        current_id = match.group(1)
                    if current_id is not None:
                        yield current_id, message_from_bytes(item[1])

    def _split_filters(self, value: str | list[str] | None):
        if not value:
            return []
        if isinstance(value, list):
            return [item.strip() for item in value if item and item.strip()]
        return [item.strip() for item in str(value).split(",") if item.strip()]

    def _format_decimal(self, value) -> str:
        return f"{Decimal(str(value)):.4f}"
