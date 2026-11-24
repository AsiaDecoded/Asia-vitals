"""Print the layout of EIA's STEO monthly workbook (sheet names; table 3a rows and date header)."""
import sys
import openpyxl

wb = openpyxl.load_workbook(sys.argv[1], read_only=True, data_only=True)
print("SHEETS", wb.sheetnames)
for name in wb.sheetnames:
    if not name.lower().startswith("3a"):
        continue
    rows = list(wb[name].iter_rows(values_only=True))
    for i, r in enumerate(rows[:6]):
        print("HDR", i, [c for c in r[:4]], "...", [c for c in r[-3:]], "ncols", len(r))
    for i, r in enumerate(rows):
        lab = " | ".join(str(c) for c in r[:2] if c is not None)
        if lab:
            vals = [c for c in r[2:] if c is not None]
            print("ROW", i, lab[:90], "n", len(vals), "last", vals[-3:] if vals else None)
