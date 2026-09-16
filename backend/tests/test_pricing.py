from app.pricing import estimate_cost_usd
from app.schema import Usage


def test_cost_opus_with_cache_and_search():
    u = Usage(input_tokens=100_000, cache_read_input_tokens=1_000_000, cache_creation_input_tokens=50_000,
              output_tokens=20_000, web_search_requests=8)
    # 0.5 + 0.5 + 0.3125 + 0.5 + 0.08
    assert estimate_cost_usd("claude-opus-5", u) == 1.8925


def test_cost_sonnet_and_unknown_model_falls_back_to_opus():
    u = Usage(input_tokens=1_000_000, output_tokens=100_000)
    assert estimate_cost_usd("claude-sonnet-5", u) == 3.0
    assert estimate_cost_usd("something-else", u) == estimate_cost_usd("claude-opus-5", u) == 7.5
