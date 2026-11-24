"""
用户（UP主/空间）相关的接口 URL。
原 `src/up.py`、`src/video.py` 中的用户信息接口迁移至此。
"""

from src.config.constants import API_BASE, API_VC_BASE, SPACE_BASE


class UserUrls:
    """用户空间信息、粉丝、关注等接口。"""

    # 固定端点（无路径参数）
    ACC_INFO = f"{API_BASE}/x/space/acc/info"  # 用户公开信息（昵称/头像等）
    ACC_INFO_WBI = f"{API_BASE}/x/space/wbi/acc/info"  # 用户信息（需 wbi 签名 + 风控参数）
    CARD = f"{API_BASE}/x/web-interface/card"  # 用户卡片信息（粉丝数等）
    CARDS = f"{API_VC_BASE}/account/v1/user/cards"  # 批量用户名片（IM，uids 逗号分隔）
    SPACE_ARC_SEARCH = f"{API_BASE}/x/space/wbi/arc/search"  # 用户空间视频列表（需 wbi 签名）
    MY_INFO = f"{API_BASE}/x/space/myinfo"  # 当前登录用户的完整资料（需登录，无需 wbi）
    NAV = f"{API_BASE}/x/web-interface/nav"  # 登录状态/硬币/钱包余额
    RELATION_STAT = f"{API_BASE}/x/relation/stat"  # 关注/粉丝/黑名单数（参数 vmid）
    FOLLOWINGS = f"{API_BASE}/x/relation/followings"  # 关注明细（vmid/pn/ps/order_type）
    FOLLOWERS = f"{API_BASE}/x/relation/followers"  # 粉丝明细（vmid/pn/ps）
    RELATION_TAGS = f"{API_BASE}/x/relation/tags"  # 关注分组列表（仅当前账号）
    RELATION_TAG = f"{API_BASE}/x/relation/tag"  # 关注分组明细（tagid/pn/ps）
    RELATION_MODIFY = f"{API_BASE}/x/relation/modify"  # 关注/取消关注（POST，需 csrf）
    UPSTAT = f"{API_BASE}/x/space/upstat"  # 用户空间统计（播放/点赞/阅读）

    @staticmethod
    def space_home(mid: int) -> str:
        """用户空间主页。"""
        return f"{SPACE_BASE}/{mid}/"

    @staticmethod
    def favlist(mid: int) -> str:
        """用户收藏夹页面。"""
        return f"{SPACE_BASE}/{mid}/favlist"
