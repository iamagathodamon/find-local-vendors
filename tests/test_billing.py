import unittest

from src.billing import (
    SANDBOX_KEY,
    cap_error,
    default_state,
    get_key,
    issue_key,
    record_call,
)


class BillingTests(unittest.TestCase):
    def test_sandbox_key_is_present(self):
        state = default_state()
        key = get_key(state, SANDBOX_KEY)
        self.assertIsNotNone(key)
        self.assertTrue(key["sandbox"])

    def test_missing_key_is_none(self):
        self.assertIsNone(get_key(default_state(), "nope"))

    def test_sandbox_cap_after_three_calls(self):
        state = default_state()
        key = get_key(state, SANDBOX_KEY)
        for _ in range(3):
            record_call(state, key, trade="HVAC", city="Dallas, TX", result_count=2, ok=True)
        bucket = state["spend"][list(state["spend"].keys())[0]][SANDBOX_KEY]
        err = cap_error(key, bucket)
        self.assertEqual(err["error"], "cap_reached")
        self.assertIn("3", err["message"])

    def test_paid_key_charges_and_caps(self):
        state = default_state()
        key = issue_key(state, label="roofer.agent", price_cents=50, daily_cap_cents=50)
        first = record_call(state, key, trade="roofing", city="Austin, TX", result_count=4, ok=True)
        self.assertEqual(first["cost_cents"], 50)
        self.assertTrue(first["id"].startswith("rcpt_"))
        bucket = state["spend"][list(state["spend"].keys())[0]][key["id"]]
        err = cap_error(key, bucket)
        self.assertEqual(err["error"], "cap_reached")
        self.assertIn("daily cap", err["message"])

    def test_failed_paid_call_does_not_charge(self):
        state = default_state()
        key = issue_key(state, label="buyer")
        receipt = record_call(
            state, key, trade="HVAC", city="Dallas, TX", result_count=0, ok=False, error="upstream"
        )
        self.assertEqual(receipt["cost_cents"], 0)


if __name__ == "__main__":
    unittest.main()
