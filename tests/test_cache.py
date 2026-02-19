"""Tests for cache module."""

import sys
import os
import time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from wombat_miles import cache


def test_set_get():
    """Test basic set and get."""
    cache.set("test_key_1", {"miles": 50000}, ttl=60)
    result = cache.get("test_key_1")
    assert result == {"miles": 50000}


def test_get_missing():
    """Test get with missing key."""
    result = cache.get("nonexistent_key_xyz")
    assert result is None


def test_expired():
    """Test that expired entries return None."""
    cache.set("test_expired", "old_data", ttl=0)
    time.sleep(0.1)
    result = cache.get("test_expired")
    assert result is None


def test_make_key():
    """Test cache key generation."""
    key = cache.make_key("alaska", "sfo", "lax", "2025-03-20")
    assert key == "alaska_SFO_LAX_2025-03-20"


def test_clear_all():
    """Test clearing all cache."""
    cache.set("test_clear_1", "data1", ttl=3600)
    cache.set("test_clear_2", "data2", ttl=3600)
    cache.clear_all()
    assert cache.get("test_clear_1") is None
    assert cache.get("test_clear_2") is None


def test_clear_expired():
    """Test clearing only expired entries."""
    cache.set("test_fresh", "fresh_data", ttl=3600)
    cache.set("test_stale", "stale_data", ttl=0)
    time.sleep(0.1)
    count = cache.clear_expired()
    assert count >= 1
    assert cache.get("test_fresh") == "fresh_data"
    assert cache.get("test_stale") is None


if __name__ == "__main__":
    test_set_get()
    test_get_missing()
    test_expired()
    test_make_key()
    test_clear_all()
    test_clear_expired()
    print("✅ All cache tests passed!")
