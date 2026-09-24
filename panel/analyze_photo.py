"""Measure LED centers and compare photographed tiles with the fixed target.

Read-only with respect to the photo, FPGA, and generated display ROM.
"""
import argparse
import itertools
import json
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage
from scipy.optimize import linear_sum_assignment
from make_pattern import pixel


def homography(grid, points):
    rows, values = [], []
    for (c, r), (x, y) in zip(grid, points):
        rows.extend(([c, r, 1, 0, 0, 0, -c*x, -r*x],
                     [0, 0, 0, c, r, 1, -c*y, -r*y]))
        values.extend((x, y))
    h = np.linalg.lstsq(rows, values, rcond=None)[0]
    return np.append(h, 1).reshape(3, 3)


def project(h, points):
    p = np.column_stack((points, np.ones(len(points)))) @ h.T
    return p[:, :2] / p[:, 2:]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('photo', type=Path)
    args = ap.parse_args()
    rgb = np.asarray(Image.open(args.photo).convert('RGB'), dtype=float)
    labels, n = ndimage.label(rgb.max(axis=2) > 150)
    centers, colors = [], []
    for i, region in enumerate(ndimage.find_objects(labels), start=1):
        if region is None:
            continue
        mask = labels[region] == i
        if not 3 <= mask.sum() <= 140:
            continue
        yy, xx = np.nonzero(mask)
        centers.append((xx.mean() + region[1].start, yy.mean() + region[0].start))
        colors.append(rgb[region][mask].mean(axis=0))
    centers, colors = np.array(centers), np.array(colors)
    grid_corners = np.array([[0,0],[63,0],[63,31],[0,31]])
    h = homography(grid_corners, np.array([[6,4],[1041,16],[1015,482],[41,519]]))
    for _ in range(8):
        q = project(np.linalg.inv(h), centers)
        rounded = np.rint(q)
        keep = ((rounded >= 0) & (rounded <= [63,31])).all(axis=1)
        keep &= np.linalg.norm(q-rounded,axis=1) < 0.45
        h = homography(rounded[keep], centers[keep])
    q = project(np.linalg.inv(h), centers)
    rounded = np.rint(q).astype(int)
    keep = ((rounded >= 0) & (rounded <= [63,31])).all(axis=1)
    keep &= np.linalg.norm(q-rounded,axis=1) < 0.45
    observed = np.zeros((32,64),dtype=int)
    for (c,r), color in zip(rounded[keep], colors[keep]):
        red, green, blue = color
        if blue < 0.55*max(red,green):
            value = 3 if min(red,green) > 0.6*max(red,green) else (1 if red>green else 2)
        elif red < 0.55*max(green,blue):
            value = 4 if blue > green*0.85 else 2
        elif green < 0.75*min(red,blue):
            value = 5
        else:
            value = 7
        observed[r,c] = value
    expected = np.array([[pixel(63-x,31-y) for x in range(64)] for y in range(32)])
    print('LED centers fitted:',int(keep.sum()),'of',len(centers))
    print('Fitted corners:',project(h,grid_corners).round(2).tolist())
    for color in (1,2,4,5):
        y,x=np.where(observed==color)
        print('Marker',color,'pixels',len(x),'bounds',
              (int(x.min()),int(y.min()),int(x.max()),int(y.max())) if len(x) else None)
    # Match all eight 32x8 tiles, including +/- one-pixel phase for diagnosis.
    best = None
    for dx,dy in itertools.product(range(-2,3),repeat=2):
        shifted=np.roll(observed,(dy,dx),axis=(0,1))
        tiles=[shifted[y:y+8,x:x+32] for y in range(0,32,8) for x in (0,32)]
        refs=[expected[y:y+8,x:x+32] for y in range(0,32,8) for x in (0,32)]
        costs=np.array([[np.count_nonzero(a!=b) for b in refs] for a in tiles])
        a,b=linear_sum_assignment(costs)
        score=int(costs[a,b].sum())
        if best is None or score<best['mismatches']:
            best={'mismatches':score,'shift':[dx,dy],
                  'observed_tile_to_expected_tile':b.tolist(),
                  'tile_mismatches':costs[a,b].tolist()}
    print('Best tile match:',json.dumps(best))
    out=Path(__file__).parent/'photo-analysis.json'
    out.write_text(json.dumps({'photo':str(args.photo),'fit':h.tolist(),
                             'match':best,'observed':observed.tolist()},indent=2),encoding='utf-8')


if __name__=='__main__':
    main()
