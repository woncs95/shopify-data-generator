import unittest
from shopify_data_generator import category_recommendations as recommendations


class CategoryRecommendationTests(unittest.TestCase):
    def test_bulk_uncertain_recommendation_stops_before_product_generation(self):
        from unittest.mock import patch
        from app import shopify_registration_app as app
        with patch.object(app, 'collect_product_research', return_value={}), patch.object(
            app, 'recommend_product_categories', return_value=[{'id': 'real', 'fullName': 'Cream',
                'confidence': 'medium', 'reason': 'Uncertain'}]), patch.object(
            app, 'generate_ai_draft', side_effect=AssertionError('Must stop before draft generation')):
            result = app.process_bulk_upload_row(env={}, model='model', seo_model='', fallback_model='',
                use_web=False, row={'product_name': 'Test', 'vendor': 'Brand'}, row_number=2,
                tag_options=[], discovery_products=[], products_df=None, product_label_to_id={},
                product_label_to_handle={}, product_handle_to_label={}, safe_metafields=None,
                allowed_metafields=[], location_id='location', update_existing=False,
                recommend_missing_category=True)
        self.assertEqual(result['status'], 'skipped')
        self.assertEqual(result['stage'], 'categoryReview')
        self.assertEqual(result['category_recommendation']['id'], 'real')

    def test_only_shopify_candidates_are_returned_with_canonical_names(self):
        replies = iter([{'search_terms': ['sunscreen']}, {'recommendations': [
            {'id': 'invented', 'reason': 'wrong', 'confidence': 'high'},
            {'id': 'real', 'fullName': 'Invented label', 'reason': 'SPF product', 'confidence': 'high'}]}])
        result = recommendations.recommend(lambda *_: next(replies),
            lambda _: [{'id': 'real', 'fullName': 'Skin Care > Sunscreen'}],
            'Relief Sun', 'BOJ', {'records': [{'text': 'SPF50 sunscreen'}]})
        self.assertEqual(result, [{'id': 'real', 'fullName': 'Skin Care > Sunscreen',
                                   'reason': 'SPF product', 'confidence': 'high'}])

    def test_no_shopify_matches_does_not_ask_ai_to_invent_a_category(self):
        calls = []
        def ask(*args):
            calls.append(args)
            return {'search_terms': ['unknown']}
        with self.assertRaisesRegex(ValueError, 'No Shopify'):
            recommendations.recommend(ask, lambda _: [], 'unknown', 'brand', {})
        self.assertEqual(len(calls), 1)

    def test_research_reaches_ranking_and_duplicate_searches_are_bounded(self):
        calls, searches = [], []
        def ask(prompt, payload):
            calls.append(payload)
            if len(calls) == 1:
                return {'search_terms': ['cream', 'cream', 'moisturizer', 'lotion', 'excess']}
            return {'recommendations': [{'id': 'real', 'reason': 'Hydrates', 'confidence': 'medium'}]}
        def search(term):
            searches.append(term)
            return [{'id': 'real', 'fullName': 'Moisturizer'}]
        recommendations.recommend(ask, search, 'cream', 'brand', {'records': [{'text': 'Hydrates'}]})
        self.assertEqual(searches, ['cream', 'moisturizer', 'lotion'])
        self.assertEqual(calls[1]['research']['records'][0]['text'], 'Hydrates')
        self.assertEqual(len(calls[1]['candidates']), 1)

    def test_invalid_recommendations_fail_without_defaulting_to_first_search_result(self):
        replies = iter([{'search_terms': ['cream']}, {'recommendations': [{'id': 'invented'}]}])
        with self.assertRaisesRegex(ValueError, 'valid recommendation'):
            recommendations.recommend(lambda *_: next(replies),
                lambda _: [{'id': 'real', 'fullName': 'Cream'}], 'cream', '', {})
