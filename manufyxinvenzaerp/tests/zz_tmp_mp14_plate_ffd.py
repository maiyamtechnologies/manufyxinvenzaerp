"""READ-ONLY: how many 740.02 x 311 x 10 plates MP-2026-00014's PLATE10 cut list
actually needs, by a guillotine strip heuristic (upper bound) alongside the
provable lower bound. Temporary helper; rolls back."""
import math
import frappe
from frappe.utils import flt

MP = "MP-2026-00014"


def run():
    mp = frappe.get_doc("Material Planning", MP)
    BL, BW = 740.02, 311.0
    pieces = []
    for r in mp.material_mapping:
        if r.item_code != "PLATE10" or not r.batch:
            continue
        for _ in range(int(round(flt(r.sec_qty)))):
            pieces.append((flt(r.length), flt(r.width)))
    print("cut pieces: %d" % len(pieces))

    # Strip (shelf) packing: sort by width desc, open a shelf of that width across
    # the plate length; a new plate when the shelf heights exceed the plate width.
    # This is a heuristic UPPER bound: if it fits in 35, 35 plates can do the job.
    pieces_sorted = sorted(pieces, key=lambda p: (-max(p), -min(p)))
    plates = []  # each: list of shelves [shelf_height, used_length]
    for L, W in pieces_sorted:
        # orient long side along the plate length
        h, l = (W, L) if L >= W else (L, W)
        placed = False
        for shelves in plates:
            for sh in shelves:
                if sh[0] >= h - 1e-9 and sh[1] + l <= BL + 1e-9:
                    sh[1] += l
                    placed = True
                    break
            if placed:
                break
            used_h = sum(s[0] for s in shelves)
            if used_h + h <= BW + 1e-9:
                shelves.append([h, l])
                placed = True
                break
        if not placed:
            plates.append([[h, l]])
    print("shelf-packing UPPER bound: %d plates (bought 35)" % len(plates))

    area = sum(p[0] * p[1] for p in pieces)
    print("area lower bound: ceil(%.0f / %.0f) = %d plates" % (area, BL * BW, math.ceil(area / (BL * BW))))
    frappe.db.rollback()
