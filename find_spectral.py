path = r"C:\Users\Nehar\Desktop\HELPS\Codes\landing_zone_engine.py"
text = open(path, "r", encoding="utf-8").read()

for line in text.splitlines():
    if "spectral" in line.lower() or "b2" in line.lower() or "b04" in line.lower() or "rgb" in line.lower():
        print(line[:120])
