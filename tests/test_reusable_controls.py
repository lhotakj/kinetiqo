"""Unit tests for reusable UI controls across Mega Stats, Poster, and Map.

Verifies:
- _font_select.html and _font_options.html
- _control_range.html
- _control_color_tint.html
- _image_upload_buttons.html
- _map_control_basemap.html
- _map_control_color.html
- _map_control_range.html
- _map_control_separator.html
- Size options and Dimensions display unification in stats.html and poster.html
"""

import os
import unittest
import jinja2


class BaseTemplateTestCase(unittest.TestCase):
    """Base test case providing an isolated Jinja2 environment for templates."""

    @classmethod
    def setUpClass(cls):
        templates_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            'src', 'kinetiqo', 'web', 'templates'
        )
        cls.loader = jinja2.FileSystemLoader(templates_dir)
        cls.env = jinja2.Environment(
            loader=cls.loader,
            autoescape=True,
        )
        cls.env.globals['url_for'] = (
            lambda endpoint, filename=None, **kwargs:
            f"/static/{filename}" if endpoint == 'static' else f"/{endpoint}"
        )

    def render(self, template_name, **context):
        template = self.env.get_template(template_name)
        return template.render(**context)


class TestFontSelectControl(BaseTemplateTestCase):
    """Unit tests for _font_select.html."""

    def test_default_rendering(self):
        html = self.render('_font_select.html', poster_google_fonts=[])
        self.assertIn('for="font-select"', html)
        self.assertIn('id="font-select"', html)
        self.assertIn('Font:', html)
        self.assertIn('flex flex-col items-start', html)
        self.assertIn('w-full', html)

    def test_custom_control_id_and_label(self):
        html = self.render(
            '_font_select.html',
            font_control_id='customFontId',
            font_label='Choose Typography:',
            poster_google_fonts=[]
        )
        self.assertIn('for="customFontId"', html)
        self.assertIn('id="customFontId"', html)
        self.assertIn('Choose Typography:', html)

    def test_font_options_inclusion(self):
        fonts = [{'name': 'Inter'}, {'name': 'Oswald'}, {'name': 'Italiana'}]
        html = self.render('_font_select.html', poster_google_fonts=fonts)
        self.assertIn('<option value="Inter">Inter</option>', html)
        self.assertIn('<option value="Italiana">Italiana</option>', html)
        self.assertIn('<option value="Oswald">Oswald</option>', html)
        # Verify alphabetical sorting (Inter < Italiana < Oswald)
        pos_inter = html.index('value="Inter"')
        pos_italiana = html.index('value="Italiana"')
        pos_oswald = html.index('value="Oswald"')
        self.assertTrue(pos_inter < pos_italiana < pos_oswald)


class TestFontOptionsControl(BaseTemplateTestCase):
    """Unit tests for _font_options.html."""

    def test_alphabetical_sorting(self):
        fonts = [{'name': 'Ubuntu'}, {'name': 'Bebas Neue'}, {'name': 'Fanwood Text'}]
        html = self.render('_font_options.html', poster_google_fonts=fonts)
        self.assertIn('<option value="Bebas Neue">Bebas Neue</option>', html)
        self.assertIn('<option value="Fanwood Text">Fanwood Text</option>', html)
        self.assertIn('<option value="Ubuntu">Ubuntu</option>', html)
        pos_bebas = html.index('value="Bebas Neue"')
        pos_fanwood = html.index('value="Fanwood Text"')
        pos_ubuntu = html.index('value="Ubuntu"')
        self.assertTrue(pos_bebas < pos_fanwood < pos_ubuntu)

    def test_empty_font_list(self):
        html = self.render('_font_options.html', poster_google_fonts=[])
        self.assertEqual(html.strip(), '')


