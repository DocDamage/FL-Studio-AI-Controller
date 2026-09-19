"""Exercise real synthetic review playback; report HTTP or explicit DOM fallback."""
from __future__ import annotations

import base64
import io
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import threading

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import numpy as np
import soundfile as sf
from playwright.sync_api import Error, sync_playwright
from flcopilot.demo import DemoAdapter
from flcopilot.server import LocalServer
from flcopilot.service import Service


def main():
    evidence = ROOT/'evidence'; evidence.mkdir(exist_ok=True)
    checks, errors = [], []
    with tempfile.TemporaryDirectory(prefix='flcopilot-waveform-ui-') as temp:
        service = Service(Path(temp), DemoAdapter())
        server = LocalServer(service, 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        t = np.arange(192003)/8000
        envelope = (.15+.85*np.sin(t*.7)**4)[:,None]
        y = np.random.default_rng(732).normal(0,.08,(len(t),2))*envelope
        y[:,1] *= .7
        ids=[]
        for name, value in [('Before.wav',y), ('After.wav',y*.6), ('WrongRange.wav',y[:-2000])]:
            buf=io.BytesIO();sf.write(buf,value,8000,format='WAV',subtype='FLOAT');raw=buf.getvalue()
            ids.append(service.assets.import_stream(io.BytesIO(raw),len(raw),name)['id'])
        reviews=[]
        for label, candidate in [('Drum passage',ids[1]),('Second saved review',ids[1]),('Wrong export range',ids[2])]:
            reviews.append(service.review_audio({'baseline':ids[0],'candidate':candidate,'confirm_same_range':True,
                                                 'title':label,'section_seconds':10}))
        assert [r['report']['status'] for r in reviews]==['ready','ready','blocked']
        original_files=service.assets.manifest.read_bytes()
        def request(req):
            route=req['path'].removeprefix('/api/');data=req.get('data')
            try:
                readers={'status':service.status,'assets':service.assets.list,'history':service.journal.history,
                         'reviews':service.reviews.history,'capabilities':service.capabilities,'render-watch':service.render_watch_status}
                if route in readers: out=readers[route]()
                elif route=='inspect': out=service.jobs.submit('Inspect simulator',service.inspect)
                elif route=='bounces': out=service.bounces.list(data)
                elif route=='review-get': out=service.review_get(data)
                elif route=='review-waveform': out=service.jobs.submit('Read verified waveforms',lambda:service.review_waveform(data))
                elif route=='stop': out=service.executor.stop()
                elif route=='reset-stop': service.executor.reset_stop();out=service.status()
                elif route.startswith('jobs/'): out=service.jobs.get(route[5:])
                elif route.startswith('file/'):
                    return {'status':200,'binary':base64.b64encode(service.assets.resolve(route[5:]).read_bytes()).decode()}
                else: raise ValueError('Unsupported fixture route: '+route)
                return {'status':200,'data':out}
            except Exception as exc: return {'status':400,'data':{'error':str(exc)}}
        try:
            with sync_playwright() as p:
                browser=p.chromium.launch(executable_path=os.environ.get('FLCOPILOT_BROWSER') or shutil.which('chromium'),
                                          headless=True,args=['--no-sandbox'])
                page=browser.new_page(viewport={'width':1440,'height':1000})
                page.on('pageerror',lambda e:errors.append(str(e)))
                transport='authenticated localhost HTTP'
                try: page.goto(server.origin+'/#'+server.token,wait_until='networkidle')
                except Error as exc:
                    if 'ERR_BLOCKED_BY_ADMINISTRATOR' not in str(exc): raise
                    transport='direct-Service DOM fallback';page.close()
                    page=browser.new_page(viewport={'width':1440,'height':1000})
                    page.on('pageerror',lambda e:errors.append(str(e)))
                    html=(ROOT/'flcopilot/web/index.html').read_text()
                    modules=re.findall(r'<script src="/([a-z]+)\.js" defer></script>',html)
                    styles=re.findall(r'<link rel="stylesheet" href="/([a-z]+)\.css">',html)
                    html=re.sub(r'<script src="/[a-z]+\.js" defer></script>','',html)
                    html=re.sub(r'<link rel="stylesheet" href="/[a-z]+\.css">','',html)
                    page.set_content(html)
                    for css in styles: page.add_style_tag(content=(ROOT/f'flcopilot/web/{css}.css').read_text())
                    page.expose_function('__waveformRequest',request)
                    page.evaluate('''()=>{
                        Object.defineProperty(window,'sessionStorage',{value:{getItem:()=>"test-token",setItem:()=>{}}});
                        window.fetch=async(path,options={})=>{
                            const r=await window.__waveformRequest({path,data:options.body?JSON.parse(options.body):undefined});
                            return {ok:r.status===200,statusText:String(r.status),json:async()=>r.data,
                                blob:async()=>new Blob([Uint8Array.from(atob(r.binary),c=>c.charCodeAt(0))],{type:'audio/wav'})};
                        };
                    }''')
                    for module in modules: page.add_script_tag(content=(ROOT/f'flcopilot/web/{module}.js').read_text())
                page.wait_for_function('status && snapshot')
                page.locator('[data-tab="review"]').click()
                def open_review(index):
                    page.locator(f'.review-open[data-id="{reviews[index]["review_id"]}"]').click()
                    page.wait_for_function('(id)=>reviewCurrent?.review_id===id',arg=reviews[index]['review_id'])
                def load():
                    page.locator('#waveform-load').click()
                    page.wait_for_function('waveformData && !waveformBusy')
                def pause():
                    page.locator('#review-pause').click()
                    page.wait_for_function('!reviewLoading && document.querySelector("#review-player").paused')
                def set_range(start,end):
                    page.locator('#waveform-start').fill(str(start));page.locator('#waveform-end').fill(str(end))
                    page.locator('#waveform-apply').click()
                open_review(0)
                assert page.locator('#waveform-controls').is_hidden()
                load()
                assert page.evaluate('waveformData.channels')==2
                assert 'shared scale' in page.locator('#waveform-a').get_attribute('aria-label')
                checks.append('Real matched WAVs produce stereo peak/RMS envelopes on a shared amplitude scale')
                page.locator('#waveform-seek').fill('3')
                assert page.evaluate('document.querySelector("#review-player").paused && reviewPosition===3')
                page.locator('#review-play-a').click()
                page.wait_for_function('reviewSide==="a" && !reviewLoading && !document.querySelector("#review-player").paused')
                assert 3<=page.evaluate('document.querySelector("#review-player").currentTime')<5
                checks.append('Seeking before the first audio load is retained without autoplay')
                pause();set_range(2,3.5)
                assert page.evaluate('document.querySelector("#review-player").paused && waveformLoop.start===2')
                page.locator('#review-play-a').click()
                page.wait_for_function('!document.querySelector("#review-player").paused')
                page.evaluate('document.querySelector("#review-player").currentTime=3.7')
                page.wait_for_function('document.querySelector("#review-player").currentTime>=2 && document.querySelector("#review-player").currentTime<3.5')
                checks.append('Applied loop wraps the current player without modifying audio')
                page.locator('#review-play-b').click()
                page.wait_for_function('reviewSide==="b" && !reviewLoading && !document.querySelector("#review-player").paused')
                assert page.evaluate('waveformLoop.start===2 && waveformLoop.end===3.5')
                assert 2<=page.evaluate('document.querySelector("#review-player").currentTime')<3.5
                checks.append('A/B switching retains the loop and approximate position')
                pause();set_range(1,1.1)
                page.wait_for_function('document.querySelector("#notice").textContent.includes("0.25")')
                assert page.evaluate('waveformLoop===null && !document.querySelector("#waveform-repeat").checked')
                checks.append('Invalid short ranges cannot leave a previous loop active')
                page.locator('#waveform-window').select_option('1');page.locator('#waveform-use-window').click()
                assert page.evaluate('waveformLoop.start===10 && waveformLoop.end===20 && document.querySelector("#review-player").paused')
                checks.append('Measured time windows become loops without starting playback')
                page.locator('#waveform-panel').screenshot(path=str(evidence/'Waveform_Review_Desktop.png'))
                page.set_viewport_size({'width':390,'height':844})
                page.wait_for_timeout(100)
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                page.locator('#waveform-panel').screenshot(path=str(evidence/'Waveform_Review_Mobile.png'))
                checks.append('390px controls and canvas stay within the viewport')
                page.set_viewport_size({'width':1440,'height':1000})
                # Full-file end looping exercises the actual media ended event.
                set_range(0,24.000375)
                page.locator('#review-play-a').click();page.wait_for_function('!reviewLoading && !document.querySelector("#review-player").paused')
                page.evaluate('document.querySelector("#review-player").currentTime=23.98')
                page.wait_for_function('!document.querySelector("#review-player").paused && document.querySelector("#review-player").currentTime<2')
                checks.append('Whole-file loop continues across the media end boundary')
                page.locator('#stop').click()
                page.wait_for_function('status.stopped && document.querySelector("#review-player").paused')
                assert page.locator('#waveform-repeat').is_checked() is False
                checks.append('Global Stop pauses audition and disables repeat')
                # UI Stop state is reset through the actual service/API, not bypassed.
                page.evaluate('async()=>{await api("reset-stop",{});await refreshStatus();}')
                open_review(1)
                assert page.locator('#waveform-controls').is_hidden()
                assert page.evaluate('waveformLoop===null && Object.keys(reviewURLs).length===0')
                checks.append('Opening another review clears loops, envelopes and cached audio URLs')
                # Delay a real file response to exercise cancellation and latest seek wins.
                page.evaluate('''()=>{window.originalFileBlob=fileBlob;window.releaseAudio=null;
                    fileBlob=async file=>{const url=await window.originalFileBlob(file);await new Promise(r=>window.releaseAudio=r);return url;};}''')
                page.locator('#review-play-a').click();page.wait_for_function('window.releaseAudio!==null')
                page.evaluate('reviewSeekTo(6)')
                page.evaluate('window.releaseAudio()')
                page.wait_for_function('!reviewLoading && !document.querySelector("#review-player").paused')
                assert page.evaluate('document.querySelector("#review-player").currentTime')>=6
                checks.append('A seek during an in-flight audio load wins over the old position')
                pause();page.evaluate('window.releaseAudio=null')
                page.locator('#review-play-b').click();page.wait_for_function('window.releaseAudio!==null')
                pause();page.evaluate('window.releaseAudio()');page.wait_for_timeout(100)
                assert page.evaluate('document.querySelector("#review-player").paused && !reviewLoading')
                page.evaluate('()=>{fileBlob=window.originalFileBlob;}')
                checks.append('Pause cancels a pending side switch without late autoplay')
                # Delay a real waveform result, then open another saved review.
                page.evaluate('''()=>{window.originalJob=job;window.releaseWave=null;
                    job=async(...args)=>{const result=await window.originalJob(...args);
                        if(args[0]==="review-waveform")await new Promise(r=>window.releaseWave=r);return result;};}''')
                page.locator('#waveform-load').click();page.wait_for_function('window.releaseWave!==null')
                open_review(0);page.evaluate('window.releaseWave()');page.wait_for_timeout(100)
                assert page.evaluate('waveformData===null && waveformLoop===null')
                page.evaluate('()=>{job=window.originalJob;}')
                checks.append('A late waveform response cannot populate a different review')
                load()
                row=next(r for r in reviews[0]['files'] if r['kind']=='audio')
                service.assets.resolve(row['id']).write_bytes(b'changed output after earlier preview')
                page.locator('#waveform-load').click()
                page.wait_for_function('!waveformBusy && document.querySelector("#waveform-state").textContent.includes("No current waveform")')
                assert page.evaluate('waveformData===null && Object.keys(reviewURLs).length===0')
                assert page.locator('#waveform-controls').is_hidden()
                checks.append('Failed reverification clears stale waveforms and cached playback blobs')
                open_review(2)
                assert page.locator('#review-audition').is_hidden()
                assert page.evaluate('waveformData===null')
                checks.append('Blocked review withholds waveform and looping controls')
                assert original_files==service.assets.manifest.read_bytes()
                assert not service.adapter.calls and not service.journal.history()
                assert all(service.reviews.get(r['review_id'])==r for r in reviews)
                checks.append('Navigation and loops create no assets, decisions, plans or DAW writes')
                assert not errors
                result={'transport':transport,'checks':checks,'page_errors':errors,'fixture':'Synthetic exported audio',
                        'native_fl_tested':False,'physical_audio_listening_performed':False,'browser_policy_changed':False}
                (evidence/'waveform_ui.json').write_text(json.dumps(result,indent=2)+'\n')
                print(json.dumps(result,indent=2));browser.close()
        finally:
            server.shutdown();thread.join(timeout=2);server.server_close();service.close()


if __name__=='__main__': main()
