"""Local web review UI — a thumbnail-driven companion to the terminal review.

`klean review` always prints the terminal summary; by default it also serves
this page so image-heavy desktops can be triaged visually. Both surfaces read
and write the same plan.json, so you can approve in whichever you prefer.

Pure stdlib (http.server) — no framework, no network access, binds to
localhost on an ephemeral port. The /thumb endpoint only ever serves files that
resolve inside the scanned target directory.
"""

from __future__ import annotations

import json
import threading
import webbrowser
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .model import Action, Plan

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"}

PAGE = """<!doctype html><html><head><meta charset=utf-8>
<title>Klean review</title>
<style>
 :root{color-scheme:dark light}
 body{font:14px/1.4 -apple-system,system-ui,sans-serif;margin:0;
   background:#11131a;color:#e6e8ee}
 header{position:sticky;top:0;background:#171a24;padding:14px 20px;
   border-bottom:1px solid #2a2f3d;display:flex;align-items:center;gap:16px;z-index:5}
 header h1{font-size:16px;margin:0;flex:0 0 auto}
 #stats{color:#9aa3b8;flex:1}
 button{background:#2b6cff;color:#fff;border:0;border-radius:7px;
   padding:8px 14px;font-size:13px;cursor:pointer}
 button.ghost{background:#222736;color:#cdd3e0}
 .group{margin:18px 20px}
 .ghead{display:flex;align-items:center;gap:12px;margin:18px 0 8px;
   font-weight:600;font-size:15px}
 .ghead .sub{font-weight:400;color:#9aa3b8}
 .ghead button{padding:4px 10px;font-size:12px}
 .item{display:flex;align-items:center;gap:12px;padding:8px 10px;
   border:1px solid #232838;border-radius:9px;margin:6px 0;background:#161a24}
 .item.on{border-color:#2b6cff;background:#172037}
 .item input[type=checkbox]{width:18px;height:18px;flex:0 0 auto}
 .thumb{width:54px;height:54px;border-radius:6px;object-fit:cover;
   background:#222736;flex:0 0 auto;display:flex;align-items:center;
   justify-content:center;font-size:22px;color:#7d8699}
 .meta{flex:1;min-width:0}
 .name{font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
 .reason{color:#9aa3b8;font-size:12px}
 .badge{font-size:10px;padding:1px 6px;border-radius:5px;background:#33384a;
   margin-left:6px;text-transform:uppercase}
 .H{background:#1f5132}.M{background:#5a4a16}.L{background:#3a3f52}
 .size{color:#cdd3e0;font-variant-numeric:tabular-nums;flex:0 0 auto}
 .dest{flex:0 0 auto}
 .dest input{background:#0e1017;border:1px solid #2a2f3d;color:#cdd3e0;
   border-radius:6px;padding:5px 8px;width:200px;font-size:12px}
 .done{padding:40px;text-align:center;color:#9aa3b8}
</style></head><body>
<header>
 <h1>🧹 Klean</h1>
 <span id=stats>loading…</span>
 <button class=ghost onclick="save(false)">Save</button>
 <button onclick="save(true)">Approve &amp; close</button>
</header>
<div id=app></div>
<script>
let PLAN=null;
const ICON={image:'🖼',video:'🎞',audio:'🎵',document:'📄',data:'📊',
  archive:'🗜',code:'💻',folder:'📁',other:'📄'};
const ACT=[['trash','🗑 Trash','to reversible quarantine'],
  ['archive','📦 Archive','to external memory'],
  ['move','📁 Organize','into a subfolder']];
function mb(b){return (b/1048576).toFixed(1)}
async function load(){
  PLAN=await (await fetch('/api/plan')).json();
  render();
}
function render(){
  const app=document.getElementById('app');app.innerHTML='';
  let approved=0,total=0,freed=0;
  for(const [act,label,note] of ACT){
    const items=PLAN.items.filter(i=>i.action===act);
    if(!items.length)continue;
    const g=document.createElement('div');g.className='group';
    const h=document.createElement('div');h.className='ghead';
    h.innerHTML=`<span>${label}</span><span class=sub>${items.length} · ${note}</span>`;
    const all=document.createElement('button');all.className='ghost';all.textContent='approve all';
    all.onclick=()=>{items.forEach(i=>i.approved=true);render()};
    const none=document.createElement('button');none.className='ghost';none.textContent='none';
    none.onclick=()=>{items.forEach(i=>i.approved=false);render()};
    h.append(all,none);g.append(h);
    for(const it of items){
      total++;if(it.approved)approved++;
      freed+=(act!=='move'&&it.approved)?it.file.size:0;
      const row=document.createElement('div');row.className='item'+(it.approved?' on':'');
      const cb=document.createElement('input');cb.type='checkbox';cb.checked=it.approved;
      cb.onchange=()=>{it.approved=cb.checked;render()};
      const th=document.createElement('div');th.className='thumb';
      if(it.file.ftype==='image'){const im=document.createElement('img');
        im.className='thumb';im.loading='lazy';
        im.src='/thumb?path='+encodeURIComponent(it.file.path);
        im.onerror=()=>{im.replaceWith(Object.assign(document.createElement('div'),
          {className:'thumb',textContent:ICON.image}))};
        th.replaceWith(im);var thumbEl=im;}
      else{th.textContent=ICON[it.file.ftype]||ICON.other;var thumbEl=th;}
      const meta=document.createElement('div');meta.className='meta';
      meta.innerHTML=`<div class=name>${esc(it.file.name)}</div>`+
        `<div class=reason>${esc(it.reason)}<span class="badge ${it.confidence[0].toUpperCase()}">${it.confidence}</span></div>`;
      const size=document.createElement('div');size.className='size';size.textContent=mb(it.file.size)+' MB';
      row.append(cb,thumbEl,meta,size);
      if(act==='archive'){const d=document.createElement('div');d.className='dest';
        const inp=document.createElement('input');inp.value=it.dest||'';
        inp.title='archive destination';inp.onchange=()=>{it.dest=inp.value};
        d.append(inp);row.append(d);}
      g.append(row);
    }
    app.append(g);
  }
  document.getElementById('stats').textContent=
    `${approved}/${total} approved · ${mb(freed)} MB leaves the Desktop when applied`;
}
function esc(s){const d=document.createElement('div');d.textContent=s;return d.innerHTML}
async function save(close){
  await fetch('/api/plan',{method:'POST',headers:{'content-type':'application/json'},
    body:JSON.stringify(PLAN.items.map(i=>({path:i.file.path,approved:i.approved,dest:i.dest})))});
  if(close){await fetch('/api/done',{method:'POST'});
    document.body.innerHTML='<div class=done><h2>Saved ✓</h2>'+
      '<p>You can close this tab. Run <b>klean apply</b> in your terminal to execute.</p></div>';}
  else{render();}
}
load();
</script></body></html>"""


