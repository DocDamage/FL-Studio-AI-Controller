"use strict";
// Read-only navigation of existing matched WAVs. No DAW calls or saved decisions.
let waveformData=null, waveformGeneration=0, waveformBusy=false;
let waveformLoop=null, waveformFrame=0, waveformPlaying=false, waveformLastDraw=0;
function waveformReset(){
    waveformGeneration++;waveformData=null;waveformBusy=false;waveformLoop=null;waveformPlaying=false;
    cancelAnimationFrame(waveformFrame);waveformFrame=0;
    $("waveform-controls").hidden=true;$("waveform-load").disabled=false;
    $("waveform-repeat").checked=false;$("waveform-repeat").disabled=true;
    $("waveform-state").textContent="Load waveforms to navigate and loop an audition range. No audio or project edits.";
    $("waveform-loop-state").textContent="No loop selected.";
}
function waveformRepeating(){return waveformData&&waveformLoop&&$("waveform-repeat").checked;}
function waveformRange(start,end){
    if(!waveformData)throw Error("Load verified waveforms first.");
    if(!Number.isFinite(start)||!Number.isFinite(end)||start<0||end>waveformData.duration_seconds||end-start<.25)
        throw Error("Choose a finite range within the file, at least 0.25 seconds long.");
    waveformLoop={start,end};$("waveform-start").value=String(start);$("waveform-end").value=String(end);
    $("waveform-repeat").disabled=false;$("waveform-repeat").checked=true;
    reviewSeekTo(start);waveformLoopStatus();waveformDraw();
}
function waveformLoopStatus(){
    $("waveform-loop-state").textContent=waveformLoop?
        `${waveformRepeating()?"Repeat enabled":"Repeat off"} · ${waveformLoop.start.toFixed(2)}–${waveformLoop.end.toFixed(2)} s · shared by A and B`:
        "No loop selected. Apply a range or choose a measured window.";
}
function waveformClear(){
    waveformLoop=null;$("waveform-repeat").checked=false;$("waveform-repeat").disabled=true;
    waveformLoopStatus();waveformDraw();
}
async function waveformLoad(){
    if(waveformBusy)return;
    if(!reviewCurrent||reviewCurrent.report.status!=="ready")throw Error("Open a ready review first.");
    // Discard old player blobs and envelopes before re-verifying, including failures.
    reviewDispose();const generation=waveformGeneration, reviewID=reviewCurrent.review_id;
    waveformBusy=true;$("waveform-load").disabled=true;
    $("waveform-state").textContent="Checking both audition files and their report, then reading bounded waveform summaries…";
    try{
        const data=await job("review-waveform",{review_id:reviewID,bins:800});
        if(generation!==waveformGeneration||reviewCurrent?.review_id!==reviewID)return;
        waveformData=data;$("waveform-controls").hidden=false;
        $("waveform-seek").max=String(data.duration_seconds);$("waveform-seek").value="0";
        $("waveform-start").value="0";$("waveform-end").value=String(data.duration_seconds);
        $("waveform-window").replaceChildren(new Option("Choose a measured window",""));
        reviewCurrent.report.sections.forEach((s,i)=>$("waveform-window").append(new Option(`${s.start_seconds.toFixed(2)}–${s.end_seconds.toFixed(2)} s`,String(i))));
        $("waveform-state").textContent=`${data.channels===2?"Stereo: separate L/R lanes":"Mono"} · ${data.bin_count} bins · ${data.sample_rate} Hz · current output hashes checked. Min/max peaks and RMS share one scale. Original input bounces were not reverified.`;
        waveformDraw();
    }catch(error){
        if(generation===waveformGeneration){$("waveform-state").textContent="No current waveform: "+error.message;throw error;}
    }finally{
        if(generation===waveformGeneration){waveformBusy=false;$("waveform-load").disabled=false;}
    }
}
function waveformDraw(){
    if(!waveformData||!$("review").classList.contains("active"))return;
    waveformLastDraw=performance.now();
    const data=waveformData, player=$("review-player"), pos=reviewLoading?reviewPosition:(player.readyState>=1?player.currentTime:reviewPosition);
    $("waveform-position").textContent=`${pos.toFixed(2)} / ${data.duration_seconds.toFixed(2)} s`;
    $("waveform-seek").value=String(pos);$("waveform-seek").setAttribute("aria-valuetext",`${pos.toFixed(2)} seconds of ${data.duration_seconds.toFixed(2)}`);
    // One scale for all channels on both sides; no cancellation from downmixing.
    let scale=1;
    for(const side of Object.values(data.sides))for(const row of side.channels)
        for(let i=0;i<data.bin_count;i++)scale=Math.max(scale,Math.abs(row.min[i]),Math.abs(row.max[i]));
    const style=getComputedStyle(document.documentElement), text=style.getPropertyValue("--text").trim()||"#eeeeee";
    for(const side of ["a","b"]){
        const canvas=$("waveform-"+side), width=Math.max(1,canvas.clientWidth), height=28+data.channels*86, dpr=Math.min(devicePixelRatio||1,2);
        canvas.width=Math.round(width*dpr);canvas.height=Math.round(height*dpr);canvas.style.height=height+"px";
        const ctx=canvas.getContext("2d");ctx.scale(dpr,dpr);
        const pad=14, span=Math.max(1,width-2*pad), x=t=>pad+(t/data.duration_seconds)*span;
        ctx.fillStyle=text;ctx.font="11px sans-serif";ctx.fillText(`±${scale.toFixed(2)} FS`,pad,13);
        if(waveformLoop){ctx.globalAlpha=.13;ctx.fillRect(x(waveformLoop.start),20,x(waveformLoop.end)-x(waveformLoop.start),height-20);ctx.globalAlpha=1;}
        const color=style.getPropertyValue(side==="a"?"--green":"--waveform-b").trim()||(side==="a"?"#adff7f":"#8ebcff");
        data.sides[side].channels.forEach((row,channel)=>{
            const center=64+channel*86, amplitude=32/scale;
            ctx.strokeStyle=text;ctx.globalAlpha=.2;ctx.beginPath();ctx.moveTo(pad,center);ctx.lineTo(width-pad,center);ctx.stroke();ctx.globalAlpha=1;
            ctx.fillStyle=text;ctx.fillText(data.channels===1?"MONO":channel===0?"L":"R",pad,center-34);
            ctx.strokeStyle=color;ctx.lineWidth=Math.max(.65,span/data.bin_count);
            ctx.beginPath();
            for(let i=0;i<data.bin_count;i++){
                const px=pad+(data.frame_edges[i]+data.frame_edges[i+1])/2/data.frames*span;
                ctx.moveTo(px,center-row.min[i]*amplitude);ctx.lineTo(px,center-row.max[i]*amplitude);
            }ctx.stroke();ctx.globalAlpha=.25;ctx.beginPath();
            for(let i=0;i<data.bin_count;i++){
                const px=pad+(data.frame_edges[i]+data.frame_edges[i+1])/2/data.frames*span;
                ctx.moveTo(px,center-row.rms[i]*amplitude);ctx.lineTo(px,center+row.rms[i]*amplitude);
            }ctx.stroke();ctx.globalAlpha=1;
        });
        ctx.strokeStyle=text;ctx.lineWidth=1.5;ctx.beginPath();ctx.moveTo(x(pos),20);ctx.lineTo(x(pos),height);ctx.stroke();
        canvas.setAttribute("aria-label",`${side.toUpperCase()} ${data.channels===2?"stereo L/R":"mono"} waveform; shared scale ±${scale.toFixed(2)} full scale. Use the seek slider to navigate.`);
    }
}
function waveformTick(){
    waveformFrame=0;
    if(!waveformData)return;
    const player=$("review-player");
    if(!player.paused&&!reviewLoading&&waveformRepeating()&&!player.seeking&&
        (player.currentTime>=waveformLoop.end||player.currentTime<waveformLoop.start))reviewSeekTo(waveformLoop.start);
    if(player.paused||performance.now()-waveformLastDraw>=66)waveformDraw();
    if(!player.paused&&!document.hidden)waveformFrame=requestAnimationFrame(waveformTick);
}
function waveformSchedule(){if(!waveformFrame)waveformFrame=requestAnimationFrame(waveformTick);}
action("waveform-load",waveformLoad);
action("waveform-apply",async()=>waveformRange($("waveform-start").valueAsNumber,$("waveform-end").valueAsNumber));
action("waveform-clear",async()=>waveformClear());
action("waveform-use-window",async()=>{
    const value=$("waveform-window").value;if(value==="")throw Error("Choose a measured window first.");
    const section=reviewCurrent?.report.sections[Number(value)];
    if(!section)throw Error("This measured window is no longer available.");
    waveformRange(section.start_seconds,section.end_seconds);
});
$("waveform-seek").addEventListener("input",()=>reviewSeekTo($("waveform-seek").valueAsNumber));
for(const id of ["waveform-start","waveform-end"])$(id).addEventListener("input",waveformClear);
$("waveform-repeat").addEventListener("change",()=>{waveformLoopStatus();waveformSchedule();});
for(const side of ["a","b"])$("waveform-"+side).addEventListener("click",event=>{
    if(!waveformData)return;
    const rect=event.currentTarget.getBoundingClientRect(), fraction=(event.clientX-rect.left-14)/Math.max(1,rect.width-28);
    reviewSeekTo(fraction*waveformData.duration_seconds);
});
window.addEventListener("flcopilot-review-disposed",waveformReset);
window.addEventListener("flcopilot-review-position",waveformDraw);
window.addEventListener("flcopilot-review-paused",()=>{waveformPlaying=false;});
window.addEventListener("flcopilot-review-will-play",event=>{
    if(waveformRepeating()&&(event.detail.position<waveformLoop.start||event.detail.position>=waveformLoop.end))event.detail.position=waveformLoop.start;
});
$("stop").addEventListener("click",()=>{
    $("waveform-repeat").checked=false;waveformPlaying=false;waveformLoopStatus();
    // Invalidate any in-flight preview; a late result cannot resurrect it.
    if(waveformBusy)waveformReset();
});
const waveformPlayer=$("review-player");
waveformPlayer.addEventListener("play",()=>{waveformPlaying=true;waveformSchedule();});
waveformPlayer.addEventListener("pause",()=>{if(!waveformPlayer.ended)waveformPlaying=false;waveformSchedule();});
waveformPlayer.addEventListener("timeupdate",()=>{if(!waveformFrame)waveformTick();});
waveformPlayer.addEventListener("ended",()=>{
    if(waveformPlaying&&waveformRepeating()&&!reviewLoading){
        reviewSeekTo(waveformLoop.start);reviewAudition(reviewSide||"a").catch(error=>notice(error.message));
    }
});
window.addEventListener("resize",waveformSchedule);
document.addEventListener("visibilitychange",waveformSchedule);

document.querySelector('[data-tab="review"]').addEventListener("click",waveformSchedule);
