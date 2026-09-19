"""Checklist browser checks using real HTTP or an explicitly reported DOM fallback."""
from __future__ import annotations
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
from playwright.sync_api import Error, sync_playwright
from flcopilot.demo import DemoAdapter
from flcopilot.server import LocalServer
from flcopilot.service import Service


def main():
    checks, errors = [], []
    fallback = False
    evidence = ROOT/'evidence'; evidence.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='flcopilot-acceptance-ui-') as temp:
        s = Service(Path(temp), DemoAdapter())
        server = LocalServer(s, 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        def request(req):
            route = req['path'].removeprefix('/api/'); data = req.get('data')
            current = server.service
            try:
                readers = {'status':current.status, 'assets':current.assets.list,
                    'capabilities':current.capabilities, 'reviews':current.reviews.history,
                    'history':current.journal.history, 'render-watch':current.render_watch_status}
                if route == 'render-acceptance':
                    out = current.acceptance.get() if data is None else current.acceptance.save(data)
                elif route == 'render-acceptance-export':
                    out = current.jobs.submit('Export acceptance progress', lambda:current.acceptance.export(data))
                elif route in readers: out=readers[route]()
                elif route=='bounces': out=current.bounces.list(data)
                elif route=='inspect': out=current.jobs.submit('Inspect simulator',current.inspect)
                elif route.startswith('jobs/'): out=current.jobs.get(route[5:])
                else: raise ValueError('Unsupported browser fixture route: '+route)
                return {'status':200,'data':out}
            except Exception as exc:
                return {'status':400,'data':{'error':str(exc)}}
        try:
            with sync_playwright() as p:
                browser=p.chromium.launch(executable_path=os.environ.get('FLCOPILOT_BROWSER') or shutil.which('chromium'),
                                          headless=True,args=['--no-sandbox'])
                def open_page():
                    nonlocal fallback
                    page=browser.new_page(viewport={'width':1440,'height':1000})
                    page.on('pageerror',lambda e:errors.append(str(e)))
                    page.on('dialog',lambda d:d.accept())
                    if not fallback:
                        try:
                            page.goto(server.origin+'/#'+server.token,wait_until='networkidle')
                            return page
                        except Error as exc:
                            if 'ERR_BLOCKED_BY_ADMINISTRATOR' not in str(exc): raise
                            fallback=True; page.close()
                            page=browser.new_page(viewport={'width':1440,'height':1000})
                            page.on('pageerror',lambda e:errors.append(str(e)))
                            page.on('dialog',lambda d:d.accept())
                    html=(ROOT/'flcopilot/web/index.html').read_text()
                    modules=re.findall(r'<script src="/([a-z]+)\.js" defer></script>',html)
                    html=re.sub(r'<script src="/[a-z]+\.js" defer></script>','',html)
                    html=re.sub(r'<link rel="stylesheet" href="/[a-z]+\.css">','',html)
                    page.set_content(html)
                    for css in ("style", "acceptance"):
                        page.add_style_tag(content=(ROOT/f"flcopilot/web/{css}.css").read_text())
                    page.expose_function('__acceptanceRequest',request)
                    page.evaluate('''() => {
                        Object.defineProperty(window,"sessionStorage",{value:{getItem:()=>"test-token",setItem:()=>{}}});
                        window.fetch=async(path,opts={})=>{
                            const r=await window.__acceptanceRequest({path,data:opts.body?JSON.parse(opts.body):undefined});
                            return {ok:r.status===200,statusText:String(r.status),json:async()=>r.data};
                        };
                    }''')
                    for name in modules:
                        page.add_script_tag(content=(ROOT/f'flcopilot/web/{name}.js').read_text())
                    return page
                page=open_page(); page.wait_for_function('status && snapshot')
                page.locator('[data-tab="setup"]').click()
                page.wait_for_function('acceptanceState && !acceptanceBusy')
                assert page.locator('#acceptance-checks select').count()==11
                assert page.locator('#acceptance-complete').is_disabled()
                checks.append('Eleven observations start untested; demo completion is disabled')
                page.locator('#acceptance-project').fill('<img src=x onerror="window.injected=true">')
                page.locator('#acceptance-private').fill('PRIVATE TEST NOTE')
                page.locator('#acceptance-notes').fill('Shared browser observation')
                page.locator('#acceptance-check-cancel_watch').select_option('pass')
                assert page.locator('#acceptance-progress').is_disabled()
                checks.append('Unsaved edits disable report exports')
                page.locator('#acceptance-save').click()
                page.wait_for_function('acceptanceState.revision===2 && !acceptanceBusy')
                assert page.locator('#acceptance-state').inner_text().startswith('Saved revision 2')
                assert page.locator('#acceptance-panel img').count()==0 and page.evaluate('window.injected!==true')
                checks.append('Saved fields remain inert text, not HTML')
                page.locator('#acceptance-notes').fill('Keep my unsaved edit')
                page.locator('#acceptance-evidence-refresh').click()
                page.wait_for_function('!acceptanceBusy')
                assert page.locator('#acceptance-notes').input_value()=='Keep my unsaved edit'
                checks.append('Refreshing evidence preserves unsaved notes')
                s.acceptance.save({'expected_revision':2,'fields':{'notes':['Other view']},'assets':[]})
                page.locator('#acceptance-save').click()
                page.wait_for_function('document.querySelector("#notice").textContent.includes("another view")')
                assert page.locator('#acceptance-notes').input_value()=='Keep my unsaved edit'
                checks.append('Conflicting save is refused without losing the local draft')
                page.locator('#acceptance-reload').click()
                page.wait_for_function('acceptanceState.revision===3 && !acceptanceBusy')
                assert page.locator('#acceptance-notes').input_value()=='Other view'
                checks.append('Explicit reload restores the saved revision')
                page.locator('#acceptance-progress').click()
                page.wait_for_function('!document.querySelector("#acceptance-export").hidden && !acceptanceBusy')
                report=next(r for r in s.assets.list() if r['kind']=='report')
                shared=json.loads(s.assets.resolve(report['id']).read_text())
                assert shared['status']=='not_run' and 'private_notes' not in shared and 'project_label' not in shared
                assert shared['notes']==['Other view']
                checks.append('Progress export is real JSON with private fields omitted')
                page.close(); s.close(); s=Service(Path(temp),DemoAdapter()); server.service=s
                page=open_page(); page.wait_for_function('status && snapshot')
                page.locator('[data-tab="setup"]').click()
                page.wait_for_function('acceptanceState && !acceptanceBusy')
                assert page.locator('#acceptance-private').input_value()=='PRIVATE TEST NOTE'
                assert page.locator('#acceptance-check-cancel_watch').input_value()=='pass'
                assert s.render_watch_status()['watch'] is None
                checks.append('Real service restart restores notes and observations without rearming a watch')
                page.locator('#acceptance-project').fill('Disposable test copy')
                page.locator('#acceptance-private').fill('')
                page.locator('#acceptance-save').click()
                page.wait_for_function('!acceptanceDirty && !acceptanceBusy')
                page.locator('#acceptance-panel').scroll_into_view_if_needed()
                page.locator('#acceptance-panel').screenshot(path=str(evidence/'Acceptance_Workbench_Desktop.png'))
                page.set_viewport_size({'width':390,'height':844})
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                page.locator('#acceptance-panel').screenshot(path=str(evidence/'Acceptance_Workbench_Mobile.png'))
                checks.append('390px layout has no horizontal overflow')
                browser.close()
        finally:
            server.shutdown(); thread.join(timeout=2); server.server_close(); s.close()
    result={'transport':'direct-Service DOM fallback' if fallback else 'authenticated localhost HTTP',
        'checks':checks,'page_errors':errors,'native_fl_tested':False}
    (evidence/'acceptance_workbench_ui.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
    if errors: raise SystemExit(1)


if __name__=='__main__': main()
