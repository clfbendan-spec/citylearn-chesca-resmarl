from pathlib import Path
import re

text = Path(r"D:/Users/clfbe/anaconda3/envs/cl/lib/site-packages/citylearn/building.py").read_text(encoding="utf-8")

# Find observation construction around temperature set point
patterns = [
    r"indoor_dry_bulb_temperature_set_point['\"]\s*:",
    r"\['indoor_dry_bulb_temperature_set_point'\]",
    r"indoor_dry_bulb_temperature_set_point\]",
]
for pat in patterns:
    for m in re.finditer(pat, text):
        i = m.start()
        print("=" * 40, pat)
        print(text[max(0, i - 100) : i + 250])

# Also search energy_simulation for cooling vs heating columns loading
text2 = Path(r"D:/Users/clfbe/anaconda3/envs/cl/lib/site-packages/citylearn/data.py").read_text(encoding="utf-8")
for m in re.finditer(r"Temperature Set Point|cooling_set_point|heating_set_point", text2):
    i = m.start()
    print("-" * 20, m.group(0))
    print(text2[max(0, i - 80) : i + 200])