class TestControlRange(BaseTemplateTestCase):
    """Unit tests for _control_range.html."""

    def test_default_values(self):
        html = self.render('_control_range.html', control_id='my-slider', label='Opacity')
        self.assertIn('<label for="my-slider">Opacity</label>', html)
        self.assertIn('id="my-slider"', html)
        self.assertIn('min="0"', html)
        self.assertIn('max="100"', html)
        self.assertIn('value="100"', html)
        self.assertIn('id="my-slider-val"', html)
        self.assertIn('100%', html)

    def test_custom_values_and_suffix(self):
        html = self.render(
            '_control_range.html',
            control_id='tone-op',
            label='Tone Opacity',
            min_val=10,
            max_val=80,
            value=45,
            suffix=' deg',
            value_id='custom-tone-val'
        )
        self.assertIn('<label for="tone-op">Tone Opacity</label>', html)
        self.assertIn('id="tone-op"', html)
        self.assertIn('min="10"', html)
        self.assertIn('max="80"', html)
        self.assertIn('value="45"', html)
        self.assertIn('id="custom-tone-val"', html)
        self.assertIn('45 deg', html)


class TestControlColorTint(BaseTemplateTestCase):
    """Unit tests for _control_color_tint.html."""

    def test_default_rendering(self):
        html = self.render(
            '_control_color_tint.html',
            control_id='tint-picker',
            clear_btn_id='tint-clear-btn',
            value_id='tint-val'
        )
        self.assertIn('<label for="tint-picker">Color Tone</label>', html)
        self.assertIn('id="tint-picker"', html)
        self.assertIn('value="#ffffff"', html)
        self.assertIn('id="tint-clear-btn"', html)
        self.assertIn('id="tint-val"', html)
        self.assertIn('None', html)

    def test_custom_values(self):
        html = self.render(
            '_control_color_tint.html',
            control_id='overlay-tint',
            label='Background Tint',
            value='#ff6600',
            clear_btn_id='btn-reset-tint',
            value_id='val-tint-text',
            value_text='#ff6600'
        )
        self.assertIn('<label for="overlay-tint">Background Tint</label>', html)
        self.assertIn('id="overlay-tint"', html)
        self.assertIn('value="#ff6600"', html)
        self.assertIn('id="btn-reset-tint"', html)
        self.assertIn('id="val-tint-text"', html)
        self.assertIn('#ff6600', html)


class TestImageUploadButtons(BaseTemplateTestCase):
    """Unit tests for _image_upload_buttons.html."""

    def test_default_rendering(self):
        html = self.render('_image_upload_buttons.html')
        self.assertIn('id="uploadInput-btn"', html)
        self.assertIn('for="uploadInput"', html)
        self.assertIn('id="uploadInput"', html)
        self.assertIn('id="uploadInput-spinner"', html)
        self.assertIn('kinetiqo-loading-32x32.webp', html)
        self.assertIn('id="uploadInput-text"', html)
        self.assertIn('Upload Image', html)
        self.assertIn('id="clearImageBtn"', html)
        self.assertIn('Clear Image', html)
        self.assertIn('id="uploadInput-status"', html)
        self.assertIn('role="alert"', html)
        self.assertIn('Supports PNG, JPG, WEBP, HEIC', html)

    def test_custom_parameters(self):
        html = self.render(
            '_image_upload_buttons.html',
            upload_input_id='statsBgUpload',
            upload_button_id='statsUploadBtn',
            upload_label='Add Photo',
            clear_button_id='statsClearBtn',
            clear_label='Remove Photo'
        )
        self.assertIn('id="statsUploadBtn"', html)
        self.assertIn('for="statsBgUpload"', html)
        self.assertIn('id="statsBgUpload"', html)
        self.assertIn('Add Photo', html)
        self.assertIn('id="statsClearBtn"', html)
        self.assertIn('Remove Photo', html)


class TestMapControlBasemap(BaseTemplateTestCase):
    """Unit tests for _map_control_basemap.html."""

    def test_basemap_rendering(self):
        providers = {
            'osm': {'name': 'OpenStreetMap', 'disabled': False},
            'maptiler': {'name': 'MapTiler Outdoor', 'disabled': True},
        }
        html = self.render(
            '_map_control_basemap.html',
            tile_providers=providers,
            current_basemap='osm'
        )
        self.assertIn('<label for="basemapPicker"', html)
        self.assertIn('Base Map:', html)
        self.assertIn('id="basemapPicker"', html)
        self.assertIn('value="osm"', html)
        self.assertIn('selected', html)
        self.assertIn('value="maptiler"', html)
        self.assertIn('disabled', html)
        self.assertIn('(API key required)', html)


