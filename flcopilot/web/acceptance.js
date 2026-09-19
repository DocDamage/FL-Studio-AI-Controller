"use strict";
// Desktop checklist only. Never fills observations automatically or authorizes FL.
let acceptanceState=null, acceptanceDirty=false, acceptanceBusy=false;
let acceptanceEvidenceGeneration=0;
const acceptanceFields={date:"acceptance-date",windows_build:"acceptance-windows",fl_studio_build:"acceptance-fl",project_label:"acceptance-project"};
function acceptanceButtons(){
    const ready=acceptanceState && !acceptanceState.load_error;
    for(const id of ["acceptance-save","acceptance-reload","acceptance-evidence-refresh"]){$(id).disabled=acceptanceBusy;}
    $("acceptance-save").disabled=acceptanceBusy||!ready;
    $("acceptance-progress").disabled=acceptanceBusy||!ready||acceptanceDirty;
    $("acceptance-complete").disabled=acceptanceBusy||!ready||acceptanceDirty||!acceptanceState?.runtime.native_host_eligible;
    if(!acceptanceState)return;
    const passed=Object.values(acceptanceState.record.tests).filter(v=>v==="pass").length;
    $("acceptance-state").textContent=acceptanceState.load_error?
        "Saved checklist is unreadable and was not overwritten. Preserve render-acceptance-draft.json, move it aside, then restart.":
        `${acceptanceDirty?"Unsaved edits — export is disabled":"Saved revision "+acceptanceState.revision} · ${passed}/11 saved observations passed · ${acceptanceState.runtime.app_mode} / Python ${acceptanceState.runtime.python_version}. `+
        (acceptanceState.runtime.native_host_eligible?"Live connection is checked when exporting a completed record.":"Progress reports only here; completed acceptance requires Windows with the live adapter.");
}
function acceptanceChanged(){acceptanceDirty=true;$("acceptance-export").hidden=true;acceptanceButtons();}
function acceptanceDraw(state){
    acceptanceState=state;acceptanceDirty=false;$("acceptance-form").hidden=state.load_error;
    for(const [field,id] of Object.entries(acceptanceFields))$(id).value=state.record[field]||"";
    $("acceptance-saved").checked=state.record.saved_project_copy_confirmed===true;
    $("acceptance-notes").value=(state.record.notes||[]).join("\n");
    $("acceptance-private").value=(state.record.private_notes||[]).join("\n");
    $("acceptance-checks").replaceChildren();
    for(const [name,description] of Object.entries(state.checks)){
        const label=document.createElement("label");label.className="field diagnostic-check";
        const title=document.createElement("span");title.textContent=description;
        const select=document.createElement("select");select.dataset.check=name;select.id="acceptance-check-"+name;
        for(const [value,text] of [["not_run","Not tested"],["pass","Pass — I observed it"],["fail","Fail"],["blocked","Blocked"]]){
            const option=document.createElement("option");option.value=value;option.textContent=text;select.append(option);
        }
        select.value=state.record.tests[name];select.addEventListener("change",acceptanceChanged);
        label.append(title,select);$("acceptance-checks").append(label);
    }
    acceptanceButtons();
}
function acceptanceOptions(id,rows,selected,placeholder){
    const select=$(id);select.replaceChildren(new Option(placeholder,""));
    for(const row of rows)select.append(new Option(row.label,row.id));
    if(selected&&!rows.some(r=>r.id===selected))select.append(new Option("Saved selection unavailable — choose again",selected));
    select.value=selected||"";
}
async function acceptanceEvidence(useSaved=false){
    const generation=++acceptanceEvidenceGeneration;
    const [audio,reviews]=await Promise.all([api("assets"),api("reviews")]);
    if(generation!==acceptanceEvidenceGeneration||!acceptanceState)return;
    const selected=useSaved?[...(acceptanceState.assets||[])]:[$("acceptance-a").value,$("acceptance-b").value];
    const review=useSaved?acceptanceState.review_id:$("acceptance-review").value;
    const watched=audio.filter(a=>a.kind==="input"&&a.source==="watched_fl_export").map(a=>({id:a.id,label:a.name}));
    for(const [i,id] of ["acceptance-a","acceptance-b"].entries())acceptanceOptions(id,watched,selected[i],"Choose a captured bounce");
    acceptanceOptions("acceptance-review",reviews.filter(r=>r.status==="ready").map(r=>({id:r.review_id,label:r.title})),review,"Choose a ready review (latest 50)");
}
async function acceptanceLoad(){
    if(acceptanceDirty&&!window.confirm("Discard unsaved checklist changes and reload the saved revision?"))return;
    acceptanceDraw(await api("render-acceptance"));
    $("acceptance-export").hidden=true;await acceptanceEvidence(true);
}
function acceptancePayload(){
    const fields={};for(const [name,id] of Object.entries(acceptanceFields))fields[name]=$(id).value.trim()||null;
    fields.saved_project_copy_confirmed=$("acceptance-saved").checked;
    fields.tests=Object.fromEntries([...$("acceptance-checks").querySelectorAll("select")].map(s=>[s.dataset.check,s.value]));
    for(const [name,id] of [["notes","acceptance-notes"],["private_notes","acceptance-private"]])fields[name]=$(id).value.split("\n").map(t=>t.trim()).filter(Boolean);
    return {expected_revision:acceptanceState.revision,fields,assets:[$("acceptance-a").value,$("acceptance-b").value].filter(Boolean),review_id:$("acceptance-review").value||null};
}
async function acceptanceRun(fn){
    if(acceptanceBusy)return;acceptanceBusy=true;
    // Lock the editor while requests are in flight, so a response cannot erase typing.
    for(const el of $("acceptance-form").querySelectorAll("input,select,textarea"))el.disabled=true;
    acceptanceButtons();
    try{await fn();}catch(error){notice(error.message);}
    finally{acceptanceBusy=false;for(const el of $("acceptance-form").querySelectorAll("input,select,textarea"))el.disabled=false;acceptanceButtons();}
}
$("acceptance-reload").onclick=()=>acceptanceRun(acceptanceLoad);
$("acceptance-evidence-refresh").onclick=()=>acceptanceRun(()=>acceptanceEvidence());
$("acceptance-save").onclick=()=>acceptanceRun(async()=>{
    const saved=await api("render-acceptance",acceptancePayload());
    acceptanceDraw(saved);await acceptanceEvidence(true);notice("Checklist saved locally. No FL controls or audio were changed.",true);
});
async function acceptanceExport(completed){
    if(acceptanceDirty)throw Error("Save or reload your checklist before exporting.");
    const prompt=completed?"Confirm that you personally performed every passing test in a native Windows/FL session on a saved project copy. Verify current evidence and export the completed record?":"Export the saved progress report? Shared notes and version text will be included; private notes will not.";
    if(!window.confirm(prompt))return;
    $("acceptance-export").hidden=true;
    const result=await job("render-acceptance-export",{expected_revision:acceptanceState.revision,completed,confirm:true});
    showFiles($("acceptance-export"),[result.file],completed?"Completed human acceptance record":"Acceptance progress report");
    notice(result.note,true);
}
$("acceptance-progress").onclick=()=>acceptanceRun(()=>acceptanceExport(false));
$("acceptance-complete").onclick=()=>acceptanceRun(()=>acceptanceExport(true));
for(const el of $("acceptance-form").querySelectorAll("input,select,textarea"))el.addEventListener("input",acceptanceChanged);
document.querySelector('[data-tab="setup"]').addEventListener("click",()=>{
    if(!acceptanceState)acceptanceRun(acceptanceLoad);
});
window.addEventListener("beforeunload",event=>{if(acceptanceDirty){event.preventDefault();event.returnValue="";}});
