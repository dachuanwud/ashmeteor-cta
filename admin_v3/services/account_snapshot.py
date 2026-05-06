from decimal import Decimal


def decimal_or_zero(value):
    try:
        if value is None or value == '':
            return Decimal('0')
        return Decimal(str(value))
    except Exception:
        return Decimal('0')


def calculate_cm_base_notional(position_amount,
                               mark_price,
                               raw_notional='0',
                               contract_size='0'):
    amount = decimal_or_zero(position_amount)
    mark_price = decimal_or_zero(mark_price)
    raw_notional = decimal_or_zero(raw_notional)
    contract_size = decimal_or_zero(contract_size)

    if raw_notional != 0:
        return raw_notional
    if contract_size > 0 and mark_price > 0:
        return amount * contract_size / mark_price
    return Decimal('0')


def build_position_snapshot(raw_position, market_type, contract_size='0'):
    raw_position = raw_position or {}
    market_type = (market_type or '').upper()
    amount = decimal_or_zero(raw_position.get('positionAmt'))
    if amount == 0:
        return None

    symbol = raw_position.get('symbol', '')
    mark_price = decimal_or_zero(raw_position.get('markPrice')
                                 or raw_position.get('lastPrice'))
    raw_notional = decimal_or_zero(raw_position.get('notional')
                                   or raw_position.get('notionalValue'))

    if market_type == 'CM':
        base_notional_qty = calculate_cm_base_notional(
            amount,
            mark_price,
            raw_notional=raw_notional,
            contract_size=contract_size)
        notional_usd = abs(
            base_notional_qty * mark_price) if mark_price > 0 else Decimal('0')
    else:
        base_notional_qty = amount
        notional_usd = abs(raw_notional)
        if notional_usd == 0:
            notional_usd = abs(amount * mark_price)

    return {
        'market_type':
            market_type,
        'symbol':
            symbol,
        'side':
            'SELL' if amount < 0 else 'BUY',
        'position_amount':
            amount,
        'base_notional_qty':
            base_notional_qty,
        'entry_price':
            decimal_or_zero(raw_position.get('entryPrice')),
        'mark_price':
            mark_price,
        'notional_usd':
            notional_usd,
        'unrealized_profit_usd':
            decimal_or_zero(raw_position.get('unRealizedProfit')
                            or raw_position.get('unrealizedProfit')),
        'leverage':
            decimal_or_zero(raw_position.get('leverage')),
    }

