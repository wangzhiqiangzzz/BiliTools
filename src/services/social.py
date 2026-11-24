"""社交与个人内容服务：关注/粉丝/分组、收藏夹、稍后再看、追番。

对应 downkyicore 的 FriendRelationCoordinator / FavoritesCoordinator /
PersonalMediaCoordinator / UserSpacePageCoordinator 中供 UI 使用的部分。

所有接口都返回稳定的 dataclass 模型，不把原始 dict 直接丢给 UI。
"""

import logging
from typing import Optional

from src.api.session import BiliSession
from src.config.cookie import BiliCookies
from src.models.social_model import FavFolder, FollowGroup, MediaItem, RelationUser
from src.urls.fav_urls import FavUrls
from src.urls.user_urls import UserUrls

logger = logging.getLogger(__name__)


class SocialService:
    """关注/收藏/追番等个人内容服务。"""

    def __init__(self, session: Optional[BiliSession] = None):
        self.session = session if session is not None else BiliSession()

    # ---- 关注 / 粉丝 ----

    def get_following(self, mid: int, pn: int = 1, ps: int = 20,
                      order: str = "") -> tuple[list[RelationUser], int]:
        """关注明细。返回 (用户列表, 总数)。order='attention' 按最近关注排序。"""
        data = self.session.get(
            UserUrls.FOLLOWINGS,
            params={"vmid": mid, "pn": pn, "ps": ps, "order_type": order},
        )
        items = [RelationUser.from_dict(x) for x in (data.get("list") or [])]
        return items, int(data.get("total") or 0)

    def get_followers(self, mid: int, pn: int = 1, ps: int = 20) -> tuple[list[RelationUser], int]:
        """粉丝明细。返回 (用户列表, 总数)。"""
        data = self.session.get(
            UserUrls.FOLLOWERS,
            params={"vmid": mid, "pn": pn, "ps": ps},
        )
        items = [RelationUser.from_dict(x) for x in (data.get("list") or [])]
        return items, int(data.get("total") or 0)

    def get_follow_groups(self) -> list[FollowGroup]:
        """关注分组列表（仅当前登录账号）。"""
        data = self.session.get(UserUrls.RELATION_TAGS)
        return [FollowGroup.from_dict(x) for x in (data or [])]

    def get_group_members(self, tag_id: int, pn: int = 1, ps: int = 20) -> list[RelationUser]:
        """某个关注分组内的用户。"""
        data = self.session.get(
            UserUrls.RELATION_TAG,
            params={"tagid": tag_id, "pn": pn, "ps": ps, "order_type": ""},
        )
        return [RelationUser.from_dict(x) for x in (data or [])]

    def modify_relation(self, fid: int, action: int) -> bool:
        """关注/取消关注。action=1 关注，action=2 取消关注。"""
        csrf = BiliCookies.from_file().bili_jct or ""
        self.session.post(
            UserUrls.RELATION_MODIFY,
            data={"fid": fid, "act": action, "csrf": csrf},
        )
        return True

    # ---- 收藏夹 ----

    def get_fav_folders(self, mid: int, pn: int = 1, ps: int = 20) -> list[FavFolder]:
        """我创建的收藏夹列表。"""
        data = self.session.get(
            FavUrls.FOLDER_LIST,
            params={"up_mid": mid, "pn": pn, "ps": ps},
        )
        return [FavFolder.from_dict(x) for x in ((data or {}).get("list") or [])]

    def get_fav_medias(self, media_id: int, pn: int = 1, ps: int = 20) -> tuple[list[MediaItem], int]:
        """收藏夹内视频明细。返回 (媒体列表, 总数)。"""
        data = self.session.get(
            FavUrls.RESOURCE_LIST,
            params={"media_id": media_id, "pn": pn, "ps": ps, "platform": "web"},
        )
        items = [MediaItem.from_video_dict(x) for x in ((data or {}).get("medias") or [])]
        return items, int((data or {}).get("total") or 0)

    # ---- 稍后再看 / 追番 ----

    def get_watch_later(self, pn: int = 1, ps: int = 20) -> list[MediaItem]:
        """稍后再看列表。"""
        data = self.session.get(
            FavUrls.WATCH_LATER,
            params={"pn": pn, "ps": ps},
        )
        return [MediaItem.from_video_dict(x) for x in ((data or {}).get("list") or [])]

    def get_bangumi_follow(self, mid: int, pn: int = 1, ps: int = 15,
                           follow_type: int = 1) -> tuple[list[MediaItem], int]:
        """追番/追剧。follow_type=1 番剧，2 影视。返回 (列表, 总数)。"""
        data = self.session.get(
            FavUrls.BANGUMI_FOLLOW,
            params={"vmid": mid, "type": follow_type, "pn": pn, "ps": ps},
        )
        items = [MediaItem.from_bangumi_dict(x) for x in ((data or {}).get("list") or [])]
        return items, int((data or {}).get("total") or 0)

    # ---- 历史记录 ----

    def get_history(self, max_id: int = 0, view_at: int = 0, business: str = "",
                    ps: int = 30) -> tuple[list[MediaItem], dict]:
        """历史记录一页。返回 (媒体列表, 下一页游标 dict)。"""
        data = self.session.get(
            "https://api.bilibili.com/x/web-interface/history/cursor",
            params={"max": max_id, "view_at": view_at, "business": business,
                    "type": "all", "ps": ps},
        )
        items = [MediaItem.from_history_dict(x) for x in ((data or {}).get("list") or [])]
        cursor = data.get("cursor") or {}
        return items, cursor