class TestMapControlColor(BaseTemplateTestCase):
    """Unit tests for _map_control_color.html."""

    def test_color_rendering(self):
        html = self.render(
            '_map_control_color.html',
            control_id='routeColorPicker',
            label='Route Color',
            value='#fc4c02',
            clear_button_id='routeColorClear',
            clear_button_label='Default',
            value_text_id='routeColorValue',
            value_text='#fc4c02'
        )
        self.assertIn('<label for="routeColorPicker"', html)
        self.assertIn('Route Color', html)
        self.assertIn('id="routeColorPicker"', html)
        self.assertIn('value="#fc4c02"', html)
        self.assertIn('id="routeColorClear"', html)
        self.assertIn('Default', html)
        self.assertIn('id="routeColorValue"', html)
        self.assertIn('#fc4c02', html)


class TestMapControlRange(BaseTemplateTestCase):
    """Unit tests for _map_control_range.html."""

    def test_range_rendering(self):
        html = self.render(
            '_map_control_range.html',
            control_id='weightPicker',
            label='Line Weight',
            min_value=1,
            max_value=10,
            value=3,
            suffix='px'
        )
        self.assertIn('<label for="weightPicker"', html)
        self.assertIn('Line Weight', html)
        self.assertIn('id="weightPicker"', html)
        self.assertIn('min="1"', html)
        self.assertIn('max="10"', html)
        self.assertIn('value="3"', html)
        # id="weightValue" (replaces 'Picker' with 'Value')
        self.assertIn('id="weightValue"', html)
        self.assertIn('3px', html)


class TestMapControlSeparator(BaseTemplateTestCase):
    """Unit tests for _map_control_separator.html."""

    def test_separator_rendering(self):
        html = self.render('_map_control_separator.html')
        self.assertIn('|', html)
        self.assertIn('select-none', html)


class TestMegaStatsAndPosterUnifiedControls(BaseTemplateTestCase):
    """Verify size controls and dimensions display on Mega Stats and Poster."""

    def test_stats_size_options_and_no_xs_s(self):
        """Mega stats must support M, L, XL, XXL, XXXL and NOT support XS or S."""
        template_file = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            'src', 'kinetiqo', 'web', 'templates', 'stats.html'
        )
        with open(template_file, encoding='utf-8') as f:
            content = f.read()

        # Check options in #stats-size select
        self.assertIn('<option value="1280">M (width 1280px)</option>', content)
        self.assertIn('<option value="1440">L (width 1440px)</option>', content)
        self.assertIn('<option value="1600">XL (width 1600px)</option>', content)
        self.assertIn('<option value="1920">XXL (width 1920px)</option>', content)
        self.assertIn('<option value="2048">XXXL (width 2048px)</option>', content)

        # Must NOT contain XS or S in stats-size options
        stats_size_block = content[content.index('id="stats-size"'):content.index('</select>', content.index('id="stats-size"'))]
        self.assertNotIn('XS (width', stats_size_block)
        self.assertNotIn('S (width', stats_size_block)
        self.assertNotIn('value="800"', stats_size_block)
        self.assertNotIn('value="1024"', stats_size_block)

    def test_stats_dimensions_display_inline(self):
        """Mega stats Dimensions label and value must be accessible and inline."""
        template_file = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            'src', 'kinetiqo', 'web', 'templates', 'stats.html'
        )
        with open(template_file, encoding='utf-8') as f:
            content = f.read()

        self.assertIn('<label for="stats-dimensions">Dimensions</label>', content)
        self.assertIn('<span id="stats-dimensions" class="text-sm text-gray-700 dark:text-gray-300 font-mono whitespace-nowrap">— × —</span>', content)

    def test_poster_dimensions_display_inline_and_clean_size(self):
        """Poster dimensions must be on the same line as label and show only the size."""
        template_file = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            'src', 'kinetiqo', 'web', 'templates', 'poster.html'
        )
        with open(template_file, encoding='utf-8') as f:
            content = f.read()

        self.assertIn('<label for="posterDimensions">Dimensions</label>', content)
        self.assertIn('<div id="posterDimensions" class="text-sm text-gray-700 dark:text-gray-300 font-mono whitespace-nowrap">— × —</div>', content)
        self.assertNotIn('Poster dimensions: — × —', content)
        self.assertNotIn('Poster\n                            dimensions: — × —', content)


if __name__ == '__main__':
    unittest.main()
