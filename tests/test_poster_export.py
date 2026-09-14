import json
from kinetiqo.web.app import merge_poster_settings, POSTER_DEFAULT_SETTINGS


def test_merge_poster_settings_defaults():
    merged = merge_poster_settings({})
    # Keys from defaults present
    assert merged['boxVisible'] == POSTER_DEFAULT_SETTINGS['boxVisible']
    assert merged['statsVisible'] == POSTER_DEFAULT_SETTINGS['statsVisible']
    assert merged['bgType'] == POSTER_DEFAULT_SETTINGS['bgType']


def test_merge_poster_settings_overrides():
    raw = {
        'posterSize': 1000,
        'boxVisible': {'boxElevation': False},
        'statsVisible': {'elevation': False}
    }
    merged = merge_poster_settings(raw)
    assert merged['posterSize'] == 1000
    assert merged['boxVisible']['boxElevation'] is False
    assert merged['statsVisible']['elevation'] is False
    # other defaults still present
    assert merged['boxVisible']['boxTitle'] is True
    assert 'ratio' in merged
