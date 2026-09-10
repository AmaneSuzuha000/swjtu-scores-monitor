"""新教务（yhxt / yethan）客户端：登录 + 成绩抓取 + 归一化。

迁移自旧教务（jwc /vatuu + CAS cookie + 验证码 OCR）。旧路径的三个硬伤：
  1. 登录要过验证码，必须带 OCR 模型（依赖重、识别率不确定）；
  2. 会话失效不返回 4xx，而是 302 回登录页 / 回填登录页文本，靠“表格没找到”
     判断会把“登录失效”误报成“没有成绩”；
  3. 成绩是 HTML 表格，列位置一变解析就错。
新教务是 JSON API，且认证载体是单一 header（ytoken）。

认证（真实抓包/前端逆向结论，见 case evidence）：
  - 浏览器登录流程：CAS 登录成功 → 302 到
      https://yhxt.swjtu.edu.cn/cas-login.html?ticket=ST-xxx
    → 前端 GET /yethan/public/casCallback?ticket=... → 返回 {data:{token}}，
    该 token 即 ytoken，之后所有 /yethan/* 请求带 header `ytoken: <token>`。
  - 因此本模块支持两条取 token 的路：
      (a) 直接给 ytoken（YHXT_YTOKEN，或复用已有的 auth-state JSON）；
      (b) 给统一认证账号密码，走无头 CAS 登录换取 ytoken。
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlencode, urljoin, urlparse, parse_qs

import requests

from utils import aes_cbc

CAS_BASE = os.getenv("CAS_BASE", "https://cas.swjtu.edu.cn/authserver")
# 与前端 login-cas.js 里的 serviceUrl 一致（后端也按这个 service 注册回调）
SERVICE_URL = os.getenv("YHXT_SERVICE_URL", "https://yhxt.swjtu.edu.cn/cas-login.html")
YHXT_BASE = os.getenv("YHXT_BASE", "https://yhxt.swjtu.edu.cn/yethan")

API_TIMEOUT = int(os.getenv("YHXT_API_TIMEOUT", "20"))

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/136.0 Safari/537.36"
)

SUCCESS_CODE = "00000"


class YhxtError(Exception):
    """新教务 API 通用错误。"""


class YhxtAuthError(YhxtError):
    """认证失败 / 会话失效：必须与“没有成绩”区分开，否则会误报。"""


def _headers(ytoken: str = "") -> dict[str, str]:
    h = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Referer": "https://yhxt.swjtu.edu.cn/study/",
        "Origin": "https://yhxt.swjtu.edu.cn",
        "Connection": "keep-alive",
    }
    if ytoken:
        h["ytoken"] = ytoken
    return h


# ------------------------------------------------------------------ 登录

def _load_cas_form(session: requests.Session, service: str) -> tuple[str, str]:
    """打开 CAS 登录页，取出 execution 与 pwdEncryptSalt。"""
    resp = session.get(
        f"{CAS_BASE}/login", params={"service": service},
        headers={"User-Agent": USER_AGENT}, timeout=API_TIMEOUT, allow_redirects=True,
    )
    resp.raise_for_status()
    html = resp.text

    execution = ""
    m = re.search(r'name=["\']execution["\'][^>]*value=["\']([^"\']+)["\']', html)
    if not m:
        m = re.search(r'value=["\']([^"\']+)["\'][^>]*name=["\']execution["\']', html)
    if m:
        execution = m.group(1)

    salt = ""
    m = re.search(r'id=["\']pwdEncryptSalt["\'][^>]*value=["\']([^"\']*)["\']', html)
    if m:
        salt = m.group(1)
    if not salt:
        m = re.search(r'value=["\']([^"\']*)["\'][^>]*id=["\']pwdEncryptSalt["\']', html)
        if m:
            salt = m.group(1)

    if not execution or not salt:
        raise YhxtAuthError(
            "CAS 登录页结构变化：未能取到 execution/pwdEncryptSalt"
            f"（execution={bool(execution)}, salt={bool(salt)}）。"
            "登录页若出现验证码/风控，需要人工介入或改用 ytoken 方式。"
        )
    return execution, salt


def _extract_ticket(url: str) -> str:
    if not url:
        return ""
    qs = parse_qs(urlparse(url).query)
    return (qs.get("ticket") or [""])[0]


def login_cas(
    username: str,
    password: str,
    *,
    session: requests.Session | None = None,
    service: str = SERVICE_URL,
) -> tuple[str, list[dict]]:
    """无头 CAS 登录，返回 (ytoken, cookies)。

    只做一次尝试：CAS 连续失败会触发图形验证码/风控，反复重试只会把账号锁得更死。
    """
    session = session or requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    execution, salt = _load_cas_form(session, service)
    payload = {
        "username": username,
        "password": aes_cbc.encrypt_cas_password(password, salt),
        "lt": "",
        "execution": execution,
        "_eventId": "submit",
        "cllt": "userNameLogin",
        "dllt": "generalLogin",
        "rememberMe": "true",
    }
    resp = session.post(
        f"{CAS_BASE}/login", params={"service": service}, data=payload,
        headers={"User-Agent": USER_AGENT, "Referer": f"{CAS_BASE}/login"},
        timeout=API_TIMEOUT, allow_redirects=True,
    )
    resp.raise_for_status()

    if "authserver/login" in (resp.url or "") or "请输入验证码" in resp.text or "captcha" in resp.url:
        raise YhxtAuthError(
            "CAS 登录未通过（停留在登录页/需要验证码）。请人工登录一次该账号完成风控校验，"
            "或改用 YHXT_YTOKEN 方式。"
        )

    ticket = _extract_ticket(resp.url)
    if not ticket:
        # 有些部署不会把 ticket 放在最终 URL，而在中间跳转的 Location 里
        for hop in resp.history:
            ticket = ticket or _extract_ticket(hop.headers.get("Location", ""))
        ticket = ticket or _extract_ticket(resp.text)
    if not ticket:
        raise YhxtAuthError("CAS 登录后未拿到 ticket（账号密码可能有误，或被风控拦截）。")

    return exchange_ticket(ticket, session=session)


def exchange_ticket(ticket: str, *, session: requests.Session | None = None) -> tuple[str, list[dict]]:
    """ticket -> ytoken（对应前端 /yethan/public/casCallback）。"""
    session = session or requests.Session()
    resp = session.get(
        f"{YHXT_BASE}/public/casCallback", params={"ticket": ticket},
        headers=_headers(), timeout=API_TIMEOUT,
    )
    resp.raise_for_status()
    try:
        data = resp.json()
    except ValueError as exc:
        raise YhxtAuthError(f"casCallback 返回非 JSON：{resp.text[:200]}") from exc

    token = ((data.get("data") or {}) if isinstance(data.get("data"), dict) else {}).get("token")
    if not token:
        raise YhxtAuthError(f"casCallback 未返回 token：{json.dumps(data, ensure_ascii=False)[:300]}")
    return token, _dump_cookies(session)


def _dump_cookies(session: requests.Session) -> list[dict]:
    out = []
    for c in session.cookies:
        out.append({
            "name": c.name, "value": c.value, "domain": c.domain,
            "path": c.path or "/", "expires": c.expires or -1,
            "httpOnly": bool(c._rest.get("HttpOnly")) if hasattr(c, "_rest") else False,
            "secure": bool(c.secure),
            "sameSite": (c._rest.get("SameSite") if hasattr(c, "_rest") else None),
        })
    return out


def load_ytoken_from_auth_state(path: str | Path) -> str:
    """从已有的 auth-state JSON 里取 ytoken（兼容浏览器导出的多种字段名）。"""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    for key in ("ytoken", "token", "YHXT_YTOKEN"):
        val = data.get(key)
        if isinstance(val, str) and val:
            return val
    raise YhxtAuthError(f"{path} 中未找到 ytoken 字段")


# ------------------------------------------------------------------ 客户端

class YhxtClient:
    """新教务成绩 API 客户端。"""

    def __init__(self, ytoken: str, cookies: list[dict] | None = None,
                 timeout: int = API_TIMEOUT):
        if not ytoken:
            raise YhxtAuthError("ytoken 为空")
        self.ytoken = ytoken
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(_headers(ytoken))
        for c in cookies or []:
            try:
                self.session.cookies.set(c.get("name"), c.get("value"),
                                         domain=c.get("domain"), path=c.get("path", "/"))
            except Exception:
                # cookie 属性缺 domain 时 set 会抛错，纯装饰性信息，忽略
                continue

    # ---- 底层请求：统一处理超时 / 认证失效 ----
    def _get(self, path: str, params: dict | None = None) -> dict:
        url = f"{YHXT_BASE}{path}"
        try:
            resp = self.session.get(url, params=params, timeout=self.timeout)
        except requests.exceptions.Timeout as exc:
            raise YhxtError(f"请求超时（{self.timeout}s）: {path}") from exc
        except requests.exceptions.RequestException as exc:
            raise YhxtError(f"请求失败: {path}: {exc}") from exc

        if resp.status_code in (401, 403):
            raise YhxtAuthError(f"ytoken 已失效（HTTP {resp.status_code}）: {path}")
        resp.raise_for_status()

        try:
            data = resp.json()
        except ValueError as exc:
            if "login" in (resp.url or "") or "统一身份认证" in resp.text[:2000]:
                raise YhxtAuthError(f"会话失效，被重定向到登录页: {path}") from exc
            raise YhxtError(f"响应不是 JSON: {path}: {resp.text[:200]}") from exc

        code = str(data.get("code", ""))
        if code != SUCCESS_CODE:
            msg = data.get("message") or data.get("msg") or ""
            # 认证类错误必须显式抛出：不能退化成“没有成绩”
            if code in {"401", "403", "A0230", "A0301"} or "登录" in str(msg) or "token" in str(msg).lower():
                raise YhxtAuthError(f"API 认证失败 code={code} msg={msg}")
            raise YhxtError(f"API 返回错误 code={code} msg={msg} path={path}")
        return data

    # ---- 接口 ----
    def student_info(self) -> dict:
        return self._get("/register/student-course/info").get("data") or {}

    def validate(self) -> bool:
        """判断 ytoken 是否可用（不发成绩请求，代价最小）。"""
        try:
            self.student_info()
            return True
        except YhxtAuthError:
            return False

    def get_score_all_list(self) -> dict:
        """学生成绩总表（含本学期在修课程，未出分时 mark 为 null）。"""
        return self._get("/public/score/getAllScoreByStudentId",
                         {"keywords": "", "onlyMarked": "true"}).get("data") or {}

    def get_exam_marks(self) -> list[dict]:
        """全部已出成绩明细（含任课教师 staffName）。"""
        data = self._get("/score/exam-mark-all/list", {"keywords": ""}).get("data")
        return data if isinstance(data, list) else []


# ------------------------------------------------------------------ 归一化

def _display_mark(item: dict) -> str:
    """成绩展示值：优先 markStr（等级制/百分制都由后端格式化），退回 mark。"""
    mark_str = item.get("markStr")
    if mark_str not in (None, ""):
        return str(mark_str)
    mark = item.get("mark")
    return "" if mark in (None, "") else str(mark)


def _normal_components(item: dict) -> list[dict] | None:
    """把新教务的 平时/期末 两个聚合分还原成旧版“平时成绩详情”的形状，
    这样 actions/index.py 的变化对比与邮件渲染逻辑不需要改。
    """
    details: list[dict] = []
    normal, last = item.get("normalMark"), item.get("lastMark")
    if normal not in (None, ""):
        details.append({
            "平时成绩名称": "平时成绩",
            "成绩": str(normal),
            "占比": "" if item.get("normalMarkPer") is None else f"{item.get('normalMarkPer')}%",
            "提交时间": "",
        })
    if last not in (None, ""):
        details.append({
            "平时成绩名称": "期末成绩",
            "成绩": str(last),
            "占比": "" if item.get("lastMarkPer") is None else f"{item.get('lastMarkPer')}%",
            "提交时间": "",
        })
    return details or None


def normalize_record(item: dict) -> dict:
    """新教务成绩记录 -> 本项目统一 schema。

    保留旧字段名（课程名称/教师/成绩/学分/平时成绩详情）是为了让下游
    对比与通知逻辑零改动；后缀新增的是新教务独有的信息，用于更详细的邮件。
    """
    return {
        # ——— 旧 schema（下游依赖，勿随意改名）———
        "课程名称": item.get("courseName") or "",
        "教师": item.get("staffName") or "",
        "成绩": _display_mark(item),
        "学分": "" if item.get("creditHour") in (None, "") else str(item.get("creditHour")),
        "平时成绩详情": _normal_components(item),
        "平时成绩总结": item.get("memo") or "",
        # ——— 新教务独有 ———
        "学期": item.get("termName") or "",
        "课程代码": item.get("courseCode") or "",
        "课程性质": item.get("courseType") or "",
        "成绩类型": item.get("gradeType") or "",
        "考试类型": item.get("examType") or "",
        "平时": "" if item.get("normalMark") in (None, "") else item.get("normalMark"),
        "期末": "" if item.get("lastMark") in (None, "") else item.get("lastMark"),
        "平时占比": item.get("normalMarkPer"),
        "期末占比": item.get("lastMarkPer"),
        "记录ID": item.get("sid") or "",
        "已出分": item.get("mark") not in (None, ""),
    }


def merge_sources(marks: list[dict], roster: list[dict]) -> list[dict]:
    """合并两个来源：

    - marks  （exam-mark-all/list）: 权威成绩，带教师；
    - roster （scoreAllList）       : 在修课程名单，未出分时 mark=null。

    以 (学期, 课程代码) 为键合并：有成绩的字段优先来自 marks，
    这样“本学期在修、尚未出分”的课程会以 mark="" 进入基线，等出分时
    自然被识别为“新增总成绩”。
    """
    merged: dict[tuple, dict] = {}

    def key_of(it: dict) -> tuple:
        return (it.get("termName") or "", it.get("courseCode") or "", it.get("courseName") or "")

    for it in roster:
        merged[key_of(it)] = dict(it)
    for it in marks:
        k = key_of(it)
        base = merged.get(k, {})
        row = dict(base)
        row.update({kk: vv for kk, vv in it.items() if vv not in (None, "")})
        # 保留 roster 里有、marks 里没有的字段
        for kk, vv in base.items():
            row.setdefault(kk, vv)
        merged[k] = row

    return list(merged.values())


def fetch_normalized(client: YhxtClient) -> list[dict]:
    """抓取并归一化全部成绩（两个来源合并）。"""
    marks = client.get_exam_marks()
    roster: list[dict] = []
    try:
        roster = client.get_score_all_list().get("scoreAllList") or []
    except YhxtError as exc:
        # 总表拿不到不影响成绩监控主体：marks 已经是权威成绩源
        print(f"（警告）读取学生成绩总表失败，仅使用成绩明细表: {exc}")
    rows = merge_sources(marks, roster)
    return [normalize_record(r) for r in rows]


def build_client_from_env() -> YhxtClient:
    """按环境决定取 token 的方式，返回可用客户端。

    优先级：YHXT_YTOKEN > YHXT_AUTH_STATE(文件) > CAS 账号密码登录。
    """
    token = (os.getenv("YHXT_YTOKEN") or "").strip()
    if token:
        return YhxtClient(token)

    state_path = (os.getenv("YHXT_AUTH_STATE") or "").strip()
    if state_path and Path(state_path).exists():
        return YhxtClient(load_ytoken_from_auth_state(state_path))

    username = (os.getenv("SWJTU_USERNAME") or os.getenv("YHXT_USERNAME") or "").strip()
    password = os.getenv("SWJTU_PASSWORD") or os.getenv("YHXT_PASSWORD") or ""
    if username and password:
        token, cookies = login_cas(username, password)
        return YhxtClient(token, cookies)

    raise YhxtAuthError(
        "未提供任何新教务凭据：请设置 YHXT_YTOKEN（推荐）、YHXT_AUTH_STATE，"
        "或 SWJTU_USERNAME/SWJTU_PASSWORD 走无头 CAS 登录。"
    )


def refresh_ytoken_if_needed(client: YhxtClient) -> YhxtClient:
    """token 失效且配置了账号密码时，自动重新登录一次。"""
    if client.validate():
        return client
    username = (os.getenv("SWJTU_USERNAME") or "").strip()
    password = os.getenv("SWJTU_PASSWORD") or ""
    if not (username and password):
        raise YhxtAuthError("ytoken 已失效，且未配置账号密码，无法自动续期。")
    print("ytoken 已失效，正在用账号密码重新登录……")
    token, cookies = login_cas(username, password)
    return YhxtClient(token, cookies)


if __name__ == "__main__":
    # 手动排查用：验证当前凭据能否取到成绩
    c = build_client_from_env()
    info = c.student_info()
    print(f"学生: {info.get('studentName')} ({info.get('studentId')}) {info.get('className')}")
    rows = fetch_normalized(c)
    print(f"成绩记录: {len(rows)}")
    for r in rows[:5]:
        print(" ", json.dumps(r, ensure_ascii=False))
