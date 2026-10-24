import io
import unittest
from PIL import Image
from shopify_data_generator import product_images as images


class ProductImageTests(unittest.TestCase):
    def test_app_enables_openrouter_web_and_does_not_run_fallback_after_success(self):
        from unittest.mock import patch
        from app import shopify_registration_app as app
        payloads = []
        def openrouter(key, payload, schema_name, fallback_model=''):
            payloads.append(payload)
            return {'pages': [{'url': 'https://brand.example/product', 'source_kind': 'official_brand',
                               'authority_evidence': 'Brand official site https://brand.example'}]}
        page = '<title>Brand Relief Sun</title><meta property="og:image" content="/front.jpg">'
        with patch.object(app, 'request_openrouter_json', side_effect=openrouter), patch.object(
            images, 'fetch_page', return_value=page), patch.object(images, 'validate_image',
            return_value={'width': 800, 'height': 800, 'digest': 'one'}), patch.object(
            app, 'searxng_search_cached', side_effect=AssertionError('Fallback must not run')):
            result = app.find_product_images({'OPENROUTER_API_KEY': 'test'}, 'model', '', 'Relief Sun', 'Brand')
        self.assertEqual(result['provider'], 'OpenRouter web')
        self.assertEqual(result['images'][0]['url'], 'https://brand.example/front.jpg')
        self.assertEqual(payloads[0]['plugins'][0]['id'], 'web')

    def test_rejects_different_product_kind_shade_and_measurement_unit(self):
        for actual, expected in [
            ('Brand Green Tea Cleanser 50 ml', 'Brand Green Tea Serum 50 ml'),
            ('Brand Lip Tint 02 Coral', 'Brand Lip Tint 01 Rose'),
            ('Brand Serum 50 g', 'Brand Serum 50 ml'),
        ]:
            self.assertFalse(images.product_matches(actual, expected))

    def test_collection_recommendations_are_not_product_page_images(self):
        page = '<title>All products</title><script type="application/ld+json">{"@type":"ItemList","itemListElement":[{"@type":"Product","name":"Relief Sun","image":"/a.jpg"}]}</script>'
        self.assertEqual(images.extract_images(page, 'https://example.com/collection', 'Relief Sun'), [])

    def test_main_heading_can_identify_product_when_seo_title_is_abbreviated(self):
        page = '<title>Hydration Award Winner</title><h1>Advanced Snail 96 Mucin Power Essence</h1><meta property="og:image" content="/main.jpg">'
        self.assertEqual(len(images.extract_images(page, 'https://example.com/product', 'Advanced Snail 96 Mucin Power Essence')), 1)

    def test_gallery_marker_does_not_override_a_different_shade_in_alt(self):
        page = '<title>Brand Lip Tint 01 Rose</title><div class="product-gallery"><img src="/wrong.jpg" alt="Brand Lip Tint 02 Coral"><img src="/right.jpg" alt="Front"></div>'
        found = images.extract_images(page, 'https://example.com/product', 'Brand Lip Tint 01 Rose')
        self.assertEqual([item['url'] for item in found], ['https://example.com/right.jpg'])

    def test_extracts_matching_product_gallery_but_not_recommendations_or_logo(self):
        html = '''<script type="application/ld+json">{"@graph":[
        {"@type":"Product","name":"Brand Relief Sun 50 ml","image":["/front.jpg",{"url":"/back.jpg"}]},
        {"@type":"Product","name":"Other Shampoo","image":"/shampoo.jpg"}]}</script>
        <img src="/logo.jpg"><meta property="og:image" content="/front.jpg">'''
        result = images.extract_images(html, 'https://brand.example/products/sun', 'Brand Relief Sun 50 ml')
        self.assertEqual([x['url'] for x in result], ['https://brand.example/front.jpg', 'https://brand.example/back.jpg'])

    def test_unrelated_product_page_is_rejected(self):
        html = '<title>Brand Shampoo</title><meta property="og:image" content="/shampoo.jpg">'
        self.assertEqual(images.extract_images(html, 'https://brand.example/shampoo', 'Brand Relief Sun 50 ml'), [])

    def test_fallback_runs_after_images_fail_validation_not_just_after_search_error(self):
        order = []
        def provider(name):
            def run():
                order.append(name)
                return [{'url': 'https://example.com/' + name}]
            return run
        def page(url):
            return '<title>Relief Sun</title><meta property="og:image" content="/' + url.rsplit('/', 1)[-1] + '.jpg">'
        def validate(url):
            if 'openrouter' in url:
                raise ValueError('HTML, not an image')
            return {'width': 800, 'height': 800, 'digest': 'same'}
        result = images.discover([('openrouter', provider('openrouter')), ('searxng', provider('searxng')),
                                 ('serpapi', provider('serpapi'))], page, validate, 'Relief Sun')
        self.assertEqual(order, ['openrouter', 'searxng'])
        self.assertEqual(result['provider'], 'searxng')
        self.assertEqual(len(result['images']), 1)
        self.assertTrue(result['warnings'])

    def test_primary_success_deduplicates_bytes_and_does_not_call_fallback(self):
        def fallback():
            self.fail('Fallback must not run after primary success')
        page = '<title>Relief Sun</title><script type="application/ld+json">{"@type":"Product","name":"Relief Sun","image":["/a.jpg","/b.jpg"]}</script>'
        result = images.discover([('openrouter', lambda: [{'url': 'https://example.com/product'}]),
                                 ('searxng', fallback)], lambda _: page,
                                lambda _: {'width': 800, 'height': 800, 'digest': 'same'}, 'Relief Sun')
        self.assertEqual(len(result['images']), 1)
        self.assertEqual(result['images'][0]['source_url'], 'https://example.com/product')

    def test_rejects_invalid_bytes_and_tiny_images(self):
        with self.assertRaises(ValueError):
            images.inspect_image(b'<html>denied</html>')
        output = io.BytesIO()
        Image.new('RGB', (32, 32)).save(output, format='PNG')
        with self.assertRaises(ValueError):
            images.inspect_image(output.getvalue())
        output = io.BytesIO()
        Image.new('RGB', (800, 800)).save(output, format='PNG')
        self.assertEqual(images.inspect_image(output.getvalue())['width'], 800)

    def test_rejects_nonpublic_image_addresses(self):
        for url in ['file:///etc/passwd', 'http://127.0.0.1/a', 'http://169.254.169.254/a', 'https://user:pass@example.com/a']:
            with self.assertRaises(ValueError):
                images.public_url(url)
