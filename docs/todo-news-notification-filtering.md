# TODO: News Notification Filtering

## Problem

Current news ingestion and email notification are already wired through:

- portfolio holdings
- news crawling
- deduplication
- category classification
- push decision
- email delivery

However, pushing every eligible news item will create too much noise.

## Goal

Introduce a second-stage filtering policy before notification delivery so that
only sufficiently important news reaches the user proactively.

## Required future work

1. Add configurable push severity rules
   - per category thresholds
   - per source priorities
   - optional stock-specific whitelists / blacklists

2. Add stronger content filtering
   - announcement keyword priorities
   - research/news confidence heuristics
   - sentiment keyword ranking

3. Add batch / digest modes
   - intraday immediate push for critical items only
   - scheduled digest for low-priority items

4. Add notification observability
   - why an item was pushed
   - why an item was suppressed
   - visibility in admin/API/UI

5. Add tests for push-noise control
   - critical announcement should push
   - low-value sentiment should suppress
   - digest-only items should not immediate-push

## Status

Deferred intentionally. Current notification path stays functional, but this
filtering layer should be implemented before broad daily use.
