from pathlib import Path

text = Path(r"D:/Users/clfbe/anaconda3/envs/cl/lib/site-packages/citylearn/data.py").read_text(encoding="utf-8")
i = text.find("Temperature Set Point")
print("CSV mapping context:")
print(text[i - 300 : i + 600])

text2 = Path(r"D:/Users/clfbe/anaconda3/envs/cl/lib/site-packages/citylearn/building.py").read_text(encoding="utf-8")
# Find how generic set_point observation is produced
needle = "indoor_dry_bulb_temperature_set_point"
positions = []
start = 0
while True:
    j = text2.find(needle, start)
    if j < 0:
        break
    positions.append(j)
    start = j + 1
print("\noccurrences in building.py", len(positions))
for j in positions:
    ctx = text2[j - 120 : j + 200]
    if any(k in ctx for k in ("observation", "data[", "hvac_mode", "return", "cooling", "heating")):
        print("----", j)
        print(ctx)
