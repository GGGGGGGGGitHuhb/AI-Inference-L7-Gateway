import unittest
from Checks import response, receipts, truncated
from Fixture import payload, prefix, TAIL


class Detectors(unittest.TestCase):
    def test_response_content(self):
        response(200, payload('x', 'model-a'), 'x', 'model-a')
        for status, data in [(503, payload('x', 'model-a')), (200, payload('other', 'model-a')),
                             (200, payload('x', 'model-b'))]:
            with self.assertRaises(AssertionError):
                response(status, data, 'x', 'model-a')

    def test_stream_completion(self):
        response(200, prefix('x', 'model-a') + TAIL, 'x', 'model-a', True)
        with self.assertRaises(AssertionError):
            response(200, prefix('x', 'model-a'), 'x', 'model-a', True)

    def test_receipts(self):
        receipts([{'id': 'x'}], ['x'])
        for rows in [[], [{'id': 'x'}, {'id': 'x'}], [{'id': 'wrong'}]]:
            with self.assertRaises(AssertionError):
                receipts(rows, ['x'])

    def test_truncated_is_not_timeout_or_success(self):
        truncated(200, prefix('x', 'model-a'), 'x', 'model-a', True)
        for data, failed in [(prefix('x', 'model-a'), False), (prefix('x', 'model-a') + TAIL, True)]:
            with self.assertRaises(AssertionError):
                truncated(200, data, 'x', 'model-a', failed)


if __name__ == '__main__':
    unittest.main()
