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


def test_merge_poster_settings_map_controls():
    merged_defaults = merge_poster_settings({})
    assert merged_defaults['routeColor'] == '#38bdf8'
    assert merged_defaults['routeWidth'] == 4
    assert merged_defaults['routeOpacity'] == 100
    assert merged_defaults['toneOpacity'] == 50
    assert merged_defaults['mapToneColor'] == ''

    custom_map = {
        'bgType': 'map',
        'routeColor': '#ff0055',
        'routeWidth': 6,
        'routeOpacity': 85,
        'mapToneColor': '#222222',
        'toneOpacity': 40,
        'mapOpacity': 75
    }
    merged_custom = merge_poster_settings(custom_map)
    assert merged_custom['bgType'] == 'map'
    assert merged_custom['routeColor'] == '#ff0055'
    assert merged_custom['routeWidth'] == 6
    assert merged_custom['routeOpacity'] == 85
    assert merged_custom['mapToneColor'] == '#222222'
    assert merged_custom['toneOpacity'] == 40
    assert merged_custom['mapOpacity'] == 75

