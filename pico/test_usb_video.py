import binascii
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from PIL import Image
from usb_video import pack_image, packet, prepare_image, load_frames, play_playlist


class VideoTests(unittest.TestCase):
    def test_playlist_wall_clock(self):
        class Clock:
            now = 0.0
            def read(self):
                return self.now
            def sleep(self, delay):
                self.now += delay
        timer = Clock()
        sent = []
        class FakeDisplay:
            def exchange(self, command, payload):
                sent.append((timer.now, payload))
                timer.now += 0.07
                return {'frames': len(sent)}
        # One frame has a delay longer than the slot: the switch must not wait for it.
        clips = [('a', [(None, b'a', 50)]), ('b', [(None, b'b', 0.04)])]
        with patch('builtins.print'):
            play_playlist(FakeDisplay(), clips, seconds=10, loops=2,
                          clock=timer.read, sleep=timer.sleep)
        transitions = [sent[0]]
        for current, previous in zip(sent[1:], sent):
            if current[1] != previous[1]:
                transitions.append(current)
        self.assertEqual([item[1] for item in transitions], [b'a', b'b', b'a', b'b'])
        for (actual, _), expected in zip(transitions, [0, 10, 20, 30]):
            self.assertLessEqual(abs(actual - expected), 0.071)
        self.assertLessEqual(timer.now, 40.071)

    def test_packet(self):
        self.assertEqual(binascii.crc_hqx(b'123456789', 0xffff), 0x29b1)
        raw = packet(1, 255, bytes(range(256)) * 24)
        self.assertEqual(len(raw), 6150)
        self.assertEqual(binascii.crc_hqx(raw[2:], 0xffff), 0)
        self.assertEqual(len(packet(2, 0)), 6)
        with self.assertRaises(ValueError):
            packet(1, 0, b'')

    def test_mapping(self):
        image = Image.new('RGB', (64, 32))
        for y in range(32):
            for x in range(64):
                image.putpixel((x, y), (x, y, (3*x+y) % 256))
        payload = pack_image(image)
        visited = set()
        for y in range(32):
            for x in range(64):
                serial = 64*(x//32) + 32*(1-((y%16)//8)) + x%32
                address = ((y%8)*16 + serial%16)*8 + serial//16
                for color in range(3):
                    index = (3*(y//16)+color)*1024 + address
                    visited.add(index)
                    self.assertEqual(payload[index], image.getpixel((x, y))[color])
        self.assertEqual(len(visited), 6144)

    def test_rotation_alpha(self):
        image = Image.new('RGBA', (32, 64), (12, 34, 56, 0))
        image.putpixel((0, 0), (255, 0, 0, 255))
        result = prepare_image(image, 90, 'exact')
        self.assertEqual(result.size, (64, 32))
        self.assertEqual(result.getpixel((63, 0)), (255, 0, 0))
        self.assertEqual(result.getpixel((0, 0)), (0, 0, 0))
        with self.assertRaises(ValueError):
            prepare_image(image, 0, 'exact')

    def test_gif_duration_and_disposal(self):
        a = Image.new('RGBA', (32, 64))
        b = a.copy()
        a.putpixel((1, 1), (255, 0, 0, 255))
        b.putpixel((2, 2), (0, 255, 0, 255))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'test.gif'
            a.save(path, save_all=True, append_images=[b], duration=[80, 120], disposal=2)
            frames = load_frames(path, 90, 'exact')
        self.assertEqual([f[2] for f in frames], [0.08, 0.12])
        self.assertEqual(frames[1][0].getpixel((62, 1)), (0, 0, 0))
        self.assertEqual(frames[1][0].getpixel((61, 2)), (0, 255, 0))


if __name__ == '__main__':
    unittest.main()
