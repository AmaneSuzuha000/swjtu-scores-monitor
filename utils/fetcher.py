"""成绩抓取门面（新教务 yhxt）。

历史：本模块原先抓 jwc 旧教务（/vatuu），依赖 CAS cookie + 验证码 OCR，
成绩是 HTML 表格（table3）。旧教务已停用，这里改为新教务 yhxt 的 JSON API，
但**对外接口保持不变**（ScoreFetcher.login / get_all_scores /
get_normal_scores / get_combined_scores），这样 actions/ 与 api/ 的下游逻辑
（变化对比、邮件渲染、Gist 存储）一行都不用改。

新教务的接口与认证细节见 utils/yhxt.py。
"""

from __future__ import annotations

import os
import sys

from utils.yhxt import (
    YhxtAuthError,
    YhxtClient,
    YhxtError,
    build_client_from_env,
    fetch_normalized,
    refresh_ytoken_if_needed,
)


class ScoreFetcher:
    """保持旧签名的门面：真正的实现委托给 utils.yhxt。

    username/password 现在是**可选的**——新教务优先用 ytoken；
    只有在需要无头 CAS 登录时才用到账号密码。
    """

    def __init__(self, username: str | None = None, password: str | None = None,
                 *, ytoken: str | None = None):
        self.username = username or ""
        self.password = password or ""
        self.ytoken = (ytoken or "").strip()
        self.client: YhxtClient | None = None
        self.is_logged_in = False

    # ------------------------------------------------------------------
    def login(self, max_retries: int = 10, retry_delay: int = 1) -> bool:
        """建立可用的成绩查询会话。

        旧教务要过验证码并重试 10 次；新教务用 token，失败基本都是凭据问题，
        重试没有意义（CAS 连续失败反而会触发风控），因此参数保留但只尝试一次。
        """
        try:
            if self.ytoken:
                self.client = YhxtClient(self.ytoken)
            else:
                self.client = build_client_from_env()
                if self.username and self.password:
                    # 让 build_client_from_env 之外的显式账号密码也生效
                    os.environ.setdefault("SWJTU_USERNAME", self.username)
                    os.environ.setdefault("SWJTU_PASSWORD", self.password)
        except YhxtError as exc:
            print(f"登录失败: {exc}")
            return False

        if not self.client.validate():
            try:
                self.client = refresh_ytoken_if_needed(self.client)
            except YhxtError as exc:
                print(f"会话不可用: {exc}")
                return False

        info = self.client.student_info()
        print(f"已登录新教务：{info.get('studentName')} "
              f"({info.get('studentId')}) {info.get('className')}")
        self.is_logged_in = True
        return True

    # ------------------------------------------------------------------
    def get_all_scores(self) -> list[dict] | None:
        """全部成绩（新教务：成绩明细 + 在修课程总表合并后归一化）。"""
        if not self.is_logged_in or self.client is None:
            print("错误：未登录。")
            return None
        try:
            rows = fetch_normalized(self.client)
        except YhxtAuthError as exc:
            # 认证失效绝不能退化成“没有成绩”，否则会被当成成绩被清空
            print(f"错误：会话已失效（{exc}），本次不按无成绩处理。")
            self.is_logged_in = False
            raise
        except YhxtError as exc:
            print(f"获取成绩时出错: {exc}")
            return None

        print(f"成功获取到 {len(rows)} 条成绩记录。")
        return rows

    def get_normal_scores(self) -> list[dict] | None:
        """平时成绩明细。

        新教务不提供“平时成绩名称/占比/提交时间”这种逐条明细，只有
        平时成绩/期末成绩两个聚合分（已并入 get_all_scores 的每条记录）。
        保留此方法是为了兼容旧调用方：返回空列表（有数据但无独立明细），
        而不是 None（表示读取失败）。
        """
        if not self.is_logged_in:
            print("错误：未登录。")
            return None
        print("新教务无独立平时成绩明细接口，聚合分已包含在总成绩记录中。")
        return []

    def get_combined_scores(self) -> list[dict] | None:
        """兼容旧签名：新教务的总成绩记录里已经包含平时/期末聚合分。"""
        return self.get_all_scores()


if __name__ == "__main__":
    sf = ScoreFetcher(os.environ.get("SWJTU_USERNAME"), os.environ.get("SWJTU_PASSWORD"))
    if sf.login():
        rows = sf.get_combined_scores() or []
        print(f"获取到 {len(rows)} 条成绩记录")
        for r in rows[:5]:
            print(r)
    else:
        sys.exit(1)
