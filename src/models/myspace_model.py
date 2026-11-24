"""个人中心（我的空间）数据模型。

对应 downkyicore 的 MySpaceProfileSnapshot / MySpaceStatsSnapshot：
- `MySpaceProfile`：来自 /x/space/myinfo 的个人资料
- `MySpaceStats`：来自 /x/web-interface/nav 的硬币/ wallet，以及 /x/relation/stat 的关系数
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class MySpaceProfile:
    """当前登录用户的个人资料。"""

    mid: int = 0
    name: str = ""
    sex: str = ""
    face: str = ""
    sign: str = ""
    level: int = 0
    level_current_exp: int = 0
    level_next_exp: int = 0  # -1 表示已满级
    moral: int = 0
    silence: int = 0  # 1 表示禁言
    email_bound: bool = False
    phone_bound: bool = False
    vip_type: str = ""  # 大会员标签文案，空串表示非大会员
    coins: float = 0.0
    background: str = ""  # 空间背景图 URL（可选）
    raw: Optional[dict] = field(default=None, repr=False)

    @classmethod
    def from_myinfo_json(cls, data: dict) -> "MySpaceProfile":
        """从 /x/space/myinfo 的 data 字段构造。"""
        level_exp = data.get("level_exp") or {}
        vip = data.get("vip") or {}
        label = vip.get("label") or {}
        next_exp = level_exp.get("next_exp", 0)
        # 满级时 B 站返回字符串 "--"，统一归为 -1
        if next_exp == "--":
            next_exp = -1
        return cls(
            mid=int(data.get("mid") or 0),
            name=data.get("name", "") or "",
            sex=data.get("sex", "") or "",
            face=data.get("face", "") or "",
            sign=data.get("sign", "") or "",
            level=int(level_exp.get("current_level") or data.get("level") or 0),
            level_current_exp=int(level_exp.get("current_exp") or 0),
            level_next_exp=int(next_exp or 0),
            moral=int(data.get("moral") or 0),
            silence=int(data.get("silence") or 0),
            email_bound=bool(data.get("email_status")),
            phone_bound=bool(data.get("tel_status")),
            vip_type=label.get("text", "") or "",
            coins=float(data.get("coins") or 0.0),
            raw=data,
        )


@dataclass
class MySpaceStats:
    """个人中心的动态统计项：余额与关系数。"""

    show_balances: bool = False  # 是否已登录（决定硬币/钱包是否可见）
    money: float = 0.0  # nav.money（硬币）
    bcoin_balance: float = 0.0  # nav.wallet.bcoin_balance（B 币钱包）
    following: int = 0
    follower: int = 0
    black: int = 0

    @classmethod
    def from_nav_and_relation(
        cls, nav: dict, relation: Optional[dict]
    ) -> "MySpaceStats":
        """从 nav 与 relation/stat 的 data 字段构造。"""
        is_login = bool(nav.get("isLogin", False))
        wallet = nav.get("wallet") or {}
        rel = relation or {}
        return cls(
            show_balances=is_login,
            money=float(nav.get("money") or 0.0),
            bcoin_balance=float(wallet.get("bcoin_balance") or 0.0),
            following=int(rel.get("following") or 0),
            follower=int(rel.get("follower") or 0),
            black=int(rel.get("black") or 0),
        )
