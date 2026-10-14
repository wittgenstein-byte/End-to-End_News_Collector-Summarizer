from __future__ import annotations

from backend.scrapers import SOURCES


def test_sources_registration():
    expected_sources = {
        'ThaiPBS',
        'Bangkok Post',
        'Matichon',
        '101 World',
        'The Standard',
        'Khaosod',
        'Thairath',
        'Thai Post',
        'Daily News',
        'Komchadluek',
        'Nation Online',
        'Bangkokbiznews',
    }
    registered_names = {s.name for s in SOURCES}
    assert expected_sources.issubset(registered_names), f'Missing sources: {expected_sources - registered_names}'

    for source in SOURCES:
        assert source.name, 'Source must have a name'
        assert source.url.startswith('http'), f'{source.name} must have a valid URL'
        assert source.color.startswith('#'), f'{source.name} must have a valid hex color'
        assert callable(source.scrape_fn), f'{source.name} scrape_fn must be callable'
