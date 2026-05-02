from decimal import Decimal


ACCOUNT_TYPE_STANDARD = 'standard'
ACCOUNT_TYPE_UNIFIED = 'unified'


def normalize_account_type(account_type):
    if account_type == ACCOUNT_TYPE_UNIFIED:
        return ACCOUNT_TYPE_UNIFIED
    return ACCOUNT_TYPE_STANDARD


class BinanceAccountAdapter:
    def __init__(self, exchange, account_type=ACCOUNT_TYPE_STANDARD):
        self.exchange = exchange
        self.account_type = normalize_account_type(account_type)

    def _call_exchange(self, method_names, params=None):
        for name in method_names:
            if hasattr(self.exchange, name):
                method = getattr(self.exchange, name)
                if params is None:
                    return method()
                return method(params=params)
        raise AttributeError(
            f'exchange does not support any of: {", ".join(method_names)}')

    @property
    def is_unified(self):
        return self.account_type == ACCOUNT_TYPE_UNIFIED

    def get_account_summary(self):
        if self.is_unified:
            return self.exchange.papiGetAccount()
        account = self._call_exchange(
            ('fapiPrivateV2_get_account', 'fapiPrivateV2GetAccount'))
        return {
            'accountStatus': 'NORMAL',
            'accountEquity': account.get('totalMarginBalance', '0'),
            'totalAvailableBalance': account.get('availableBalance', '0'),
            'raw': account,
        }

    def get_balance_assets(self):
        if not self.is_unified:
            return self.get_account_summary().get('raw', {}).get('assets', [])

        balances = self.exchange.papiGetBalance()
        if isinstance(balances, dict):
            balances = [balances]

        assets = []
        for item in balances:
            cm_wallet = Decimal(str(item.get('cmWalletBalance') or '0'))
            cm_pnl = Decimal(str(item.get('cmUnrealizedPNL') or '0'))
            margin_balance = cm_wallet + cm_pnl
            normalized = dict(item)
            normalized['walletBalance'] = str(cm_wallet)
            normalized['marginBalance'] = str(margin_balance)
            assets.append(normalized)
        return assets

    def get_cm_account(self):
        if self.is_unified:
            return {
                'assets': self.get_cm_assets(),
                'positions': self.get_cm_positions(),
            }
        return self._call_exchange(
            ('dapiPrivate_get_account', 'dapiPrivateGetAccount'))

    def get_cm_assets(self):
        if not self.is_unified:
            return self.get_cm_account().get('assets', [])

        assets = []
        for item in self.get_balance_assets():
            wallet_balance = item.get('walletBalance', '0')
            margin_balance = item.get('marginBalance', '0')
            if item.get('asset') != 'USDT':
                wallet_balance = item.get('totalWalletBalance',
                                          wallet_balance)
                margin_balance = wallet_balance
            assets.append({
                'asset': item.get('asset', ''),
                'walletBalance': wallet_balance,
                'marginBalance': margin_balance,
                'unrealizedProfit': item.get('cmUnrealizedPNL', '0'),
            })
        return assets

    def get_cm_positions(self):
        if self.is_unified:
            return self.exchange.papiGetCmPositionRisk()
        return self.get_cm_account().get('positions', [])

    def get_cm_position_risk(self, params=None):
        params = params or {}
        if self.is_unified:
            return self.exchange.papiGetCmPositionRisk(params=params)
        return self._call_exchange(
            ('dapiPrivate_get_positionrisk', 'dapiPrivateGetPositionRisk'),
            params=params)

    def get_um_position_risk(self, params=None):
        params = params or {}
        if self.is_unified:
            return self.exchange.papiGetUmPositionRisk(params=params)
        return self._call_exchange(
            ('fapiPrivateV2_get_positionrisk', 'fapiPrivateV2GetPositionRisk'),
            params=params)

    def get_cm_adl_quantile(self, params=None):
        params = params or {}
        if self.is_unified:
            return self.exchange.papiGetCmAdlQuantile(params=params)
        return self._call_exchange(
            ('dapiPrivate_get_adlquantile', 'dapiPrivateGetAdlQuantile'),
            params=params)

    def place_cm_order(self, params):
        if self.is_unified:
            return self.exchange.papiPostCmOrder(params=params)
        return self._call_exchange(
            ('dapiPrivate_post_order', 'dapiPrivatePostOrder'), params=params)

    def place_um_order(self, params):
        if self.is_unified:
            return self.exchange.papiPostUmOrder(params=params)
        return self._call_exchange(
            ('fapiPrivate_post_order', 'fapiPrivatePostOrder'), params=params)

    def place_margin_order(self, params):
        if self.is_unified:
            return self.exchange.papiPostMarginOrder(params=params)
        return self._call_exchange(
            ('private_post_order', 'privatePostOrder'), params=params)

    def get_open_orders(self, market_type, params=None):
        params = params or {}
        if self.is_unified:
            if market_type == 'um':
                return self.exchange.papiGetUmOpenOrders(params=params)
            if market_type == 'cm':
                return self.exchange.papiGetCmOpenOrders(params=params)
            if market_type == 'margin':
                return self.exchange.papiGetMarginOpenOrders(params=params)
        if market_type == 'um':
            return self._call_exchange(
                ('fapiPrivate_get_openorders', 'fapiPrivateGetOpenOrders'),
                params=params)
        if market_type == 'cm':
            return self._call_exchange(
                ('dapiPrivate_get_openorders', 'dapiPrivateGetOpenOrders'),
                params=params)
        if market_type == 'margin':
            return self._call_exchange(
                ('private_get_openorders', 'privateGetOpenOrders'),
                params=params)
        raise ValueError(f'unsupported market_type: {market_type}')

    def cancel_order(self, market_type, params):
        if self.is_unified:
            if market_type == 'um':
                return self.exchange.papiDeleteUmOrder(params=params)
            if market_type == 'cm':
                return self.exchange.papiDeleteCmOrder(params=params)
            if market_type == 'margin':
                return self.exchange.papiDeleteMarginOrder(params=params)
        if market_type == 'um':
            return self._call_exchange(
                ('fapiPrivate_delete_order', 'fapiPrivateDeleteOrder'),
                params=params)
        if market_type == 'cm':
            return self._call_exchange(
                ('dapiPrivate_delete_order', 'dapiPrivateDeleteOrder'),
                params=params)
        if market_type == 'margin':
            return self._call_exchange(
                ('private_delete_order', 'privateDeleteOrder'), params=params)
        raise ValueError(f'unsupported market_type: {market_type}')

    def get_user_trades(self, market_type, params=None):
        params = params or {}
        if self.is_unified:
            if market_type == 'um':
                return self.exchange.papiGetUmUserTrades(params=params)
            if market_type == 'cm':
                return self.exchange.papiGetCmUserTrades(params=params)
            if market_type == 'margin':
                return self.exchange.papiGetMarginMyTrades(params=params)
        if market_type == 'um':
            return self._call_exchange(
                ('fapiPrivateGetUserTrades', 'fapiPrivate_get_usertrades'),
                params=params)
        if market_type == 'cm':
            return self._call_exchange(
                ('dapiPrivateGetUserTrades', 'dapiPrivate_get_usertrades'),
                params=params)
        if market_type == 'margin':
            return self._call_exchange(
                ('privateGetMyTrades', 'private_get_mytrades'), params=params)
        raise ValueError(f'unsupported market_type: {market_type}')


def make_binance_account_adapter(exchange, account_type=ACCOUNT_TYPE_STANDARD):
    return BinanceAccountAdapter(exchange, account_type)
