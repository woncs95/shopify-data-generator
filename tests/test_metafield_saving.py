import unittest

from shopify_data_generator import metafield_saving as saving


class MetafieldSavingTests(unittest.TestCase):
    def test_retry_retains_hidden_pending_fields_and_only_replaces_edited_values(self):
        pending = [dict(namespace='custom', key='a', value='old'), dict(namespace='custom', key='b', value='keep')]
        current = [dict(namespace='custom', key='a', value='new'), dict(namespace='custom', key='c', value='ignore')]
        self.assertEqual(saving.retry_inputs(pending, current), [current[0], pending[1]])

    def test_retry_can_explicitly_omit_a_cleared_field_without_losing_hidden_fields(self):
        pending = [dict(namespace='custom', key='a', value='old'), dict(namespace='custom', key='b', value='keep')]
        self.assertEqual(saving.retry_inputs(pending, [], {'custom.a'}), [pending[1]])

    def test_new_product_requires_category_before_any_write(self):
        from unittest.mock import patch
        from app import shopify_registration_app as app
        with patch.object(app, 'resolve_existing_product', return_value=(None, '')):
            with self.assertRaisesRegex(RuntimeError, 'category'):
                app.create_product_workflow({}, {'title': 'Test'}, 'Brand', '', 10, None, 0,
                    'location', [], None, 'GRAMS', None, [], '', [])

    def test_category_constraints_reject_missing_and_wrong_category(self):
        definition = {'constraints': {'key': 'category', 'values': ['cat-a']}}
        self.assertFalse(saving.applicable(definition, ''))
        self.assertFalse(saving.applicable(definition, 'cat-b'))
        self.assertTrue(saving.applicable(definition, 'cat-a'))
        self.assertTrue(saving.applicable({'constraints': None}, ''))
        self.assertFalse(saving.applicable(None, 'cat-a'))

    def test_invalid_category_does_not_block_custom_field_and_remains_retryable(self):
        sent = []
        def graphql(query, variables):
            sent.extend(variables['metafields'])
            return {'metafieldsSet': {'metafields': variables['metafields'], 'userErrors': []}}
        inputs = [dict(ownerId='p', namespace='custom', key='benefits', value='hello'),
                  dict(ownerId='p', namespace='shopify', key='skin', value='v')]
        defs = {'custom.benefits': {'constraints': None},
                'shopify.skin': {'constraints': {'key': 'category', 'values': ['cat-a']}}}
        result = saving.save(graphql, inputs, defs, '')
        self.assertEqual([x['key'] for x in sent], ['benefits'])
        self.assertFalse(result['ok'])
        self.assertEqual(result['userErrors'][0]['identity'], 'shopify.skin')
        self.assertEqual(result['pending'], [inputs[1]])
        retry = saving.save(graphql, result['pending'], defs, 'cat-a')
        self.assertTrue(retry['ok'])
        self.assertEqual([x['key'] for x in sent], ['benefits', 'skin'])

    def test_failed_atomic_batch_keeps_all_its_fields_and_maps_error_index(self):
        def graphql(query, variables):
            return {'metafieldsSet': {'metafields': [], 'userErrors': [
                {'field': ['metafields', '1', 'value'], 'message': 'Invalid', 'code': 'INVALID_VALUE'}]}}
        inputs = [dict(ownerId='p', namespace='custom', key=k, value='v') for k in ['a', 'b']]
        result = saving.save(graphql, inputs, {f'custom.{k}': {'constraints': None} for k in ['a', 'b']}, '')
        self.assertFalse(result['ok'])
        self.assertEqual(result['pending'], inputs)
        self.assertEqual(result['userErrors'][0]['identity'], 'custom.b')

    def test_batches_never_exceed_25_and_transport_failure_preserves_pending(self):
        sizes = []
        def graphql(query, variables):
            sizes.append(len(variables['metafields']))
            if len(sizes) == 2:
                raise RuntimeError('offline')
            return {'metafieldsSet': {'metafields': variables['metafields'], 'userErrors': []}}
        inputs = [dict(ownerId='p', namespace='custom', key=str(i), value='v') for i in range(26)]
        defs = {f'custom.{i}': {'constraints': None} for i in range(26)}
        result = saving.save(graphql, inputs, defs, '')
        self.assertEqual(sizes, [25, 1])
        self.assertEqual(len(result['metafields']), 25)
        self.assertEqual(result['pending'], inputs[25:])

    def test_constraints_are_paginated_before_deciding_applicability(self):
        def graphql(query, variables):
            if 'definitionId' in variables:
                return {'metafieldDefinition': {'constraints': {'values': {
                    'nodes': [{'value': 'cat-b'}], 'pageInfo': {'hasNextPage': False, 'endCursor': None}}}}}
            return {'metafieldDefinitions': {'nodes': [{'id': 'd', 'namespace': 'shopify', 'key': 'skin',
                'constraints': {'key': 'category', 'values': {'nodes': [{'value': 'cat-a'}],
                'pageInfo': {'hasNextPage': True, 'endCursor': 'next'}}}}],
                'pageInfo': {'hasNextPage': False, 'endCursor': None}}}
        defs = saving.load_definitions(graphql)
        self.assertTrue(saving.applicable(defs['shopify.skin'], 'cat-b'))


if __name__ == '__main__':
    unittest.main()
