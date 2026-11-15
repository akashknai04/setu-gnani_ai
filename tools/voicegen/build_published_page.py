"""Assemble the published single-file page: styles, markup, engine data, scenarios, recordings, scripts."""
import base64, json, sys
W, V = sys.argv[1], sys.argv[2]
R = "/home/claude/deliverysaathi/frontend/"
css = open(R + "phone.css", encoding="utf-8").read().replace("@media (min-width: 560px) {\n  body { padding: 24px 0; }", "@media (min-width: 560px) {\n  body { padding: 0; }") + open(W + "/stage.css", encoding="utf-8").read()
data = json.dumps(json.load(open(W + "/engine_data.json", encoding="utf-8")), ensure_ascii=False)
scen = json.dumps(json.load(open(R + "scenarios.json", encoding="utf-8")), ensure_ascii=False)
man = json.load(open(R + "voice/manifest.json", encoding="utf-8"))
clips = {f"{v['role']}|{v['lang']}|{v['text']}": "data:audio/mpeg;base64," + base64.b64encode(open(R + "voice/" + v["file"], "rb").read()).decode() for v in man.values()}
clips_js = json.dumps(clips, ensure_ascii=False)
js = [open(R + "sound.js", encoding="utf-8").read(), open(W + "/engine.js", encoding="utf-8").read(), open(W + "/app2.js", encoding="utf-8").read()]
for x in [data, scen, clips_js] + js: assert "</script" not in x.lower()
head = '''<title>DeliverySaathi Call</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,700;12..96,800&family=Hanken+Grotesk:wght@400;500;600;700&family=JetBrains+Mono:wght@500;600&family=Noto+Sans+Kannada:wght@400;600&family=Noto+Sans+Devanagari:wght@400;600&display=swap">
'''
out = (head + "<style>\n" + css + "\n</style>\n" + open(W + "/ui2_body.html", encoding="utf-8").read()
       + f"\n<script>\nconst DATA = {data};\nconst SCEN = {scen};\nconst CLIPS = {clips_js};\n</script>\n"
       + "".join(f"<script>\n{x}\n</script>\n" for x in js))
open(W + "/deliverysaathi-demo.html", "w", encoding="utf-8").write(out)
open(W + "/test_page.html", "w", encoding="utf-8").write('<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">' + out)
print(f"{len(out.encode())/1e6:.2f} MB, {len(clips)} clips")
