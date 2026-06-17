"""Local web review UI — pick actions per file and apply them, in the browser.

`klean review` and `klean ui` print the terminal summary AND serve this page so
an image-heavy desktop can be triaged visually. You can change each file's
action, approve it, and run Apply / Undo right here — no terminal round-trip
required. Every UI action also prints its CLI equivalent to the terminal, so
the browser teaches you the command-line workflow as you go.

Pure stdlib (http.server) — no framework, no network access, binds to
localhost on an ephemeral port. The /thumb endpoint only serves image files
that resolve inside the scanned target directory.
"""

from __future__ import annotations

import json
import threading
import webbrowser
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import config
from .execute import apply_plan
from .model import Action, Plan
from .undo import undo_run

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"}

PAGE = """<!doctype html><html><head><meta charset=utf-8>
<title>Klean review</title>
<style>
 :root{color-scheme:dark light}
 body{font:14px/1.4 -apple-system,system-ui,sans-serif;margin:0;
   background:#11131a;color:#e6e8ee}
 header{position:sticky;top:0;background:#171a24;padding:14px 20px;
   border-bottom:1px solid #2a2f3d;display:flex;align-items:center;gap:14px;z-index:5}
 header h1{font-size:16px;margin:0;flex:0 0 auto}
 #stats{color:#9aa3b8;flex:1}
 button{background:#2b6cff;color:#fff;border:0;border-radius:7px;
   padding:8px 14px;font-size:13px;cursor:pointer}
 button.ghost{background:#222736;color:#cdd3e0}
 button:disabled{opacity:.45;cursor:default}
 #banner{display:none;padding:10px 20px;background:#143024;color:#a8e6c0;
   border-bottom:1px solid #1f5132}
 .group{margin:8px 20px}
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
 select,.dest input{background:#0e1017;border:1px solid #2a2f3d;color:#cdd3e0;
   border-radius:6px;padding:5px 7px;font-size:12px}
 .dest input{width:190px}
 .done{padding:40px;text-align:center;color:#9aa3b8}
</style></head><body>
<header>
 <h1>🧹 Klean</h1>
 <span id=stats>loading…</span>
 <button class=ghost onclick="save()">Save</button>
 <button id=applyBtn onclick="apply()">Apply approved</button>
 <button class=ghost id=undoBtn onclick="undo()">Undo</button>
</header>
<div id=banner></div>
<div id=app></div>
<script>
let PLAN=null;
const ICON={image:'🖼',video:'🎞',audio:'🎵',document:'📄',data:'📊',
  archive:'🗜',code:'💻',folder:'📁',other:'📄'};
const ACTS=['keep','trash','archive','move'];
const ACTLABEL={trash:'🗑 Trash',archive:'📦 Archive',move:'📁 Organize',keep:'Keep'};
const NOTE={trash:'to reversible quarantine',archive:'to external memory',
  move:'into a subfolder',keep:'left in place'};
function mb(b){return (b/1048576).toFixed(1)}
function banner(msg){const b=document.getElementById('banner');
  b.textContent=msg;b.style.display='block';}
async function load(){PLAN=await (await fetch('/api/plan')).json();render();}
function render(){
  const app=document.getElementById('app');app.innerHTML='';
  let approved=0,total=0,freed=0;
  for(const act of ['trash','archive','move','keep']){
    const items=PLAN.items.filter(i=>i.action===act);
    if(!items.length)continue;
    const g=document.createElement('div');g.className='group';
    const h=document.createElement('div');h.className='ghead';
    h.innerHTML=`<span>${ACTLABEL[act]}</span><span class=sub>${items.length} · ${NOTE[act]}</span>`;
    if(act!=='keep'){
      const all=document.createElement('button');all.className='ghost';all.textContent='approve all';
      all.onclick=()=>{items.forEach(i=>i.approved=true);render()};
      const none=document.createElement('button');none.className='ghost';none.textContent='none';
      none.onclick=()=>{items.forEach(i=>i.approved=false);render()};
      h.append(all,none);
    }
    g.append(h);
    for(const it of items){
      if(it.action!=='keep'){total++;if(it.approved)approved++;}
      if((act==='trash'||act==='archive')&&it.approved)freed+=it.file.size;
      g.append(rowEl(it));
    }
    app.append(g);
  }
  document.getElementById('stats').textContent=
    `${approved}/${total} approved · ${mb(freed)} MB leaves the Desktop when applied`;
}
function rowEl(it){
  const row=document.createElement('div');row.className='item'+(it.approved&&it.action!=='keep'?' on':'');
  const cb=document.createElement('input');cb.type='checkbox';cb.checked=it.approved;
  cb.disabled=it.action==='keep';
  cb.onchange=()=>{it.approved=cb.checked;render()};
  let thumbEl;
  if(it.file.ftype==='image'){const im=document.createElement('img');
    im.className='thumb';im.loading='lazy';
    im.src='/thumb?path='+encodeURIComponent(it.file.path);
    im.onerror=()=>{im.replaceWith(Object.assign(document.createElement('div'),
      {className:'thumb',textContent:ICON.image}))};thumbEl=im;}
  else{thumbEl=document.createElement('div');thumbEl.className='thumb';
    thumbEl.textContent=ICON[it.file.ftype]||ICON.other;}
  const meta=document.createElement('div');meta.className='meta';
  meta.innerHTML=`<div class=name>${esc(it.file.name)}</div>`+
    `<div class=reason>${esc(it.reason)}<span class="badge ${it.confidence[0].toUpperCase()}">${it.confidence}</span></div>`;
  const size=document.createElement('div');size.className='size';size.textContent=mb(it.file.size)+' MB';
  // action dropdown — change a file's fate inline
  const sel=document.createElement('select');
  for(const a of ACTS){const o=document.createElement('option');o.value=a;o.textContent=ACTLABEL[a];
    if(a===it.action)o.selected=true;sel.append(o);}
  sel.onchange=()=>{it.action=sel.value;
    if(it.action==='keep')it.approved=false;
    if((it.action==='move'||it.action==='archive')&&!it.dest)it.dest='';
    render();};
  row.append(cb,thumbEl,meta,size,sel);
  if(it.action==='archive'||it.action==='move'){
    const d=document.createElement('div');d.className='dest';
    const inp=document.createElement('input');inp.value=it.dest||'';
    inp.placeholder=it.action==='archive'?'archive destination':'subfolder';
    inp.onchange=()=>{it.dest=inp.value};d.append(inp);row.append(d);}
  return row;
}
function esc(s){const d=document.createElement('div');d.textContent=s;return d.innerHTML}
async function save(){
  await fetch('/api/plan',{method:'POST',headers:{'content-type':'application/json'},
    body:JSON.stringify(PLAN.items.map(i=>({path:i.file.path,action:i.action,
      approved:i.approved,dest:i.dest})))});
}
async function apply(){
  await save();
  if(!confirm('Apply all approved actions? Trashed files go to a reversible quarantine.'))return;
  const r=await (await fetch('/api/apply',{method:'POST'})).json();
  banner(`✓ Applied ${r.moved} action(s) · ${r.errors} error(s). Quarantine: ${r.quarantine}. Use Undo to reverse.`);
  document.getElementById('applyBtn').disabled=true;
}
async function undo(){
  const r=await (await fetch('/api/undo',{method:'POST'})).json();
  banner(`↩ Restored ${r.restored} item(s). Re-run \`klean scan\` for a fresh plan.`);
  document.getElementById('applyBtn').disabled=false;
}
load();
</script></body></html>"""


