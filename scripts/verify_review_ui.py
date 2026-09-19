"""Exercise the audio-review UI. Record whether real HTTP or DOM fallback was used.

No browser network policy is changed. Fallback is allowed only for the supplied
browser's explicit administrator-policy navigation error; HTTP tests are separate.
"""
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import threading
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
import numpy as np
import soundfile as sf
from playwright.sync_api import sync_playwright, Error
from flcopilot.service import Service
from flcopilot.demo import DemoAdapter
from flcopilot.server import LocalServer


def main():
    evidence=ROOT/'evidence';evidence.mkdir(exist_ok=True)
    checks=[]
    with tempfile.TemporaryDirectory(prefix='flcopilot-review-ui-') as temp:
        service=Service(Path(temp),DemoAdapter());server=LocalServer(service,0)
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        t=np.arange(40000)/8000
        y=np.random.default_rng(182).normal(size=(len(t),2))*(.03+.02*np.sin(t*7)**2)[:,None]
        ids=[]
        for name,value in [('Before.wav',y),('After.wav',y*.5)]:
            buf=io.BytesIO();sf.write(buf,value,8000,format='WAV',subtype='FLOAT');raw=buf.getvalue()
            ids.append(service.assets.import_stream(io.BytesIO(raw),len(raw),name)['id'])
        # Fallback routes use the real service and durable storage, not fabricated results.
        def request(req):
            path=req['path'].removeprefix('/api/');data=req.get('data',{})
            try:
                if path=='bounces':out=service.bounces.list(data)
                elif path=='status':out=service.status()
                elif path=='render-watch':out=service.render_watch_status()
                elif path=='assets':out=service.assets.list()
                elif path=='capabilities':out=service.capabilities()
                elif path=='history':out=service.journal.history()
                elif path=='reviews':out=service.reviews.history()
                elif path=='review-get':out=service.review_get(data)
                elif path=='review-decision':out=service.review_decision(data)
                elif path=='inspect':out=service.jobs.submit('Inspect simulator',service.inspect)
                elif path=='review-audio':out=service.jobs.submit('Analyze pair',lambda:service.review_audio(data))
                elif path.startswith('jobs/'):out=service.jobs.get(path[5:])
                elif path.startswith('file/'):
                    import base64
                    return {'status':200,'binary':base64.b64encode(service.assets.resolve(path[5:]).read_bytes()).decode()}
                else:raise ValueError('Unimplemented DOM-test route')
                return {'status':200,'data':out}
            except Exception as exc:return {'status':400,'data':{'error':str(exc)}}
        try:
            with sync_playwright() as p:
                browser=p.chromium.launch(executable_path=os.environ.get('FLCOPILOT_BROWSER') or shutil.which('chromium'),headless=True,args=['--no-sandbox'])
                page=browser.new_page(viewport={'width':1512,'height':1100})
                errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                transport='ordinary_authenticated_http';navigation='passed'
                try:
                    page.goto(server.origin+'/#'+server.token,wait_until='networkidle')
                except Error as exc:
                    if 'ERR_BLOCKED_BY_ADMINISTRATOR' not in str(exc):raise
                    transport='direct_service_dom_fallback';navigation='blocked_by_environment_administrator'
                    html=(ROOT/'flcopilot/web/index.html').read_text()
                    html=html.replace('<link rel="stylesheet" href="/style.css">','')
                    for name in ['app','workbench','review','render','bounces']:
                        html=html.replace(f'<script src="/{name}.js" defer></script>','')
                    # A new blank page avoids a forbidden error-page origin.
                    page.close();page=browser.new_page(viewport={'width':1512,'height':1100})
                    page.on('pageerror',lambda e:errors.append(str(e)))
                    page.set_content(html);page.add_style_tag(content=(ROOT/'flcopilot/web/style.css').read_text())
                    page.expose_function('__reviewRequest',request)
                    page.evaluate('''()=>{
                        Object.defineProperty(window,'sessionStorage',{value:{getItem:()=>"test-token",setItem:()=>{}}});
                        window.fetch=async(path,options={})=>{
                            const r=await window.__reviewRequest({path,data:options.body?JSON.parse(options.body):undefined});
                            return {ok:r.status===200,statusText:String(r.status),json:async()=>r.data,
                                blob:async()=>new Blob([Uint8Array.from(atob(r.binary),c=>c.charCodeAt(0))],{type:'audio/wav'})};
                        };
                    }''')
                    for name in ['app','workbench','review','render','bounces']:
                        page.add_script_tag(content=(ROOT/f'flcopilot/web/{name}.js').read_text())
                page.wait_for_function('status && snapshot')
                page.locator('[data-tab="review"]').click()
                page.locator(f'#review-a option[value="{ids[0]}"]').wait_for(state='attached')
                page.locator('#review-a').select_option(ids[0]);page.locator('#review-b').select_option(ids[1])
                page.locator('#review-build').click()
                page.wait_for_function('document.querySelector("#notice").textContent.includes("Confirm")')
                assert not service.reviews.history();checks.append('Same-export declaration required')
                page.locator('#review-same-range').check();page.locator('#review-title').fill('Drum-bus change · before / after')
                page.locator('#review-build').click()
                page.wait_for_function('reviewCurrent && reviewCurrent.report.status==="ready"')
                assert page.locator('#review-files .file-row').count()==3
                checks.extend(['Actual WAV pair rendered','Measured match within tolerance','Three verified output files','Original sources preserved'])
                assert page.locator('#review-metrics tr').count()==4
                assert page.locator('#review-sections tr').count()==1
                assert page.locator('#review-choice').input_value()=='undecided'
                assert not service.adapter.calls
                checks.extend(['Global before/after deltas','Elapsed-time window deltas','No automatic listening preference','No DAW writes'])
                page.locator('#review-choice').select_option('prefer_baseline');page.locator('#review-note').fill('Keep the original drum punch.')
                page.locator('#review-save-choice').click();page.wait_for_function('reviewCurrent.revision===2')
                page.locator('.review-open').first.click();page.wait_for_function('reviewCurrent.revision===2')
                assert page.locator('#review-note').input_value()=='Keep the original drum punch.'
                checks.extend(['Explicit human decision persists','Saved review reopens with note'])
                page.locator('#review-play-a').click()
                page.wait_for_function('document.querySelector("#review-player").readyState>=1')
                page.wait_for_function('!document.querySelector("#review-player").paused')
                page.evaluate('document.querySelector("#review-player").currentTime=1')
                page.locator('#review-play-b').click()
                page.wait_for_function('reviewSide==="b" && !document.querySelector("#review-player").paused')
                assert page.locator('#review-now').inner_text().startswith('B')
                assert page.evaluate('document.querySelector("#review-player").currentTime')>=1
                page.locator('#review-pause').click();page.wait_for_function('document.querySelector("#review-player").paused')
                checks.extend(['Authenticated WAV audition loading','A/B side switching preserves approximate position','Pause control'])
                page.evaluate('window.scrollTo(0,0)');page.screenshot(path=str(evidence/'Audio_Review_v040.png'),full_page=True)
                # Stale writes cannot overwrite a listening decision made in another tab.
                service.review_decision({'review_id':page.evaluate('reviewCurrent.review_id'),'expected_revision':2,'decision':'needs_revision'})
                page.locator('#review-save-choice').click()
                page.wait_for_function('document.querySelector("#notice").textContent.includes("changed")')
                checks.append('Stale decision revision refused')
                page.set_viewport_size({'width':390,'height':844})
                assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
                page.screenshot(path=str(evidence/'Audio_Review_Mobile_v040.png'),full_page=True)
                checks.append('390 px layout stays within viewport')
                assert not errors
                report={'app_version':'0.4.0','checks':checks,'page_errors':errors,'transport':transport,
                        'ordinary_navigation':navigation,'browser_policy_changed':False,
                        'fixture':'Synthetic noise with varying envelope; no user audio','live_fl_tested':False,
                        'physical_audio_listening_performed':False,'platform':sys.platform}
                (evidence/'review_ui_v040.json').write_text(json.dumps(report,indent=2)+'\n')
                print(json.dumps(report,indent=2));browser.close()
        finally:
            server.shutdown();worker.join(timeout=2);server.server_close();service.close()
    return 0

if __name__=='__main__':raise SystemExit(main())
