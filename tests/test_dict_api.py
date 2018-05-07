import unittest

import zproc


class TestStateDictMethods(unittest.TestCase):
    def setUp(self):
        ctx = zproc.Context()
        ctx.state.update({'foo': 'foo', 'bar': 'bar'})

        self.test1, self.test2 = ctx.state, {'foo': 'foo', 'bar': 'bar'}

    def test_update(self):
        self.test1.update({'zoo': 1, 'dog': 2})
        self.test2.update({'zoo': 1, 'dog': 2})

        self.assertEqual(self.test1, self.test2)

    def test__contains__(self):
        self.assertEqual('foo' in self.test1, 'foo' in self.test2)
        self.assertEqual('foo' not in self.test1, 'foo' not in self.test2)

    def test__delitem__(self):
        del self.test1['foo']
        del self.test2['foo']
        self.assertEqual(self.test1, self.test2)

    def test__eq__(self):
        self.assertEqual(self.test1 == {'bar': 'bar'}, self.test2 == {'bar': 'bar'})

    def test__format__(self):
        self.assertEqual(format(self.test1), format(self.test2))

    def test__getitem__(self):
        self.assertEqual(self.test1['bar'], self.test2['bar'])

    def test__iter__(self):
        for k1, k2 in zip(self.test1, self.test2):
            self.assertEqual(k1, k2)

    def test__len__(self):
        self.assertEqual(len(self.test1), len(self.test2))

    def test__ne__(self):
        self.assertEqual(self.test1 != {'bar': 'bar'}, self.test2 != {'bar': 'bar'})

    def test__setitem__(self):
        self.test1['foo'] = 2
        self.test2['foo'] = 2
        self.assertEqual(self.test1, self.test2)

    def test_clear(self):
        self.test1.clear()
        self.test2.clear()
        self.assertEqual(self.test1, self.test2)

    def test_copy(self):
        self.assertEqual(self.test1.copy(), self.test2.copy())

    def test_fromkeys(self):
        self.assertEqual(self.test1.fromkeys([1, 2, 3], 'foo'), self.test2.fromkeys([1, 2, 3], 'foo'))

    def test_get(self):
        self.assertEqual(self.test1.get('xxx', []), self.test2.get('xxx', []))
        self.assertEqual(self.test1.get('foo'), self.test2.get('foo'))

    def test_items(self):
        self.assertEqual(tuple(self.test1.items()), tuple(self.test2.items()))

    def test_values(self):
        self.assertEqual(tuple(self.test1.values()), tuple(self.test2.values()))

    def test_keys(self):
        self.assertEqual(tuple(self.test1.keys()), tuple(self.test2.keys()))

    def test_setdefault(self):
        self.test1.setdefault('zzz', None)
        self.test2.setdefault('zzz', None)
        self.assertEqual(self.test1, self.test2)

    def test_pop(self):
        self.assertEqual(self.test1.pop('foo'), self.test2.pop('foo'))
        self.assertEqual(self.test1, self.test2)

    def test_popitem(self):
        self.assertEqual(self.test1.popitem(), self.test2.popitem())
        self.assertEqual(self.test1, self.test2)


if __name__ == '__main__':
    unittest.main()
