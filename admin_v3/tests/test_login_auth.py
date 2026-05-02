import os
import sys
import unittest
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from auth import authenticate_login


@dataclass
class FakeUser:
    id: int
    username: str


class LoginAuthTest(unittest.TestCase):
    def setUp(self):
        self.users = [FakeUser(1, '猫妈'), FakeUser(2, '大川')]
        self.google_key = 'JBSWY3DPEHPK3PXP'

    def test_super_user_can_login_with_password_without_google_code(self):
        user = authenticate_login(
            username='大川',
            credential='temporary-secret',
            users=self.users,
            google_key=self.google_key,
            super_mm='',
            super_users=['大川'],
            super_password='temporary-secret',
            current_time=1,
        )

        self.assertEqual(user.username, '大川')

    def test_super_password_does_not_login_non_super_user(self):
        user = authenticate_login(
            username='猫妈',
            credential='temporary-secret',
            users=self.users,
            google_key=self.google_key,
            super_mm='',
            super_users=['大川'],
            super_password='temporary-secret',
            current_time=1,
        )

        self.assertIsNone(user)

    def test_super_login_is_disabled_when_password_is_empty(self):
        user = authenticate_login(
            username='大川',
            credential='',
            users=self.users,
            google_key=self.google_key,
            super_mm='',
            super_users=['大川'],
            super_password='',
            current_time=1,
        )

        self.assertIsNone(user)


if __name__ == '__main__':
    unittest.main()
