"""Regression against the block permutation observed in the user's photo."""
import unittest

from make_pattern import coordinate, pixel


class MappingTest(unittest.TestCase):
    def test_photo_permutation(self):
        # Row-major 32x8 tiles, photographed upside down. This permutation is
        # unchanged by a 180-degree rotation of both source and destination.
        observed_to_original = [3, 1, 2, 0, 7, 5, 6, 4]
        visited = set()
        for lane in range(2):
            for row in range(8):
                for chip in range(8):
                    for channel in range(16):
                        serial = chip * 16 + channel
                        old_x = serial % 64
                        old_y = row + (8 if serial < 64 else 0) + 16 * lane
                        old_tile = (old_y // 8) * 2 + old_x // 32
                        physical_tile = observed_to_original.index(old_tile)
                        measured = ((physical_tile % 2) * 32 + old_x % 32,
                                    (physical_tile // 2) * 8 + old_y % 8)
                        self.assertEqual(coordinate(row, channel, chip, lane), measured)
                        visited.add(measured)
        self.assertEqual(visited, {(x, y) for y in range(32) for x in range(64)})

    def test_corner_markers(self):
        for x, y, color in ((5, 5, 1), (58, 5, 2), (5, 26, 4), (58, 26, 5)):
            self.assertEqual(pixel(x, y), color)


if __name__ == '__main__':
    unittest.main()
