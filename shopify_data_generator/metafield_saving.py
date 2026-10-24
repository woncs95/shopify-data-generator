"""Category-aware metafield validation and recoverable, bounded writes."""

DEFINITIONS_QUERY = '''query($after: String) {
  metafieldDefinitions(ownerType: PRODUCT, first: 100, after: $after) {
    nodes { id namespace key constraints { key values(first: 250) {
      nodes { value } pageInfo { hasNextPage endCursor }
    } } }
    pageInfo { hasNextPage endCursor }
  }
}'''
CONSTRAINTS_QUERY = '''query($definitionId: ID!, $after: String) {
  metafieldDefinition(id: $definitionId) { constraints { values(first: 250, after: $after) {
    nodes { value } pageInfo { hasNextPage endCursor }
  } } }
}'''
SET_QUERY = '''mutation($metafields: [MetafieldsSetInput!]!) {
  metafieldsSet(metafields: $metafields) {
    metafields { id namespace key value }
    userErrors { field message code }
  }
}'''
PRODUCT_CATEGORY_QUERY = '''query($id: ID!) {
  product(id: $id) { id category { id fullName } }
}'''
CATEGORIES_QUERY = '''query($search: String!, $after: String) {
  taxonomy { categories(search: $search, first: 100, after: $after) {
    nodes { id fullName } pageInfo { hasNextPage endCursor }
  } }
}'''


def load_definitions(graphql):
    definitions = {}
    after = None
    while True:
        page = graphql(DEFINITIONS_QUERY, {'after': after})['metafieldDefinitions']
        for node in page['nodes']:
            constraints = node.get('constraints')
            if constraints and constraints.get('key'):
                values_page = constraints['values']
                values = [v['value'] for v in values_page['nodes']]
                while values_page['pageInfo']['hasNextPage']:
                    values_page = graphql(CONSTRAINTS_QUERY, {
                        'definitionId': node['id'], 'after': values_page['pageInfo']['endCursor']
                    })['metafieldDefinition']['constraints']['values']
                    values.extend(v['value'] for v in values_page['nodes'])
                node = {**node, 'constraints': {'key': constraints['key'], 'values': values}}
            definitions[f"{node['namespace']}.{node['key']}"] = node
        if not page['pageInfo']['hasNextPage']:
            return definitions
        after = page['pageInfo']['endCursor']


def applicable(definition, category_id):
    # Unknown definitions fail closed; a refresh may have removed a definition.
    if definition is None:
        return False
    constraints = definition.get('constraints')
    if not constraints or not constraints.get('key'):
        return True
    return constraints['key'] == 'category' and bool(category_id) and category_id in constraints['values']


def search_categories(graphql, search):
    nodes, after = [], None
    while True:
        page = graphql(CATEGORIES_QUERY, {'search': search, 'after': after})['taxonomy']['categories']
        nodes.extend(page['nodes'])
        if not page['pageInfo']['hasNextPage']:
            return nodes
        after = page['pageInfo']['endCursor']


def product_category(graphql, product_id):
    product = graphql(PRODUCT_CATEGORY_QUERY, {'id': product_id})['product']
    if not product:
        raise ValueError('Product no longer exists in Shopify.')
    return product.get('category') or {}


def save(graphql, inputs, definitions, category_id):
    result = {'ok': True, 'metafields': [], 'userErrors': [], 'pending': []}
    groups = {False: [], True: []}
    for item in inputs:
        identity = f"{item['namespace']}.{item['key']}"
        definition = definitions.get(identity)
        if not applicable(definition, category_id):
            result['pending'].append(item)
            result['userErrors'].append({'identity': identity, 'code': 'CATEGORY_CONSTRAINT',
                'message': 'Definition is unavailable or does not apply to the product category. Choose a compatible category or remove this value.'})
        else:
            constrained = bool((definition.get('constraints') or {}).get('key'))
            groups[constrained].append(item)
    for group in groups.values():
        for offset in range(0, len(group), 25):
            batch = group[offset:offset + 25]
            try:
                response = graphql(SET_QUERY, {'metafields': batch})['metafieldsSet']
                errors = response.get('userErrors') or []
                if not errors:
                    result['metafields'].extend(response.get('metafields') or [])
                    continue
            except Exception as error:
                errors = [{'message': str(error), 'code': 'REQUEST_FAILED'}]
            # Shopify rejects the whole batch on a user error. A transport failure
            # has an unknown outcome, so retain that batch for idempotent retry.
            result['pending'].extend(batch)
            for error in errors:
                field = error.get('field') or []
                identity = ', '.join(f"{x['namespace']}.{x['key']}" for x in batch)
                if len(field) > 1 and str(field[1]).isdigit() and int(field[1]) < len(batch):
                    item = batch[int(field[1])]
                    identity = f"{item['namespace']}.{item['key']}"
                result['userErrors'].append({**error, 'identity': identity})
    result['ok'] = not result['userErrors']
    return result


def retry_inputs(pending, current, omitted=()):
    replacements = {(item['namespace'], item['key']): item for item in current}
    return [replacements.get((item['namespace'], item['key']), item) for item in pending
            if f"{item['namespace']}.{item['key']}" not in omitted]
