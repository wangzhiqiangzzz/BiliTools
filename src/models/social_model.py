"""社交/个人内容数据模型。

对应 downkyicore 的 FriendInfo / FavoritesMedia / BangumiFollowMedia /
ToViewMedia / HistoryMedia / Publication 等 DTO：
- `RelationUser`  关注/粉丝列表项
- `FollowGroup`   关注分组
- `FavFolder`     收藏夹（我创建的）
- `MediaItem`     通用媒体项（收藏夹视频/稍后再看/历史/空间投稿共用）
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RelationUser:
    """关注/粉丝列表中的用户。"""

    mid: int = 0
    name: str = ""
    face: str = ""
    sign: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "RelationUser":
        return cls(
            mid=int(data.get("mid") or 0),
            name=data.get("uname", "") or "",
            face=data.get("face", "") or "",
            sign=data.get("sign", "") or "",
        )


@dataclass
class FollowGroup:
    """关注分组。"""

    tag_id: int = 0
    name: str = ""
    count: int = 0

    @classmethod
    def from_dict(cls, data: dict) -> "FollowGroup":
        return cls(
            tag_id=int(data.get("tagid") or 0),
            name=data.get("name", "") or "",
            count=int(data.get("count") or 0),
        )


@dataclass
class FavFolder:
    """收藏夹（我创建的）。"""

    media_id: int = 0
    title: str = ""
    media_count: int = 0
    face: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "FavFolder":
        return cls(
            media_id=int(data.get("media_id") or 0),
            title=data.get("title", "") or "",
            media_count=int(data.get("media_count") or 0),
            face=data.get("upper", {}).get("face", "") or data.get("face", "") or "",
        )


@dataclass
class MediaItem:
    """通用媒体项：收藏夹视频 / 稍后再看 / 历史记录 / 追番 / 空间投稿。"""

    bvid: str = ""
    aid: int = 0
    cid: int = 0
    title: str = ""
    cover: str = ""
    author: str = ""
    mid: int = 0
    duration: int = 0  # 秒
    pubdate: int = 0
    progress: int = 0  # 观看进度（秒，历史记录用）
    play: int = 0  # 播放量
    danmaku: int = 0  # 弹幕数
    extra: str = ""  # 附加说明（追番的进度/收藏时间等）
    raw: Optional[dict] = field(default=None, repr=False)

    @classmethod
    def from_video_dict(cls, data: dict) -> "MediaItem":
        """从常见视频结构（收藏/稍后再看/空间投稿）构造。"""
        owner = data.get("owner") or data.get("upper") or {}
        return cls(
            bvid=data.get("bvid", "") or "",
            aid=int(data.get("aid") or 0),
            cid=int(data.get("cid") or 0),
            title=data.get("title", "") or "",
            cover=data.get("pic", "") or data.get("cover", "") or "",
            author=owner.get("name", "") or "",
            mid=int(owner.get("mid") or 0),
            duration=int(data.get("duration") or 0),
            pubdate=int(data.get("pubdate") or data.get("fav_time") or 0),
            progress=int(data.get("progress") or 0),
            play=int(data.get("play") or 0),
            danmaku=int(data.get("video_review") or data.get("danmaku") or 0),
            raw=data,
        )

    @classmethod
    def from_history_dict(cls, data: dict) -> "MediaItem":
        """从历史记录 cursor 接口结构构造。"""
        return cls(
            bvid=data.get("bvid", "") or "",
            aid=int(data.get("aid") or 0),
            cid=int(data.get("cid") or 0),
            title=data.get("title", "") or "",
            cover=data.get("pic", "") or "",
            author=data.get("author_name", "") or "",
            mid=int(data.get("author_mid") or 0),
            duration=int(data.get("duration") or 0),
            progress=int(data.get("progress") or 0),
            raw=data,
        )

    @classmethod
    def from_bangumi_dict(cls, data: dict) -> "MediaItem":
        """从追番列表结构构造。"""
        return cls(
            title=data.get("title", "") or "",
            cover=data.get("cover", "") or data.get("pic", "") or "",
            mid=int(data.get("media_id") or 0),
            extra=(data.get("follow_status_text") or data.get("area") or ""),
            raw=data,
        )
