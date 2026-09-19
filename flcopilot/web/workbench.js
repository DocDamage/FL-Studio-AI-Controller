"use strict";
// All controls come from one expiring server observation; never derive plugin indices from names.
let wbObservation=null, wbControl=null, wbBusy=false, wbRevision=0;
function wbInvalidate(){
    wbRevision++;wbObservation=null;wbControl=null;
    $("wb-next").disabled=true;$("wb-editor").hidden=true;
    $("wb-control-name").textContent="Select a parameter";
    $("wb-control-source").textContent="Scan again to obtain a current observation.";
    $("wb-coverage").textContent="Not scanned for this selection. No controls have moved.";
    $("wb-rows").innerHTML='<tr><td colspan="4" class="empty">Scan the selected index window.</td></tr>';
}
function wbEffects(){
    const previous=$("wb-effect").value;
    const effects=(snapshot?.tracks||[]).flatMap(t=>(t.plugins||[]).map(p=>({
        value:`${t.index}:${p.slot_index}`,label:`Insert ${t.index} · ${t.name} / slot ${p.slot_index+1} · ${p.name}`})));
    $("wb-effect").innerHTML='<option value="">Choose a loaded effect</option>'+effects.map(e=>`<option value="${esc(e.value)}">${esc(e.label)}</option>`).join("");
    $("wb-effect").value=effects.some(e=>e.value===previous)?previous:
        status?.demo&&effects.some(e=>e.value==="6:0")?"6:0":effects[0]?.value||"";
    wbInvalidate();
}
window.addEventListener("flcopilot-inspected",wbEffects);
for(const id of ["wb-effect","wb-query","wb-start","wb-window"])$(id).addEventListener("input",wbInvalidate);
action("wb-refresh",async()=>{await inspect();notice("Loaded effects refreshed. Scanning remains read-only.",true);});
function wbRequest(){
    const value=$("wb-effect").value;
    if(!/^\d+:\d+$/.test(value))throw Error("Inspect the session and choose a loaded effect first.");
    const [track,slot]=value.split(":").map(Number);
    return {track,slot,start:Number($("wb-start").value),max_indices:Number($("wb-window").value),query:$("wb-query").value};
}
async function wbScan(start){
    if(wbBusy)throw Error("A parameter scan is already running.");
    const request=wbRequest();if(start!==undefined)request.start=start;
    wbBusy=true;wbInvalidate();const revision=wbRevision;
    for(const id of ["wb-effect","wb-query","wb-start","wb-window","wb-scan","wb-refresh"])$(id).disabled=true;
    try{
        const result=await job("plugin-scan",request);
        if(revision!==wbRevision)throw Error("The selection or session was refreshed during scanning; scan again.");
        wbObservation=result;
        $("wb-start").value=request.start;
        $("wb-coverage").textContent=`${result.demo?"SIMULATED · ":""}Raw indices ${result.start}–${Math.max(result.start,result.end_exclusive-1)} / ${result.reported_count} reported · ${result.examined_count} examined · ${result.parameters.length} matching named controls. ${result.complete?"Full raw range covered.":result.has_more?"More indices remain; this is a partial map.":"This window reaches the end; earlier indices are not included."}${result.address_limit_reached?" App index limit reached.":""}`;
        $("wb-next").disabled=result.next_start===null;
        $("wb-rows").innerHTML=result.parameters.length?result.parameters.map(p=>`<tr><td><span class="tracknum">${p.index}</span><strong>${esc(p.name)}</strong></td><td>${esc(p.display??"Unavailable")}</td><td class="db">${number(p.normalized,4)}</td><td><button class="wb-select edit" data-index="${p.index}" ${!p.can_normalized&&!p.can_display?"disabled":""}>Select</button></td></tr>`).join(""):
            '<tr><td colspan="4" class="empty">No matching named controls in this window. Try another search or continue to the next indices.</td></tr>';
        document.querySelectorAll(".wb-select").forEach(b=>b.onclick=()=>wbSelect(Number(b.dataset.index)));
    }finally{
        wbBusy=false;
        for(const id of ["wb-effect","wb-query","wb-start","wb-window","wb-scan","wb-refresh"])$(id).disabled=false;
    }
}
action("wb-scan",()=>wbScan());
$("wb-next").onclick=async()=>{try{if(wbObservation?.next_start==null)throw Error("Scan a fresh window first.");await wbScan(wbObservation.next_start);}catch(e){notice(e.message);}};
function wbSelect(index){
    wbControl=wbObservation?.parameters.find(p=>p.index===index);
    if(!wbControl)return;
    $("wb-control-name").textContent=wbControl.name;
    $("wb-control-source").textContent=`${wbObservation.plugin} · insert ${wbObservation.track} · slot ${wbObservation.slot+1} · raw index ${index}`;
    $("wb-current-display").textContent=wbControl.display||"No display readback";
    $("wb-current-normalized").textContent=`Normalized ${number(wbControl.normalized,4)}`;
    $("wb-mode").querySelector('[value="display"]').disabled=!wbControl.can_display;
    $("wb-mode").querySelector('[value="normalized"]').disabled=!wbControl.can_normalized;
    $("wb-mode").value=wbControl.can_display?"display":"normalized";
    $("wb-editor").hidden=false;wbMode();
}
function wbMode(){
    if(!wbControl)return;
    const display=$("wb-mode").value==="display", unit=wbControl.unit;
    $("wb-tolerance-field").hidden=!display;
    $("wb-unit").textContent=display?unit:"Unitless normalized value · 0–1";
    $("wb-tolerance-unit").textContent=display?unit:"";
    $("wb-value").value=display?wbControl.amount:wbControl.normalized;
    $("wb-tolerance").value=unit==="Hz"?"1":"0.1";
    $("wb-control-warning").textContent=display?"Stop playback and recording in FL. The search may move through intermediate values. Approval does not guarantee that the target is reachable.":"Use a known normalized value only. This is not a percentage or a guess at the knob's engineering units.";
}
$("wb-mode").onchange=wbMode;
action("wb-preview",async()=>{
    if(!wbObservation||!wbControl)throw Error("Select a control from a fresh scan.");
    if(!$("wb-value").value.trim())throw Error("Enter a requested value.");
    const mode=$("wb-mode").value;
    if(mode==="display"&&!$("wb-tolerance").value.trim())throw Error("Enter the readback tolerance.");
    const value=mode==="display"?{amount:Number($("wb-value").value),unit:wbControl.unit,tolerance:Number($("wb-tolerance").value)}:Number($("wb-value").value);
    const result=await job("plugin-preview",{observation_id:wbObservation.observation_id,parameter:wbControl.index,mode,value});
    showPlan(result.plan);notice("Preview prepared from observed controls. Nothing has been applied.",true);
});