class _Handler(BaseHTTPRequestHandler):
    plan_path: Path
    target: Path
    run_dir: Path
    done: threading.Event

    def log_message(self, *args):
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
            p.relative_to(self.target.resolve())  # confinement check
            if p.suffix.lower() not in _IMAGE_EXTS or not p.is_file():
                raise ValueError
            self._send(200, p.read_bytes(), "application/octet-stream")
        except (ValueError, OSError):
            self._send(404, b"", "text/plain")

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/plan":
            length = int(self.headers.get("Content-Length", 0))
            self._apply_updates(json.loads(self.rfile.read(length)))
            print("  ≈ CLI: approvals saved — run `klean apply` to execute")
            self._send(200, b'{"ok":true}')
        elif path == "/api/apply":
            print("  ≈ CLI: klean apply")
            result = apply_plan(Plan.load(self.plan_path), self.run_dir)
            print(f"    moved {result['moved']}, errors {result['errors']}")
            self._send(200, json.dumps(result).encode())
        elif path == "/api/undo":
            print("  ≈ CLI: klean undo")
            result = undo_run(self.run_dir)
            print(f"    restored {result['restored']}")
            self._send(200, json.dumps(result).encode())
        else:
            self._send(404, b"not found", "text/plain")

    def _apply_updates(self, updates: list[dict]):
        plan = Plan.load(self.plan_path)
        by_path = {u["path"]: u for u in updates}
        for it in plan.items:
            u = by_path.get(it.file.path)
            if u is None:
                continue
            it.action = Action(u.get("action", it.action.value))
            it.approved = bool(u.get("approved"))
            it.dest = u.get("dest") or None
            # Fill a sensible default destination if the user picked
            # move/archive but left the box empty.
            if it.action == Action.ARCHIVE and not it.dest:
                it.dest = str(config.DEFAULT_ARCHIVE_DIR)
            elif it.action == Action.MOVE and not it.dest:
                it.dest = str(self.target / "Organized")
            elif it.action in (Action.MOVE, Action.ARCHIVE):
                # Relative subfolder → resolve under the target.
                d = Path(it.dest).expanduser()
                it.dest = str(d if d.is_absolute() else self.target / it.dest)
        plan.reviewed = True
        plan.save(self.plan_path)


def serve(plan_path: Path, target: Path, run_dir: Path,
          open_browser: bool = True) -> None:
    """Serve the review/apply UI and block until the user presses Ctrl-C."""
    done = threading.Event()
    _Handler.plan_path = plan_path
    _Handler.target = target
    _Handler.run_dir = run_dir
    _Handler.done = done

    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(_Handler))
    port = server.server_address[1]
    url = f"http://127.0.0.1:{port}/"
    threading.Thread(target=server.serve_forever, daemon=True).start()

    print(f"\n  Review UI:  {url}")
    print("  Pick actions, approve, then click Apply (or Undo) — right in the browser.")
    print("  Equivalent CLI workflow:")
    print("      klean review     # approve in the terminal instead")
    print("      klean apply      # execute approved actions")
    print("      klean undo       # reverse the last apply")
    print("  Press Ctrl-C here when you're done.\n")
    if open_browser:
        webbrowser.open(url)

    try:
        done.wait()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
    print("  Review session ended.")
