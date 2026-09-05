import sys
sys.path.insert(0, "src")
from collections import Counter
from pitchgraph.io.loader import StatsBomb
sb = StatsBomb()
e = sb.events(3869685)
ps = [x for x in e if x["type"]["name"] == "Pass"]
print("pass sub-keys:", Counter(k for x in ps for k in x["pass"]).most_common())
print()
print("pass.technique:", Counter(x["pass"].get("technique", {}).get("name") for x in ps).most_common())
print("pass.type     :", Counter(x["pass"].get("type", {}).get("name") for x in ps).most_common())
print("pass.height   :", Counter(x["pass"].get("height", {}).get("name") for x in ps).most_common())
print()
for flag in ("through_ball", "switch", "cross", "cut_back", "shot_assist"):
    print("  %-14s %d" % (flag, sum(1 for x in ps if x["pass"].get(flag))))
print()
print("offside-ish events:", Counter(x["type"]["name"] for x in e if "ffside" in str(x)).most_common(6))
print("dribble outcomes:", Counter(x.get("dribble",{}).get("outcome",{}).get("name") for x in e if x["type"]["name"]=="Dribble").most_common())
