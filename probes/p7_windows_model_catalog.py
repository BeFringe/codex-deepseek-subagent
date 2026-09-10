"""Parent-owned, hash-bound metadata for one isolated DeepSeek mutation probe.

The descriptor enables registration; it does not qualify provider wire behavior,
grant assignment authority, or authorize writes. Those need native live receipts.
"""

import copy
import hashlib
import json

CHILD = 'deepseek-v4-flash'


def descriptor():
    return {'slug': CHILD, 'display_name': 'DeepSeek isolated Windows qualification',
            'description': None, 'default_reasoning_level': 'low',
            'supported_reasoning_levels': [{'effort': 'low', 'description': 'Existing qualification role effort; provider behavior requires live validation'}], 'shell_type': 'disabled',
            'visibility': 'none', 'supported_in_api': True, 'priority': 99,
            'availability_nux': None, 'upgrade': None,
            'model_messages': {'instructions_template': 'Follow the exact parent assignment and trusted Hook authority. Use only the native tools exposed for that assignment.',
                               'instructions_variables': None},
            'include_skills_usage_instructions': False, 'include_plugin_usage_instructions': False,
            'include_apps_usage_instructions': False, 'supports_reasoning_summary_parameter': False,
            'default_reasoning_summary': 'none', 'support_verbosity': False, 'default_verbosity': None,
            'apply_patch_tool_type': 'freeform', 'web_search_tool_type': 'text',
            'truncation_policy': {'mode': 'bytes', 'limit': 10000},
            'supports_image_detail_original': False, 'context_window': 64000,
            'max_context_window': 64000, 'experimental_supported_tools': [],
            'input_modalities': ['text'], 'supports_search_tool': False,
            'use_responses_lite': False, 'node_repl_disabled': True,
            'multi_agent_version': None, 'multi_agent_reasoning_effort': None,
            'tool_mode': None}


def build(raw, expected_sha256, *, parent_slug, child_slug=CHILD):
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError('bundled model catalog hash mismatch')
    if child_slug != CHILD:
        raise ValueError('unexpected child model slug')
    catalog = json.loads(raw)
    models = catalog.get('models')
    if not isinstance(models, list):
        raise ValueError('complete ModelsResponse is required')
    slugs = [model['slug'] for model in models]
    if len(slugs) != len(set(slugs)) or slugs.count(parent_slug) != 1 or CHILD in slugs:
        raise ValueError('missing parent, duplicate slug, or preexisting child descriptor')
    result = copy.deepcopy(catalog)
    result['models'].append(descriptor())
    return result


def validate_generated(raw, expected_sha256, bundled, *, parent_slug):
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError('generated model catalog hash mismatch')
    value = json.loads(raw)
    expected = build(bundled, hashlib.sha256(bundled).hexdigest(), parent_slug=parent_slug)
    if value != expected:
        raise ValueError('generated catalog changes parent or widens child descriptor')
    return value
