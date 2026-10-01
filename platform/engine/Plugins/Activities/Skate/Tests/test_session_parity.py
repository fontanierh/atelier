"""Ensure the migration comparator cannot silently hide behavioral changes."""
import math
import struct
import unittest
from session_parity import first_difference


class ComparatorTests(unittest.TestCase):
    def test_reports_first_changed_bone_and_single_float_bit(self):
        one = 1.0
        next_float = struct.unpack('<f',struct.pack('<I',0x3f800001))[0]
        difference = first_difference({'bones':[[one,one]]}, {'bones':[[one,next_float]]})
        self.assertEqual(difference['path'], '$.bones[0][1]')
        self.assertEqual(difference['actual_bits'], '3f800001')

    def test_preserves_zero_sign_and_rejects_nonfinite_values(self):
        self.assertIsNotNone(first_difference(0.0,-0.0))
        self.assertIsNotNone(first_difference(math.nan,math.nan))
        self.assertIsNotNone(first_difference(math.inf,math.inf))

    def test_missing_extra_fields_and_truncated_bones_fail(self):
        for actual in ({}, {'state':'Ground','ignored':0}, {'state':'Air'}):
            self.assertIsNotNone(first_difference({'state':'Ground'},actual))
        self.assertIsNotNone(first_difference([1.,2.],[1.]))

    def test_integer_ticks_are_not_rounded_to_float(self):
        self.assertIsNotNone(first_difference(2**54,2**54+1))
        self.assertIsNotNone(first_difference(1,True))

    def test_same_native_float_serialized_with_more_decimal_digits_matches(self):
        self.assertIsNone(first_difference(0.10000000149011612,0.1))
        self.assertIsNone(first_difference({'score':0.0,'tick':12}, {'score':0,'tick':12}))


if __name__ == '__main__':
    unittest.main()
