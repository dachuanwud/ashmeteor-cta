import os
import sys
import unittest
from datetime import datetime
from decimal import Decimal

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from services.account_snapshot import build_position_snapshot
from services.cta_runtime import (align_cta_run_time, build_cta_key,
                                  merge_closed_kline_history)
from services.halfset_coordinator import calculate_halfset_multi_targets


class AccountSnapshotServiceTest(unittest.TestCase):
    def test_cm_position_snapshot_keeps_base_and_usd_units_separate(self):
        row = build_position_snapshot(
            {
                'symbol': 'ETHUSD_PERP',
                'positionAmt': '-50',
                'notionalValue': '-0.2144',
                'markPrice': '2332',
                'unRealizedProfit': '1.25',
            },
            'CM',
        )

        self.assertEqual(row['base_notional_qty'], Decimal('-0.2144'))
        self.assertEqual(row['notional_usd'], Decimal('499.9808'))
        self.assertEqual(row['side'], 'SELL')

    def test_um_position_snapshot_uses_usd_notional_directly(self):
        row = build_position_snapshot(
            {
                'symbol': 'ETHUSDT',
                'positionAmt': '-0.2',
                'notional': '-466.4',
                'markPrice': '2332',
            },
            'UM',
        )

        self.assertEqual(row['base_notional_qty'], Decimal('-0.2'))
        self.assertEqual(row['notional_usd'], Decimal('466.4'))


class CtaRuntimeServiceTest(unittest.TestCase):
    def test_runtime_helpers_align_time_and_keep_only_closed_klines(self):
        self.assertEqual(
            build_cta_key('ETHUSDT', '4h', 'adapt_bolling_anti_chase',
                          '[200,20]'),
            'ETHUSDT_4h_adapt_bolling_anti_chase_[200,20]',
        )
        aligned = align_cta_run_time(datetime(2026, 5, 6, 15, 37), '4h')
        self.assertEqual(aligned, datetime(2026, 5, 6, 12, 0))

        old = pd.DataFrame([{
            'candle_begin_time': datetime(2026, 5, 6, 4, 0),
            'close': 1,
        }, {
            'candle_begin_time': datetime(2026, 5, 6, 8, 0),
            'close': 2,
        }])
        new = pd.DataFrame([{
            'candle_begin_time': datetime(2026, 5, 6, 8, 0),
            'close': 3,
        }, {
            'candle_begin_time': datetime(2026, 5, 6, 12, 0),
            'close': 4,
        }])

        merged = merge_closed_kline_history(old, new, aligned)

        self.assertEqual(list(merged['candle_begin_time']),
                         [datetime(2026, 5, 6, 4, 0),
                          datetime(2026, 5, 6, 8, 0)])
        self.assertEqual(list(merged['close']), [1, 3])


class HalfsetCoordinatorServiceTest(unittest.TestCase):
    def test_multi_overlay_targets_share_remaining_half_budget(self):
        targets = calculate_halfset_multi_targets(
            Decimal('0.4'),
            '0.5',
            [{
                'cta_key': 'long',
                'is_running': 1,
                'last_signal': 1,
                'weight': 2,
                'trade_ratio': 1,
            }, {
                'cta_key': 'short',
                'is_running': 1,
                'last_signal': -1,
                'weight': 1,
                'trade_ratio': 1,
            }],
        )

        self.assertEqual(targets['half_target_qty'], Decimal('-0.20'))
        self.assertEqual(targets['overlays'][0]['target_qty'],
                         Decimal('0.1333333333333333333333333333'))
        self.assertEqual(targets['overlays'][1]['target_qty'],
                         Decimal('-0.06666666666666666666666666667'))
        self.assertEqual(targets['cta_target_qty'],
                         Decimal('0.06666666666666666666666666663'))


if __name__ == '__main__':
    unittest.main()
