"""Cache primitives shared across the project.

Every cache read and write in the codebase goes through :class:`CacheManager`
using a namespace declared in :class:`CacheNameSpaces`. That gives us one place
to look when reasoning about caching, one place to clear when data changes, and
a naming convention that is hard to get wrong.
"""

import hashlib
import json
from collections.abc import Callable, Iterable
from typing import Any

from django.core.cache import cache

DEFAULT_TTL_SECONDS = 300
INDEX_KEY_SUFFIX = "keys"
INDEX_TTL_SECONDS = 3600


class CacheNameSpaces:
    """Every cache namespace used in the codebase, declared in one place.

    A namespace groups related keys and gives invalidation a target: when the
    data behind a namespace changes, the writer clears that namespace instead of
    tracking individual keys. Time to live is declared next to the namespace.
    """

    LISTING_SEARCH = "listings:search"
    LISTING_SEARCH_TTL = 60


class CacheManager:
    """The only class that talks to Django's cache framework.

    Keys are namespaced: ``make_key(CacheNameSpaces.LISTING_SEARCH, ...)``
    produces ``"listings:search:<hash>"``. Long or complex parts are hashed, so
    cache keys never grow unbounded and never contain user input verbatim.
    """

    @staticmethod
    def make_key(namespace: str, *parts: Any) -> str:
        """Build a namespaced cache key from one or more parts.

        Args:
            namespace: One of the :class:`CacheNameSpaces` values.
            *parts: Values identifying the entry. A single scalar part is used
                verbatim; multiple or complex parts are hashed.

        Returns:
            The full cache key, e.g. ``"listings:search:9f2c1d8b"``.
        """
        if len(parts) == 1 and isinstance(parts[0], (str, int, float, bool)):
            suffix = str(parts[0])
            if len(suffix) <= 64 and " " not in suffix:
                return f"{namespace}:{suffix}"
        payload = json.dumps(
            [str(part) for part in parts],
            sort_keys=True,
            default=str,
        )
        return f"{namespace}:{hashlib.sha256(payload.encode()).hexdigest()[:32]}"

    @classmethod
    def get(cls, key: str) -> Any:
        """Read a value from the cache.

        Args:
            key: Full cache key.

        Returns:
            The cached value, or ``None`` when absent or unavailable.
        """
        return cache.get(key)

    @classmethod
    def set(cls, key: str, value: Any, *, ttl: int = DEFAULT_TTL_SECONDS) -> None:
        """Write a value to the cache and register its key in the namespace.

        Args:
            key: Full cache key.
            value: Value to store. Must be picklable.
            ttl: Time to live in seconds.
        """
        cache.set(key, value, timeout=ttl)
        cls._register_key(key)

    @classmethod
    def get_or_set(
        cls, key: str, factory: Callable[[], Any], *, ttl: int = DEFAULT_TTL_SECONDS
    ) -> Any:
        """Return the cached value for a key, computing and storing it if missing.

        Args:
            key: Full cache key.
            factory: Callable producing the value when the cache misses.
            ttl: Time to live in seconds.

        Returns:
            The cached or freshly computed value.
        """
        value = cache.get(key)
        if value is None:
            value = factory()
            cls.set(key, value, ttl=ttl)
        return value

    @classmethod
    def delete(cls, key: str) -> None:
        """Delete a single cache key.

        Args:
            key: Full cache key.
        """
        cache.delete(key)

    @classmethod
    def clear_namespace(cls, namespace: str) -> int:
        """Delete every entry belonging to a namespace.

        Each write registers its key under an index key, so clearing works on any
        cache backend (Redis in production, locmem in tests) without relying on
        backend specific pattern deletes.

        Args:
            namespace: One of the :class:`CacheNameSpaces` values.

        Returns:
            Number of cache entries removed.
        """
        index_key = f"{namespace}:{INDEX_KEY_SUFFIX}"
        registered: Iterable[str] = cache.get(index_key) or []
        removed = 0
        for key in list(registered):
            if cache.delete(key):
                removed += 1
        cache.delete(index_key)
        return removed

    @staticmethod
    def _register_key(key: str) -> None:
        """Record a key under its namespace index so it can be cleared later.

        Args:
            key: Full cache key whose namespace index should be updated.
        """
        namespace = key.rsplit(":", 1)[0] if key.count(":") else key
        index_key = f"{namespace}:{INDEX_KEY_SUFFIX}"
        registered = list(cache.get(index_key) or [])
        if key not in registered:
            registered.append(key)
        cache.set(index_key, registered, timeout=INDEX_TTL_SECONDS)
