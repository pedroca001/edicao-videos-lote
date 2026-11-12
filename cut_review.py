"""Ephemeral loopback review of source gestures and the proposed visual timeline."""
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import secrets
import subprocess
import tempfile
import webbrowser

from motion_planner import plan_from_review, candidate_review


def plan_digest(plan):
    return hashlib.sha256(json.dumps(plan,sort_keys=True).encode()).hexdigest()


def validate_final_review(analysis,target,review):
    plan=plan_from_review(analysis,target,review)
    if plan['missing_frames']:
        raise ValueError(f'Faltam {plan["missing_seconds"]:.2f}s removiveis. Revisar pausas, mexidas repetitivas ou aceleracao seletiva. Nenhum corte em gesto sera forcado.')
    if review.get('plan_sha256') != plan_digest(plan) or review.get('endpoints_reviewed') is not True:
        raise ValueError('Confira a timeline proposta e suas emendas antes de renderizar. Revisao final ausente ou plano alterado.')
    return plan


HTML = '''<!doctype html><meta charset="utf-8"><title>Revisar cortes por movimento</title>
<style>body{font:16px system-ui;background:#f8f9fa;color:#161616;max-width:1100px;margin:24px auto;padding:12px}video{height:370px;background:#111}button,input,select{font:inherit;padding:7px}table{width:100%;font-size:13px}td{padding:4px}input[type=number]{width:75px}.note{width:170px}#status{white-space:pre-wrap;background:#e8f4ef;padding:14px}button{cursor:pointer;margin:6px}</style>
<h1>Preservar gestos, retirar esperas</h1><p id="name"></p>
<p>Confira a fonte, incluindo o interior de cada trecho. Uma mão segurando produto ou um fio de mel parado não é repouso descartável. As sugestões de movimento abaixo ainda não foram aprovadas.</p>
<video id="source" controls src="/source?TOKEN"></video> <video id="preview" controls hidden></video>
<p>Marque somente intervalos conferidos. Tempos em segundos; mantenha as adições completas. Proteja ao menos o primeiro segundo e os últimos 1,5s. Use “repetição” somente para ciclos de mexer com começo/fim compatíveis. Aceleração seletiva: até 1,15x nesta interface.</p>
<table><thead><tr><th>Usar</th><th>Início</th><th>Fim</th><th>Tipo</th><th>Ação</th><th>Motivo</th><th></th></tr></thead><tbody id="rows"></tbody></table>
<button onclick="add()">Adicionar intervalo</button><button onclick="propose()">Verificar duração e gerar prévia</button>
<p id="status">Aguardando revisão da fonte.</p>
<label><input id="endpoints" type="checkbox"> Assisti à prévia e às emendas: ingredientes, mãos e apresentação permanecem coerentes.</label><br>
<button id="approve" disabled onclick="finish()">Usar estes cortes</button><button onclick="cancel()">Cancelar</button>
<script>
const initial=INITIAL; const token='TOKEN';let approval=null;
const kinds={pause:'Repouso',repetition:'Mexida repetitiva',speed:'Acelerar trecho',protect:'Proteger ação',exception:'Exceção em ação'};
document.querySelector('#name').textContent=initial.name+' | Fonte: '+initial.source_frames/24+'s | Alvo: '+initial.target_frames/24+'s';
function invalidate(){approval=null;document.querySelector('#approve').disabled=true;document.querySelector('#endpoints').checked=false}
function add(r={}){const tr=document.createElement('tr');tr.innerHTML='<td><input type="checkbox" class="use"></td><td><input class="start" type="number" step="0.041667"></td><td><input class="end" type="number" step="0.041667"></td><td><select class="kind"></select></td><td><input class="action note"></td><td><input class="reason note"></td><td><button class="seek">Ver</button></td>';
tr.querySelector('.start').value=((r.start_frame||24)/24).toFixed(3);tr.querySelector('.end').value=((r.end_frame||48)/24).toFixed(3);
Object.entries(kinds).forEach(([k,v])=>tr.querySelector('select').add(new Option(v,k)));tr.querySelector('select').value=r.kind||'pause';tr.querySelector('.action').value=r.action==='a_confirmar'?'':r.action||'';tr.querySelector('.reason').value=r.reason||'';
tr.querySelector('.seek').onclick=()=>{const v=document.querySelector('#source');v.currentTime=Math.max(0,Number(tr.querySelector('.start').value)-.75);v.play()};tr.oninput=invalidate;document.querySelector('#rows').append(tr)}
initial.regions.forEach(add);
function review(){return {source_sha256:initial.source_sha256,source_frames:initial.source_frames,fps:24,regions:[...document.querySelectorAll('#rows tr')].filter(r=>r.querySelector('.use').checked).map(r=>({start_frame:Math.round(Number(r.querySelector('.start').value)*24),end_frame:Math.round(Number(r.querySelector('.end').value)*24),kind:r.querySelector('.kind').value,action:r.querySelector('.action').value.trim(),reason:r.querySelector('.reason').value.trim(),verified:true,max_speed:1.15}))}}
async function call(route,data){const r=await fetch('/'+route+'?'+token,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});const j=await r.json();if(!r.ok)throw Error(j.error);return j}
async function propose(){invalidate();document.querySelector('#status').textContent='Preparando prévia...';try{const r=review(),p=await call('preview',r);approval={...r,plan_sha256:p.digest};const v=document.querySelector('#preview');v.src='/preview?'+token+'&v='+Date.now();v.hidden=false;document.querySelector('#status').textContent=p.summary;document.querySelector('#approve').disabled=false}catch(e){document.querySelector('#status').textContent=e.message}}
async function finish(){if(!approval||!document.querySelector('#endpoints').checked){alert('Confira as emendas da prévia e marque a confirmação.');return}try{await call('approve',{...approval,endpoints_reviewed:true});document.querySelector('#status').textContent='Cortes confirmados. Pode fechar esta aba; processamento no Terminal.'}catch(e){document.querySelector('#status').textContent=e.message}}
async function cancel(){await call('cancel',{});document.querySelector('#status').textContent='Cancelado.'}
</script>'''


