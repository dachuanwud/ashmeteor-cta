import hmac
import time

from google import CalGoogleCode


def find_user(users, username):
    matches = [u for u in users if u.username == username]
    if len(matches) == 0:
        return None
    return matches[0]


def is_super_login(username, credential, super_users, super_password):
    if not super_password or not credential:
        return False
    if username not in super_users:
        return False
    return hmac.compare_digest(str(credential), str(super_password))


def authenticate_login(username,
                       credential,
                       users,
                       google_key,
                       super_mm,
                       super_users,
                       super_password,
                       current_time=None):
    user = find_user(users, username)
    if user is None:
        return None

    if is_super_login(username, credential, super_users, super_password):
        return user

    current_time = current_time or int(time.time()) // 30
    correct_code = CalGoogleCode.cal_google_code(google_key, current_time)
    if credential == correct_code:
        return user
    if super_mm and hmac.compare_digest(str(credential), str(super_mm)):
        return user
    return None
