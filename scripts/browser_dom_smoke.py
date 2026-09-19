"""Browser DOM harness with direct service calls; no browser network-policy changes.
HTTP endpoints are tested independently in pytest. Localhost browser navigation
was blocked by this environment's administrator policy; do not label this test
as successful ordinary-browser launch acceptance.
"""
import base64,io,json,sys,tempfile,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from flcopilot.service import Service
from flcopilot.demo import DemoAdapter
from playwright.sync_api import sync_playwright
P=Path(__file__).resolve().parent.parent;evidence=P/'evidence'
with tempfile.TemporaryDirectory(prefix='flcopilot-dom-') as root:
    service=Service(Path(root),DemoAdapter())
    # Native service methods are real. Only the browser's fetch transport is replaced.
    def request(req):
        path=req['path'].removeprefix('/api/');d=req.get('data');status=200
        try:
            if path=='status':out=service.status()
            elif path=='assets':out=service.assets.list()
            elif path=='capabilities':out=service.capabilities()
            elif path=='history':out=service.journal.history()
            elif path=='settings':out=service.settings(d)
            elif path=='inspect':out=service.jobs.submit('Inspecting simulator',service.inspect)
            elif path=='prompt':out=service.jobs.submit('Preparing preview',lambda:service.prompt(d['prompt']))
            elif path=='execute':
                d.pop('focus_handoff',None);out=service.jobs.submit('Applying simulator changes',lambda:service.execute(d))
            elif path=='prepare':out=service.prepare(d)
            elif path=='plugin-scan':out=service.jobs.submit('Reading parameters',lambda:service.plugin_scan(d))
            elif path=='plugin-preview':out=service.jobs.submit('Preparing parameter preview',lambda:service.plugin_preview(d))
            elif path=='analyze':out=service.jobs.submit('Analyzing real fixture',lambda:service.analyze(d['asset']))
            elif path=='master':out=service.jobs.submit('Rendering real WAV',lambda:service.master(d))
            elif path=='midi':out=service.create_midi(d)
            elif path=='diagnostics':out=service.jobs.submit('Reading connection diagnostics',lambda:service.diagnostics(d.get('export',False)))
            elif path=='control-test-preview':out=service.jobs.submit('Preparing control test',lambda:service.control_test_preview(d))
            elif path=='restore-preview':out=service.jobs.submit('Preparing restore',lambda:service.restore_preview(d))
            elif path=='stop':out=service.executor.stop()
            elif path=='reset-stop':service.executor.reset_stop();out=service.status()
            elif path.startswith('jobs/'):out=service.jobs.get(path[5:])
            elif path=='import':
                raw=base64.b64decode(req['binary']);out=service.assets.import_stream(io.BytesIO(raw),len(raw),req['name'])
            elif path.startswith('file/'):
                f=service.assets.resolve(path[5:]);return {'status':200,'binary':base64.b64encode(f.read_bytes()).decode(),'type':'audio/wav'}
            else:raise ValueError('Unimplemented DOM-test route: '+path)
        except Exception as exc:out={'error':str(exc)};status=400
        return {'status':status,'data':out}
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=__import__('os').environ.get('FLCOPILOT_BROWSER') or __import__('shutil').which('chromium'),headless=True,args=['--no-sandbox'])
        page=browser.new_page(viewport={'width':1512,'height':1100},device_scale_factor=1)
        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        html=(P/'flcopilot/web/index.html').read_text().replace('<link rel="stylesheet" href="/style.css">','').replace('<script src="/app.js" defer></script>','').replace('<script src="/workbench.js" defer></script>','').replace('<script src="/review.js" defer></script>','').replace('<script src="/render.js" defer></script>','')
        page.set_content(html)
        page.add_style_tag(content=(P/'flcopilot/web/style.css').read_text())
        page.expose_function('__nativeRequest',request)
        page.evaluate('''()=>{
            Object.defineProperty(window,'sessionStorage',{value:{getItem:()=>"test-token",setItem:()=>{}}});
            window.fetch=async(path,opts={})=>{
                let req={path};if(opts.body){if(typeof opts.body==='string')req.data=JSON.parse(opts.body);else{
                    const bytes=new Uint8Array(await opts.body.arrayBuffer());let s='';for(let i=0;i<bytes.length;i+=8192)s+=String.fromCharCode(...bytes.subarray(i,i+8192));req.binary=btoa(s);req.name=decodeURIComponent(opts.headers['X-Filename']);}}
                const r=await window.__nativeRequest(req);return {ok:r.status===200,statusText:String(r.status),json:async()=>r.data,
                    blob:async()=>new Blob([Uint8Array.from(atob(r.binary),c=>c.charCodeAt(0))],{type:r.type})};
            };
        }''')
        print("DOM: Loading application",flush=True)
        page.add_script_tag(content=(P/'flcopilot/web/app.js').read_text())
        page.add_script_tag(content=(P/'flcopilot/web/workbench.js').read_text())
        print("DOM: Waiting for simulator inspection",flush=True)
        page.get_by_text(f'{len(service.adapter.tracks)} TRACKS',exact=True).wait_for()
        assert page.locator('#banner').inner_text().startswith('SIMULATOR')
        page.locator('#prompt').fill('Lower Drums by 2 dB');page.locator('#plan-prompt').click()
        page.locator('#plan-title').filter(has_text='Lower Drums').wait_for()
        assert page.locator('#apply').is_disabled()
        page.locator('[data-mode="assist"]').click();page.wait_for_function('!document.querySelector("#apply").disabled')
        page.evaluate("window.scrollTo(0,0)")
        page.screenshot(path=str(evidence/'Session_Simulator_Preview.png'),full_page=True)
        page.locator('#apply').click();page.locator('#run-result').get_by_text('verified',exact=True).wait_for()
        assert service.adapter.track(1)['volume_db']==-4
        print("DOM: Starting original control flows",flush=True)
        # v0.2: exact mute/stereo controls and separately approved compensation.
        page.wait_for_function('snapshot.tracks.find(t=>t.index===1).volume_db===-4')
        page.locator('.edit[data-track="2"]').click()
        page.locator('#edit-kind').select_option('mute')
        assert page.locator('#edit-mute-field').is_visible()
        page.locator('#edit-mute').select_option('true')
        page.locator('#preview-edit').click()
        page.wait_for_function('plan && plan.operations[0].kind==="mute"')
        assert service.adapter.track(2)['muted'] is False
        page.locator('#apply').click()
        page.wait_for_function('snapshot.tracks.find(t=>t.index===2).muted===true')
        page.locator('.edit[data-track="3"]').click()
        page.locator('#edit-kind').select_option('stereo')
        page.locator('#edit-value').fill('0.5')
        page.locator('#preview-edit').click()
        page.wait_for_function('plan && plan.operations[0].kind==="stereo"')
        page.locator('#apply').click()
        page.wait_for_function('snapshot.tracks.find(t=>t.index===3).stereo_separation===0.5')
        page.locator('[data-tab="history"]').click()
        page.locator('.preview-restore').first.click()
        page.wait_for_function('plan && plan.purpose==="restore"')
        assert service.adapter.track(3)['stereo_separation']==.5
        page.evaluate('window.scrollTo(0,0)')
        page.screenshot(path=str(evidence/'Verified_Restore_Preview.png'),full_page=True)
        page.locator('#apply').click()
        page.wait_for_function('snapshot.tracks.find(t=>t.index===3).stereo_separation===0')
        print("DOM: Starting plugin workbench",flush=True)
        # v0.3: real service discovery, unit conversion, preview, application and compensation.
        page.locator('[data-tab="plugins"]').click()
        assert page.locator('#wb-effect').input_value()=='6:0'
        call_count=len(service.adapter.calls)
        print("DOM: Scanning first window",flush=True)
        page.locator('#wb-scan').click()
        page.locator('.wb-select[data-index="129"]').wait_for()
        assert len(service.adapter.calls)==call_count
        assert 'partial map' in page.locator('#wb-coverage').inner_text()
        page.locator('.wb-select[data-index="129"]').click()
        page.locator('#wb-value').fill('-9')
        print("DOM: Preparing display preview",flush=True)
        page.locator('#wb-preview').click()
        page.wait_for_function('plan && plan.operations[0].kind==="parameter_display"')
        assert '-9 dB ± 0.1 dB' in page.locator('#plan-rows').inner_text()
        assert len(service.adapter.calls)==call_count
        revision=page.evaluate('wbRevision')
        page.locator('#apply').click()
        page.wait_for_function('revision=>plan===null && wbRevision>revision',arg=revision)
        assert service.adapter.display_parameter(6,0,129)['display']=='-9.000000 dB'
        page.locator('[data-tab="history"]').click()
        page.locator('.preview-restore').first.click()
        page.wait_for_function('plan && plan.purpose==="restore" && plan.operations[0].kind==="parameter_display"')
        revision=page.evaluate('wbRevision')
        page.locator('#apply').click()
        page.wait_for_function('revision=>plan===null && wbRevision>revision',arg=revision)
        assert service.adapter.params[(6,0,129)]['value']==.5
        page.locator('[data-tab="plugins"]').click()
        print("DOM: Scanning high parameter index",flush=True)
        page.locator('#wb-start').fill('2048');page.locator('#wb-query').fill('frequency')
        page.locator('#wb-scan').click()
        page.wait_for_function('!wbBusy')
        print('DOM: high-index scan status',page.locator('#wb-coverage').inner_text(),page.locator('#notice').inner_text(),flush=True)
        page.locator('.wb-select[data-index="2049"]').wait_for()
        page.locator('.wb-select[data-index="2049"]').click()
        assert page.locator('#wb-unit').inner_text()=='Hz'
        assert page.locator('#wb-value').input_value()=='1000'
        page.locator('#wb-value').fill('750')
        page.evaluate('window.scrollTo(0,0)')
        page.screenshot(path=str(evidence/'Plugin_Workbench_v040.png'),full_page=True)
        page.locator('#wb-next').click()
        page.wait_for_function('wbObservation && wbObservation.start===2560')
        assert 'No matching named controls' in page.locator('#wb-rows').inner_text()
        page.locator('#wb-start').fill('4096');page.locator('#wb-query').fill('attack')
        page.locator('#wb-scan').click()
        page.locator('.wb-select[data-index="4097"]').wait_for()
        assert page.locator('#wb-next').is_disabled()
        page.locator('.wb-select[data-index="4097"]').click()
        assert page.locator('#wb-value').input_value()=='20'
        page.locator('#wb-mode').select_option('normalized')
        assert page.locator('#wb-tolerance-field').is_hidden()
        page.locator('#wb-value').fill('.25');page.locator('#wb-preview').click()
        page.wait_for_function('plan && plan.operations[0].kind==="parameter" && plan.operations[0].parameter===4097')
        assert service.adapter.params[(6,0,4097)]['value']==.5
        page.locator('[data-tab="plugins"]').click()
        service.adapter.params[(6,0,4097)]['name']='<img src=x onerror="window.injected=true">'
        page.locator('#wb-query').fill('');page.locator('#wb-scan').click()
        page.locator('.wb-select[data-index="4097"]').wait_for()
        assert page.locator('#wb-rows img').count()==0
        assert page.evaluate('window.injected !== true')
        service.adapter.params[(6,0,4097)]['name']='Demo attack'
        page.locator('[data-tab="setup"]').click()
        print("DOM: Checking diagnostics",flush=True)
        page.locator('#check-connection').click()
        page.wait_for_function('document.querySelectorAll(".diagnostic-check").length===14')
        assert page.locator('#diagnostic-summary').inner_text().startswith('SIMULATOR')
        page.evaluate('window.scrollTo(0,0)')
        page.screenshot(path=str(evidence/'Connection_Readiness_Simulator.png'),full_page=True)
        page.locator('#export-diagnostics').click()
        page.locator('#diagnostic-exports .file-row').wait_for()
        assert page.locator('#diagnostic-local').is_hidden()
        page.locator('#control-test-track').fill('4')
        page.locator('#preview-control-test').click()
        page.wait_for_function('plan && plan.purpose==="control_test"')
        assert service.adapter.track(4)['volume_db']==-10.
        page.locator('#apply').click()
        page.wait_for_function('snapshot.tracks.find(t=>t.index===4).volume_db===-11')
        page.locator('[data-tab="history"]').click()
        page.locator('.preview-restore').first.click()
        page.wait_for_function('plan && plan.purpose==="restore"')
        page.locator('#apply').click()
        page.wait_for_function('snapshot.tracks.find(t=>t.index===4).volume_db===-10')
        print("DOM: Creating MIDI and audio",flush=True)
        page.locator('[data-tab="midi"]').click();page.locator('#make-midi').click();page.locator('#midi-result .file-row').wait_for()
        import numpy as np,soundfile as sf
        sr=44100;t=np.arange(4*sr)/sr;y=np.column_stack([.18*np.sin(2*np.pi*440*t)+.03*np.sin(2*np.pi*73*t),.17*np.sin(2*np.pi*440*t)])
        wave=Path(root)/'Synthetic_Test_Bounce.wav';sf.write(wave,y,sr,subtype='FLOAT')
        page.locator('[data-tab="audio"]').click();page.locator('#audio-files').set_input_files(str(wave))
        page.wait_for_function('document.querySelector("#audio-asset").value.length===32')
        page.locator('#analyze').click();page.locator('#audio-report h2').filter(has_text='Bounce analysis').wait_for()
        page.locator('#master').click();page.locator('#exports .file-row').first.wait_for(timeout=45000)
        assert page.locator('#exports .file-row').count()==4
        page.evaluate("window.scrollTo(0,0)")
        page.screenshot(path=str(evidence/'Audio_Lab_Synthetic_Result.png'),full_page=True)
        page.locator('[data-tab="history"]').click();page.locator('.history-row').first.wait_for()
        page.locator('[data-tab="setup"]').click();assert page.locator('.capability').count()==len(service.capabilities()['features'])
        page.locator('#stop').click();page.wait_for_function('document.querySelector("#banner").textContent.includes("STOP LATCHED")')
        page.locator('#reset-stop').click();page.wait_for_function('!document.querySelector("#banner").textContent.includes("STOP LATCHED")')
        page.set_viewport_size({'width':390,'height':844});page.locator('[data-tab="session"]').click()
        assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
        page.evaluate("window.scrollTo(0,0)")
        page.screenshot(path=str(evidence/'Mobile_Simulator.png'),full_page=True)
        page.locator('[data-tab="setup"]').click()
        assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
        page.locator('[data-tab="plugins"]').click()
        assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
        print("DOM: Collecting final report",flush=True)
        report={'app_version':service.status()['version'],'checks':['Simulator banner','Inspect-mode approval blocked','Prompt preview','Assist-mode approval','Actual simulator state readback','Real MIDI creation','Real audio upload through browser file object','Real loudness analysis','Real master + four exports','History rendering',f"{len(service.capabilities()['features'])} capability labels",'Stop/reset','390px page overflow check','Explicit mute preview and application','Stereo-separation preview and application','Verified journal restore preview','Separately approved restore readback','Fourteen diagnostic checks','Simulator cannot qualify host','Privacy-filtered report export UI','1 dB control-test preview','Approved 1 dB reduction','Separately approved test restore','Read-only plugin scan','Honest partial coverage','Display-target preview with units and tolerance','Approved display change','Separately approved display restore','High-index frequency and kHz conversion','Next-window search with empty matches','End-of-map pagination disabled','Seconds-to-ms conversion','Normalized alternative preview only','Plugin names escaped as data','390px plugin-workbench overflow check'],
            'page_errors':errors,'environment':'Linux Chromium 1512px and 390px; in-memory DOM harness calling real Service methods',
            'network_transport':'Fetch replaced by test harness. HTTP endpoints separately tested in pytest.',
            'browser_navigation_limit':'Ordinary localhost navigation was blocked by environment administrator policy; no policy was modified.',
            'live_fl_tested':False,'audio_fixture':'Synthetic generated sine mixture, not user audio'}
        (evidence/'browser_dom_report_v040.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
        browser.close()
        if errors:sys.exit(1)
    service.close()
