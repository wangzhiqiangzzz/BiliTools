"""个人中心（我的空间）服务：当前登录用户的资料、余额与关系数。

对应 downkyicore 的 UserSpacePageCoordinator：
- `get_profile()`  → /x/space/myinfo（需登录）+ 可选背景图（/x/space/wbi/acc/info）
- `get_stats()`    → /x/web-interface/nav（硬币/钱包）+ /x/relation/stat（关注/粉丝/黑名单）

背景图接口需要 wbi 签名，属于增强项：失败时静默降级为空，不影响个人页主体。
"""

import logging
from typing import Optional

from src.api.auth import get_wbi
from src.api.session import BiliSession
from src.models.myspace_model import MySpaceProfile, MySpaceStats
from src.urls.user_urls import UserUrls

logger = logging.getLogger(__name__)


class MySpaceService:
    """当前登录用户的个人中心数据服务。"""

    def __init__(self, session: Optional[BiliSession] = None):
        self.session = session if session is not None else BiliSession()

    def get_profile(self, mid: int = 0) -> MySpaceProfile:
        """获取个人资料（不含背景图失败时的兜底）。

        :param mid: 用户 mid，仅用于可选背景图接口；资料本身来自 myinfo 当前登录态。
        """
        data = self.session.get(UserUrls.MY_INFO)
        profile = MySpaceProfile.from_myinfo_json(data)
        profile.background = self._fetch_background(mid or profile.mid)
        return profile

    def get_stats(self, mid: int) -> MySpaceStats:
        """获取硬币/钱包余额与关注粉丝数。"""
        nav = self.session.get(UserUrls.NAV)
        relation: Optional[dict] = None
        try:
            relation = self.session.get(UserUrls.RELATION_STAT, params={"vmid": mid})
        except Exception as e:
            logger.warning("[MySpaceService] 关系数获取失败：%s", e)
        return MySpaceStats.from_nav_and_relation(nav, relation)

    def _fetch_background(self, mid: int) -> str:
        """获取空间背景图 URL；需要 wbi 签名，失败返回空串（用本地默认背景）。"""
        if not mid:
            return ""
        try:
            params = get_wbi({"mid": mid})
            data = self.session.get(UserUrls.ACC_INFO_WBI, params=params)
            # top_photo 在 wbi 接口里；card 接口无此字段
            return data.get("top_photo", "") or ""
        except Exception as e:
            logger.warning("[MySpaceService] 背景图获取失败（已降级）：%s", e)
            return ""

    def logout(self) -> None:
        """退出登录：删除 cookie 文件并清除缓存（供个人页退出登录按钮使用）。"""
        from src.config.cookie import BiliCookies
        from src.config.path import get_cookie_path

        path = get_cookie_path()
        try:
            p = path if isinstance(path, str) else str(path)
            from pathlib import Path

            Path(p).unlink(missing_ok=True)
        except OSError as e:
            logger.warning("[MySpaceService] 删除 cookie 文件失败：%s", e)
        BiliCookies.clear_cache()
