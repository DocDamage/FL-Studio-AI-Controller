"use strict";
// Folder consent is deliberately absent from MCP. No paths are persisted in JS.
let renderWatch=null, renderWatchBusy=false, renderWatchPolling=false, renderSeenAsset=null;
function renderWatchDraw(){
    const active=renderWatch && ["queued","watching","importing"].includes(renderWatch.status);
    for(const id of ["render-folder","render-timeout","render-consent"]){$(id).disabled=!!active || renderWatchBusy;}
    $("render-arm").disabled=!!active || renderWatchBusy;
    $("render-cancel").disabled=!active || !!renderWatch?.cancel_requested || renderWatchBusy;
    let text="No folder is being watched.";
    if(renderWatch){
        const messages={queued:"Armed. Export one new file now; the intake worker is queued.",
            watching:`Armed. Export one new audio file in FL Studio (up to ${renderWatch.timeout} seconds).`,
            importing:"Verifying the exported bytes before publishing a local copy…",
            complete:"Captured a verified copy. FL rendering and session provenance were not verified.",
            cancelled:"Watch cancelled. Existing exports were not changed.",
            error:renderWatch.error||"No render was imported. Choose a clean folder and arm again."};
        text=messages[renderWatch.status]||"Checking export intake…";
        if(active && renderWatch.cancel_requested)text="Cancellation requested; waiting for the intake to settle…";
    }
    $("render-watch-state").textContent=text;
    const record=renderWatch?.status==="complete"?renderWatch.result:null;
    $("render-captured").hidden=!record;
    $("render-captured-name").textContent=record?`${record.name} · SHA-256 ${record.sha256.slice(0,16)}…`:"";
}
async function renderWatchRefresh(){
    if(renderWatchPolling)return;
    renderWatchPolling=true;
    try{
        const response=await api("render-watch");renderWatch=response.watch;renderWatchDraw();
        const record=renderWatch?.status==="complete"?renderWatch.result:null;
        if(record && record.id!==renderSeenAsset){
            await refreshAssets();$("audio-asset").value=record.id;renderSeenAsset=record.id;
        }
    }finally{renderWatchPolling=false;}
}
async function renderWatchAction(fn){
    renderWatchBusy=true;renderWatchDraw();
    try{await fn();await renderWatchRefresh();}
    catch(error){notice(error.message);}
    finally{renderWatchBusy=false;renderWatchDraw();}
}
$("render-arm").onclick=()=>renderWatchAction(async()=>{
    if(!$("render-consent").checked)throw Error("Confirm one-file access to this exact local export folder first.");
    const timeout=Number($("render-timeout").value);
    if(!Number.isInteger(timeout)||timeout<5||timeout>600)throw Error("Choose a whole-number wait limit from 5 to 600 seconds.");
    await api("render-watch",{folder:$("render-folder").value,timeout,confirm_folder:true});
    $("render-consent").checked=false;
});
$("render-cancel").onclick=()=>renderWatchAction(async()=>{
    if(!renderWatch)throw Error("No current watch to cancel.");
    await api("render-watch-cancel",{watch_id:renderWatch.watch_id});
});
function renderCaptured(){
    if(renderWatch?.status!=="complete" || !renderWatch.result)throw Error("Capture a new export first.");
    return renderWatch.result;
}
action("render-analyze",async()=>{
    const record=renderCaptured();
    const report=await job("analyze",{asset:record.id});
    audioReport("Captured bounce analysis",report,report);
});
async function renderUse(side){
    const record=renderCaptured();
    await reviewRefresh();$(side).value=record.id;
    // A new source invalidates any earlier matching-range confirmation.
    $("review-same-range").checked=false;
    tab("review");notice("Bounce selected. Confirm both exports used the same range and settings before building A/B.",true);
}
action("render-use-before",()=>renderUse("review-a"));
action("render-use-after",()=>renderUse("review-b"));
document.querySelector('[data-tab="audio"]').addEventListener("click",()=>renderWatchRefresh().catch(e=>notice(e.message)));
renderWatchRefresh().catch(e=>notice(e.message));
const renderWatchTimer=setInterval(()=>{
    if($("audio").classList.contains("active") || (renderWatch && ["queued","watching","importing"].includes(renderWatch.status))){
        renderWatchRefresh().catch(e=>notice(e.message));
    }
},750);
window.addEventListener("beforeunload",()=>clearInterval(renderWatchTimer));