def interactive_review(ffmpeg,source,analysis,target):
    from edit_batch import build_filter
    token=secrets.token_urlsafe(24)
    draft=dict(candidate_review(analysis),name=Path(source).name,target_frames=target)
    html=HTML.replace('INITIAL',json.dumps(draft,ensure_ascii=True).replace('<','\\u003c')).replace('TOKEN',token).encode()
    state={'done':False,'review':None}
    with tempfile.TemporaryDirectory(prefix='cut_review_') as temp:
        scratch=Path(temp);preview=scratch/'preview.mp4'
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def json_response(self,obj,status=200):
                data=json.dumps(obj).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
            def valid(self):return self.path.partition('?')[2].split('&')[0]==token
            def do_GET(self):
                if not self.valid():self.send_error(403);return
                route=self.path.partition('?')[0]
                if route=='/':
                    self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(html)));self.end_headers();self.wfile.write(html);return
                path=Path(source) if route=='/source' else preview if route=='/preview' else None
                if path is None or not path.exists():self.send_error(404);return
                size=path.stat().st_size;start,end=0,size-1;partial=False
                range_header=self.headers.get('Range','')
                if range_header:
                    try:
                        a,b=range_header.removeprefix('bytes=').split('-');start=int(a);end=min(int(b) if b else size-1,size-1);partial=True
                        if not 0<=start<=end<size:raise ValueError()
                    except ValueError:self.send_error(416);return
                self.send_response(206 if partial else 200);self.send_header('Content-Type','video/mp4');self.send_header('Accept-Ranges','bytes');self.send_header('Content-Length',str(end-start+1))
                if partial:self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
                self.end_headers()
                try:
                    with path.open('rb') as f:
                        f.seek(start);left=end-start+1
                        while left:
                            chunk=f.read(min(left,65536));self.wfile.write(chunk);left-=len(chunk)
                except (BrokenPipeError,ConnectionResetError):pass
            def do_POST(self):
                if not self.valid():self.send_error(403);return
                try:
                    length=int(self.headers.get('Content-Length',0))
                    if length>100000:raise ValueError('Revisao muito grande.')
                    review=json.loads(self.rfile.read(length));route=self.path.partition('?')[0]
                    if route=='/cancel':state['done']=True;self.json_response({});return
                    if route=='/approve':
                        validate_final_review(analysis,target,review)
                        if review.get('plan_sha256')!=state.get('preview_digest'):raise ValueError('Gere e assista a previa deste plano.')
                        state.update(done=True,review=review);self.json_response({});return
                    if route!='/preview':raise ValueError('Rota invalida.')
                    plan=plan_from_review(analysis,target,review)
                    if plan['missing_frames']:raise ValueError(f'Faltam {plan["missing_seconds"]:.2f}s. Confira outras pausas; depois mexidas repetitivas, aceleracao seletiva e, por ultimo, excecoes justificadas. Nenhum gesto foi cortado para fechar a conta.')
                    # Empty subtitles; review plain visual timeline before decoration.
                    (scratch/'captions.ass').write_text('[Script Info]\nScriptType: v4.00+\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n')
                    (scratch/'filter.txt').write_text(build_filter({'clips':plan['clips']},24))
                    result=subprocess.run([ffmpeg,'-v','error','-y','-i',str(source),'-filter_complex_threads','2','-filter_complex_script','filter.txt','-map','[out]','-an','-c:v','libx264','-preset','ultrafast','-crf','25',str(preview)],cwd=scratch,capture_output=True,text=True)
                    if result.returncode:raise ValueError(result.stderr[-1500:])
                    state['preview_digest']=plan_digest(plan)
                    summary=f'{len(plan["clips"])} segmentos, corte seco, {target/24:.3f}s. Confira o resultado e todas as emendas.\n'
                    summary+='\n'.join(f'Retirar {r["start_frame"]/24:.3f}-{r["end_frame"]/24:.3f}s: {r["action"]} ({r["kind"]})' for r in plan['removed'])
                    self.json_response(dict(digest=state['preview_digest'],summary=summary))
                except Exception as e:self.json_response({'error':str(e)},400)
        with HTTPServer(('127.0.0.1',0),Handler) as server:
            url=f'http://127.0.0.1:{server.server_port}/?{token}'
            print('Revisao visual local: '+url,flush=True);webbrowser.open(url);server.timeout=1
            while not state['done']:server.handle_request()
    if state['review'] is None:raise KeyboardInterrupt
    return state['review']
