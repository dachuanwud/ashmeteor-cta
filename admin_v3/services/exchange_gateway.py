from binance_account import (ACCOUNT_TYPE_STANDARD,
                             make_binance_account_adapter)


class ExchangeGateway:
    """Narrow exchange boundary used by services.

    Routes and schedulers should depend on this small surface instead of
    directly branching on fapi/dapi/papi method names.
    """

    def __init__(self, exchange, account_type=ACCOUNT_TYPE_STANDARD):
        self.exchange = exchange
        self.account_type = account_type
        self.account = make_binance_account_adapter(exchange, account_type)

    @property
    def is_unified(self):
        return self.account.is_unified

    def get_account_summary(self):
        return self.account.get_account_summary()

    def get_balance_assets(self):
        return self.account.get_balance_assets()

    def get_margin_asset_balance(self, asset):
        return self.account.get_margin_asset_balance(asset)

    def get_margin_max_borrowable(self, asset):
        return self.account.get_margin_max_borrowable(asset)

    def get_um_position_risk(self, params=None):
        return self.account.get_um_position_risk(params=params)

    def get_cm_position_risk(self, params=None):
        return self.account.get_cm_position_risk(params=params)

    def place_um_order(self, params):
        return self.account.place_um_order(params)

    def place_cm_order(self, params):
        return self.account.place_cm_order(params)

    def place_margin_order(self, params):
        return self.account.place_margin_order(params)


def make_exchange_gateway(exchange, account_type=ACCOUNT_TYPE_STANDARD):
    return ExchangeGateway(exchange, account_type)
