import hashlib
from pathlib import Path
import tempfile
import unittest

from contexto_core.index import connect, scan
from contexto_core.support import support_context


class SupportContextTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'project'
        self.root.mkdir()
        self.db = connect(Path(self.temp.name) / 'index.sqlite')
        self.addCleanup(self.db.close)

    def source(self, text, encoding='utf-8'):
        (self.root / 'mod.py').write_bytes(text.encode(encoding))
        scan(self.root, self.db)

    def result(self, symbol='target', **options):
        return support_context(self.root, self.db, 'mod.py', symbol, **options)

    @staticmethod
    def rendered(result):
        return ''.join(r['text'] for r in result['ranges'])

    def test_import_alias_and_transitive_constant_support_excludes_unrelated(self):
        source = 'import math as calc\nBASE = 4\nLIMIT = BASE * 2\nUNRELATED = "omit_me"\ndef target(value):\n    return calc.sqrt(value) + LIMIT\n'
        self.source(source)
        result = self.result()
        text = self.rendered(result)
        self.assertIn('import math as calc', text)
        self.assertIn('BASE = 4', text)
        self.assertIn('LIMIT = BASE * 2', text)
        self.assertNotIn('omit_me', text)
        self.assertNotIn('def target', text)
        self.assertEqual(result['sha256'], hashlib.sha256(source.encode()).hexdigest())
        self.assertTrue(result['complete'])

    def test_arguments_and_comprehension_locals_do_not_select_module_values(self):
        self.source('value = "unused1"\nitem = "unused2"\nLIMIT = 3\ndef target(value):\n    return [item + LIMIT for item in value]\n')
        result = self.result()
        self.assertNotIn('unused', self.rendered(result))
        self.assertIn('LIMIT = 3', self.rendered(result))
        self.assertTrue(result['complete'])

    def test_defaults_decorator_and_forward_type_annotations_have_support(self):
        self.source('from __future__ import annotations\nfrom typing import Sequence\nDEFAULT = 5\ndef decorate(fn):\n    return fn\n@decorate\ndef target(value: "Sequence[int]" = DEFAULT) -> int:\n    return len(value)\n')
        result = self.result()
        text = self.rendered(result)
        self.assertIn('from __future__ import annotations', text)
        self.assertIn('from typing import Sequence', text)
        self.assertIn('DEFAULT = 5', text)
        self.assertEqual(result['required_symbols'], [{'path': 'mod.py', 'symbol': 'decorate'}])
        self.assertNotIn('def decorate', text)

    def test_method_and_nested_global_references(self):
        self.source('LIMIT = 5\nclass Worker:\n    def target(self):\n        def inner():\n            return LIMIT\n        return inner()\n')
        result = self.result('Worker.target')
        self.assertIn('LIMIT = 5', self.rendered(result))
        self.assertTrue(result['complete'])

    def test_selected_nested_closure_is_explicitly_unresolved(self):
        self.source('def outer(value):\n    def target():\n        return value\n    return target\n')
        result = self.result('outer.target')
        self.assertFalse(result['complete'])
        self.assertIn({'name': 'value', 'reason': 'enclosing_scope'}, result['unresolved'])

    def test_nested_default_does_not_confuse_outer_argument_with_module_value(self):
        self.source('value = "wrong_module_value"\ndef outer(value):\n    def target(arg=value):\n        return arg\n    return target\n')
        result = self.result('outer.target')
        self.assertNotIn('wrong_module_value', self.rendered(result))
        self.assertFalse(result['complete'])
        self.assertIn({'name': 'value', 'reason': 'enclosing_definition_scope'}, result['unresolved'])

    def test_method_default_class_binding_is_not_replaced_with_module_binding(self):
        self.source('LIMIT = "wrong_module_value"\nclass Worker:\n    LIMIT = 4\n    def target(self, value=LIMIT):\n        return value\n')
        result = self.result('Worker.target')
        self.assertNotIn('wrong_module_value', self.rendered(result))
        self.assertFalse(result['complete'])
        self.assertIn({'name': 'LIMIT', 'reason': 'enclosing_definition_scope'}, result['unresolved'])

    def test_multiline_sensitive_constant_is_redacted_before_return(self):
        self.source('password = (\n    "qwerty123456"\n)\ndef target():\n    return password\n')
        result = self.result()
        self.assertNotIn('qwerty123456', self.rendered(result))
        self.assertIn('OCULTA', self.rendered(result))
        self.assertFalse(any('qwerty123456' in str(row) for row in self.db.execute('SELECT symbols FROM files')))

    def test_line_limit_omits_whole_statement_instead_of_truncation(self):
        self.source('VALUES = [\n    1,\n    2,\n    3,\n]\ndef target():\n    return VALUES\n')
        result = self.result(max_lines=3)
        self.assertFalse(result['ranges'])
        self.assertEqual(result['omissions'][0]['reason'], 'support_max_lines')
        self.assertFalse(result['complete'])

    def test_changed_hash_and_symlink_rejected(self):
        self.source('VALUE = 1\ndef target():\n    return VALUE\n')
        (self.root / 'mod.py').write_text('VALUE = 2\ndef target():\n    return VALUE\n')
        with self.assertRaisesRegex(ValueError, 'reindexar'):
            self.result()

    def test_conditional_rebinding_retains_guard_and_warns(self):
        self.source('VALUE = 1\nif __name__ == "__main__":\n    VALUE = 2\ndef target():\n    return VALUE\n')
        result = self.result()
        text = self.rendered(result)
        self.assertIn('if __name__ == "__main__":', text)
        self.assertIn('VALUE = 1', text)
        self.assertIn('VALUE = 2', text)
        self.assertFalse(result['complete'])
        self.assertIn({'name': 'VALUE', 'reason': 'ambiguous_module_binding'}, result['unresolved'])

    def test_imported_module_attributes_need_local_import_only(self):
        self.source('import imaginary_settings as config\ndef target():\n    return config.MAXIMUM\n')
        result = self.result()
        self.assertIn('import imaginary_settings as config', self.rendered(result))
        self.assertTrue(result['complete'])

    def test_pep263_and_unicode_line_numbers(self):
        self.source('# coding: latin-1\nTITLE = "España"\ndef target():\n    return TITLE\n', 'latin-1')
        result = self.result()
        self.assertIn('L2: TITLE = "España"', self.rendered(result))

    def test_dynamic_namespace_and_wildcard_are_not_claimed_complete(self):
        self.source('from imaginary_settings import *\ndef target():\n    return globals().get("x") or UNKNOWN\n')
        result = self.result()
        self.assertFalse(result['complete'])
        self.assertIn({'name': 'target', 'reason': 'dynamic_namespace'}, result['unresolved'])
        self.assertIn({'name': 'UNKNOWN', 'reason': 'wildcard_or_unbound_global'}, result['unresolved'])

    def test_module_rebindings_and_mutations_never_claim_initial_value_complete(self):
        cases = [
            ('X = 1\ndel X\n', 'del X'),
            ('X = 1\nfor X in [2, 3]:\n    pass\n', 'for X in [2, 3]'),
            ('X = 1\ntry:\n    1 / 0\nexcept ZeroDivisionError:\n    X = 2\n', 'X = 2'),
            ('X = 1\nmatch 2:\n    case 2:\n        X = 2\n', 'X = 2'),
            ('X = 1\nY = (X := 2)\n', 'X := 2'),
            ('X = [1]\nX[0], Y = 2, 3\n', 'X[0], Y = 2, 3'),
            ('X: int\n', 'X: int'),
            ('X = X + 1\n', 'X = X + 1'),
        ]
        for prefix, marker in cases:
            with self.subTest(prefix=prefix):
                self.source(prefix + 'def target():\n    return X\n')
                result = self.result()
                self.assertFalse(result['complete'])
                self.assertTrue(result['unresolved'])
                self.assertIn(marker, self.rendered(result))

    def test_wildcard_can_replace_known_names_and_builtins(self):
        for prefix, body in [('X = 1\n', 'X'), ('', 'len([])')]:
            with self.subTest(body=body):
                self.source(prefix + 'from imaginary import *\ndef target():\n    return ' + body + '\n')
                result = self.result()
                self.assertFalse(result['complete'])
                self.assertIn('from imaginary import *', self.rendered(result))
                self.assertIn({'name': '*', 'reason': 'wildcard_can_replace_bindings'}, result['unresolved'])

    def test_pass_through_free_variable_requires_enclosing_scope(self):
        self.source('def outer(value):\n    def target():\n        def inner():\n            return value\n        return inner\n    return target\n')
        result = self.result('outer.target')
        self.assertFalse(result['complete'])
        self.assertIn({'name': 'value', 'reason': 'enclosing_scope'}, result['unresolved'])

    def test_descendant_and_class_annotations_retain_imports(self):
        cases = [
            ('def target():\n    def inner(value: Sequence[int]):\n        return value\n    return inner\n', 'target'),
            ('class Target:\n    value: "Sequence[int]"\n', 'Target'),
        ]
        for code, symbol in cases:
            with self.subTest(symbol=symbol):
                self.source('from __future__ import annotations\nfrom typing import Sequence\n' + code)
                result = self.result(symbol)
                self.assertIn('from typing import Sequence', self.rendered(result))

    def test_dynamic_module_namespace_read_or_write_is_explicit(self):
        cases = ['Y = 2\nX = globals()["Y"]\n', 'X = 1\nglobals()["X"] = 2\n']
        for code in cases:
            with self.subTest(code=code):
                self.source(code + 'def target():\n    return X\n')
                result = self.result()
                self.assertFalse(result['complete'])
                self.assertIn('globals()', self.rendered(result))
                self.assertIn({'name': '*', 'reason': 'dynamic_module_namespace'}, result['unresolved'])


if __name__ == '__main__':
    unittest.main()
