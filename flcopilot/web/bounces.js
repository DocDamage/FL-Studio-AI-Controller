"use strict";
// Library notes are inert user data. This module never prepares or executes DAW plans.
let bounceSelected=null, bounceOffset=0, bounceNext=null, bounceRequest=0, bounceOpenRequest=0;
let bounceTimer=null, bounceDirty=false, bounceBusy=false;
function bounceMarkDirty(){bounceDirty=true;$("bounce-revision").textContent="Unsaved label or notes";}
function bounceDiscard(){return !bounceDirty||window.confirm("Discard unsaved bounce label or notes?");}
function bounceShow(row){
    bounceSelected=row;bounceDirty=false;$("bounce-editor").hidden=false;
    $("bounce-name").textContent=row.name;$("bounce-label").value=row.label;$("bounce-note").value=row.note;
    const date=row.imported_at?new Date(row.imported_at*1000).toLocaleString():"Date not recorded";
    $("bounce-source-detail").textContent=`${row.source==="watched"?"Watched export":"Manual import"} · ${date} · ${row.bytes===null?"Size not recorded":number(row.bytes/1048576,2)+" MiB"}`;
    $("bounce-revision").textContent=`Saved revision ${row.revision}`;
    $("bounce-verification").textContent="Stored hash: "+row.sha256+". Not rechecked by listing.";
}
async function bounceOpen(id){
    if(bounceBusy||!bounceDiscard())return;
    const generation=++bounceOpenRequest;
    const row=await api("bounce-get",{asset:id});
    if(generation===bounceOpenRequest)bounceShow(row);
}
async function bounceRefresh(reset=false){
    if(reset)bounceOffset=0;
    const generation=++bounceRequest;
    const result=await api("bounces",{query:$("bounce-query").value,source:$("bounce-source").value,offset:bounceOffset,limit:20});
    if(generation!==bounceRequest)return;
    if(!result.items.length&&bounceOffset&&result.total){bounceOffset=Math.floor((result.total-1)/20)*20;return bounceRefresh();}
    bounceNext=result.next_offset;
    $("bounce-rows").replaceChildren();
    for(const item of result.items){
        const row=document.createElement("div");row.className="review-history-row";
        const details=document.createElement("div"),title=document.createElement("strong"),small=document.createElement("small");
        title.textContent=item.label||item.name;
        small.textContent=(item.label?item.name+" · ":"")+(item.source==="watched"?"Watched export":"Manual import");
        details.append(title,small);
        const open=document.createElement("button");open.className="quiet bounce-open";open.textContent="Open";open.dataset.id=item.id;
        open.addEventListener("click",()=>bounceOpen(item.id).catch(e=>notice(e.message)));
        row.append(details,open);$("bounce-rows").append(row);
    }
    $("bounce-page").textContent=result.items.length?`${bounceOffset+1}–${bounceOffset+result.items.length} of ${result.total} bounces`:"No matching bounces. Import audio or capture a new export.";
    $("bounce-prev").disabled=bounceOffset===0;$("bounce-next").disabled=bounceNext===null;
}
function bounceSchedule(){clearTimeout(bounceTimer);bounceTimer=setTimeout(()=>bounceRefresh().catch(e=>notice(e.message)),200);}
async function bounceUse(side){
    if(!bounceSelected)throw Error("Open a saved bounce first.");
    const asset=bounceSelected.id;
    await reviewRefresh();
    const select=$(side);
    if(![...select.options].some(o=>o.value===asset))throw Error("This input is no longer available. Refresh the library.");
    select.value=asset;$("review-same-range").checked=false;tab("review");
    notice("Saved bounce selected. Confirm matching export range and settings before creating A/B.",true);
}
for(const id of ["bounce-label","bounce-note"])$(id).addEventListener("input",bounceMarkDirty);
action("bounce-refresh",()=>bounceRefresh());
$("bounce-prev").addEventListener("click",()=>{bounceOffset=Math.max(0,bounceOffset-20);bounceRefresh().catch(e=>notice(e.message));});
$("bounce-next").addEventListener("click",()=>{if(bounceNext!==null){bounceOffset=bounceNext;bounceRefresh().catch(e=>notice(e.message));}});
action("bounce-reopen",async()=>{if(bounceSelected)await bounceOpen(bounceSelected.id);});
action("bounce-save",async()=>{
    if(!bounceSelected)throw Error("Open a saved bounce first.");
    bounceBusy=true;bounceOpenRequest++;
    const sent={asset:bounceSelected.id,expected_revision:bounceSelected.revision,label:$("bounce-label").value,note:$("bounce-note").value};
    try{
        const updated=await api("bounce-edit",sent);
        // Preserve typing that happened while the save was in flight.
        if($("bounce-label").value===sent.label&&$("bounce-note").value===sent.note)bounceShow(updated);
        else{bounceSelected=updated;bounceMarkDirty();}
        notice("Bounce label and notes saved. The audio and FL project were not changed.",true);
        await bounceRefresh();
    }finally{bounceBusy=false;}
});
action("bounce-analyze",async()=>{
    if(!bounceSelected)throw Error("Open a saved bounce first.");
    const row=bounceSelected,report=await job("analyze",{asset:row.id});
    audioReport("Bounce library analysis · "+(row.label||row.name),report,report);
});
action("bounce-verify",async()=>{
    if(!bounceSelected)throw Error("Open a saved bounce first.");
    const id=bounceSelected.id;
    $("bounce-verification").textContent="Checking the current stored bytes…";
    let result;
    try{result=await job("bounce-verify",{asset:id});}
    catch(error){if(bounceSelected?.id===id)$("bounce-verification").textContent="Verification failed. No current integrity claim is made.";throw error;}
    if(bounceSelected?.id===id)$("bounce-verification").textContent=`Stored copy verified at ${new Date(result.verified_at*1000).toLocaleString()}. SHA-256 ${result.sha256}. FL session provenance remains unverified.`;
});
action("bounce-before",()=>bounceUse("review-a"));
action("bounce-after",()=>bounceUse("review-b"));
$("bounce-query").addEventListener("input",()=>{bounceOffset=0;bounceSchedule();});
$("bounce-source").addEventListener("change",()=>bounceRefresh(true).catch(e=>notice(e.message)));
window.addEventListener("flcopilot-assets-updated",bounceSchedule);
document.querySelector('[data-tab="audio"]').addEventListener("click",()=>bounceRefresh().catch(e=>notice(e.message)));
window.addEventListener("beforeunload",event=>{if(bounceDirty){event.preventDefault();event.returnValue="";}});
bounceRefresh().catch(e=>notice(e.message));
