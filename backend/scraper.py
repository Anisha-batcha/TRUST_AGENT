from __future__ import annotations

import os
import re
import time
from random import choice
from dataclasses import dataclass
from typing import Any


class ScrapeError(RuntimeError):
    pass


@dataclass
class ScrapeResult:
    metrics: dict[str, float]
    source_url: str
    mode: str
    raw_text: str


def _to_url(target: str, category: str) -> str:
    t = target.strip()
    if t.startswith("http://") or t.startswith("https://"):
        return t

    handle = t.lstrip("@").strip("/")
    domain_map = {
        "instagram": "https://www.instagram.com/{}",
        "x": "https://x.com/{}",
        "linkedin": "https://www.linkedin.com/in/{}",
        "youtube": "https://www.youtube.com/@{}",
        "facebook": "https://www.facebook.com/{}",
        "telegram": "https://t.me/{}",
    }
    template = domain_map.get(category.lower())
    if template:
        return template.format(handle)

    if "." in handle:
        return f"https://{handle}"
    return f"https://www.google.com/search?q={handle}"


def _hash_proxy_seed(text: str) -> float:
    total = 0
    for idx, ch in enumerate(text):
        total += (idx + 1) * ord(ch)
    return (total % 1000) / 1000.0


def _extract_numeric_near(text: str, keyword: str) -> float | None:
    # Capture values like 2,345 / 12.4K / 1.1M around the keyword.
    # Common layouts:
    #   "12.4K followers"
    #   "followers: 12.4K"
    patterns = [
        rf"([0-9][0-9,]*(?:\.[0-9]+)?\s*[kKmM]?)\s+{re.escape(keyword)}",
        rf"{re.escape(keyword)}\s*[:\-]?\s*([0-9][0-9,]*(?:\.[0-9]+)?\s*[kKmM]?)",
    ]
    m = None
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            break
    if not m:
        return None

    raw = m.group(1).replace(",", "").strip().lower()
    mult = 1.0
    if raw.endswith("k"):
        mult = 1000.0
        raw = raw[:-1]
    elif raw.endswith("m"):
        mult = 1_000_000.0
        raw = raw[:-1]
    try:
        return float(raw) * mult
    except ValueError:
        return None


def _build_metrics_from_page(page_text: str, target: str, category: str) -> dict[str, float]:
    text = re.sub(r"\s+", " ", page_text).lower()
    category_norm = (category or "").strip().lower()

    def _contains_any(needles: list[str]) -> bool:
        return any(n in text for n in needles)

    def _count_any(needles: list[str]) -> int:
        return sum(text.count(n) for n in needles)

    # Category-aware heuristic extraction: social vs non-social targets.
    non_social = {"website", "startup", "freelancer", "mobile_app"}
    if category_norm in non_social:
        # Website/startup-like pages: derive trust signals from content density + policy/contact presence.
        seed = _hash_proxy_seed(f"{target}|{category}|{len(text)}")
        text_density = min(1.0, len(text) / 9000)

        has_contact = _contains_any(["contact", "support@", "help@", "customer support", "phone", "email", "address"])
        has_about = _contains_any(["about", "our story", "company", "team", "mission"])
        has_policy = _contains_any(["privacy", "terms", "refund", "returns", "shipping", "cookie"])
        has_https = target.strip().lower().startswith("https://") or "https" in text[:500]

        pos_hits = _count_any(["trusted", "secure", "verified", "official", "authentic"])
        neg_hits = _count_any(["scam", "fraud", "complaint", "chargeback", "fake", "phishing"])
        sentiment = 0.52 + (text_density * 0.18) + ((pos_hits - neg_hits) * 0.02)

        profile_completeness = 0.45 + (0.15 if has_contact else 0) + (0.12 if has_about else 0) + (0.12 if has_policy else 0)
        if has_https:
            profile_completeness += 0.04
        profile_completeness = min(0.98, max(0.35, profile_completeness))

        # Review spike: treat "reviews/testimonials" mention with low content as suspicious.
        reviews = _extract_numeric_near(text, "reviews")
        rating = _extract_numeric_near(text, "rating")
        review_mention = _contains_any(["reviews", "testimonials", "ratings"])
        reviews = reviews if reviews is not None else (10 + seed * 420)
        rating = rating if rating is not None else (3.2 + seed * 1.5)
        rating = min(5.0, max(1.0, float(rating)))

        review_spike_ratio = 0.12 + (0.2 if review_mention and text_density < 0.25 and reviews > 120 else 0.0)
        review_spike_ratio += (0.08 if "limited time" in text or "hurry" in text else 0.0)
        review_spike_ratio = min(0.95, max(0.05, review_spike_ratio))

        # Engagement is not social-like here; use a stable proxy.
        engagement_rate = 0.01 + (0.09 * text_density) - (0.03 * review_spike_ratio)
        engagement_rate = min(0.18, max(0.004, engagement_rate))

        # Age proxy: more content tends to correlate with maturity (demo-safe).
        account_age_days = int(60 + (text_density * 3200) + (seed * 900))

        follower_growth_consistency = 0.42 + (0.45 * text_density) - (0.12 * review_spike_ratio)
        follower_growth_consistency = min(0.99, max(0.12, follower_growth_consistency))

        sentiment_score = min(0.92, max(0.18, sentiment))

        return {
            "engagement_rate": round(float(engagement_rate), 4),
            "review_spike_ratio": round(float(review_spike_ratio), 3),
            "profile_completeness": round(float(profile_completeness), 3),
            "account_age_days": int(account_age_days),
            "sentiment_score": round(float(sentiment_score), 3),
            "follower_growth_consistency": round(float(follower_growth_consistency), 3),
        }

    followers = _extract_numeric_near(text, "followers")
    following = _extract_numeric_near(text, "following")
    likes = _extract_numeric_near(text, "likes")
    comments = _extract_numeric_near(text, "comments")
    reviews = _extract_numeric_near(text, "reviews")

    seed = _hash_proxy_seed(f"{target}|{category}|{len(text)}")
    followers = followers if followers is not None else (400 + seed * 15000)
    following = following if following is not None else (50 + seed * 1000)
    likes = likes if likes is not None else (20 + seed * 1200)
    comments = comments if comments is not None else (3 + seed * 220)
    reviews = reviews if reviews is not None else (15 + seed * 600)

    engagement_rate = min(0.18, max(0.004, (likes + comments) / max(followers, 1.0)))

    # If following is very high compared to followers, profile quality drops.
    follow_ratio = following / max(followers, 1.0)
    profile_completeness = min(0.98, max(0.35, 0.9 - (follow_ratio * 0.3)))

    # Rough signal: short pages with sudden large review counts can be noisy.
    text_density = min(1.0, len(text) / 9000)
    review_spike_ratio = min(0.95, max(0.05, (reviews / max((followers * 0.03), 1.0)) * 0.15 + (1 - text_density) * 0.25))

    account_age_days = int(30 + (text_density * 2800) + (seed * 800))
    sentiment_score = min(0.92, max(0.18, 0.35 + text_density * 0.45 + (0.12 if "verified" in text else 0)))
    follower_growth_consistency = min(0.99, max(0.12, 0.4 + text_density * 0.35 - review_spike_ratio * 0.2))

    return {
        "engagement_rate": round(engagement_rate, 4),
        "review_spike_ratio": round(review_spike_ratio, 3),
        "profile_completeness": round(profile_completeness, 3),
        "account_age_days": account_age_days,
        "sentiment_score": round(sentiment_score, 3),
        "follower_growth_consistency": round(follower_growth_consistency, 3),
    }


