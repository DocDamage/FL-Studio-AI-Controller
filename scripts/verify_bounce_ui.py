"""Real synthetic-audio library UI checks; ordinary HTTP attempted before DOM fallback."""
from __future__ import annotations
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import threading

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import numpy as np
import soundfile as sf
from playwright.sync_api import sync_playwright, Error
from flcopilot.assets import atomic_json
from flcopilot.demo import DemoAdapter
from flcopilot.server import LocalServer
from flcopilot.service import Service


def main():
    checks = []; errors = []; fallback = False
    evidence = ROOT / 'evidence'; evidence.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='flcopilot-bounce-ui-') as temp:
        workspace = Path(temp)/'workspace'; s = Service(workspace, DemoAdapter())
        server = LocalServer(s, 0); thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        ids = []
        samples = np.random.default_rng(291).normal(size=(24000, 2))*.04
        for name, audio, metadata in [('Original.wav', samples, None), ('Captured.wav', samples*.5,
                {'source':'watched_fl_export', 'watch_id':'a'*32, 'render_triggered_by_app':False,
                 'causal_provenance_verified':False})]:
            stream = io.BytesIO(); sf.write(stream, audio, 8000, format='WAV', subtype='FLOAT'); raw = stream.getvalue()
            ids.append(s.assets.import_stream(io.BytesIO(raw), len(raw), name, metadata=metadata)['id'])
        # An input from an earlier version has no reliable stored import date.
        s.assets.data[ids[0]].pop('imported_at'); atomic_json(s.assets.manifest, s.assets.data)

        def request(req):
            service = server.service; route = req['path'].removeprefix('/api/'); data = req.get('data')
            try:
                readers = {'status':service.status, 'assets':service.assets.list, 'capabilities':service.capabilities,
                           'history':service.journal.history, 'reviews':service.reviews.history,
                           'render-watch':service.render_watch_status}
                if route in readers: out = readers[route]()
                elif route == 'bounces': out = service.bounces.list(data)
                elif route == 'bounce-get': out = service.bounces.get(data)
                elif route == 'bounce-edit': out = service.bounces.edit(data)
                elif route == 'bounce-verify': out = service.jobs.submit('Verify input', lambda:service.bounces.verify(data))
                elif route == 'inspect': out = service.jobs.submit('Inspect demo',service.inspect)
                elif route == 'analyze': out = service.jobs.submit('Analyze fixture',lambda:service.analyze(data['asset']))
                elif route == 'review-audio': out = service.jobs.submit('Review fixture',lambda:service.review_audio(data))
                elif route.startswith('jobs/'): out = service.jobs.get(route[5:])
                else: raise ValueError('Unsupported browser fixture route')
                return {'status':200,'data':out}
            except Exception as exc:
                return {'status':400,'data':{'error':str(exc)}}

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(executable_path=os.environ.get('FLCOPILOT_BROWSER') or shutil.which('chromium'),
                                            headless=True,args=['--no-sandbox'])
                def page_open():
                    nonlocal fallback
                    page = browser.new_page(viewport={'width':1512,'height':1100})
                    page.on('pageerror',lambda e:errors.append(str(e))); page.on('dialog',lambda d:d.accept())
                    if not fallback:
                        try:
                            page.goto(server.origin+'/#'+server.token,wait_until='networkidle')
                            return page
                        except Error as exc:
                            if 'ERR_BLOCKED_BY_ADMINISTRATOR' not in str(exc): raise
                            fallback = True; page.close()
                            page = browser.new_page(viewport={'width':1512,'height':1100})
                            page.on('pageerror',lambda e:errors.append(str(e))); page.on('dialog',lambda d:d.accept())
                    html = (ROOT/'flcopilot/web/index.html').read_text()
                    html = html.replace('<link rel="stylesheet" href="/style.css">','')
                    modules = ['app','workbench','review','render','bounces']
                    for name in modules: html = html.replace(f'<script src="/{name}.js" defer></script>','')
                    page.set_content(html); page.add_style_tag(content=(ROOT/'flcopilot/web/style.css').read_text())
                    page.expose_function('__bounceRequest',request)
                    page.evaluate('''()=>{
                        Object.defineProperty(window,'sessionStorage',{value:{getItem:()=>"test-token",setItem:()=>{}}});
                        window.fetch=async(path,opts={})=>{
                            const r=await window.__bounceRequest({path,data:opts.body?JSON.parse(opts.body):undefined});
                            return {ok:r.status===200,statusText:String(r.status),json:async()=>r.data};
                        };
                    }''')
                    for name in modules: page.add_script_tag(content=(ROOT/f'flcopilot/web/{name}.js').read_text())
                    return page

                page = page_open(); page.wait_for_function('status && snapshot')
                page.locator('[data-tab="audio"]').click()
                page.wait_for_function('document.querySelectorAll(".bounce-open").length===2')
                page.locator(f'.bounce-open[data-id="{ids[0]}"]').click()
                page.wait_for_function('bounceSelected!==null')
                assert 'Date not recorded' in page.locator('#bounce-source-detail').inner_text()
                checks.append('Historical imports appear without invented dates')
                page.locator('#bounce-label').fill('<img src=x onerror="window.injected=true">')
                page.locator('#bounce-note').fill('Keep the punch.\nReview bass definition.')
                page.locator('#bounce-save').click(); page.wait_for_function('bounceSelected.revision===2 && !bounceBusy')
                page.wait_for_function('document.querySelector("#bounce-rows").textContent.includes("<img")')
                assert page.locator('#bounce-rows img').count()==0 and page.evaluate('window.injected!==true')
                checks.append('Labels and notes are stored as inert text, not HTML')
                page.locator('#bounce-label').fill('Original drum punch')
                page.locator('#bounce-save').click(); page.wait_for_function('bounceSelected.revision===3 && !bounceBusy')
                page.locator('#bounce-query').fill('PUNCH')
                page.wait_for_function('document.querySelectorAll(".bounce-open").length===1')
                page.locator('#bounce-source').select_option('watched')
                page.wait_for_function('document.querySelectorAll(".bounce-open").length===0')
                page.locator('#bounce-query').fill(''); page.locator('#bounce-source').select_option('all')
                page.wait_for_function('document.querySelectorAll(".bounce-open").length===2')
                checks.append('Case-insensitive note search and source filters combine correctly')
                page.locator('#bounce-note').fill('Unsaved local text')
                page.locator('#bounce-refresh').click()
                assert page.locator('#bounce-note').input_value()=='Unsaved local text'
                checks.append('List refresh does not erase unsaved notes')
                s.bounces.edit({'asset':ids[0], 'expected_revision':3,'label':'Original drum punch','note':'Saved in another view'})
                page.locator('#bounce-save').click()
                page.wait_for_function('document.querySelector("#notice").textContent.includes("another view")')
                assert page.locator('#bounce-note').input_value()=='Unsaved local text'
                page.locator('#bounce-reopen').click(); page.wait_for_function('bounceSelected.revision===4')
                assert page.locator('#bounce-note').input_value()=='Saved in another view'
                checks.append('Stale note saves are refused; explicit reload restores the saved revision')
                # Reconstruct the Service against the actual persisted manifest, not a fabricated response.
                page.close(); s.close(); s = Service(workspace,DemoAdapter()); server.service = s
                page = page_open(); page.wait_for_function('status && snapshot')
                page.locator('[data-tab="audio"]').click()
                page.locator(f'.bounce-open[data-id="{ids[0]}"]').click()
                page.wait_for_function('bounceSelected && bounceSelected.revision===4')
                assert page.locator('#bounce-label').input_value()=='Original drum punch'
                assert s.render_watch_status()['watch'] is None
                checks.append('Service restart preserves annotations without rearming folder access')
                page.locator('#bounce-verify').click()
                page.wait_for_function('document.querySelector("#bounce-verification").textContent.includes("verified at")')
                page.locator('#bounce-analyze').click()
                page.wait_for_function('document.querySelector("#audio-report").textContent.includes("Bounce library analysis") && activeJobs===0')
                checks.extend(['Verification hashes the stored copy', 'Library input reaches the actual audio analyzer'])
                page.locator('#bounce-before').click()
                page.wait_for_function(f'document.querySelector("#review-a").value==="{ids[0]}"')
                page.locator('[data-tab="audio"]').click()
                page.locator(f'.bounce-open[data-id="{ids[1]}"]').click()
                page.wait_for_function(f'bounceSelected && bounceSelected.id==="{ids[1]}"')
                page.locator('#bounce-after').click()
                page.wait_for_function(f'document.querySelector("#review-b").value==="{ids[1]}"')
                assert not page.locator('#review-same-range').is_checked()
                page.locator('#review-same-range').check()
                page.locator('#review-a').select_option(ids[1])
                assert not page.locator('#review-same-range').is_checked()
                page.locator('#review-a').select_option(ids[0]); page.locator('#review-same-range').check()
                page.locator('#review-build').click()
                page.wait_for_function('reviewCurrent && reviewCurrent.report.status==="ready" && activeJobs===0')
                checks.extend(['Saved inputs reach baseline/candidate selectors', 'Changing either selector invalidates range consent',
                               'Actual library pair creates measured A/B outputs'])
                page.locator('[data-tab="audio"]').click()
                page.locator('#bounce-verify').click()
                page.wait_for_function('document.querySelector("#bounce-verification").textContent.includes("verified at") && activeJobs===0')
                s.assets.resolve(ids[1]).write_bytes(b'corrupted stored copy')
                page.locator('#bounce-verify').click()
                page.wait_for_function('document.querySelector("#bounce-verification").textContent.includes("failed")')
                assert 'verified at' not in page.locator('#bounce-verification').inner_text()
                checks.append('Failed re-verification clears the earlier success display')
                page.locator(f'.bounce-open[data-id="{ids[0]}"]').click()
                page.wait_for_function(f'bounceSelected && bounceSelected.id==="{ids[0]}"')
                page.evaluate('document.querySelector("#notice").hidden=true')
                page.locator('#bounce-library').scroll_into_view_if_needed()
                page.locator('#bounce-library').screenshot(path=str(evidence/'Bounce_Library_Panel.png'))
                page.screenshot(path=str(evidence/'Bounce_Library_Desktop.png'),full_page=True)
                page.set_viewport_size({'width':390,'height':844})
                assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
                page.screenshot(path=str(evidence/'Bounce_Library_Mobile.png'),full_page=True)
                checks.append('390px library layout stays within the viewport')
                assert not s.adapter.calls and not s.journal.history() and not errors, errors
                checks.extend(['Zero DAW commands or prepared plans', 'No JavaScript page errors'])
                report = {'checks':checks,'page_errors':errors,'live_fl_tested':False,'platform':sys.platform,
                          'transport':'direct_service_dom_fallback' if fallback else 'ordinary_authenticated_http',
                          'browser_policy_changed':False,'service_restart_tested':True,
                          'physical_audio_listening_performed':False,'fixture':'Synthetic WAV inputs only'}
                (evidence/'bounce_library_ui.json').write_text(json.dumps(report,indent=2)+'\n')
                print(json.dumps(report,indent=2)); browser.close()
        finally:
            server.shutdown(); thread.join(timeout=2); server.server_close(); server.service.close()
    return 0


if __name__=='__main__': raise SystemExit(main())
