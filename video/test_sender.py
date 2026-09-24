import binascii
import unittest
from PIL import Image
from send_image import pack_image, packet, parse_reply
from animate import demo_frames


class SenderTests(unittest.TestCase):
    def test_animation(self):
        images = demo_frames()
        self.assertEqual(len(images), 6)
        self.assertEqual(len({pack_image(image) for image in images}), 6)

    def test_mapping(self):
        image = Image.new('RGB', (64, 32))
        for y in range(32):
            for x in range(64):
                image.putpixel((x, y), (x, y, (x * 3 + y) & 255))
        payload = pack_image(image)
        visited = set()
        for y in range(32):
            for x in range(64):
                serial = 64*(x//32) + 32*(1-((y%16)//8)) + x%32
                address = ((y%8)*16 + serial%16)*8 + serial//16
                for color in range(3):
                    index = (3*(y//16)+color)*1024 + address
                    visited.add(index)
                    self.assertEqual(payload[index], image.getpixel((x,y))[color])
        self.assertEqual(len(visited), 6144)

    def test_packet(self):
        self.assertEqual(binascii.crc_hqx(b'123456789', 0xffff), 0x29b1)
        data = packet(1, 17, bytes(range(256))*24)
        self.assertEqual(len(data), 6150)
        self.assertEqual(binascii.crc_hqx(data[2:], 0xffff), 0)
        with self.assertRaises(ValueError):
            packet(1, 0, b'')

    def test_reply(self):
        raw = bytearray((0xa5,0x5a,1,0,7,1,0x12,0x34))
        check = 0
        for value in raw:
            check ^= value
        raw.append(check)
        self.assertTrue(parse_reply(raw)['ready'])
        self.assertEqual(parse_reply(raw)['last_crc'], 0x1234)
        raw[3] ^= 1
        with self.assertRaises(ValueError):
            parse_reply(raw)


if __name__ == '__main__':
    unittest.main()
