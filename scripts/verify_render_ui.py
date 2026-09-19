"""Exercise one-shot export intake and its before/after UI with real WAV fixtures.

Attempt ordinary authenticated HTTP. If administrator policy explicitly blocks it,
record that and exercise DOM-to-service transport instead; never alter browser policy.
"""
from __future__ import annotations
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
from flcopilot.demo import DemoAdapter
from flcopilot.server import LocalServer
from flcopilot.service import Service


def main():
    evidence = ROOT / 'evidence'
    evidence.mkdir(exist_ok=True)
    checks = []
    with tempfile.TemporaryDirectory(prefix='flcopilot-render-ui-') as tmp:
        folder = Path(tmp) / 'manual-exports'; folder.mkdir()
        service = Service(Path(tmp) / 'workspace', DemoAdapter())
        server = LocalServer(service, 0)
        worker = threading.Thread(target=server.serve_forever, daemon=True); worker.start()

        def request(req):
            path = req['path'].removeprefix('/api/'); data = req.get('data')
            try:
                if path == 'status': out = service.status()
                elif path == 'assets': out = service.assets.list()
                elif path == 'capabilities': out = service.capabilities()
                elif path == 'history': out = service.journal.history()
                elif path == 'reviews': out = service.reviews.history()
                elif path == 'render-watch':
                    out = service.render_watch_status() if data is None else service.render_watch(data)
                elif path == 'render-watch-cancel': out = service.render_watch_cancel(data)
                elif path == 'inspect': out = service.jobs.submit('Inspect simulator', service.inspect)
                elif path == 'analyze': out = service.jobs.submit('Analyze captured WAV', lambda: service.analyze(data['asset']))
                elif path == 'review-audio': out = service.jobs.submit('Build real A/B', lambda: service.review_audio(data))
                elif path == 'stop': out = service.executor.stop()
                elif path.startswith('jobs/'): out = service.jobs.get(path[5:])
                else: raise ValueError('Unsupported DOM harness route')
                return {'status': 200, 'data': out}
            except Exception as exc:
                return {'status': 400, 'data': {'error': str(exc)}}

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(executable_path=os.environ.get('FLCOPILOT_BROWSER') or shutil.which('chromium'),
                    headless=True, args=['--no-sandbox'])
                page = browser.new_page(viewport={'width': 1512, 'height': 1100})
                errors = []; page.on('pageerror', lambda e: errors.append(str(e)))
                transport = 'ordinary_authenticated_http'; navigation = 'passed'
                try:
                    page.goto(server.origin + '/#' + server.token, wait_until='networkidle')
                except Error as exc:
                    if 'ERR_BLOCKED_BY_ADMINISTRATOR' not in str(exc): raise
                    transport = 'direct_service_dom_fallback'; navigation = 'blocked_by_environment_administrator'
                    html = (ROOT / 'flcopilot/web/index.html').read_text()
                    html = html.replace('<link rel="stylesheet" href="/style.css">', '')
                    modules = ['app', 'workbench', 'review', 'render']
                    for name in modules:
                        html = html.replace(f'<script src="/{name}.js" defer></script>', '')
                    page.close(); page = browser.new_page(viewport={'width': 1512, 'height': 1100})
                    page.on('pageerror', lambda e: errors.append(str(e)))
                    page.set_content(html)
                    page.add_style_tag(content=(ROOT / 'flcopilot/web/style.css').read_text())
                    page.expose_function('__renderRequest', request)
                    page.evaluate('''()=>{
                        Object.defineProperty(window,'sessionStorage',{value:{getItem:()=>"fixture-token",setItem:()=>{}}});
                        window.fetch=async(path,opts={})=>{
                            const r=await window.__renderRequest({path,data:opts.body?JSON.parse(opts.body):null});
                            return {ok:r.status===200,statusText:String(r.status),json:async()=>r.data};
                        };
                    }''')
                    for name in modules:
                        page.add_script_tag(content=(ROOT / f'flcopilot/web/{name}.js').read_text())
                page.wait_for_function('status && snapshot')
                page.locator('[data-tab="audio"]').click()
                page.locator('#render-folder').fill(str(folder))
                page.locator('#render-arm').click()
                page.wait_for_function('document.querySelector("#notice").textContent.includes("Confirm one-file")')
                assert service.render_watch_status()['watch'] is None
                checks.append('Folder consent required before arming')
                page.locator('#render-consent').check(); page.locator('#render-arm').click()
                page.wait_for_function('renderWatch && renderWatch.status==="watching"')
                assert page.locator('#render-folder').is_disabled()
                assert not page.locator('#render-consent').is_checked()
                checks.extend(['Armed state visible', 'Folder frozen while active', 'Consent consumed after arming'])
                samples = np.random.default_rng(714).normal(size=(24000, 2)) * .04
                sf.write(folder / 'before.wav', samples, 8000, subtype='FLOAT')
                page.wait_for_function('renderWatch && renderWatch.status==="complete"')
                first = service.render_watch_status()['watch']['result']['id']
                assert page.locator('#render-captured').is_visible()
                checks.append('Real WAV captured and shown as verified copy')
                page.locator('#render-analyze').click()
                page.locator('#audio-report').get_by_text('Captured bounce analysis', exact=True).wait_for()
                checks.append('Captured WAV analyzed through Audio lab')
                page.locator('#render-use-before').click()
                page.wait_for_function(f'document.querySelector("#review-a").value==="{first}"')
                page.locator('#review-same-range').check()
                page.locator('[data-tab="audio"]').click()
                page.locator('#render-consent').check(); page.locator('#render-arm').click()
                page.wait_for_function('renderWatch && renderWatch.status==="watching"')
                sf.write(folder / 'after.wav', samples*.5, 8000, subtype='FLOAT')
                page.wait_for_function('renderWatch && renderWatch.status==="complete" && renderWatch.result.id!=="'+first+'"')
                second = service.render_watch_status()['watch']['result']['id']
                page.locator('#render-use-after').click()
                page.wait_for_function(f'document.querySelector("#review-b").value==="{second}"')
                assert page.locator('#review-a').input_value() == first
                assert not page.locator('#review-same-range').is_checked()
                checks.extend(['Before selection preserved across second export', 'After handoff invalidates stale range confirmation'])
                page.locator('#review-build').click()
                page.wait_for_function('document.querySelector("#notice").textContent.includes("Confirm")')
                assert not service.reviews.history()
                page.locator('#review-same-range').check(); page.locator('#review-build').click()
                page.wait_for_function('reviewCurrent && reviewCurrent.report.status==="ready"')
                assert page.locator('#review-files .file-row').count() == 3
                checks.extend(['No automatic export-range assumption', 'Two watched WAVs produce measured A/B and report'])
                page.locator('[data-tab="audio"]').click()
                # Do not include the private temporary folder path in screenshots.
                page.locator('#render-folder').fill('C:\\Music\\FL Exports')
                page.screenshot(path=str(evidence / 'Render_Intake_Desktop.png'), full_page=True)
                page.set_viewport_size({'width': 390, 'height': 844})
                assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
                page.screenshot(path=str(evidence / 'Render_Intake_Mobile.png'), full_page=True)
                checks.append('390 px responsive layout has no horizontal overflow')
                page.locator('#render-folder').fill(str(folder))
                page.locator('#render-consent').check(); page.locator('#render-arm').click()
                page.wait_for_function('renderWatch && renderWatch.status==="watching"')
                page.locator('#render-cancel').click()
                page.wait_for_function('renderWatch && renderWatch.status==="cancelled"')
                assert not service.executor.stop_event.is_set()
                checks.append('Cancel watch leaves unrelated work and global Stop alone')
                page.locator('#render-consent').check(); page.locator('#render-arm').click()
                page.wait_for_function('renderWatch && renderWatch.status==="watching"')
                page.locator('#stop').click()
                page.wait_for_function('renderWatch && renderWatch.status==="cancelled"')
                assert service.executor.stop_event.is_set()
                assert not service.adapter.calls and not service.journal.history()
                assert not errors
                checks.extend(['Global Stop cancels intake', 'Zero DAW writes or control plans', 'No JavaScript page errors'])
                report = {'checks': checks, 'page_errors': errors, 'transport': transport,
                          'ordinary_navigation': navigation, 'browser_policy_changed': False,
                          'fixture': 'Synthetic WAVs only', 'live_fl_tested': False, 'platform': sys.platform}
                (evidence / 'render_ui_validation.json').write_text(json.dumps(report, indent=2)+'\n')
                print(json.dumps(report, indent=2)); browser.close()
        finally:
            server.shutdown(); worker.join(timeout=2); server.server_close(); service.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
