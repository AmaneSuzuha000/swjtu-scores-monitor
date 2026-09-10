"""手动排查脚本：直接查看新教务（yhxt）返回的原始成绩数据。

原版抓 jwc 旧教务（/vatuu + 验证码 OCR + HTML 表格），教务迁移后已不可用，
这里改为调用 yhxt JSON API。用法：

    # 方式一：直接给 ytoken（推荐，从浏览器 localStorage 的 ytoken 复制）
    set YHXT_YTOKEN=xxxxx            # PowerShell: $env:YHXT_YTOKEN='xxxxx'
    python test/score.py

    # 方式二：指向浏览器导出的 auth-state JSON
    set YHXT_AUTH_STATE=C:\\path\\yhxt_auth.json
    python test/score.py

    # 方式三：无头 CAS 登录（需要账号密码，可能触发风控）
    set SWJTU_USERNAME=2025xxxx
    set SWJTU_PASSWORD=xxxxx
    python test/score.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.yhxt import build_client_from_env, fetch_normalized  # noqa: E402


def main() -> int:
    try:
        client = build_client_from_env()
    except Exception as exc:
        print(f"未取得可用凭据: {exc}")
        return 2

    info = client.student_info()
    print("=" * 72)
    print(f"学生: {info.get('studentName')} ({info.get('studentId')})")
    print(f"学院: {info.get('collegeName')}  专业: {info.get('majorName')}")
    print(f"班级: {info.get('className')}  年级: {info.get('grade')}")
    print("=" * 72)

    marks = client.get_exam_marks()
    print(f"\n[成绩明细表 /score/exam-mark-all/list] {len(marks)} 条，前 3 条原始字段：")
    for row in marks[:3]:
        print("  " + json.dumps(row, ensure_ascii=False))

    roster = client.get_score_all_list()
    all_list = roster.get("scoreAllList") or []
    print(f"\n[学生成绩总表 /public/score/getAllScoreByStudentId] "
          f"scoreList={len(roster.get('scoreList') or [])} "
          f"scoreAllList={len(all_list)} 条，前 3 条原始字段：")
    for row in all_list[:3]:
        print("  " + json.dumps(row, ensure_ascii=False))

    rows = fetch_normalized(client)
    print(f"\n[归一化后] {len(rows)} 条（供 actions/api 使用）：")
    for r in rows[:5]:
        print("  " + json.dumps(r, ensure_ascii=False))

    out = Path(__file__).resolve().parent / "scores_snapshot.json"
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n已写出快照: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
