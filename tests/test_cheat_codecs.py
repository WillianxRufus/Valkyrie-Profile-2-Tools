# SPDX-FileCopyrightText: 2026 Valkyrie Profile 2 Translation Tools contributors
# SPDX-License-Identifier: GPL-3.0-only
import struct
import unittest

from tools.cheat_patcher import sle, slz, slz3, slz12


class Slz3Tests(unittest.TestCase):
    def test_round_trips_literals_and_matches(self):
        samples = [
            b"",
            b"AB",
            bytes(range(64)) * 4,
            (b"ValkyrieProfile2!" * 40)[:680],
            b"\0" * 1024,
        ]
        for sample in samples:
            with self.subTest(size=len(sample)):
                encoded = slz3.compress(sample)
                self.assertEqual(sample, slz.decompress(encoded))

    def test_rejects_odd_input(self):
        with self.assertRaisesRegex(ValueError, "odd"):
            slz3.compress(b"odd")


class Slz12Tests(unittest.TestCase):
    def test_round_trips_modes_one_and_two(self):
        samples = [
            b"",
            bytes(range(64)) * 4,
            b"A" * 300 + b"VP2" * 100,
        ]
        for mode in (1, 2):
            for sample in samples:
                with self.subTest(mode=mode, size=len(sample)):
                    encoded = slz12.compress(sample, mode)
                    self.assertEqual(sample, slz.decompress(encoded))

    def test_rejects_other_modes(self):
        with self.assertRaisesRegex(ValueError, "modes 1 and 2"):
            slz12.compress(b"data", 3)


class SleTests(unittest.TestCase):
    def test_conceal_and_reveal_are_inverses(self):
        encoded = slz3.compress(b"ABCD" * 50, next_offset=0x1234)
        concealed = sle.conceal(encoded)
        self.assertEqual(b"SLE", concealed[:3])
        self.assertNotEqual(encoded[16:], concealed[16:])
        self.assertEqual(encoded, sle.reveal(concealed))

    def test_walks_a_chain(self):
        first_plain = bytearray(64)
        struct.pack_into("<I", first_plain, 8, 0x00100000)
        second_plain = bytearray(96)
        struct.pack_into("<I", second_plain, 8, 0x00200000)
        first_without_link = sle.conceal(slz3.compress(bytes(first_plain)))
        first = sle.conceal(
            slz3.compress(bytes(first_plain), next_offset=len(first_without_link))
        )
        second = sle.conceal(slz3.compress(bytes(second_plain)))
        decoded = list(sle.iter_streams(first + second))
        self.assertEqual(2, len(decoded))
        self.assertEqual(bytes(first_plain), decoded[0].output)
        self.assertEqual(len(first), decoded[1].offset)
        self.assertEqual(bytes(second_plain), decoded[1].output)


if __name__ == "__main__":
    unittest.main()
