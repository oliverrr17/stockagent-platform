from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.utils import timezone

from analysis.services.market_data import build_market_data_provider
from config.trading_calendar import is_cn_equity_trading_day
from portfolio.models import (
    CashAccount,
    CashFlow,
    FXRate,
    PortfolioPerformanceSnapshot,
    Position,
    PositionDailyContributionSnapshot,
    SecurityPriceSnapshot,
)
from trades.models import TradeRecord


def _local_date(value) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        if timezone.is_naive(value):
            value = timezone.make_aware(value, timezone.get_current_timezone())
        return timezone.localtime(value).date()
    return date.fromisoformat(str(value))


def _to_decimal(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _snapshot_trade_date(snapshot: dict | None) -> date | None:
    if not snapshot:
        return None

    raw_value = snapshot.get("trade_date")
    if not raw_value:
        return None

    text = str(raw_value).strip()
    if len(text) == 8 and text.isdigit():
        return datetime.strptime(text, "%Y%m%d").date()
    if "T" in text:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    return date.fromisoformat(text)


@dataclass
class PortfolioPoint:
    date: str
    total_assets_cny: float
    total_return_cny: float
    daily_return_pct: float
    monthly_return_pct: float
    yearly_return_pct: float
    cumulative_return_pct: float


class PortfolioAnalyticsService:
    def __init__(self, market_data_provider=None):
        self.market_data_provider = market_data_provider or build_market_data_provider()
        self._snapshot_cache: dict[tuple[str, str, str], dict] = {}
        self._fx_cache: dict[tuple[str, str, str], Decimal] = {}

    def get_overview(
        self,
        start_date: date | None = None,
        active_rows: list[dict] | None = None,
        cash_balances: dict | None = None,
    ):
        effective_start = start_date or self._effective_start_date()
        effective_end = self._effective_end_date()
        active_rows = active_rows if active_rows is not None else self.get_position_analytics(as_of_date=effective_end)
        cash_balances = cash_balances if cash_balances is not None else self.get_cash_balances(as_of_date=effective_end)
        needs_hkd_rate = (
            _to_decimal(cash_balances["HKD"]["balance"]) != Decimal("0")
            or any(row["market"] == TradeRecord.Market.HK_STOCK for row in active_rows)
        )
        fx_rate = self.get_fx_rate("HKD", "CNY", effective_end) if needs_hkd_rate else Decimal("1")
        total_assets_cny = (
            _to_decimal(cash_balances["CNY"]["balance"])
            + _to_decimal(cash_balances["HKD"]["balance"]) * fx_rate
            + sum(_to_decimal(row["market_value_cny"]) for row in active_rows)
        )
        unrealized_pnl_cny = sum(_to_decimal(row["unrealized_pnl_cny"]) for row in active_rows)
        realized_pnl_cny = self._realized_pnl_since(effective_start)
        total_return_cny = realized_pnl_cny + unrealized_pnl_cny
        curves = self._build_curves(effective_start, effective_end)
        latest_returns = self._latest_returns(curves["daily"])

        return {
            "base_currency": "CNY",
            "start_date": effective_start.isoformat(),
            "valuation_date": effective_end.isoformat(),
            "audit_status": curves["daily"][-1].get("audit_status", PortfolioPerformanceSnapshot.AuditStatus.PROVISIONAL)
            if curves["daily"]
            else PortfolioPerformanceSnapshot.AuditStatus.PROVISIONAL,
            "cash_balances": {
                "CNY": {
                    "balance": float(cash_balances["CNY"]["balance"]),
                    "balance_cny": float(cash_balances["CNY"]["balance"]),
                },
                "HKD": {
                    "balance": float(cash_balances["HKD"]["balance"]),
                    "balance_cny": float((_to_decimal(cash_balances["HKD"]["balance"]) * fx_rate).quantize(Decimal("0.0001"))),
                    "fx_rate": float(fx_rate),
                },
            },
            "positions_market_value_cny": float(sum(_to_decimal(row["market_value_cny"]) for row in active_rows)),
            "total_assets_cny": float(total_assets_cny),
            "realized_pnl_cny": float(realized_pnl_cny),
            "unrealized_pnl_cny": float(unrealized_pnl_cny),
            "total_return_cny": float(total_return_cny),
            "returns": latest_returns,
            "curves": curves,
        }

    def get_daily_contributions(self, snapshot_date: date):
        snapshot = PortfolioPerformanceSnapshot.objects.get(snapshot_date=snapshot_date)
        rows = PositionDailyContributionSnapshot.objects.filter(snapshot_date=snapshot_date).order_by("market", "stock_code")
        return {
            "snapshot_date": snapshot.snapshot_date.isoformat(),
            "audit_status": snapshot.audit_status,
            "external_flow_cny": float(snapshot.external_flow_cny),
            "computed_daily_pnl_cny": float(snapshot.computed_daily_pnl_cny),
            "contributions": [
                {
                    "stock_code": row.stock_code,
                    "stock_name": row.stock_name,
                    "market": row.market,
                    "start_quantity": row.start_quantity,
                    "end_quantity": row.end_quantity,
                    "previous_close": float(row.previous_close),
                    "latest_price": float(row.latest_price),
                    "trade_cash_delta": float(row.trade_cash_delta),
                    "daily_pnl_native": float(row.daily_pnl_native),
                    "daily_pnl_cny": float(row.daily_pnl_cny),
                    "fx_rate": float(row.fx_rate),
                    "price_source": row.price_source,
                    "source_trade_date": row.source_trade_date.isoformat() if row.source_trade_date else None,
                    "degraded": row.degraded,
                    "degraded_reason": row.degraded_reason,
                    "audit_status": row.audit_status,
                }
                for row in rows
            ],
        }

    def get_cash_balances(self, as_of_date: date, include_trade_cash: bool = True):
        balances = {
            "CNY": {"balance": Decimal("0")},
            "HKD": {"balance": Decimal("0")},
        }
        for account in CashAccount.objects.all():
            amount = Decimal("0")
            for flow in account.flows.filter(occurred_at__date__lte=as_of_date):
                amount += self._signed_cash_flow(flow)
            balances[account.currency]["balance"] = amount
        if include_trade_cash:
            for trade in TradeRecord.objects.filter(trade_time__date__lte=as_of_date):
                currency = "HKD" if trade.market == TradeRecord.Market.HK_STOCK else "CNY"
                gross_amount = _to_decimal(trade.price) * Decimal(trade.quantity)
                fees = self._trade_fee_total(trade)
                if trade.direction == TradeRecord.Direction.SELL:
                    balances[currency]["balance"] += gross_amount - fees
                else:
                    balances[currency]["balance"] -= gross_amount + fees
        return balances

    def get_position_analytics(self, as_of_date: date | None = None):
        target_date = as_of_date or self._effective_end_date()
        baseline_states = self._baseline_states(target_date)
        current_holdings = self._holdings_on_date(target_date)
        trades_by_code = defaultdict(list)
        for trade in TradeRecord.objects.filter(trade_time__date=target_date).order_by("trade_time", "id"):
            trades_by_code[trade.stock_code].append(trade)
        rows = []
        for position in Position.objects.filter(status=Position.Status.ACTIVE, quantity__gt=0).order_by("stock_code"):
            snapshot = self._get_snapshot(position.stock_code, position.market, target_date)
            latest_price = _to_decimal(snapshot.get("latest_price") or position.weighted_avg_cost)
            previous_close = _to_decimal(snapshot.get("previous_close") or latest_price)
            if self._uses_stale_a_share_daily_bar(snapshot, position.market, target_date):
                previous_close = latest_price
            degraded = bool(snapshot.get("degraded", False))
            degraded_reason = str(snapshot.get("degraded_reason") or "").strip()
            if not snapshot:
                degraded = True
                degraded_reason = "当前无真实行情，已回退为成本价估算。"
            fx_rate = (
                self.get_fx_rate("HKD", "CNY", target_date)
                if position.market == TradeRecord.Market.HK_STOCK
                else Decimal("1")
            )
            quantity = Decimal(position.quantity)
            cost_basis_native = _to_decimal(position.weighted_avg_cost) * quantity
            market_value_native = latest_price * quantity
            unrealized_native = market_value_native - cost_basis_native
            daily_native = self._daily_pnl_native_for_security(
                stock_code=position.stock_code,
                market=position.market,
                target_date=target_date,
                snapshot=snapshot,
                latest_price=latest_price,
                previous_close=previous_close,
                baseline_states=baseline_states,
                current_holdings=current_holdings,
                trades_by_code=trades_by_code,
            )
            rows.append(
                {
                    "stock_code": position.stock_code,
                    "stock_name": position.stock_name,
                    "market": position.market,
                    "quantity": position.quantity,
                    "latest_price": float(latest_price),
                    "previous_close": float(previous_close),
                    "cost_basis_native": float(cost_basis_native),
                    "market_value_native": float(market_value_native),
                    "market_value_cny": float((market_value_native * fx_rate).quantize(Decimal("0.0001"))),
                    "unrealized_pnl_native": float(unrealized_native),
                    "unrealized_pnl_cny": float((unrealized_native * fx_rate).quantize(Decimal("0.0001"))),
                    "daily_pnl_native": float(daily_native),
                    "daily_pnl_cny": float((daily_native * fx_rate).quantize(Decimal("0.0001"))),
                    "return_pct": float(((unrealized_native / cost_basis_native) * Decimal("100")).quantize(Decimal("0.0001"))) if cost_basis_native > 0 else 0.0,
                    "currency": "HKD" if position.market == TradeRecord.Market.HK_STOCK else "CNY",
                    "fx_rate": float(fx_rate),
                    "data_source": str(snapshot.get("data_source") or "fallback_cost"),
                    "degraded": degraded,
                    "degraded_reason": degraded_reason,
                }
            )
        return rows

    def _daily_pnl_native_for_security(
        self,
        *,
        stock_code: str,
        market: str,
        target_date: date,
        snapshot: dict,
        latest_price: Decimal,
        previous_close: Decimal,
        baseline_states: dict,
        current_holdings: dict,
        trades_by_code: dict,
    ) -> Decimal:
        if self._uses_stale_a_share_daily_bar(snapshot, market, target_date):
            previous_close = latest_price

        baseline_state = baseline_states.get(stock_code, {"market": market, "quantity": 0})
        start_qty = int(baseline_state.get("quantity", 0))
        end_qty = int(current_holdings.get(stock_code, {}).get("quantity", 0))
        trade_cash_delta = Decimal("0")
        for trade in trades_by_code.get(stock_code, []):
            gross_amount = _to_decimal(trade.price) * Decimal(trade.quantity)
            fees = self._trade_fee_total(trade)
            if trade.direction == TradeRecord.Direction.SELL:
                trade_cash_delta += gross_amount - fees
            else:
                trade_cash_delta -= gross_amount + fees

        start_value = previous_close * Decimal(start_qty)
        end_value = latest_price * Decimal(end_qty)
        return end_value + trade_cash_delta - start_value

    def get_position_detail(self, stock_code: str, as_of_date: date | None = None):
        rows = self.get_position_analytics(as_of_date=as_of_date)
        for row in rows:
            if row["stock_code"] == stock_code:
                return row
        raise ValueError(f"Position analytics not found for stock_code={stock_code}")

    def get_cleared_positions(self):
        rows = []
        for position in Position.objects.filter(status=Position.Status.CLEARED).order_by("-updated_at"):
            fx_rate = (
                self.get_fx_rate("HKD", "CNY", timezone.localdate())
                if position.market == TradeRecord.Market.HK_STOCK
                else Decimal("1")
            )
            realized_native = _to_decimal(position.realized_pnl)
            rows.append(
                {
                    "stock_code": position.stock_code,
                    "stock_name": position.stock_name,
                    "market": position.market,
                    "quantity": position.quantity,
                    "status": position.status,
                    "realized_pnl_native": float(realized_native),
                    "realized_pnl_cny": float((realized_native * fx_rate).quantize(Decimal("0.0001"))),
                    "updated_at": position.updated_at,
                }
            )
        return rows

    def get_fx_rate(self, base_currency: str, quote_currency: str, rate_date: date):
        if base_currency == quote_currency:
            return Decimal("1")

        cache_key = (base_currency, quote_currency, rate_date.isoformat())
        if cache_key in self._fx_cache:
            return self._fx_cache[cache_key]

        existing = FXRate.objects.filter(
            base_currency=base_currency,
            quote_currency=quote_currency,
            rate_date__lte=rate_date,
        ).order_by("-rate_date").first()
        if existing:
            rate = _to_decimal(existing.rate)
            self._fx_cache[cache_key] = rate
            return rate

        if self.market_data_provider is None:
            raise ValueError(f"FX rate unavailable for {base_currency}/{quote_currency} on {rate_date}")

        try:
            rate = _to_decimal(self.market_data_provider.get_fx_rate(base_currency, quote_currency, rate_date))
        except Exception:
            latest_any = FXRate.objects.filter(
                base_currency=base_currency,
                quote_currency=quote_currency,
            ).order_by("-rate_date").first()
            if latest_any:
                rate = _to_decimal(latest_any.rate)
                self._fx_cache[cache_key] = rate
                return rate
            self._fx_cache[cache_key] = Decimal("1")
            return Decimal("1")
        FXRate.objects.update_or_create(
            base_currency=base_currency,
            quote_currency=quote_currency,
            rate_date=rate_date,
            defaults={"rate": rate, "source": getattr(self.market_data_provider, "provider_name", "market_provider")},
        )
        self._fx_cache[cache_key] = rate
        return rate

    def _effective_start_date(self):
        earliest = CashFlow.objects.order_by("occurred_at").values_list("occurred_at", flat=True).first()
        earliest_snapshot = PortfolioPerformanceSnapshot.objects.order_by("snapshot_date").values_list("snapshot_date", flat=True).first()
        candidates = []
        if earliest is not None:
            candidates.append(_local_date(earliest))
        if earliest_snapshot is not None:
            candidates.append(earliest_snapshot)
        if not candidates:
            return timezone.localdate()
        return min(candidates)

    def _effective_end_date(self):
        candidate_dates: list[date] = []
        today = timezone.localdate()
        latest_snapshot_date = SecurityPriceSnapshot.objects.order_by("-trade_date").values_list("trade_date", flat=True).first()
        if latest_snapshot_date is not None and latest_snapshot_date <= today:
            candidate_dates.append(latest_snapshot_date)

        if self.market_data_provider is not None:
            for position in Position.objects.filter(status=Position.Status.ACTIVE, quantity__gt=0):
                try:
                    snapshot = self.market_data_provider.get_snapshot(position.stock_code, position.market)
                except Exception:
                    snapshot = {}
                snapshot_date = _snapshot_trade_date(snapshot)
                if snapshot_date is not None and snapshot_date <= today:
                    candidate_dates.append(snapshot_date)

        if candidate_dates:
            return max(candidate_dates)
        return today

    def _signed_cash_flow(self, flow: CashFlow):
        amount = _to_decimal(flow.amount)
        if flow.direction == CashFlow.Direction.WITHDRAWAL:
            return -amount
        return amount

    def _total_contributions_cny(self, as_of_date: date):
        total = Decimal("0")
        for flow in CashFlow.objects.filter(occurred_at__date__lte=as_of_date).select_related("cash_account"):
            signed_amount = self._signed_cash_flow(flow)
            if flow.cash_account.currency == CashAccount.Currency.HKD:
                fx_rate = self.get_fx_rate("HKD", "CNY", _local_date(flow.occurred_at))
                total += signed_amount * fx_rate
            else:
                total += signed_amount
        return total

    def _build_curves(self, start_date: date, end_date: date):
        daily_points = []
        previous_assets = None
        cumulative = Decimal("1")
        pending_external_flow = Decimal("0")

        for current_date in self._date_range(start_date, end_date):
            pending_external_flow += self._external_flow_on_date(current_date)
            if not self._should_include_curve_date(current_date):
                continue

            total_assets_cny = self._portfolio_value_on_date(current_date)
            external_flow_cny = pending_external_flow
            if previous_assets in (None, Decimal("0")):
                daily_pnl_cny, contribution_rows, audit_status = self._daily_pnl_details_for_date(current_date)
                previous_total_assets_cny = total_assets_cny - daily_pnl_cny
                if previous_total_assets_cny > 0:
                    daily_return = daily_pnl_cny / previous_total_assets_cny
                else:
                    daily_return = Decimal("0")
            else:
                daily_pnl_cny, contribution_rows, audit_status = self._daily_pnl_details_for_date(current_date)
                daily_return = (total_assets_cny - previous_assets - pending_external_flow) / previous_assets
            cumulative *= Decimal("1") + daily_return
            total_return_cny = total_assets_cny - self._total_contributions_cny(current_date)
            daily_points.append(
                {
                    "date": current_date.isoformat(),
                    "total_assets_cny": float(total_assets_cny.quantize(Decimal("0.0001"))),
                    "total_return_cny": float(total_return_cny.quantize(Decimal("0.0001"))),
                    "daily_return_pct": float((daily_return * Decimal("100")).quantize(Decimal("0.0001"))),
                    "monthly_return_pct": 0.0,
                    "yearly_return_pct": 0.0,
                    "cumulative_return_pct": float(((cumulative - Decimal("1")) * Decimal("100")).quantize(Decimal("0.0001"))),
                    "audit_status": audit_status,
                    "external_flow_cny": float(external_flow_cny.quantize(Decimal("0.0001"))),
                    "computed_daily_pnl_cny": float(daily_pnl_cny.quantize(Decimal("0.0001"))),
                    "contributions": contribution_rows,
                }
            )
            previous_assets = total_assets_cny
            pending_external_flow = Decimal("0")

        self._annotate_period_returns(daily_points)
        self._persist_points(daily_points)

        return {
            "daily": daily_points,
            "monthly": self._collapse_curve(daily_points, mode="month"),
            "yearly": self._collapse_curve(daily_points, mode="year"),
        }

    def _should_include_curve_date(self, target_date: date) -> bool:
        if CashFlow.objects.filter(occurred_at__date=target_date).exists():
            return True
        if TradeRecord.objects.filter(trade_time__date=target_date).exists():
            return True

        holdings = self._holdings_on_date(target_date)
        for stock_code, item in holdings.items():
            if item["quantity"] <= 0:
                continue
            snapshot = self._get_snapshot(stock_code, item["market"], target_date)
            if self._is_real_snapshot_for_target_date(snapshot, target_date):
                return True
        return False

    def _is_real_snapshot_for_target_date(self, snapshot: dict, target_date: date) -> bool:
        snapshot_date = _snapshot_trade_date(snapshot)
        if snapshot_date != target_date:
            return False
        degraded_reason = str(snapshot.get("degraded_reason") or "")
        if degraded_reason == "historical_snapshot_derived_from_next_day_previous_close":
            return False
        if degraded_reason == "historical_snapshot_missing_used_previous_close":
            return is_cn_equity_trading_day(target_date)
        if degraded_reason.startswith("historical_snapshot_missing_"):
            return False
        return bool(snapshot.get("latest_price") is not None)

    def _portfolio_value_on_date(self, target_date: date):
        balances = self.get_cash_balances(target_date)
        holdings = self._holdings_on_date(target_date)
        needs_hkd_rate = (
            _to_decimal(balances["HKD"]["balance"]) != Decimal("0")
            or any(item["market"] == TradeRecord.Market.HK_STOCK and item["quantity"] > 0 for item in holdings.values())
        )
        fx_rate = self.get_fx_rate("HKD", "CNY", target_date) if needs_hkd_rate else Decimal("1")
        total = _to_decimal(balances["CNY"]["balance"]) + _to_decimal(balances["HKD"]["balance"]) * fx_rate

        for stock_code, item in holdings.items():
            if item["quantity"] <= 0:
                continue
            snapshot = self._get_snapshot(stock_code, item["market"], target_date)
            latest_price = _to_decimal(
                snapshot.get("latest_price")
                or self._curve_fallback_price(stock_code, item["market"], target_date, item["cost_price"])
            )
            market_value = latest_price * Decimal(item["quantity"])
            if item["market"] == TradeRecord.Market.HK_STOCK:
                market_value *= fx_rate
            total += market_value
        return total

    def _realized_pnl_since(self, start_date: date):
        states = self._baseline_states(start_date)
        realized_by_market = defaultdict(lambda: Decimal("0"))
        trades = TradeRecord.objects.filter(trade_time__date__gte=start_date).order_by("trade_time", "id")

        for trade in trades:
            state = states.setdefault(
                trade.stock_code,
                {
                    "market": trade.market,
                    "quantity": 0,
                    "weighted_avg_cost": _to_decimal(trade.price),
                },
            )
            if trade.direction == TradeRecord.Direction.BUY:
                current_qty = int(state["quantity"])
                current_avg = _to_decimal(state["weighted_avg_cost"])
                trade_cost = _to_decimal(trade.price) * Decimal(trade.quantity) + self._trade_fee_total(trade)
                new_qty = current_qty + int(trade.quantity)
                if new_qty > 0:
                    new_avg = ((Decimal(current_qty) * current_avg) + trade_cost) / Decimal(new_qty)
                else:
                    new_avg = Decimal("0")
                state["quantity"] = new_qty
                state["weighted_avg_cost"] = new_avg
            else:
                sell_qty = int(trade.quantity)
                current_avg = _to_decimal(state["weighted_avg_cost"])
                gross_proceeds = _to_decimal(trade.price) * Decimal(sell_qty)
                realized_native = gross_proceeds - self._trade_fee_total(trade) - (current_avg * Decimal(sell_qty))
                fx_rate = self.get_fx_rate("HKD", "CNY", _local_date(trade.trade_time)) if trade.market == TradeRecord.Market.HK_STOCK else Decimal("1")
                realized_by_market[trade.market] += realized_native * fx_rate
                state["quantity"] = int(state["quantity"]) - sell_qty

        return sum(realized_by_market.values(), Decimal("0"))

    def _daily_pnl_for_date(self, target_date: date):
        total_daily_pnl, _, _ = self._daily_pnl_details_for_date(target_date)
        return total_daily_pnl

    def _daily_pnl_details_for_date(self, target_date: date):
        baseline_states = self._baseline_states(target_date)
        current_holdings = self._holdings_on_date(target_date)
        trades_by_code = defaultdict(list)
        for trade in TradeRecord.objects.filter(trade_time__date=target_date).order_by("trade_time", "id"):
            trades_by_code[trade.stock_code].append(trade)

        involved_codes = set(baseline_states.keys()) | set(current_holdings.keys()) | set(trades_by_code.keys())
        total_daily_pnl = Decimal("0")
        contribution_rows = []
        overall_audit_status = PortfolioPerformanceSnapshot.AuditStatus.FINAL

        for stock_code in involved_codes:
            baseline_state = baseline_states.get(
                stock_code,
                {
                    "market": current_holdings[stock_code]["market"] if stock_code in current_holdings else trades_by_code[stock_code][0].market,
                    "quantity": 0,
                },
            )
            market = baseline_state["market"]
            fx_rate = self.get_fx_rate("HKD", "CNY", target_date) if market == TradeRecord.Market.HK_STOCK else Decimal("1")
            snapshot = self._get_snapshot(stock_code, market, target_date)
            previous_close = _to_decimal(snapshot.get("previous_close") or snapshot.get("latest_price") or 0)
            latest_price = _to_decimal(snapshot.get("latest_price") or previous_close)
            if self._uses_stale_a_share_daily_bar(snapshot, market, target_date):
                previous_close = latest_price

            start_qty = int(baseline_state.get("quantity", 0))
            end_qty = int(current_holdings.get(stock_code, {}).get("quantity", 0))
            trade_cash_delta = Decimal("0")
            for trade in trades_by_code.get(stock_code, []):
                gross_amount = _to_decimal(trade.price) * Decimal(trade.quantity)
                fees = self._trade_fee_total(trade)
                if trade.direction == TradeRecord.Direction.SELL:
                    trade_cash_delta += gross_amount - fees
                else:
                    trade_cash_delta -= gross_amount + fees

            start_value = previous_close * Decimal(start_qty)
            end_value = latest_price * Decimal(end_qty)
            pnl_native = end_value + trade_cash_delta - start_value
            pnl_cny = (pnl_native * fx_rate).quantize(Decimal("0.0001"))
            total_daily_pnl += pnl_cny
            source_trade_date = _snapshot_trade_date(snapshot)
            degraded = bool(snapshot.get("degraded", False))
            price_source = str(snapshot.get("data_source") or "fallback_cost")
            uses_fallback_source = price_source.startswith("fallback") or "quote" in price_source or price_source.endswith("_spot")
            audit_status = (
                PortfolioPerformanceSnapshot.AuditStatus.PROVISIONAL
                if degraded or source_trade_date != target_date or uses_fallback_source
                else PortfolioPerformanceSnapshot.AuditStatus.FINAL
            )
            if audit_status == PortfolioPerformanceSnapshot.AuditStatus.PROVISIONAL:
                overall_audit_status = PortfolioPerformanceSnapshot.AuditStatus.PROVISIONAL
            contribution_rows.append(
                {
                    "snapshot_date": target_date,
                    "stock_code": stock_code,
                    "stock_name": current_holdings.get(stock_code, {}).get("stock_name", ""),
                    "market": market,
                    "start_quantity": start_qty,
                    "end_quantity": end_qty,
                    "previous_close": previous_close.quantize(Decimal("0.0001")),
                    "latest_price": latest_price.quantize(Decimal("0.0001")),
                    "trade_cash_delta": trade_cash_delta.quantize(Decimal("0.0001")),
                    "daily_pnl_native": pnl_native.quantize(Decimal("0.0001")),
                    "daily_pnl_cny": pnl_cny,
                    "fx_rate": fx_rate.quantize(Decimal("0.000001")),
                    "price_source": price_source,
                    "source_trade_date": source_trade_date,
                    "degraded": degraded,
                    "degraded_reason": str(snapshot.get("degraded_reason") or ""),
                    "audit_status": audit_status,
                }
            )

        return total_daily_pnl, contribution_rows, overall_audit_status

    def _get_snapshot(self, stock_code: str, market: str, target_date: date):
        cache_key = (stock_code, market, target_date.isoformat())
        if cache_key in self._snapshot_cache:
            return self._snapshot_cache[cache_key]
        snapshot = self._snapshot_on_date(stock_code, market, target_date)
        self._snapshot_cache[cache_key] = snapshot
        return snapshot

    def _holdings_on_date(self, target_date: date):
        current = {
            position.stock_code: {
                "market": position.market,
                "stock_name": position.stock_name,
                "quantity": int(position.quantity),
                "cost_price": _to_decimal(position.weighted_avg_cost),
            }
            for position in Position.objects.all()
        }

        future_trades = TradeRecord.objects.filter(trade_time__date__gt=target_date).order_by("-trade_time")
        for trade in future_trades:
            item = current.setdefault(
                trade.stock_code,
                {
                    "market": trade.market,
                    "stock_name": trade.stock_name,
                    "quantity": 0,
                    "cost_price": _to_decimal(trade.price),
                },
            )
            if trade.direction == TradeRecord.Direction.BUY:
                item["quantity"] -= int(trade.quantity)
            else:
                item["quantity"] += int(trade.quantity)
        return current

    def _baseline_states(self, start_date: date):
        states = {
            position.stock_code: {
                "market": position.market,
                "quantity": int(position.quantity),
                "weighted_avg_cost": _to_decimal(position.weighted_avg_cost),
            }
            for position in Position.objects.all()
        }

        future_trades = TradeRecord.objects.filter(trade_time__date__gte=start_date).order_by("-trade_time", "-id")
        for trade in future_trades:
            state = states.setdefault(
                trade.stock_code,
                {
                    "market": trade.market,
                    "quantity": 0,
                    "weighted_avg_cost": _to_decimal(trade.price),
                },
            )
            if trade.direction == TradeRecord.Direction.SELL:
                state["quantity"] = int(state["quantity"]) + int(trade.quantity)
            else:
                current_qty = int(state["quantity"])
                buy_qty = int(trade.quantity)
                previous_qty = current_qty - buy_qty
                if previous_qty < 0:
                    previous_qty = 0
                current_cost_basis = Decimal(current_qty) * _to_decimal(state["weighted_avg_cost"])
                buy_cost = _to_decimal(trade.price) * Decimal(buy_qty) + self._trade_fee_total(trade)
                previous_cost_basis = current_cost_basis - buy_cost
                if previous_qty > 0:
                    state["weighted_avg_cost"] = previous_cost_basis / Decimal(previous_qty)
                state["quantity"] = previous_qty

        return states

    def _snapshot_on_date(self, stock_code: str, market: str, target_date: date):
        stored_snapshot = SecurityPriceSnapshot.objects.filter(
            stock_code=stock_code,
            market=market,
            trade_date=target_date,
        ).values(
            "close_price",
            "previous_close",
            "open_price",
            "high_price",
            "low_price",
            "volume",
            "amount",
            "source",
            "degraded",
            "degraded_reason",
            "trade_date",
        ).first()
        if stored_snapshot:
            return {
                "latest_price": stored_snapshot["close_price"],
                "previous_close": stored_snapshot["previous_close"],
                "open": stored_snapshot["open_price"],
                "high": stored_snapshot["high_price"],
                "low": stored_snapshot["low_price"],
                "volume": stored_snapshot["volume"],
                "amount": stored_snapshot["amount"],
                "trade_date": stored_snapshot["trade_date"],
                "data_source": stored_snapshot["source"],
                "degraded": stored_snapshot["degraded"],
                "degraded_reason": stored_snapshot["degraded_reason"],
            }

        next_day_snapshot = SecurityPriceSnapshot.objects.filter(
            stock_code=stock_code,
            market=market,
            trade_date=target_date + timedelta(days=1),
        ).values(
            "close_price",
            "previous_close",
            "open_price",
            "high_price",
            "low_price",
            "volume",
            "amount",
            "source",
            "degraded",
            "degraded_reason",
            "trade_date",
        ).first()
        if next_day_snapshot and next_day_snapshot["previous_close"] is not None and is_cn_equity_trading_day(target_date):
            prior_snapshot = SecurityPriceSnapshot.objects.filter(
                stock_code=stock_code,
                market=market,
                trade_date=target_date - timedelta(days=1),
            ).values("close_price").first()
            return {
                "latest_price": next_day_snapshot["previous_close"],
                "previous_close": prior_snapshot["close_price"] if prior_snapshot and prior_snapshot["close_price"] is not None else next_day_snapshot["previous_close"],
                "open": next_day_snapshot["open_price"],
                "high": next_day_snapshot["high_price"],
                "low": next_day_snapshot["low_price"],
                "volume": next_day_snapshot["volume"],
                "amount": next_day_snapshot["amount"],
                "trade_date": target_date,
                "data_source": next_day_snapshot["source"],
                "degraded": bool(next_day_snapshot["degraded"]),
                "degraded_reason": "historical_snapshot_derived_from_next_day_previous_close",
            }

        if self.market_data_provider is None:
            return {}
        if target_date == timezone.localdate():
            try:
                snapshot = self.market_data_provider.get_snapshot(stock_code, market)
            except Exception:
                snapshot = {}
            if snapshot:
                return snapshot
        try:
            bars = self.market_data_provider.fetch_daily_bars(
                stock_code,
                start=target_date - timedelta(days=10),
                end=target_date,
                market=market,
            )
        except Exception:
            bars = []
        if not bars:
            return self._fallback_snapshot_for_missing_history(stock_code, market, target_date)
        latest = bars[-1]
        previous_close = latest.get("pre_close") or (bars[-2]["close"] if len(bars) > 1 else latest["close"])
        return {
            "latest_price": latest["close"],
            "previous_close": previous_close,
            "trade_date": latest.get("trade_date"),
            "data_source": getattr(self.market_data_provider, "provider_name", "historical_daily_bars"),
            "degraded": False,
            "degraded_reason": "",
        }

    def _external_flow_on_date(self, target_date: date):
        total = Decimal("0")
        for flow in CashFlow.objects.filter(occurred_at__date=target_date).select_related("cash_account"):
            signed_amount = self._signed_cash_flow(flow)
            if flow.cash_account.currency == CashAccount.Currency.HKD:
                signed_amount *= self.get_fx_rate("HKD", "CNY", target_date)
            total += signed_amount
        return total

    def _trade_fee_total(self, trade):
        return (
            _to_decimal(getattr(trade, "commission", 0))
            + _to_decimal(getattr(trade, "stamp_duty", 0))
            + _to_decimal(getattr(trade, "other_fees", 0))
        )

    def _load_persisted_points(self, start_date: date, end_date: date):
        if end_date < start_date:
            return []
        queryset = PortfolioPerformanceSnapshot.objects.filter(
            snapshot_date__gte=start_date,
            snapshot_date__lte=end_date,
        ).order_by("snapshot_date")
        return [
            {
                "date": snapshot.snapshot_date.isoformat(),
                "total_assets_cny": float(snapshot.total_assets_cny),
                "total_return_cny": float(snapshot.total_return_cny),
                "daily_return_pct": float(snapshot.daily_return_pct),
                "monthly_return_pct": float(snapshot.monthly_return_pct),
                "yearly_return_pct": float(snapshot.yearly_return_pct),
                "cumulative_return_pct": float(snapshot.cumulative_return_pct),
            }
            for snapshot in queryset
        ]

    def _persist_points(self, daily_points: list[dict]):
        if not daily_points:
            return
        current_dates = {date.fromisoformat(point["date"]) for point in daily_points}
        for point in daily_points:
            PortfolioPerformanceSnapshot.objects.update_or_create(
                snapshot_date=date.fromisoformat(point["date"]),
                defaults={
                    "total_assets_cny": _to_decimal(point["total_assets_cny"]),
                    "total_return_cny": _to_decimal(point["total_return_cny"]),
                    "daily_return_pct": _to_decimal(point["daily_return_pct"]),
                    "monthly_return_pct": _to_decimal(point["monthly_return_pct"]),
                    "yearly_return_pct": _to_decimal(point["yearly_return_pct"]),
                    "cumulative_return_pct": _to_decimal(point["cumulative_return_pct"]),
                    "audit_status": point.get("audit_status", PortfolioPerformanceSnapshot.AuditStatus.PROVISIONAL),
                    "external_flow_cny": _to_decimal(point.get("external_flow_cny", 0)),
                    "computed_daily_pnl_cny": _to_decimal(point.get("computed_daily_pnl_cny", 0)),
                },
            )
            PositionDailyContributionSnapshot.objects.filter(snapshot_date=date.fromisoformat(point["date"])).delete()
            for contribution in point.get("contributions", []):
                PositionDailyContributionSnapshot.objects.create(**contribution)
        PortfolioPerformanceSnapshot.objects.filter(
            snapshot_date__gte=min(current_dates),
        ).exclude(
            snapshot_date__in=current_dates,
        ).delete()
        PositionDailyContributionSnapshot.objects.exclude(snapshot_date__in=current_dates).filter(
            snapshot_date__gte=min(current_dates)
        ).delete()

    def _annotate_period_returns(self, daily_points: list[dict]):
        for point in daily_points:
            point_date = date.fromisoformat(point["date"])
            point["monthly_return_pct"] = self._period_return_pct(
                daily_points,
                period_start=point_date.replace(day=1),
                current_date=point_date,
            )
            point["yearly_return_pct"] = self._period_return_pct(
                daily_points,
                period_start=date(point_date.year, 1, 1),
                current_date=point_date,
            )

    def _period_return_pct(self, daily_points: list[dict], period_start: date, current_date: date):
        point_by_date = {date.fromisoformat(point["date"]): point for point in daily_points}
        latest = point_by_date.get(current_date)
        if latest is None:
            return 0.0

        latest_ratio = Decimal("1") + (_to_decimal(latest["cumulative_return_pct"]) / Decimal("100"))
        baseline_point = None
        for point in daily_points:
            point_date = date.fromisoformat(point["date"])
            if point_date < period_start:
                baseline_point = point
            else:
                break

        if baseline_point is None:
            return float(_to_decimal(latest["cumulative_return_pct"]).quantize(Decimal("0.0001")))

        baseline_ratio = Decimal("1") + (_to_decimal(baseline_point["cumulative_return_pct"]) / Decimal("100"))
        period_return = ((latest_ratio / baseline_ratio) - Decimal("1")) * Decimal("100")
        return float(period_return.quantize(Decimal("0.0001")))

    def _uses_stale_a_share_daily_bar(self, snapshot: dict, market: str, target_date: date):
        if market != TradeRecord.Market.A_STOCK:
            return False
        snapshot_date = _snapshot_trade_date(snapshot)
        return snapshot_date is not None and snapshot_date < target_date

    def _fallback_snapshot_for_missing_history(self, stock_code: str, market: str, target_date: date):
        if self.market_data_provider is None:
            prior_snapshot = (
                SecurityPriceSnapshot.objects.filter(
                    stock_code=stock_code,
                    market=market,
                    trade_date__lt=target_date,
                )
                .order_by("-trade_date")
                .values("close_price", "trade_date", "source")
                .first()
            )
            if prior_snapshot and prior_snapshot["close_price"] is not None:
                return {
                    "latest_price": prior_snapshot["close_price"],
                    "previous_close": prior_snapshot["close_price"],
                    "trade_date": target_date.isoformat(),
                    "data_source": str(prior_snapshot.get("source") or "prior_stored_close"),
                    "degraded": True,
                    "degraded_reason": "historical_snapshot_missing_used_prior_stored_close",
                }
            return {}

        try:
            current_snapshot = self.market_data_provider.get_snapshot(stock_code, market)
        except Exception:
            current_snapshot = {}

        if not current_snapshot:
            prior_snapshot = (
                SecurityPriceSnapshot.objects.filter(
                    stock_code=stock_code,
                    market=market,
                    trade_date__lt=target_date,
                )
                .order_by("-trade_date")
                .values("close_price", "trade_date", "source")
                .first()
            )
            if prior_snapshot and prior_snapshot["close_price"] is not None:
                return {
                    "latest_price": prior_snapshot["close_price"],
                    "previous_close": prior_snapshot["close_price"],
                    "trade_date": target_date.isoformat(),
                    "data_source": str(prior_snapshot.get("source") or "prior_stored_close"),
                    "degraded": True,
                    "degraded_reason": "historical_snapshot_missing_used_prior_stored_close",
                }
            return {}

        prior_snapshot = (
            SecurityPriceSnapshot.objects.filter(
                stock_code=stock_code,
                market=market,
                trade_date__lt=target_date,
            )
            .order_by("-trade_date")
            .values("close_price", "trade_date", "source")
            .first()
        )

        current_trade_date = _snapshot_trade_date(current_snapshot) or timezone.localdate()
        latest_price = current_snapshot.get("latest_price")
        previous_close = current_snapshot.get("previous_close")

        if latest_price is not None and target_date == current_trade_date:
            snapshot = dict(current_snapshot)
            snapshot.setdefault("trade_date", current_trade_date.isoformat())
            return snapshot

        if previous_close is not None and target_date == current_trade_date - timedelta(days=1):
            prior_snapshot = SecurityPriceSnapshot.objects.filter(
                stock_code=stock_code,
                market=market,
                trade_date=target_date - timedelta(days=1),
            ).values("close_price").first()
            return {
                "latest_price": previous_close,
                "previous_close": prior_snapshot["close_price"] if prior_snapshot and prior_snapshot["close_price"] is not None else previous_close,
                "trade_date": target_date.isoformat(),
                "data_source": str(current_snapshot.get("data_source") or "fallback_previous_close"),
                "degraded": True,
                "degraded_reason": "historical_snapshot_missing_used_previous_close",
            }

        if latest_price is not None and target_date < current_trade_date:
            if prior_snapshot and prior_snapshot["close_price"] is not None:
                return {
                    "latest_price": prior_snapshot["close_price"],
                    "previous_close": prior_snapshot["close_price"],
                    "trade_date": target_date.isoformat(),
                    "data_source": str(prior_snapshot.get("source") or "prior_stored_close"),
                    "degraded": True,
                    "degraded_reason": "historical_snapshot_missing_used_prior_stored_close",
                }
            return {
                "latest_price": latest_price,
                "previous_close": latest_price,
                "trade_date": target_date.isoformat(),
                "data_source": str(current_snapshot.get("data_source") or "fallback_latest_price"),
                "degraded": True,
                "degraded_reason": "historical_snapshot_missing_used_latest_price",
            }

        return {}

    def _curve_fallback_price(self, stock_code: str, market: str, target_date: date, cost_price: Decimal):
        fallback_snapshot = self._fallback_snapshot_for_missing_history(stock_code, market, target_date)
        fallback_price = fallback_snapshot.get("latest_price")
        if fallback_price is not None:
            return fallback_price
        return cost_price

    def _collapse_curve(self, points: list[dict], mode: str):
        if mode not in {"month", "year"}:
            return list(points)
        grouped = defaultdict(list)
        for point in points:
            key = point["date"][:7] if mode == "month" else point["date"][:4]
            grouped[key].append(point)
        return [group[-1] for _, group in sorted(grouped.items(), key=lambda item: item[0])]

    def _latest_returns(self, daily: list[dict]):
        if len(daily) == 1:
            bootstrap_return = daily[-1]["cumulative_return_pct"]
            return {
                "daily": daily[-1]["daily_return_pct"],
                "monthly": daily[-1].get("monthly_return_pct", bootstrap_return),
                "yearly": daily[-1].get("yearly_return_pct", bootstrap_return),
            }
        return {
            "daily": daily[-1]["daily_return_pct"] if daily else 0,
            "monthly": daily[-1].get("monthly_return_pct", 0) if daily else 0,
            "yearly": daily[-1].get("yearly_return_pct", 0) if daily else 0,
        }

    def _date_range(self, start_date: date, end_date: date):
        current = start_date
        while current <= end_date:
            yield current
            current += timedelta(days=1)
