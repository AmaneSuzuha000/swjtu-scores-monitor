"""新教务（yhxt）客户端离线测试。

不需要网络：用真实抓包得到的记录结构作为 fixture，验证归一化、双源合并、
以及“认证失效必须报错而不能退化成没有成绩”这条关键语义。

直接运行: python test/test_yhxt.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.yhxt import (  # noqa: E402
    YhxtAuthError,
    YhxtClient,
    YhxtError,
    normalize_record,
    merge_sources,
    load_ytoken_from_auth_state,
)

# —— 来自实网抓包（evidence/yethan_exam-mark-all_list.json）的真实结构 ——
MARK_ROW = {
    "sid": "3634507DDA253DDB68A414800A650C97",
    "termId": "122", "termName": "2025-2026第2学期", "termYear": 2025, "termSemester": 2,
    "studentId": "2025110724", "studentName": "陈泓霖",
    "courseCode": "CFGE001815", "courseName": "浪漫主义时代欧洲音乐", "courseType": "选",
    "teachClassId": 1, "staffName": "辛星", "creditHour": 2.0,
    "mark": 85.34, "markStr": "85.34", "examType": "正考",
    "lastMark": 94.68, "lastMarkPer": 50.0, "normalMark": 76.0, "normalMarkPer": 50.0,
    "memo": "", "gradeTypeId": "1", "gradeType": "百分制", "isMinor": None,
}

# —— 来自实网抓包（evidence/yethan_getAllScoreByStudentId.json）的在修课程 ——
ROSTER_ROW = {
    "termName": "2026-2027第1学期", "termId": "65E0C2060B78110E", "termYear": 2026,
    "termSemester": 1, "courseCode": "PHYE000311", "courseName": "体育Ⅲ",
    "courseType": "必修", "creditHour": "0.5", "mark": None, "markStr": None,
    "memo": None, "lastMark": None, "normalMark": None, "lastMarkPer": None,
    "normalMarkPer": None, "gradeTypeId": None, "gradeType": None, "examType": None,
    "isSecond": None, "isMarked": 0, "teachClassId": 5, "teachId": "B2415",
}


def test_normalize_keeps_legacy_schema():
    r = normalize_record(MARK_ROW)
    # 下游 actions/index.py 与本仓库邮件模板依赖这些键名
    for key in ("课程名称", "教师", "成绩", "学分", "平时成绩详情", "平时成绩总结"):
        assert key in r, f"缺少旧 schema 键 {key}"
    assert r["课程名称"] == "浪漫主义时代欧洲音乐"
    assert r["教师"] == "辛星"
    assert r["成绩"] == "85.34"          # 优先 markStr
    assert r["学分"] == "2.0"
    assert r["学期"] == "2025-2026第2学期"
    assert r["已出分"] is True
    details = r["平时成绩详情"]
    assert [d["平时成绩名称"] for d in details] == ["平时成绩", "期末成绩"]
    assert details[0]["成绩"] == "76.0" and details[0]["占比"] == "50.0%"
    print("ok normalize keeps legacy schema")


def test_normalize_unmarked_course():
    r = normalize_record(ROSTER_ROW)
    assert r["成绩"] == ""
    assert r["已出分"] is False
    assert r["平时成绩详情"] is None      # 未出分 -> 无明细，且是 None 不是 []
    assert r["教师"] == ""
    print("ok normalize unmarked course")


def test_merge_prefers_marks_and_keeps_roster():
    merged = merge_sources([MARK_ROW], [ROSTER_ROW])
    assert len(merged) == 2
    keys = {(m["termName"], m["courseCode"]) for m in merged}
    assert ("2025-2026第2学期", "CFGE001815") in keys
    assert ("2026-2027第1学期", "PHYE000311") in keys

    # 同一门课同时出现在两个来源时，成绩字段以明细表为准，名单字段保留
    dup_mark = dict(MARK_ROW)
    dup_roster = dict(ROSTER_ROW)
    dup_roster.update({"termName": "2025-2026第2学期", "courseCode": "CFGE001815",
                       "courseName": "浪漫主义时代欧洲音乐", "teachId": "B9999"})
    merged2 = merge_sources([dup_mark], [dup_roster])
    assert len(merged2) == 1
    row = merged2[0]
    assert row["mark"] == 85.34 and row["staffName"] == "辛星"
    assert row["teachId"] == "B9999"     # 只在名单里存在的字段被保留
    print("ok merge prefers marks and keeps roster")


class _FakeResp:
    def __init__(self, status=200, payload=None, url="", text=""):
        self.status_code = status
        self._payload = payload
        self.url = url
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise AssertionError("should not reach raise_for_status")


def _client_with(resp):
    c = YhxtClient("fake-token")
    c.session.get = lambda *a, **k: resp  # type: ignore[assignment]
    return c


def test_expired_token_raises_auth_error_not_empty():
    c = _client_with(_FakeResp(401, {"code": "401"}, url="https://yhxt/x"))
    try:
        c.student_info()
    except YhxtAuthError as exc:
        assert "失效" in str(exc) or "401" in str(exc)
        print("ok expired token -> YhxtAuthError")
        return
    raise AssertionError("401 必须抛 YhxtAuthError，绝不能返回空成绩")


def test_login_html_redirect_detected_as_auth_error():
    c = _client_with(_FakeResp(200, None, url="https://cas.swjtu.edu.cn/authserver/login",
                               text="<html>统一身份认证</html>"))
    try:
        c.student_info()
    except YhxtAuthError:
        print("ok login-page redirect -> YhxtAuthError")
        return
    raise AssertionError("被重定向回登录页时必须是认证错误")


def test_api_error_code_raises():
    c = _client_with(_FakeResp(200, {"code": "500", "message": "系统异常"}))
    try:
        c.student_info()
    except YhxtError as exc:
        assert not isinstance(exc, YhxtAuthError)
        print("ok non-auth API error -> YhxtError")
        return
    raise AssertionError("非 00000 的 code 必须抛错")


def test_success_code_passes():
    c = _client_with(_FakeResp(200, {"code": "00000", "data": {"studentId": "2025110724"}}))
    assert c.student_info()["studentId"] == "2025110724"
    print("ok code 00000 -> data")


def test_auth_state_loader():
    import json
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "yhxt_auth.json")
        with open(p, "w", encoding="utf-8") as fh:
            json.dump({"ytoken": "tok-123", "cookies": []}, fh)
        assert load_ytoken_from_auth_state(p) == "tok-123"
        bad = os.path.join(d, "bad.json")
        with open(bad, "w", encoding="utf-8") as fh:
            json.dump({"cookies": []}, fh)
        try:
            load_ytoken_from_auth_state(bad)
        except YhxtAuthError:
            print("ok auth-state loader (hit + miss)")
            return
        raise AssertionError("缺少 ytoken 字段时必须报错")


def test_auth_state_accepts_inline_json():
    """GitHub Actions 上只有 Secret 文本，没有文件——内联 JSON 必须可用。"""
    assert load_ytoken_from_auth_state('{"ytoken":"tok-inline"}') == "tok-inline"
    assert load_ytoken_from_auth_state('  {"token": "tok-alt"}  ') == "tok-alt"
    print("ok auth-state inline JSON")


def test_auth_state_rejects_unusable_value():
    """路径不存在、文本又不是 JSON 时必须明确报错，而不是静默当作没有凭据。"""
    try:
        load_ytoken_from_auth_state(r"Z:\definitely\missing\auth.json")
    except YhxtAuthError as exc:
        assert "无法" in str(exc) or "不是" in str(exc)
        print("ok auth-state unusable value -> YhxtAuthError")
        return
    raise AssertionError("不可用的 auth-state 必须报错")


def test_build_client_prefers_inline_state(monkeypatch):
    """YHXT_YTOKEN > YHXT_AUTH_STATE(内联 JSON) 的优先级必须成立。"""
    from utils.yhxt import build_client_from_env
    monkeypatch.setenv("YHXT_YTOKEN", "tok-direct")
    monkeypatch.setenv("YHXT_AUTH_STATE", '{"ytoken":"tok-state"}')
    assert build_client_from_env().ytoken == "tok-direct"
    monkeypatch.delenv("YHXT_YTOKEN")
    assert build_client_from_env().ytoken == "tok-state"
    print("ok credential precedence (YHXT_YTOKEN > inline AUTH_STATE)")


def test_client_requires_token():
    try:
        YhxtClient("")
    except YhxtAuthError:
        print("ok empty token rejected")
        return
    raise AssertionError("空 token 必须被拒绝")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
    print(f"\nALL {len(tests)} TESTS PASSED")
