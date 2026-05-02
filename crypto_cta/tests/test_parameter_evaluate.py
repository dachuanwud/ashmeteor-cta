import unittest


class ParameterEvaluateTest(unittest.TestCase):
    def test_strategy_parameter_dimension_uses_single_combination_width(self):
        from cta_api.tools import get_parameter_dimension

        self.assertEqual(get_parameter_dimension([10, 20, 30]), 1)
        self.assertEqual(get_parameter_dimension([[10], [20], [30]]), 1)
        self.assertEqual(get_parameter_dimension([[10, 2], [20, 3]]), 2)


if __name__ == "__main__":
    unittest.main()
