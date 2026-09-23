"""
Direct test of robots.txt enforcement. No crawling, no DB.
Exercises the exact functions dom_extract.py uses.
"""
import asyncio
import sys
from dom_extract import get_robots, robots_can_fetch, robots_crawl_delay, USER_AGENT, HAS_PROTEGO

# (scheme, domain, path, expected_allowed)
TEST_CASES = [
    ('https', 'en.wikipedia.org', '/wiki/Global_Positioning_System', True),
    ('https', 'en.wikipedia.org', '/wiki/Special:Search',          False),
    ('https', 'en.wikipedia.org', '/w/index.php',                  False),
    ('https', 'www.reddit.com',   '/r/explainlikeimfive/comments/1som2a6/', False),
    ('https', 'www.reddit.com',   '/robots.txt',                   True),
    ('https', 'github.com',       '/torvalds/linux',               True),
    ('https', 'www.linkedin.com', '/in/somebody',                  False),
]


async def main():
    print(f"protego available: {HAS_PROTEGO}")
    print()
    print(f"{'domain':25s} {'path':40s} {'allowed':8s} {'expected':8s} {'ok':3s}")
    print("-" * 90)

    # group by domain so robots.txt is fetched once per domain
    by_domain = {}
    for scheme, domain, path, expected in TEST_CASES:
        by_domain.setdefault((scheme, domain), []).append((path, expected))

    failures = 0
    for (scheme, domain), cases in by_domain.items():
        parser = await get_robots(scheme, domain, 10000)
        delay = robots_crawl_delay(parser, USER_AGENT)
        print(f"# {domain}  crawl-delay={delay}")
        for path, expected in cases:
            url = f"{scheme}://{domain}{path}"
            allowed = robots_can_fetch(parser, url, USER_AGENT)
            ok = "✓" if allowed == expected else "✗"
            if allowed != expected:
                failures += 1
            print(f"  {domain:23s} {path:40s} {str(allowed):8s} {str(expected):8s} {ok}")

    print()
    if failures:
        print(f"{failures} mismatch(es)")
        sys.exit(1)
    else:
        print("all tests passed")


if __name__ == '__main__':
    asyncio.run(main())