def collect_signals(target: str, category: str, timeout_sec: int = 12) -> ScrapeResult:
    mode = (os.getenv("TRUSTAGENT_SCRAPE_MODE") or "auto").strip().lower()
    if mode in {"off", "disabled", "disable", "synthetic", "fallback"}:
        raise ScrapeError("Scraping disabled by TRUSTAGENT_SCRAPE_MODE")

    category_norm = (category or "").strip().lower()
    non_social = {"website", "startup", "freelancer", "mobile_app"}

    env_timeout = os.getenv("TRUSTAGENT_SCRAPE_TIMEOUT_SEC")
    if env_timeout:
        try:
            timeout_sec = max(2, int(env_timeout))
        except ValueError:
            pass

    try:
        from selenium import webdriver
        from selenium.common.exceptions import TimeoutException, WebDriverException
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.support.ui import WebDriverWait
        from webdriver_manager.chrome import ChromeDriverManager
    except ImportError as exc:
        raise ScrapeError("Selenium dependencies are not installed") from exc

    url = _to_url(target, category)
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    ]

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1366,768")
    options.add_argument("--lang=en-US")
    options.add_argument(f"--user-agent={choice(user_agents)}")

    driver = None
    try:
        last_error: Exception | None = None
        prefer_selenium = mode == "selenium" or (mode == "auto" and category_norm not in non_social)
        if prefer_selenium:
            attempts = 3
            env_attempts = os.getenv("TRUSTAGENT_SELENIUM_ATTEMPTS")
            if env_attempts:
                try:
                    attempts = max(1, min(5, int(env_attempts)))
                except ValueError:
                    pass

            for attempt in range(1, attempts + 1):
                try:
                    service = Service(ChromeDriverManager().install())
                    driver = webdriver.Chrome(service=service, options=options)
                    driver.set_page_load_timeout(timeout_sec)
                    driver.get(url)

                    try:
                        WebDriverWait(driver, timeout_sec).until(
                            EC.presence_of_element_located((By.TAG_NAME, "body"))
                        )
                    except TimeoutException:
                        pass

                    try:
                        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                        time.sleep(0.8)
                        driver.execute_script("window.scrollTo(0, 0);")
                    except Exception:
                        pass

                    page_text = driver.page_source or ""
                    if len(page_text) < 250:
                        raise ScrapeError(f"Insufficient page data from {url}")

                    metrics = _build_metrics_from_page(page_text, target, category)
                    return ScrapeResult(metrics=metrics, source_url=url, mode="selenium", raw_text=page_text[:8000])
                except (WebDriverException, TimeoutException, ValueError, ScrapeError) as exc:
                    last_error = exc
                    if attempt < attempts:
                        time.sleep(attempt * 0.8)
                finally:
                    if driver is not None:
                        driver.quit()
                        driver = None

        # Fallback path: static HTTP fetch if Selenium is blocked.
        try:
            import requests
            from bs4 import BeautifulSoup

            resp = requests.get(
                url,
                timeout=timeout_sec,
                headers={"User-Agent": choice(user_agents)},
            )
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            page_text = soup.get_text(separator=" ", strip=True)
            if len(page_text) < 200:
                raise ScrapeError(f"Static fallback could not extract enough data from {url}")

            metrics = _build_metrics_from_page(page_text, target, category)
            return ScrapeResult(metrics=metrics, source_url=url, mode="http_fallback", raw_text=page_text[:8000])
        except Exception as fallback_exc:
            if last_error is not None:
                raise ScrapeError(f"Selenium scraping failed: {last_error}; static fallback failed: {fallback_exc}") from fallback_exc
            raise ScrapeError(f"Scraping failed: {fallback_exc}") from fallback_exc
    finally:
        if driver is not None:
            driver.quit()
