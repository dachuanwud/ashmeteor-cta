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

        balances = self.exchange.papiGetBalance()
        if isinstance(balances, dict):
            balances = [balances]

        assets = []
        for item in balances:
            cm_wallet = Decimal(str(item.get('cmWalletBalance') or '0'))
            cm_pnl = Decimal(str(item.get('cmUnrealizedPNL') or '0'))
            margin_balance = cm_wallet + cm_pnl
            assets.append({
                'asset': item.get('asset', ''),
                'walletBalance': str(cm_wallet),
                'marginBalance': str(margin_balance),
            })
        return assets

    def get_cm_positions(self):
        if self.is_unified:
            return self.exchange.papiGetCmPositionRisk()
        return self.get_cm_account().get('positions', [])

    def get_cm_position_risk(self, params=None):
        if self.is_unified:
            return self.exchange.papiGetCmPositionRisk(params=params)
        return self._call_exchange(
            ('dapiPrivate_get_positionrisk', 'dapiPrivateGetPositionRisk'),
            params=params)

    def get_cm_adl_quantile(self, params=None):
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


def make_binance_account_adapter(exchange, account_type=ACCOUNT_TYPE_STANDARD):
    return BinanceAccountAdapter(exchange, account_type)
