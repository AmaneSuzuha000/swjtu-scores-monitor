"""Pure-Python AES-CBC + PKCS7，用于复刻 SWJTU CAS 登录页的密码加密。

为什么不引第三方库：本项目跑在 GitHub Actions / Vercel 上，依赖清单固定在
pyproject.toml（uv.lock 锁死）。CAS 登录只需要 AES-128-CBC 一个原语，为了它新增
cryptography/pycryptodome 会拖进二进制轮子并可能拖慢冷启动，而纯 Python 实现
在此规模（一次登录加密 1 个块串）下开销可以忽略。

CAS 前端（encrypt.js）原文：
    var $aes_chars = "ABCDEFGHJKMNPQRSTWXYZabcdefhijkmnprstwxyz2345678";
    function randomString(n){ ... 从 $aes_chars 取 n 个随机字符 ... }
    function getAesString(data, key, iv){
        return CryptoJS.AES.encrypt(data, Utf8.parse(key),
               {iv: Utf8.parse(iv), mode: CBC, padding: Pkcs7}).toString();  // 输出 base64
    }
    function encryptAES(data, salt){ return salt ? getAesString(randomString(64)+data, salt, randomString(16)) : data }
    function encryptPassword(pwd, salt){ try { return encryptAES(pwd, salt) } catch(e){} return pwd }
"""

from __future__ import annotations

import base64
import secrets

# 与前端 encrypt.js 中的 $aes_chars 完全一致（有意剔除了易混字符 0O1Il 等）
AES_CHARS = "ABCDEFGHJKMNPQRSTWXYZabcdefhijkmnprstwxyz2345678"


def random_string(n: int) -> str:
    """等价于前端 randomString(n)：用同一字符集生成 n 个随机字符。"""
    return "".join(secrets.choice(AES_CHARS) for _ in range(n))


# ---------------------------------------------------------------- AES 原语

def _xtime(a: int) -> int:
    a <<= 1
    if a & 0x100:
        a ^= 0x11B
    return a & 0xFF


def _mul(a: int, b: int) -> int:
    r = 0
    for _ in range(8):
        if b & 1:
            r ^= a
        b >>= 1
        a = _xtime(a)
    return r


def _rotl8(x: int, n: int) -> int:
    return ((x << n) | (x >> (8 - n))) & 0xFF


def _build_tables() -> tuple[list[int], list[int]]:
    """按定义构造 AES S-box：先求 GF(2^8) 乘法逆元，再做仿射变换。

    直接用定义（而不是靠生成元 3 的遍历技巧）是为了正确性可读可验，
    只跑一次、性能无关紧要。
    """
    sbox = [0] * 256
    inv = [0] * 256
    for a in range(1, 256):
        for b in range(1, 256):
            if _mul(a, b) == 1:
                inv[a] = b
                break
    for a in range(256):
        i = inv[a]  # inv[0] == 0，与 S-box[0]=0x63 的约定一致
        sbox[a] = (i ^ _rotl8(i, 1) ^ _rotl8(i, 2) ^ _rotl8(i, 3) ^ _rotl8(i, 4) ^ 0x63) & 0xFF
    inv_sbox = [0] * 256
    for a, v in enumerate(sbox):
        inv_sbox[v] = a
    return sbox, inv_sbox


SBOX, INV_SBOX = _build_tables()
RCON = [0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1B, 0x36,
        0x6C, 0xD8, 0xAB, 0x4D]


def _expand_key(key: bytes) -> tuple[list[list[int]], int]:
    """标准 AES 密钥扩展；返回 (轮密钥字数组, 轮数)。"""
    nk = len(key) // 4
    if nk not in (4, 6, 8):
        raise ValueError(f"AES 密钥长度非法: {len(key)} 字节")
    nr = nk + 6
    w = [list(key[4 * i:4 * i + 4]) for i in range(nk)]
    for i in range(nk, 4 * (nr + 1)):
        temp = list(w[i - 1])
        if i % nk == 0:
            temp = temp[1:] + temp[:1]
            temp = [SBOX[b] for b in temp]
            temp[0] ^= RCON[i // nk - 1]
        elif nk > 6 and i % nk == 4:
            temp = [SBOX[b] for b in temp]
        w.append([w[i - nk][j] ^ temp[j] for j in range(4)])
    return w, nr


def _add_round_key(state: list[int], w: list[list[int]], rnd: int) -> None:
    for c in range(4):
        word = w[rnd * 4 + c]
        for r in range(4):
            state[r + 4 * c] ^= word[r]


def _sub_bytes(state: list[int]) -> None:
    for i in range(16):
        state[i] = SBOX[state[i]]


def _shift_rows(state: list[int]) -> None:
    for r in range(1, 4):
        row = [state[r + 4 * c] for c in range(4)]
        row = row[r:] + row[:r]
        for c in range(4):
            state[r + 4 * c] = row[c]


def _mix_columns(state: list[int]) -> None:
    for c in range(4):
        col = state[4 * c:4 * c + 4]
        state[4 * c + 0] = _mul(col[0], 2) ^ _mul(col[1], 3) ^ col[2] ^ col[3]
        state[4 * c + 1] = col[0] ^ _mul(col[1], 2) ^ _mul(col[2], 3) ^ col[3]
        state[4 * c + 2] = col[0] ^ col[1] ^ _mul(col[2], 2) ^ _mul(col[3], 3)
        state[4 * c + 3] = _mul(col[0], 3) ^ col[1] ^ col[2] ^ _mul(col[3], 2)


def _encrypt_block(block: bytes, w: list[list[int]], nr: int) -> bytes:
    state = list(block)
    _add_round_key(state, w, 0)
    for rnd in range(1, nr):
        _sub_bytes(state)
        _shift_rows(state)
        _mix_columns(state)
        _add_round_key(state, w, rnd)
    _sub_bytes(state)
    _shift_rows(state)
    _add_round_key(state, w, nr)
    return bytes(state)


def _pkcs7_pad(data: bytes) -> bytes:
    pad = 16 - (len(data) % 16)
    return data + bytes([pad]) * pad


def aes_cbc_encrypt(key: bytes, iv: bytes, plaintext: bytes) -> bytes:
    """AES-CBC + PKCS7 加密。key/iv 长度必须为 16/24/32 与 16 字节。"""
    if len(iv) != 16:
        raise ValueError("IV 必须为 16 字节")
    w, nr = _expand_key(key)
    data = _pkcs7_pad(plaintext)
    out = bytearray()
    prev = iv
    for i in range(0, len(data), 16):
        block = bytes(a ^ b for a, b in zip(data[i:i + 16], prev))
        prev = _encrypt_block(block, w, nr)
        out += prev
    return bytes(out)


# ------------------------------------------------------- CAS 专用封装

def encrypt_cas_password(password: str, salt: str) -> str:
    """复刻 CAS 前端 encryptPassword(password, salt)。

    salt 为空时前端会原样返回密码（本项目要求必须拿到 salt，为空即报错，
    免得把明文密码当密文发出去）。
    """
    if not salt:
        raise ValueError("CAS pwdEncryptSalt 为空：拒绝发送未加密密码")
    payload = (random_string(64) + password).encode("utf-8")
    key = salt.strip().encode("utf-8")
    iv = random_string(16).encode("utf-8")
    return base64.b64encode(aes_cbc_encrypt(key, iv, payload)).decode("ascii")
