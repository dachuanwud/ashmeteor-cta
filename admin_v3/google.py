import hmac, base64, struct, hashlib, time


class CalGoogleCode():

    @staticmethod
    def cal_google_code(secret, current_time=int(time.time()) // 30):
        key = base64.b32decode(secret)
        msg = struct.pack(">Q", current_time)
        google_code = hmac.new(key, msg, hashlib.sha1).digest()
        o = ord(chr(google_code[19])) & 15
        google_code = (struct.unpack(">I", google_code[o:o + 4])[0]
                       & 0x7fffffff) % 1000000
        return '%06d' % google_code


if __name__ == '__main__':
    secret_key = ""
    print(CalGoogleCode.cal_google_code(secret_key))
    print(type(CalGoogleCode.cal_google_code(secret_key)))
