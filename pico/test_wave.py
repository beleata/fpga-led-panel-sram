import unittest
from generate_wave import make_waves,CONFIG,CLOCK,LAT,OE


class WaveTests(unittest.TestCase):
    def test_pins_and_clock(self):
        waves,plan=make_waves()
        for name,wave in waves.items():
            self.assertTrue(all(0 <= value < 4096 for value in wave))
            if name=='gap':
                self.assertEqual(wave,[0]*625)
                continue
            for lo,hi in zip(wave[::2],wave[1::2]):
                self.assertEqual(lo&CLOCK,0)
                self.assertEqual(hi,lo|CLOCK)
        self.assertLess(sum(2*len(w) for w in waves.values())+16*len(plan),200000)

    def test_config(self):
        waves,_=make_waves()
        for index,config in enumerate(CONFIG):
            low=waves[f'init_{index}'][::2]
            self.assertEqual(len(low),707)
            for i,word in enumerate((0x00aa,0x01aa,config,0x0055,0x0155)):
                block=low[55+i*128:55+(i+1)*128]
                for chip in range(8):
                    value=0
                    for mask in block[chip*16:(chip+1)*16]:
                        self.assertIn(mask&63,(0,63))
                        value=(value<<1)|(mask&1)
                    self.assertEqual(value,word)
                self.assertEqual(sum(bool(mask&LAT) for mask in block),5)
            self.assertTrue(all(x==OE for x in low[-12:]))

    def test_scan(self):
        waves,plan=make_waves()
        low=waves['hold'][::2]
        for count,mask in enumerate(low):
            self.assertEqual((mask>>6)&7,((count+16)//128)%8)
            self.assertEqual(bool(mask&OE),100 <= count%128 < 104)
            self.assertEqual(mask & (LAT|63),0)
        self.assertEqual(plan.count('visible'),2)
        self.assertEqual(plan.count('blank'),22*16)
        self.assertEqual(plan.count('gap'),23)
        self.assertEqual(plan[-1],'hold')


if __name__=='__main__':
    unittest.main()
