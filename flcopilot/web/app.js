"use strict";
const $=id=>document.getElementById(id), esc=x=>String(x??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const frag=location.hash.slice(1); if(frag){sessionStorage.setItem("flcopilot-token",frag);history.replaceState(null,"",location.pathname);} const token=sessionStorage.getItem("flcopilot-token")||"";
let status=null,snapshot=null,plan=null,editTrack=null,assets=[],activeJobs=0;
const number=(x,d=1)=>Number.isFinite(x)?x.toFixed(d):"—";
function notice(message,ok=false){$("notice").textContent=message;$("notice").className=ok?"ok":"";$("notice").hidden=false;}
async function api(path,data){const opts={headers:{Authorization:"Bearer "+token}};if(data!==undefined){opts.method="POST";opts.headers["Content-Type"]="application/json";opts.body=JSON.stringify(data);} const r=await fetch("/api/"+path,opts);const out=await r.json();if(!r.ok)throw Error(out.error||r.statusText);return out;}
async function job(path,data){activeJobs++;$("activity").hidden=false;$("activity-label").textContent="Starting local work…";try{let result=await api(path,data);if(!result.job)return result;for(;;){await new Promise(r=>setTimeout(r,300));let j=await api("jobs/"+result.job);$("activity-label").textContent=j.label;if(j.status==="error")throw Error(j.error);if(j.status==="complete")return j.result;}}finally{activeJobs--;if(!activeJobs)$("activity").hidden=true;}}
function action(id,fn){$(id).addEventListener("click",async()=>{const b=$(id);b.disabled=true;$("notice").hidden=true;try{await fn();}catch(e){notice(e.message);}finally{b.disabled=false;updateApproval();}});}
function tab(id){document.querySelectorAll(".tab").forEach(e=>e.classList.toggle("active",e.id===id));document.querySelectorAll(".nav").forEach(e=>e.classList.toggle("active",e.dataset.tab===id));$("section-name").textContent=id.toUpperCase();if(id==="history")loadHistory().catch(e=>notice(e.message));}
document.querySelectorAll(".nav").forEach(b=>b.onclick=()=>tab(b.dataset.tab));
async function refreshStatus(){status=await api("status");renderStatus();}
function renderStatus(){if(!status)return;$("planner-status").textContent=status.planner+". No action is executed by the planner.";$("lock-master").checked=status.locks.master;$("lock-parameters").checked=status.locks.parameters;$("windows-menu").checked=status.windows_menu_enabled;$("hotkey-status").textContent=status.hotkey||"Use the red Stop button.";document.querySelectorAll("[data-mode]").forEach(b=>b.classList.toggle("selected",b.dataset.mode===status.mode));$("mode-hint").textContent={inspect:"Read-only. Project changes are blocked.",assist:"Preview, then approve this exact plan.",finish:"One approved finishing pass. No unbounded autonomy."}[status.mode];let text=status.demo?"SIMULATOR MODE — Mixer data and DAW actions are simulated. Audio analysis, WAV exports, and MIDI files are real.":"LIVE ADAPTER — Session not yet inspected. Imported-audio tools work without FL Studio.";if(!status.demo&&snapshot)text="LIVE SESSION OBSERVED — Changes still require your approval. Windows/FL qualification for this release remains pending.";if(status.stopped)text="STOP LATCHED — Further work is blocked until in-flight operations settle and you reset stop in Setup.";if(status.blocked)text="WRITE BLOCKED — An earlier outcome is uncertain. Inspect FL and reconcile in the Run journal.";$("banner").textContent=text;$("banner").className="banner"+(status.stopped||status.blocked?" danger":status.demo?" demo":"");$("recovery").hidden=!status.blocked;updateApproval();}
async function settings(changes){status=await api("settings",changes);renderStatus();if(snapshot)renderTracks();}
document.querySelectorAll("[data-mode]").forEach(b=>b.onclick=()=>settings({mode:b.dataset.mode}).catch(e=>notice(e.message)));
for(const [id,key] of [["lock-master","master"],["lock-parameters","parameters"]])$(id).onchange=()=>settings({locks:{...status.locks,[key]:$(id).checked}}).catch(e=>{notice(e.message);renderStatus();});
$("windows-menu").onchange=()=>settings({windows_menu_enabled:$("windows-menu").checked}).catch(e=>{notice(e.message);renderStatus();});
async function inspect(){snapshot=await job("inspect",{});$("connection").textContent=snapshot.backend==="demo"?"SIMULATED SESSION":snapshot.connection.fl_app_version||"FL SESSION OBSERVED";$("session-name").textContent=snapshot.project.name||snapshot.project.project_name||"Current FL Studio project";renderTracks();await refreshStatus();window.dispatchEvent(new Event("flcopilot-inspected"));return snapshot;}
function renderTracks(){if(!snapshot)return;$("track-count").textContent=snapshot.tracks.length+" TRACKS";$("tracks").innerHTML=snapshot.tracks.map(t=>{let locked=status.locks.tracks.includes(t.index)||(t.index===0&&status.locks.master);return `<tr><td><input class="use-track" type="checkbox" data-track="${t.index}" aria-label="Include ${esc(t.name)} in gain staging" ${t.index&&!locked?"checked":""} ${t.index===0||locked?"disabled":""}></td><td><span class="tracknum">${String(t.index).padStart(2,"0")}</span><strong>${esc(t.name)}</strong><span class="fx">${esc((t.plugins||[]).map(p=>p.name).join(" · ")||"No loaded effects")}</span></td><td class="db">${number(t.volume_db)} dB</td><td>${Math.abs(t.pan||0)<.005?"C":Math.round(Math.abs(t.pan)*100)+(t.pan<0?" L":" R")}<span class="fx">Stereo ${number(t.stereo_separation,2)}</span></td><td><span class="mute-state ${t.muted?"muted":""}">${t.muted===true?"MUTED":t.muted===false?"ON":"UNKNOWN"}</span></td><td><input type="checkbox" class="track-lock" data-track="${t.index}" aria-label="Lock ${esc(t.name)}" ${locked?"checked":""} ${t.index===0?"disabled":""}></td><td><button class="edit" data-track="${t.index}" ${locked?"disabled":""}>Edit</button></td></tr>`;}).join("");$("mix").disabled=false;document.querySelectorAll(".track-lock").forEach(c=>c.onchange=()=>{const set=new Set(status.locks.tracks);c.checked?set.add(+c.dataset.track):set.delete(+c.dataset.track);settings({locks:{...status.locks,tracks:[...set]}}).catch(e=>notice(e.message));});document.querySelectorAll(".edit").forEach(b=>b.onclick=()=>openEdit(+b.dataset.track));}
function showPlan(p){
    plan=p;if(!p){notice("No high-confidence change was proposed.",true);return;}
    $("plan-empty").hidden=true;$("plan-content").hidden=false;$("plan-title").textContent=p.title;
    $("plan-state").textContent="REVIEW";$("plan-digest").textContent=p.digest;$("plan-warning").textContent=p.warning;
    $("plan-rows").innerHTML=p.operations.map((o,i)=>{
        const before=p.before[i], parameter=["parameter","parameter_display"].includes(o.kind);
        let old=parameter?before.parameter.value:o.kind==="load_effect"?"Empty insert":before.track[{volume:"volume_db",pan:"pan",rename:"name",mute:"muted",stereo:"stereo_separation"}[o.kind]];
        let requested=o.value;
        if(o.kind==="parameter_display"){old=before.parameter.display;requested=`${o.value.amount} ${o.value.unit} ± ${o.value.tolerance} ${o.value.unit}`;}
        if(o.kind==="mute"){old=old?"Muted":"Unmuted";requested=o.value?"Muted":"Unmuted";}
        return `<div class="plan-row"><small>INSERT ${o.track} · ${esc(o.kind.toUpperCase())}</small><strong>${esc(before.track.name)}</strong>${parameter?`<small>${esc(before.parameter.plugin)} · slot ${o.slot+1} · index ${o.parameter} · ${esc(before.parameter.name)}</small>`:""}<div class="change">${esc(typeof old==="number"?number(old,2):old)} → ${esc(requested)}</div><small>${esc(o.reason)}</small></div>`;
    }).join("");
    tab("session");updateApproval();
}
function updateApproval(){if(!status)return;let valid=plan&&plan.expires*1000>Date.now()&&status.mode!=="inspect"&&!status.stopped&&!status.blocked&&JSON.stringify(plan.locks)===JSON.stringify(status.locks);$("apply").disabled=!valid;$("approval-help").textContent=status.mode==="inspect"?"Select Assist or Finish to authorize execution.":plan&&JSON.stringify(plan.locks)!==JSON.stringify(status.locks)?"Protection locks changed. Prepare a new plan.":"Approval covers this plan only. No automatic save or guaranteed rollback.";}
function openEdit(index){editTrack=snapshot.tracks.find(t=>t.index===index);$("edit-target").textContent="Insert "+index+" · "+editTrack.name;$("edit-kind").value="volume";editKind();$("edit-dialog").showModal();}
function editKind(){
    const kind=$("edit-kind").value, value=$("edit-value");
    $("parameter-fields").hidden=kind!=="parameter";
    $("edit-value-field").hidden=kind==="mute";
    $("edit-mute-field").hidden=kind!=="mute";
    $("param-values").hidden=true;
    value.type=["volume","pan","parameter","stereo"].includes(kind)?"number":"text";
    value.step="0.01";
    value.value=kind==="volume"?editTrack.volume_db:kind==="pan"?editTrack.pan:
        kind==="stereo"?editTrack.stereo_separation:kind==="rename"?editTrack.name:
        kind==="parameter"?"0.5":"Fruity Limiter";
    $("edit-mute").value=editTrack.muted?"true":"false";
    $("edit-help").textContent={volume:"Maximum 12 dB per operation. Nothing moves before approval.",
        pan:"-1 is hard left; 0 is center; +1 is hard right.",rename:"Exact name, up to 64 characters.",
        mute:"Set an explicit mute state. This is not a toggle, Solo, or plugin bypass.",
        stereo:"FL stereo-separation units: -1 to +1, with 0 unchanged. Verify the result in FL; this is not an audio quality judgment.",
        parameter:"Read the exact loaded plugin parameter first. Value is normalized 0–1, not the displayed unit.",
        load_effect:"Experimental: destination must have no effects. Exact native menu name required. Focus FL during the 5-second execution handoff."}[kind];
}
$("edit-kind").onchange=editKind;$("close-dialog").onclick=()=>$("edit-dialog").close();
action("inspect",inspect);
action("plan-prompt",async()=>{showPlan((await job("prompt",{prompt:$("prompt").value})).plan);});$("prompt").onkeydown=e=>{if(e.key==="Enter")$("plan-prompt").click();};
action("preview-edit",async()=>{const kind=$("edit-kind").value;let op={kind,track:editTrack.index,value:kind==="mute"?$("edit-mute").value==="true":["volume","pan","parameter","stereo"].includes(kind)?Number($("edit-value").value):$("edit-value").value};if(kind==="parameter"){op.slot=+$("edit-slot").value;op.parameter=+$("edit-param").value;}const p=await api("prepare",{title:"Adjust "+editTrack.name,operations:[op]});$("edit-dialog").close();showPlan(p);});
action("read-params",async()=>{$("param-values").textContent=JSON.stringify(await api(`parameters?track=${editTrack.index}&slot=${+$("edit-slot").value}`),null,2);$("param-values").hidden=false;});
action("apply",async()=>{const p=plan;const insert=p.operations.some(o=>o.kind==="load_effect");if(insert)notice("Focus FL Studio now. Dispatch starts after a 5-second handoff; leave the main FL window untouched.",true);const r=await job("execute",{plan_id:p.id,digest:p.digest,confirm:true,focus_handoff:insert});plan=null;$("plan-state").textContent=r.status.toUpperCase();$("run-result").hidden=false;$("run-result").innerHTML=`<div class="result-title"><h2>${r.demo?"Simulator":"Execution"} result</h2><span class="pill">${esc(r.status)}</span></div><p>${esc(r.error||"Changes passed independent readback. Artistic quality was not evaluated.")}</p><details><summary>Receipts and evidence</summary><pre>${esc(JSON.stringify(r,null,2))}</pre></details>`;await refreshStatus();if(r.status==="verified")await inspect();else notice(r.error||"Execution stopped. Review the receipt.");});
action("mix",async()=>{const tracks=[...document.querySelectorAll(".use-track:checked")].map(e=>+e.dataset.track);if(!tracks.length)throw Error("Select at least one unlocked non-master track.");const result=await job("mix",{tracks,seconds:+$("observe-seconds").value});if(result.plan)showPlan(result.plan);else notice(result.message,true);});
action("stop",async()=>{await api("stop",{});await refreshStatus();});action("reset-stop",async()=>{await api("reset-stop",{});await refreshStatus();notice("Stop reset. Reinspect before preparing new changes.",true);});
async function refreshAssets(){assets=await api("assets");const audio=assets.filter(a=>a.kind==="input"||a.kind==="audio");for(const id of ["audio-asset","reference-asset"]){const old=$(id).value;$(id).innerHTML=`<option value="">${id==="audio-asset"?"Choose working bounce":"Choose reference / candidate"}</option>`+audio.map(a=>`<option value="${a.id}">${esc(a.name)} · ${esc(a.kind)}</option>`).join("");if(audio.some(a=>a.id===old))$(id).value=old;}}
async function upload(files){for(const f of files){if(f.size>300*1024*1024)throw Error("Upload exceeds 300 MiB.");notice("Importing "+f.name+" locally…",true);const r=await fetch("/api/import",{method:"POST",headers:{Authorization:"Bearer "+token,"Content-Type":"application/octet-stream","X-Filename":encodeURIComponent(f.name)},body:f});const a=await r.json();if(!r.ok)throw Error(a.error);await refreshAssets();$("audio-asset").value=a.id;notice("Imported "+a.name+". The original file was not changed.",true);}}
$("audio-files").onchange=()=>upload($("audio-files").files).catch(e=>notice(e.message));$("dropzone").ondragover=e=>{e.preventDefault();$("dropzone").classList.add("drag");};$("dropzone").ondragleave=()=>$("dropzone").classList.remove("drag");$("dropzone").ondrop=e=>{e.preventDefault();$("dropzone").classList.remove("drag");upload(e.dataTransfer.files).catch(e=>notice(e.message));};
function selectedAsset(){const asset=$("audio-asset").value;if(!asset)throw Error("Import and select a working bounce first.");return asset;}
function metrics(m){return `<div class="metric-grid">${[["LOUDNESS",m.integrated_lufs,"LUFS integrated"],["OVERSAMPLED PEAK",m.oversampled_peak_dbtp_estimate,"dBTP estimate · not certified"],["CREST FACTOR",m.crest_db,"dB"],["STEREO CORRELATION",m.stereo_correlation,"-1 to +1 · mono may be undefined"]].map(([l,v,u])=>`<div class="metric"><small>${l}</small><strong>${number(v,l==="STEREO CORRELATION"?2:1)}</strong><span>${u}</span></div>`).join("")}</div>`;}
function audioReport(title,report,measured){$("audio-report").hidden=false;$("audio-report").innerHTML=`<h2>${esc(title)}</h2>${metrics(measured)}${(report.warnings||measured.warnings||[]).map(w=>`<p class="warning">${esc(w)}</p>`).join("")}<details><summary>Technical report</summary><pre>${esc(JSON.stringify(report,null,2))}</pre></details>`;}
async function fileBlob(asset){const r=await fetch("/api/file/"+asset.id,{headers:{Authorization:"Bearer "+token}});if(!r.ok){const e=await r.json();throw Error(e.error);}return URL.createObjectURL(await r.blob());}
function showFiles(element,files,title="Your exports"){element.hidden=false;element.innerHTML=`<h2>${esc(title)}</h2>`;for(const f of files){const row=document.createElement("div");row.className="file-row";row.innerHTML=`<div><strong>${esc(f.name)}</strong><small>${esc(f.kind)} · SHA-256 ${esc(f.sha256.slice(0,16))}…</small></div><div class="file-buttons"></div>`;const controls=row.querySelector(".file-buttons");const download=document.createElement("button");download.className="secondary";download.textContent="Save file ↗";download.onclick=async()=>{try{const url=await fileBlob(f);const a=document.createElement("a");a.href=url;a.download=f.name;a.click();setTimeout(()=>URL.revokeObjectURL(url),60000);}catch(e){notice(e.message);}};controls.append(download);if(f.kind==="audio"){const audition=document.createElement("button");audition.className="quiet";audition.textContent="Audition";audition.onclick=async()=>{try{document.querySelectorAll("audio").forEach(a=>a.pause());const audio=document.createElement("audio");audio.controls=true;audio.src=await fileBlob(f);controls.replaceChild(audio,audition);audio.play().catch(()=>{});}catch(e){notice(e.message);}};controls.append(audition);}element.append(row);}}
action("refresh-assets",refreshAssets);action("analyze",async()=>{const r=await job("analyze",{asset:selectedAsset()});audioReport("Bounce analysis",r,r);});
action("master",async()=>{const r=await job("master",{asset:selectedAsset(),target_lufs:+$("target-lufs").value,ceiling_dbtp:+$("ceiling").value,preserve_dynamics:$("preserve").checked});audioReport("Rendered master · measured result",r.report,r.report.after);showFiles($("exports"),r.files,"Master + level-matched A/B");await refreshAssets();notice("Created four new export files. Original audio and FL project were not modified.",true);});
action("compare",async()=>{const b=$("reference-asset").value;if(!b)throw Error("Choose a second audio file.");const r=await job("compare",{a:selectedAsset(),b});audioReport("Candidate / reference comparison",r,r.candidate);});
action("make-midi",async()=>{const r=await api("midi",{bpm:+$("midi-bpm").value,key:$("midi-key").value,bars:+$("midi-bars").value,seed:+$("midi-seed").value,swing:+$("midi-swing").value});showFiles($("midi-result"),[r.file],`${r.report.bars} bars · ${r.report.bpm} BPM · ${r.report.key}`);notice(r.report.note,true);});
async function loadHistory(){
    await refreshStatus();
    const rows=await api("history");
    $("history-items").innerHTML=rows.length?rows.map(r=>`<div class="panel history-row">
        <div class="history-top"><div><h2>${esc(r.plan.title)}</h2><small>${esc(new Date(r.created*1000).toLocaleString())} · ${esc(r.plan.backend)} · ${esc(r.plan.purpose||"adjustment")}</small></div><span class="pill">${esc(r.status)}</span></div>
        ${r.status==="verified"&&!r.plan.operations.some(o=>o.kind==="load_effect")?`<div class="restore-row"><button class="secondary preview-restore" data-plan="${esc(r.id)}">Preview restore</button><small>Listed controls only. Changed state blocks recovery; no project rollback.</small></div>`:""}
        <details><summary>View exact plan and execution receipt</summary><pre>${esc(JSON.stringify(r,null,2))}</pre></details></div>`).join(""):'<div class="panel"><p>No change plans have been prepared yet.</p></div>';
    document.querySelectorAll(".preview-restore").forEach(button=>button.onclick=async()=>{
        button.disabled=true;
        try{const result=await job("restore-preview",{plan_id:button.dataset.plan});showPlan(result.plan);notice(result.warning,true);}
        catch(error){notice(error.message);}finally{button.disabled=false;}
    });
}
action("refresh-history",loadHistory);action("reconcile",async()=>{const s=await inspect();if(!window.confirm("Check the current state in FL yourself. Acknowledge it and clear the uncertainty block? This will NOT undo earlier changes."))return;await api("reconcile",{digest:s.reconcile_digest,acknowledge:true});await loadHistory();notice("Acknowledged the observed state. No rollback was performed.",true);});
action("probe-menu",async()=>{notice("Focus the main FL window now. Native menu observation begins after a 5-second handoff.",true);const r=await job("menu-probe",{});$("menu-result").textContent=JSON.stringify(r,null,2);$("menu-result").hidden=false;});
async function boot(){await refreshStatus();await refreshAssets();const c=await api("capabilities");$("capabilities").innerHTML=c.features.map(f=>`<div class="capability"><strong>${esc(f.name)}</strong><span class="badge ${["experimental","unsupported","manual handoff"].includes(f.status)?"warn":""}">${esc(f.status)}</span><p>${esc(f.detail)}</p></div>`).join("");if(status.demo)await inspect();}boot().catch(e=>notice(e.message));setInterval(updateApproval,1000);

function showDiagnostics(report){
    $("diagnostic-summary").textContent=report.summary+" · Control proof: "+report.control_evidence.status;
    $("diagnostic-checks").innerHTML=report.checks.map(c=>`<div class="diagnostic-check"><div><strong>${esc(c.label)}</strong><span class="badge ${c.status==="pass"?"":"warn"}">${esc(c.status.toUpperCase().replaceAll("_"," "))}</span></div><p>${esc(c.detail)}</p></div>`).join("");
    $("diagnostic-local").hidden=!report.local_details;
    $("diagnostic-details").textContent=JSON.stringify(report.local_details||{},null,2);
}
action("check-connection",async()=>{showDiagnostics(await job("diagnostics",{}));});
action("export-diagnostics",async()=>{
    const result=await job("diagnostics",{export:true});showDiagnostics(result.report);
    showFiles($("diagnostic-exports"),result.files,"Connection report · private details omitted");
    notice("Created a diagnostics file without paths, device names, project content, or session tokens. Review it before sharing.",true);
});
action("preview-control-test",async()=>{
    const result=await job("control-test-preview",{track:Number($("control-test-track").value)});
    showPlan(result.plan);
    notice("Preview only: a 1 dB reduction on the selected insert. After approval, use Run journal → Preview restore for a separate return-to-original plan.",true);
});
