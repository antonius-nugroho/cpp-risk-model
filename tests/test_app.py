"""End-to-end smoke test of the Streamlit app (bundled data, 2,000 iterations).

Run:  python tests/test_app.py
"""
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")  # page text includes symbols such as ⋮ and →
from streamlit.testing.v1 import AppTest
at = AppTest.from_file("../streamlit_app.py", default_timeout=600)
at.run()
print("start exc:", at.exception)
dl=at.get("download_button"); print("template buttons:", len(dl))
from app_lib.templates import TEMPLATES
print("templates build:", all(len(make()) > 5000 for _, make in TEMPLATES.values()))
btn=[b for b in at.button if b.label=="Muat data Tarahan bawaan"][0]; btn.click().run()
print("data exc:", at.exception, [e.value for e in at.error], [w.value for w in at.warning][:3])
print("captions:", [c.value for c in at.caption][-2:])
at.switch_page("app_pages/2_build.py").run()
print("build exc:", at.exception)
[b for b in at.button if b.label=="Kalibrasi model"][0].click().run()
print("calib exc:", at.exception, [e.value for e in at.error])
at.select_slider(key="w_n").set_value(2000).run()
t=time.time(); [b for b in at.button if b.label=="Jalankan simulasi"][0].click().run(); print("sim s", round(time.time()-t))
print("run exc:", at.exception, [s.value for s in at.success])
for pg in ["3_validation","4_dashboard","5_resume"]:
    at.switch_page(f"app_pages/{pg}.py").run()
    print(pg, "exc:", at.exception, [e.value for e in at.error], len(at.markdown))
b=[b for b in at.button if b.label=="Siapkan laporan Excel"][0]; b.click().run(); print("excel exc:", at.exception)

# language check: collect visible text on every page and flag common English words
import re
EN = re.compile(r"\b(the|and|of|chance|events?|outage hours|Plan|Run|Download|Upload|Model resume|Build model|"
                r"forced|planned|maintenance|expected|Mean|Target|Scenario|Unit-years|coverage)\b")
def texts(a):
    out = []
    for kind in ["title", "header", "subheader", "markdown", "caption", "info", "warning", "error", "success", "button", "tabs"]:
        for el in getattr(a, kind, []):
            v = getattr(el, "value", None) or getattr(el, "label", None) or ""
            out.append(str(v))
    return out
for pg in ["1_data", "2_build", "3_validation", "4_dashboard", "5_resume"]:
    at.switch_page(f"app_pages/{pg}.py").run()
    hits = sorted({m.group(0) for s in texts(at) for m in EN.finditer(s)})
    print(pg, "english-looking words:", hits)
