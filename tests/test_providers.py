from scripts.providers import is_daily_quota_error

# real 429 bodies captured on 2026-07-14 — both use quota/billing language
# for per-MINUTE limits, which must NOT be treated as daily exhaustion
CEREBRAS_RPM = ('HTTP 429: {"message":"Requests per minute limit exceeded - '
                'too many requests sent.","type":"too_many_requests_error",'
                '"param":"quota","code":"request_quota_exceeded"}')
GEMINI_GENERIC = ('HTTP 429: { "error": { "code": 429, "message": "You exceeded '
                  'your current quota, please check your plan and billing '
                  'details." } }')
GEMINI_RPD = ('HTTP 429: quotaId: "GenerateRequestsPerDayPerProjectPerModel-'
              'FreeTier", quotaValue: "250"')


def test_per_minute_429s_are_not_daily():
    assert not is_daily_quota_error(CEREBRAS_RPM)
    assert not is_daily_quota_error(GEMINI_GENERIC)


def test_explicit_day_window_is_daily():
    assert is_daily_quota_error(GEMINI_RPD)
    assert is_daily_quota_error("HTTP 429: daily limit reached")
    assert is_daily_quota_error("HTTP 429: requests per day exceeded")


def test_non_429_is_never_daily():
    assert not is_daily_quota_error("HTTP 404: model gone")
    assert not is_daily_quota_error("daily quota exceeded")  # no 429
