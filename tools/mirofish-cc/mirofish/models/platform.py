from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_post_list(items: list[Post]) -> list[Post]:
    return sorted(items, key=lambda post: post.timestamp, reverse=True)


@dataclass
class Post:
    """A social media post."""

    post_id: str
    author_id: str
    author_name: str
    content: str
    timestamp: str
    round_created: int
    platform: str
    likes: list[str] = field(default_factory=list)
    dislikes: list[str] = field(default_factory=list)
    reposts: list[str] = field(default_factory=list)
    quotes: list[dict[str, str]] = field(default_factory=list)
    reply_ids: list[str] = field(default_factory=list)
    parent_post_id: Optional[str] = None

    @property
    def engagement_score(self) -> float:
        """Calculate engagement: likes + reposts*2 + quotes*2 + replies*1.5."""
        return (
            len(self.likes)
            + len(self.reposts) * 2
            + len(self.quotes) * 2
            + len(self.reply_ids) * 1.5
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "post_id": self.post_id,
            "author_id": self.author_id,
            "author_name": self.author_name,
            "content": self.content,
            "timestamp": self.timestamp,
            "round_created": self.round_created,
            "platform": self.platform,
            "likes": list(self.likes),
            "dislikes": list(self.dislikes),
            "reposts": list(self.reposts),
            "quotes": [dict(item) for item in self.quotes],
            "reply_ids": list(self.reply_ids),
            "parent_post_id": self.parent_post_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Post:
        return cls(
            post_id=str(data.get("post_id", "")),
            author_id=str(data.get("author_id", "")),
            author_name=str(data.get("author_name", "")),
            content=str(data.get("content", "")),
            timestamp=str(data.get("timestamp", _utc_now_iso())),
            round_created=int(data.get("round_created", 0)),
            platform=str(data.get("platform", "")),
            likes=list(data.get("likes", [])),
            dislikes=list(data.get("dislikes", [])),
            reposts=list(data.get("reposts", [])),
            quotes=[dict(item) for item in data.get("quotes", [])],
            reply_ids=list(data.get("reply_ids", [])),
            parent_post_id=data.get("parent_post_id"),
        )

    def to_feed_summary(self) -> str:
        """Short summary for agent feeds: '@author: content (N likes, M replies)'."""
        preview = " ".join(self.content.split())
        if len(preview) > 140:
            preview = f"{preview[:137]}..."
        return f"@{self.author_name}: {preview} ({len(self.likes)} likes, {len(self.reply_ids)} replies)"


@dataclass
class Comment:
    """A comment/reply on a post."""

    comment_id: str
    post_id: str
    author_id: str
    author_name: str
    content: str
    timestamp: str
    round_created: int
    platform: str
    likes: list[str] = field(default_factory=list)
    dislikes: list[str] = field(default_factory=list)
    parent_comment_id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "comment_id": self.comment_id,
            "post_id": self.post_id,
            "author_id": self.author_id,
            "author_name": self.author_name,
            "content": self.content,
            "timestamp": self.timestamp,
            "round_created": self.round_created,
            "platform": self.platform,
            "likes": list(self.likes),
            "dislikes": list(self.dislikes),
            "parent_comment_id": self.parent_comment_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Comment:
        return cls(
            comment_id=str(data.get("comment_id", "")),
            post_id=str(data.get("post_id", "")),
            author_id=str(data.get("author_id", "")),
            author_name=str(data.get("author_name", "")),
            content=str(data.get("content", "")),
            timestamp=str(data.get("timestamp", _utc_now_iso())),
            round_created=int(data.get("round_created", 0)),
            platform=str(data.get("platform", "")),
            likes=list(data.get("likes", [])),
            dislikes=list(data.get("dislikes", [])),
            parent_comment_id=data.get("parent_comment_id"),
        )


@dataclass
class UserState:
    """An agent's state on a platform."""

    agent_id: str
    agent_name: str
    following: list[str] = field(default_factory=list)
    followers: list[str] = field(default_factory=list)
    muted: list[str] = field(default_factory=list)
    post_ids: list[str] = field(default_factory=list)
    liked_post_ids: list[str] = field(default_factory=list)
    action_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "following": list(self.following),
            "followers": list(self.followers),
            "muted": list(self.muted),
            "post_ids": list(self.post_ids),
            "liked_post_ids": list(self.liked_post_ids),
            "action_count": self.action_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> UserState:
        return cls(
            agent_id=str(data.get("agent_id", "")),
            agent_name=str(data.get("agent_name", "")),
            following=list(data.get("following", [])),
            followers=list(data.get("followers", [])),
            muted=list(data.get("muted", [])),
            post_ids=list(data.get("post_ids", [])),
            liked_post_ids=list(data.get("liked_post_ids", [])),
            action_count=int(data.get("action_count", 0)),
        )


class SocialPlatform:
    """Base social media platform simulator."""

    AVAILABLE_ACTIONS: list[str] = []

    def __init__(self, platform_type: str):
        self.platform_type = platform_type
        self.posts: dict[str, Post] = {}
        self.comments: dict[str, Comment] = {}
        self.users: dict[str, UserState] = {}
        self.current_round: int = 0
        self._seen_post_ids: dict[str, set[str]] = {}

    def _ensure_user(self, agent_id: str) -> UserState:
        if agent_id not in self.users:
            raise ValueError(f"Unknown user '{agent_id}'")
        return self.users[agent_id]

    def register_user(self, agent_id: str, agent_name: str) -> UserState:
        """Register an agent on this platform."""
        existing = self.users.get(agent_id)
        if existing:
            if agent_name:
                existing.agent_name = agent_name
            return existing
        user = UserState(agent_id=agent_id, agent_name=agent_name)
        self.users[agent_id] = user
        self._seen_post_ids[agent_id] = set()
        return user

    def create_post(self, agent_id: str, content: str) -> Post:
        """Create a new post. Returns the created Post."""
        user = self._ensure_user(agent_id)
        post = Post(
            post_id=str(uuid.uuid4()),
            author_id=agent_id,
            author_name=user.agent_name,
            content=content.strip(),
            timestamp=_utc_now_iso(),
            round_created=self.current_round,
            platform=self.platform_type,
        )
        self.posts[post.post_id] = post
        user.post_ids.append(post.post_id)
        user.action_count += 1
        return post

    def like_post(self, agent_id: str, post_id: str) -> bool:
        """Like a post. Returns False if already liked or post not found."""
        user = self._ensure_user(agent_id)
        post = self.posts.get(post_id)
        if post is None or agent_id in post.likes:
            return False
        post.likes.append(agent_id)
        if post_id not in user.liked_post_ids:
            user.liked_post_ids.append(post_id)
        if self.platform_type == "reddit" and agent_id in post.dislikes:
            post.dislikes.remove(agent_id)
        user.action_count += 1
        return True

    def follow_user(self, agent_id: str, target_id: str) -> bool:
        """Follow another user. Returns False if already following or self-follow."""
        user = self._ensure_user(agent_id)
        target = self.users.get(target_id)
        if target is None or target_id == agent_id or target_id in user.following:
            return False
        user.following.append(target_id)
        if agent_id not in target.followers:
            target.followers.append(agent_id)
        user.action_count += 1
        return True

    def do_nothing(self, agent_id: str) -> None:
        """Agent chose to do nothing this round."""
        self._ensure_user(agent_id).action_count += 1

    def _eligible_feed_posts(self, agent_id: str) -> list[Post]:
        user = self._ensure_user(agent_id)
        seen = self._seen_post_ids.setdefault(agent_id, set())
        posts: list[Post] = []
        for post in self.posts.values():
            if post.author_id == agent_id:
                continue
            if post.post_id in user.liked_post_ids or post.post_id in seen:
                continue
            if self.platform_type == "reddit" and post.author_id in user.muted:
                continue
            posts.append(post)
        return posts

    def get_feed(self, agent_id: str, limit: int = 10) -> list[Post]:
        """Build personalized feed for an agent.

        Mix: 60% posts from followed users, 40% trending posts.
        Sort by recency within each category.
        Exclude own posts.
        Exclude posts already liked by this agent.
        """
        if limit <= 0:
            return []
        user = self._ensure_user(agent_id)
        eligible = _as_post_list(self._eligible_feed_posts(agent_id))
        followed = [post for post in eligible if post.author_id in user.following]

        trending_candidates = [
            post for post in self.get_trending(limit=max(limit * 3, limit)) if post in eligible
        ]
        trending = _as_post_list(trending_candidates)

        followed_quota = min(len(followed), int(limit * 0.6))
        trending_quota = min(len(trending), limit - followed_quota)

        feed = followed[:followed_quota] + trending[:trending_quota]
        if len(feed) < limit:
            used = {post.post_id for post in feed}
            feed.extend([post for post in eligible if post.post_id not in used][: limit - len(feed)])

        self._seen_post_ids.setdefault(agent_id, set()).update(post.post_id for post in feed)
        return feed[:limit]

    def get_trending(self, limit: int = 10) -> list[Post]:
        """Top posts by engagement score."""
        if limit <= 0:
            return []
        ranked = sorted(
            self.posts.values(),
            key=lambda post: (post.engagement_score, post.timestamp),
            reverse=True,
        )
        return ranked[:limit]

    def get_agent_posts(self, agent_id: str) -> list[Post]:
        """Get all posts by an agent."""
        self._ensure_user(agent_id)
        return _as_post_list([post for post in self.posts.values() if post.author_id == agent_id])

    def get_post_with_comments(self, post_id: str) -> dict[str, Any]:
        """Get a post with all its comments."""
        post = self.posts.get(post_id)
        if post is None:
            return {"post": None, "comments": []}
        comments = sorted(
            [comment for comment in self.comments.values() if comment.post_id == post_id],
            key=lambda comment: comment.timestamp,
        )
        return {"post": post.to_dict(), "comments": [comment.to_dict() for comment in comments]}

    def advance_round(self) -> None:
        """Advance to next simulation round."""
        self.current_round += 1

    def get_stats(self) -> dict[str, Any]:
        """Platform statistics: total posts, comments, active users, etc."""
        users = list(self.users.values())
        return {
            "platform": self.platform_type,
            "current_round": self.current_round,
            "total_users": len(users),
            "active_users": len([user for user in users if user.action_count > 0]),
            "total_posts": len(self.posts),
            "total_comments": len(self.comments),
            "total_likes": sum(len(post.likes) for post in self.posts.values()),
            "total_dislikes": sum(len(post.dislikes) for post in self.posts.values()),
            "avg_actions_per_user": (
                sum(user.action_count for user in users) / len(users) if users else 0.0
            ),
        }

    def execute_action(self, agent_id: str, action_type: str, args: dict[str, Any]) -> dict[str, Any]:
        """Execute any action by type. Dispatches to specific method.

        Returns: {success: bool, result: str|None, error: str|None}
        """
        try:
            if action_type == "CREATE_POST":
                post = self.create_post(agent_id, str(args.get("content", "")))
                return {"success": True, "result": post.post_id, "error": None}
            if action_type == "LIKE_POST":
                ok = self.like_post(agent_id, str(args.get("post_id", "")))
                return {"success": ok, "result": "LIKED" if ok else None, "error": None if ok else "Unable to like post"}
            if action_type == "FOLLOW":
                ok = self.follow_user(agent_id, str(args.get("target_id", "")))
                return {"success": ok, "result": "FOLLOWED" if ok else None, "error": None if ok else "Unable to follow user"}
            if action_type == "DO_NOTHING":
                self.do_nothing(agent_id)
                return {"success": True, "result": "NO_OP", "error": None}

            if isinstance(self, TwitterPlatform):
                if action_type == "REPOST":
                    ok = self.repost(agent_id, str(args.get("post_id", "")))
                    return {"success": ok, "result": "REPOSTED" if ok else None, "error": None if ok else "Unable to repost"}
                if action_type == "QUOTE_POST":
                    post = self.quote_post(agent_id, str(args.get("post_id", "")), str(args.get("content", "")))
                    return {"success": True, "result": post.post_id, "error": None}

            if isinstance(self, RedditPlatform):
                if action_type == "DISLIKE_POST":
                    ok = self.dislike_post(agent_id, str(args.get("post_id", "")))
                    return {"success": ok, "result": "DOWNVOTED" if ok else None, "error": None if ok else "Unable to downvote post"}
                if action_type == "CREATE_COMMENT":
                    comment = self.create_comment(
                        agent_id=agent_id,
                        post_id=str(args.get("post_id", "")),
                        content=str(args.get("content", "")),
                        parent_comment_id=args.get("parent_comment_id"),
                    )
                    return {"success": True, "result": comment.comment_id, "error": None}
                if action_type == "LIKE_COMMENT":
                    ok = self.like_comment(agent_id, str(args.get("comment_id", "")))
                    return {"success": ok, "result": "COMMENT_LIKED" if ok else None, "error": None if ok else "Unable to like comment"}
                if action_type == "DISLIKE_COMMENT":
                    ok = self.dislike_comment(agent_id, str(args.get("comment_id", "")))
                    return {"success": ok, "result": "COMMENT_DISLIKED" if ok else None, "error": None if ok else "Unable to dislike comment"}
                if action_type == "SEARCH_POSTS":
                    posts = self.search_posts(str(args.get("query", "")), int(args.get("limit", 5)))
                    return {"success": True, "result": f"{len(posts)} posts found", "error": None}
                if action_type == "SEARCH_USER":
                    users = self.search_user(str(args.get("query", "")))
                    return {"success": True, "result": f"{len(users)} users found", "error": None}
                if action_type == "TREND":
                    posts = self.get_trending(int(args.get("limit", 10)))
                    return {"success": True, "result": f"{len(posts)} trending posts", "error": None}
                if action_type == "REFRESH":
                    posts = self.refresh(agent_id)
                    return {"success": True, "result": f"{len(posts)} refreshed posts", "error": None}
                if action_type == "MUTE":
                    ok = self.mute_user(agent_id, str(args.get("target_id", "")))
                    return {"success": ok, "result": "MUTED" if ok else None, "error": None if ok else "Unable to mute user"}

            return {"success": False, "result": None, "error": f"Unsupported action: {action_type}"}
        except Exception as exc:  # pragma: no cover
            return {"success": False, "result": None, "error": str(exc)}

    def to_dict(self) -> dict[str, Any]:
        return {
            "platform_type": self.platform_type,
            "current_round": self.current_round,
            "posts": {post_id: post.to_dict() for post_id, post in self.posts.items()},
            "comments": {comment_id: comment.to_dict() for comment_id, comment in self.comments.items()},
            "users": {agent_id: user.to_dict() for agent_id, user in self.users.items()},
            "seen_post_ids": {
                agent_id: sorted(post_ids) for agent_id, post_ids in self._seen_post_ids.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SocialPlatform:
        platform_type = str(data.get("platform_type", ""))
        if cls is SocialPlatform:
            if platform_type == "twitter":
                platform: SocialPlatform = TwitterPlatform()
            elif platform_type == "reddit":
                platform = RedditPlatform()
            else:
                platform = SocialPlatform(platform_type)
        else:
            platform = cls()  # type: ignore[call-arg]

        platform.current_round = int(data.get("current_round", 0))
        platform.posts = {
            post_id: Post.from_dict(raw) for post_id, raw in dict(data.get("posts", {})).items()
        }
        platform.comments = {
            comment_id: Comment.from_dict(raw)
            for comment_id, raw in dict(data.get("comments", {})).items()
        }
        platform.users = {
            agent_id: UserState.from_dict(raw)
            for agent_id, raw in dict(data.get("users", {})).items()
        }
        platform._seen_post_ids = {
            agent_id: set(post_ids)
            for agent_id, post_ids in dict(data.get("seen_post_ids", {})).items()
            if isinstance(post_ids, list)
        }
        for agent_id in platform.users:
            platform._seen_post_ids.setdefault(agent_id, set())
        return platform


class TwitterPlatform(SocialPlatform):
    """Twitter-like platform with 6 actions."""

    AVAILABLE_ACTIONS = ["CREATE_POST", "LIKE_POST", "REPOST", "FOLLOW", "DO_NOTHING", "QUOTE_POST"]

    def __init__(self):
        super().__init__("twitter")

    def repost(self, agent_id: str, post_id: str) -> bool:
        """Repost/retweet a post. Increments repost count, records reposter."""
        user = self._ensure_user(agent_id)
        post = self.posts.get(post_id)
        if post is None or agent_id in post.reposts:
            return False
        post.reposts.append(agent_id)
        user.action_count += 1
        return True

    def quote_post(self, agent_id: str, post_id: str, content: str) -> Post:
        """Quote a post with additional commentary. Creates a new post linked to original."""
        self._ensure_user(agent_id)
        original = self.posts.get(post_id)
        if original is None:
            raise ValueError(f"Unknown post '{post_id}'")
        quote = self.create_post(agent_id=agent_id, content=content)
        quote.parent_post_id = post_id
        original.quotes.append({"agent_id": agent_id, "content": content.strip()})
        return quote


class RedditPlatform(SocialPlatform):
    """Reddit-like platform with 13 actions."""

    AVAILABLE_ACTIONS = [
        "LIKE_POST",
        "DISLIKE_POST",
        "CREATE_POST",
        "CREATE_COMMENT",
        "LIKE_COMMENT",
        "DISLIKE_COMMENT",
        "SEARCH_POSTS",
        "SEARCH_USER",
        "TREND",
        "REFRESH",
        "DO_NOTHING",
        "FOLLOW",
        "MUTE",
    ]

    def __init__(self):
        super().__init__("reddit")

    def dislike_post(self, agent_id: str, post_id: str) -> bool:
        """Downvote a post."""
        user = self._ensure_user(agent_id)
        post = self.posts.get(post_id)
        if post is None or agent_id in post.dislikes:
            return False
        post.dislikes.append(agent_id)
        if agent_id in post.likes:
            post.likes.remove(agent_id)
            if post_id in user.liked_post_ids:
                user.liked_post_ids.remove(post_id)
        user.action_count += 1
        return True

    def create_comment(
        self,
        agent_id: str,
        post_id: str,
        content: str,
        parent_comment_id: Optional[str] = None,
    ) -> Comment:
        """Create a comment on a post (supports nested replies)."""
        user = self._ensure_user(agent_id)
        if post_id not in self.posts:
            raise ValueError(f"Unknown post '{post_id}'")
        if parent_comment_id is not None and parent_comment_id not in self.comments:
            raise ValueError(f"Unknown parent comment '{parent_comment_id}'")

        comment = Comment(
            comment_id=str(uuid.uuid4()),
            post_id=post_id,
            author_id=agent_id,
            author_name=user.agent_name,
            content=content.strip(),
            timestamp=_utc_now_iso(),
            round_created=self.current_round,
            platform=self.platform_type,
            parent_comment_id=parent_comment_id,
        )
        self.comments[comment.comment_id] = comment
        self.posts[post_id].reply_ids.append(comment.comment_id)
        user.action_count += 1
        return comment

    def like_comment(self, agent_id: str, comment_id: str) -> bool:
        """Upvote a comment."""
        user = self._ensure_user(agent_id)
        comment = self.comments.get(comment_id)
        if comment is None or agent_id in comment.likes:
            return False
        comment.likes.append(agent_id)
        if agent_id in comment.dislikes:
            comment.dislikes.remove(agent_id)
        user.action_count += 1
        return True

    def dislike_comment(self, agent_id: str, comment_id: str) -> bool:
        """Downvote a comment."""
        user = self._ensure_user(agent_id)
        comment = self.comments.get(comment_id)
        if comment is None or agent_id in comment.dislikes:
            return False
        comment.dislikes.append(agent_id)
        if agent_id in comment.likes:
            comment.likes.remove(agent_id)
        user.action_count += 1
        return True

    def search_posts(self, query: str, limit: int = 5) -> list[Post]:
        """Search posts by keyword matching in content."""
        term = query.strip().lower()
        if not term or limit <= 0:
            return []
        return _as_post_list([post for post in self.posts.values() if term in post.content.lower()])[:limit]

    def search_user(self, query: str) -> list[UserState]:
        """Search users by name."""
        term = query.strip().lower()
        if not term:
            return []
        return [user for user in self.users.values() if term in user.agent_name.lower()]

    def get_trending(self, limit: int = 10) -> list[Post]:
        """Reddit trending: sort by (upvotes - downvotes) * recency_weight."""
        if limit <= 0:
            return []

        def score(post: Post) -> float:
            net_votes = len(post.likes) - len(post.dislikes)
            age_rounds = max(0, self.current_round - post.round_created)
            recency_weight = 1.0 / (1.0 + age_rounds)
            return net_votes * recency_weight

        ranked = sorted(self.posts.values(), key=lambda post: (score(post), post.timestamp), reverse=True)
        return ranked[:limit]

    def mute_user(self, agent_id: str, target_id: str) -> bool:
        """Mute a user (hide their posts from feed)."""
        user = self._ensure_user(agent_id)
        if target_id not in self.users or target_id == agent_id or target_id in user.muted:
            return False
        user.muted.append(target_id)
        user.action_count += 1
        return True

    def refresh(self, agent_id: str) -> list[Post]:
        """Refresh feed - same as get_feed but resets seen posts."""
        self._ensure_user(agent_id)
        self._seen_post_ids[agent_id] = set()
        return self.get_feed(agent_id=agent_id)