class _Handler(BaseHTTPRequestHandler):
    plan_path: Path
    target: Path
    done: threading.Event

    def log_message(self, *args):  # silence stdout noise
        pass

    def _send(self, code, body, ctype="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send(200, PAGE.encode(), "text/html; charset=utf-8")
        elif parsed.path == "/api/plan":
            self._send(200, self.plan_path.read_bytes())
        elif parsed.path == "/thumb":
            self._serve_thumb(parse_qs(parsed.query).get("path", [""])[0])
        elif parsed.path == "/favicon.ico":
            self._send(204, b"")
        else:
            self._send(404, b"not found", "text/plain")

    def _serve_thumb(self, raw_path: str):
        try:
            p = Path(raw_path).resolve()
            # Confinement: only serve images inside the scanned directory.
            p.relative_to(self.target.resolve())
            if p.suffix.lower() not in _IMAGE_EXTS or not p.is_file():
                raise ValueError
            self._send(200, p.read_bytes(), "application/octet-stream")
        except (ValueError, OSError):
            self._send(404, b"", "text/plain")

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/done":
            self._send(200, b'{"ok":true}')
            self.done.set()
            return
        if parsed.path == "/api/plan":
            length = int(self.headers.get("Content-Length", 0))
            updates = json.loads(self.rfile.read(length))
            self._apply_updates(updates)
            self._send(200, b'{"ok":true}')
            return
        self._send(404, b"not found", "text/plain")

    def _apply_updates(self, updates: list[dict]):
        plan = Plan.load(self.plan_path)
        by_path = {u["path"]: u for u in updates}
        for it in plan.items:
            u = by_path.get(it.file.path)
            if u is None:
                continue
            it.approved = bool(u.get("approved"))
            if u.get("dest"):
                it.dest = u["dest"]
        plan.reviewed = True
        plan.save(self.plan_path)


def serve(plan_path: Path, target: Path, open_browser: bool = True) -> None:
    """Serve the review page and block until the user clicks 'Approve & close'.

    Approvals are persisted to plan_path on every Save, so closing the browser
    early is safe — whatever was saved last stands.
    """
    done = threading.Event()
    handler = partial(_Handler)
    _Handler.plan_path = plan_path
    _Handler.target = target
    _Handler.done = done

    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = server.server_address[1]
    url = f"http://127.0.0.1:{port}/"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    print(f"\n  Review UI:  {url}")
    print("  Approve there (or in the terminal), then run `klean apply`.")
    print("  Press Ctrl-C here when you're done.\n")
    if open_browser:
        webbrowser.open(url)

    try:
        done.wait()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
    print("  Review saved.")
