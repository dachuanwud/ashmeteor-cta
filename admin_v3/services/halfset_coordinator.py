from decimal import Decimal


def decimal_or_zero(value):
    try:
        if value is None or value == '':
            return Decimal('0')
        return Decimal(str(value))
    except Exception:
        return Decimal('0')


def boolish(value):
    if isinstance(value, str):
        return value.lower() in ('1', 'true', 'yes', 'on', '已开启', '开启')
    return bool(value)


def normalize_halfset_signal(signal):
    if signal is None:
        return Decimal('0')
    try:
        import pandas as pd
        if pd.isna(signal):
            return Decimal('0')
    except Exception:
        pass
    value = Decimal(str(int(signal)))
    if value > 0:
        return Decimal('1')
    if value < 0:
        return Decimal('-1')
    return Decimal('0')


def clamp_ratio(value):
    ratio = decimal_or_zero(value)
    if ratio < 0:
        return Decimal('0')
    if ratio > 1:
        return Decimal('1')
    return ratio


def overlay_to_dict(item):
    if item is None:
        return {}
    if isinstance(item, dict):
        return dict(item)
    if hasattr(item, 'to_dict'):
        return item.to_dict()
    keys = ('id', 'strategy', 'asset', 'cta_key', 'symbol', 'interval', 'cta',
            'period', 'weight', 'trade_ratio', 'is_running', 'last_signal',
            'target_qty', 'last_signal_time', 'last_status', 'last_msg')
    return {key: getattr(item, key, '') for key in keys}


def calculate_halfset_targets(base_qty,
                              hedge_ratio,
                              signal,
                              current_um_position='0',
                              cta_sizing_mode='auto_remaining',
                              cta_budget_usd='0',
                              cta_trade_ratio='1',
                              last_price=None):
    base_qty = decimal_or_zero(base_qty)
    hedge_ratio = clamp_ratio(hedge_ratio)
    signal = normalize_halfset_signal(signal)
    current_um_position = decimal_or_zero(current_um_position)
    cta_trade_ratio = decimal_or_zero(cta_trade_ratio) or Decimal('1')
    cta_sizing_mode = cta_sizing_mode or 'auto_remaining'
    warning = ''

    half_target_qty = -base_qty * hedge_ratio
    if cta_sizing_mode == 'manual_usd':
        price = decimal_or_zero(last_price)
        if price <= 0:
            cta_target_qty = Decimal('0')
            warning = '价格缺失，无法按手动USDT预算计算CTA目标'
        else:
            cta_target_qty = (signal * decimal_or_zero(cta_budget_usd) *
                              cta_trade_ratio / price)
    else:
        cta_sizing_mode = 'auto_remaining'
        cta_target_qty = signal * base_qty * (Decimal('1') - hedge_ratio)

    total_target_qty = half_target_qty + cta_target_qty
    return {
        'base_qty': base_qty,
        'hedge_ratio': hedge_ratio,
        'signal': signal,
        'cta_sizing_mode': cta_sizing_mode,
        'half_target_qty': half_target_qty,
        'cta_target_qty': cta_target_qty,
        'total_target_qty': total_target_qty,
        'current_um_position': current_um_position,
        'order_delta_qty': total_target_qty - current_um_position,
        'warning': warning,
    }


def calculate_halfset_multi_targets(base_qty,
                                    hedge_ratio,
                                    overlays,
                                    current_um_position='0'):
    base_qty = decimal_or_zero(base_qty)
    hedge_ratio = clamp_ratio(hedge_ratio)
    current_um_position = decimal_or_zero(current_um_position)
    half_target_qty = -base_qty * hedge_ratio
    cta_budget_qty = base_qty * (Decimal('1') - hedge_ratio)

    overlay_rows = []
    total_weight = Decimal('0')
    for overlay in overlays or []:
        row = overlay_to_dict(overlay)
        is_running = boolish(row.get('is_running', 0))
        weight = max(decimal_or_zero(row.get('weight', 1)), Decimal('0'))
        trade_ratio = max(decimal_or_zero(row.get('trade_ratio', 1)),
                          Decimal('0'))
        effective_weight = weight * trade_ratio if is_running else Decimal('0')
        total_weight += effective_weight
        row.update({
            'is_running':
                1 if is_running else 0,
            'last_signal':
                int(
                    normalize_halfset_signal(
                        row.get('last_signal', row.get('signal', 0)))),
            'weight':
                weight,
            'trade_ratio':
                trade_ratio,
            'effective_weight':
                effective_weight,
        })
        overlay_rows.append(row)

    cta_target_qty = Decimal('0')
    for row in overlay_rows:
        if total_weight > 0 and row['effective_weight'] > 0:
            target_qty = (Decimal(row['last_signal']) * cta_budget_qty *
                          row['effective_weight'] / total_weight)
        else:
            target_qty = Decimal('0')
        row['target_qty'] = target_qty
        cta_target_qty += target_qty

    total_target_qty = half_target_qty + cta_target_qty
    aggregate_signal = 0
    if cta_target_qty > 0:
        aggregate_signal = 1
    elif cta_target_qty < 0:
        aggregate_signal = -1

    return {
        'base_qty': base_qty,
        'hedge_ratio': hedge_ratio,
        'half_target_qty': half_target_qty,
        'cta_target_qty': cta_target_qty,
        'total_target_qty': total_target_qty,
        'current_um_position': current_um_position,
        'order_delta_qty': total_target_qty - current_um_position,
        'signal': aggregate_signal,
        'overlays': overlay_rows,
        'warning': '',
    }


def order_is_reduce_only(current_position, order_delta, target_position):
    current_position = decimal_or_zero(current_position)
    order_delta = decimal_or_zero(order_delta)
    target_position = decimal_or_zero(target_position)
    if current_position < 0 and order_delta > 0 and target_position <= 0:
        return True
    if current_position > 0 and order_delta < 0 and target_position >= 0:
        return True
    return False

