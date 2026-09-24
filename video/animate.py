"""Play six numbered SRAM frames, measure acknowledged frame rate, then stop."""
import argparse
import json
import statistics
import time
import itertools
from collections import deque
from PIL import Image, ImageDraw
from send_image import ROOT, Display, pack_image, packet


def demo_frames():
    digits = ('010110010010111', '110001010100111', '110001010001110',
              '101101111001001', '111100110001110', '011100111101111')
    colors = ((255,0,0),(0,255,0),(0,0,255),(255,255,0),(255,0,255),(0,255,255))
    images = []
    for index in range(6):
        image = Image.new('RGB', (64,32))
        draw = ImageDraw.Draw(image)
        draw.rectangle((0,0,63,31), outline=(0,255,255))
        draw.text((5,3), 'SRAM', fill=(255,255,255))
        for bit, value in enumerate(digits[index]):
            if value == '1':
                x,y = 53+(bit%3)*2, 3+(bit//3)*2
                draw.rectangle((x,y,x+1,y+1), fill=(255,255,255))
        draw.line((4,27,59,27), fill=(70,70,70))
        x=4+index*10
        draw.rectangle((x,18,x+5,25), fill=colors[index])
        images.append(image)
    return images


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--port', default='COM18')
    ap.add_argument('--cycles', type=int, default=3)
    ap.add_argument('--hold', type=float, default=0, help='Extra seconds after each ACK')
    ap.add_argument('--preview-only', action='store_true')
    ap.add_argument('--loop', action='store_true', help='Repeat until animation.stop exists')
    args = ap.parse_args()
    if not 1 <= args.cycles <= 1000 or not 0 <= args.hold <= 60:
        ap.error('Use 1..1000 cycles and 0..60 hold seconds')
    images = demo_frames()
    payloads = [pack_image(image) for image in images]
    sheet = Image.new('RGB', (64*3,32*2))
    for index,image in enumerate(images):
        image.save(ROOT / f'animation-{index+1}.png')
        sheet.paste(image, ((index%3)*64,(index//3)*32))
    sheet.resize((1152,384), Image.Resampling.NEAREST).save(ROOT / 'animation-preview.png')
    if args.preview_only:
        return
    display = Display(args.port)
    records = deque(maxlen=120)
    count = 0
    total_send = total_ack = 0
    fastest, slowest = float('inf'), 0
    stop_file = ROOT / 'animation.stop'
    if args.loop and stop_file.exists():
        display.close()
        raise RuntimeError('animation.stop exists; use start_animation.ps1 for a fresh run')
    last_image = None
    try:
        state = display.wait_ready()
        sequence, bank = state['last_sequence'], state['bank']
        beginning = time.perf_counter()
        cycles = itertools.count() if args.loop else range(args.cycles)
        for cycle in cycles:
            for index,payload in enumerate(payloads):
                if args.loop and stop_file.exists():
                    break
                sequence = (sequence+1)&255
                data = packet(1, sequence, payload)
                started = time.perf_counter()
                display.send_raw(data)
                sent = time.perf_counter()
                reply = display.receive(sequence)
                ended = time.perf_counter()
                if (reply['status'] or not reply['ready'] or reply['sram_error'] or
                    reply['last_sequence'] != sequence or reply['bank'] == bank or
                    reply['last_crc'] != int.from_bytes(data[-2:], 'big')):
                    raise RuntimeError(f'Frame {index+1} failed: {reply}')
                bank = reply['bank']
                last_image = images[index]
                records.append(dict(cycle=cycle+1,frame=index+1,sequence=sequence,
                                    send_seconds=sent-started,ack_seconds=ended-sent,
                                    total_seconds=ended-started,bank=bank,crc=reply['last_crc']))
                count += 1
                total_send += sent-started
                total_ack += ended-sent
                fastest,slowest = min(fastest,ended-started),max(slowest,ended-started)
                if not args.loop:
                    print(f"Frame {index+1}, cycle {cycle+1}: {ended-started:.3f}s, ACK OK", flush=True)
                if args.hold:
                    time.sleep(args.hold)
            if args.loop:
                progress = dict(running=not stop_file.exists(),frames=count,cycles=cycle+1,
                                fps=count/(time.perf_counter()-beginning),sequence=sequence,
                                bank=bank,last_frame=records[-1]['frame'] if records else None)
                # Atomic replacement lets the launcher read complete status snapshots.
                temp = ROOT / 'animation-live.tmp'
                temp.write_text(json.dumps(progress,indent=2),encoding='ascii')
                temp.replace(ROOT/'animation-live.json')
                if stop_file.exists():
                    break
        elapsed = time.perf_counter()-beginning
        result = dict(frames=count,cycles=cycle+1,hold_seconds=args.hold,
                      wall_seconds=elapsed,fps=count/elapsed,
                      mean_send_seconds=total_send/count if count else 0,
                      mean_ack_seconds=total_ack/count if count else 0,
                      min_frame_seconds=fastest if count else 0,max_frame_seconds=slowest,
                      all_acknowledged=True,records=list(records))
        filename = 'video-animation-loop.json' if args.loop else 'video-animation.json'
        (ROOT.parent/'logs'/filename).write_text(json.dumps(result,indent=2),encoding='ascii')
        print(json.dumps({k:v for k,v in result.items() if k != 'records'},indent=2))
    finally:
        display.close()
        if args.loop:
            (ROOT/'animation-live.json').write_text(json.dumps(dict(running=False,frames=count)),encoding='ascii')
        if last_image is not None:
            last_image.save(ROOT/'last-sent.png')
            last_image.resize((768,384),Image.Resampling.NEAREST).save(ROOT/'last-sent-preview.png')


if __name__ == '__main__':
    main()
