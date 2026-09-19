"use strict";
// Measurements and listening choices are separate; this workspace has no DAW writer.
let reviewCurrent=null, reviewURLs={}, reviewGeneration=0, reviewSide=null, reviewSwitch=0;
let reviewPosition=0, reviewLoading=false, reviewAbortLoad=null;
let reviewBlind=null, reviewBlindURLs={}, reviewBlindGeneration=0, reviewBlindSwitch=0;
let reviewBlindPosition=0, reviewBlindLoading=false, reviewBlindAbort=null;
function reviewPause(){
    reviewSwitch++;if(reviewAbortLoad)reviewAbortLoad();reviewAbortLoad=null;
    reviewLoading=false;$("review-player").pause();
    window.dispatchEvent(new Event("flcopilot-review-paused"));
}
function reviewSeekTo(seconds){
    if(!reviewCurrent||reviewCurrent.report.status!=="ready"||!Number.isFinite(seconds))return;
    const m=reviewCurrent.report.baseline, end=m.frames/m.sample_rate;
    reviewPosition=Math.max(0,Math.min(seconds,Math.max(0,end-.001)));
    if(reviewBlind&&reviewBlind.status==="open")reviewBlindPosition=reviewPosition;
    const player=$("review-player");
    if(!reviewLoading&&player.readyState>=1)player.currentTime=reviewPosition;
    const blindPlayer=$("review-blind-player");
    if(reviewBlind&&reviewBlind.status==="open"&&!reviewBlindLoading&&blindPlayer.readyState>=1)blindPlayer.currentTime=reviewBlindPosition;
    window.dispatchEvent(new Event("flcopilot-review-position"));
}
function reviewDispose(){
    reviewGeneration++;reviewPause();reviewBlindDispose();
    $("review-player").removeAttribute("src");$("review-player").load();
    Object.values(reviewURLs).forEach(url=>URL.revokeObjectURL(url));reviewURLs={};reviewSide=null;reviewPosition=0;
    document.querySelectorAll("[data-review-side]").forEach(b=>b.classList.remove("selected"));
    $("review-now").textContent="Select A or B to load its verified WAV.";
    window.dispatchEvent(new Event("flcopilot-review-disposed"));
}
function reviewBlindPause(){
    reviewBlindSwitch++;if(reviewBlindAbort)reviewBlindAbort();reviewBlindAbort=null;
    reviewBlindLoading=false;$("review-blind-player").pause();
}
function reviewBlindDispose(){
    reviewBlindGeneration++;reviewBlindPause();
    const player=$("review-blind-player");player.removeAttribute("src");player.load();
    Object.values(reviewBlindURLs).forEach(url=>URL.revokeObjectURL(url));reviewBlindURLs={};
    reviewBlind=null;reviewBlindPosition=0;
    $("review-blind-controls").hidden=true;$("review-blind-result").hidden=true;
    $("review-blind-state").textContent="Start a trial to hide which matched WAV is baseline or candidate.";
    $("review-blind-now").textContent="No blind sample loaded.";
}
function reviewBlindShow(trial){
    reviewBlind=trial;
    const open=trial.status==="open";
    $("review-blind-controls").hidden=false;
    $("review-blind-state").textContent=open?
        "Answer hidden. Reference A and Reference B are randomly assigned; X is exactly one of them.":
        "Answer revealed for this completed trial.";
    for(const id of ["review-blind-guess-a","review-blind-guess-b","review-blind-unsure"])$(id).disabled=!open;
    if(open){
        $("review-blind-result").hidden=true;
    }else{
        const result=trial.correct===null?"No discrimination guess was submitted.":trial.correct?
            "Correct: X matched Reference "+trial.x_matches.toUpperCase()+".":"Incorrect: X matched Reference "+trial.x_matches.toUpperCase()+".";
        const mapping=`Reference A was ${trial.mapping.a}; Reference B was ${trial.mapping.b}; X was ${trial.mapping.x}.`;
        $("review-blind-result").hidden=false;$("review-blind-result").textContent=result+" "+mapping;
    }
}
async function reviewBlindRefresh(reviewId=reviewCurrent&&reviewCurrent.review_id){
    if(!reviewId)return;
    const rows=await api("review-blind-history",{review_id:reviewId});
    if(!reviewCurrent||reviewCurrent.review_id!==reviewId)return;
    $("review-blind-history").innerHTML=rows.length?rows.map(row=>{
        const when=esc(new Date(row.created*1000).toLocaleString());
        if(row.status==="open")return `<div class="review-history-row"><div><strong>Unfinished blind trial</strong><small>${when} · answer still hidden</small></div></div>`;
        const outcome=row.correct===null?"unsure":row.correct?"correct":"incorrect";
        return `<div class="review-history-row"><div><strong>Blind A/B/X · ${esc(outcome)}</strong><small>${when} · X matched ${esc(row.x_matches.toUpperCase())} · A was ${esc(row.mapping.a)} · B was ${esc(row.mapping.b)}</small></div></div>`;
    }).join(""):'<p>No blind trials saved for this review.</p>';
    if(!reviewBlind){
        const open=rows.find(row=>row.status==="open");
        if(open){reviewBlindPosition=reviewPosition;reviewBlindShow(open);}
    }
}
async function reviewBlindStart(){
    if(!reviewCurrent||reviewCurrent.report.status!=="ready")throw Error("Open a ready review first.");
    reviewBlindDispose();
    const trial=await job("review-blind-start",{review_id:reviewCurrent.review_id});
    reviewBlindPosition=reviewPosition;reviewBlindShow(trial);
    await reviewBlindRefresh(reviewCurrent.review_id);
    notice("Blind A/B/X trial started. The answer stays server-side until you submit a guess.",true);
}
async function reviewBlindBlob(sample,trial,generation,change){
    const response=await fetch(`/api/review-blind-file/${trial.trial_id}/${sample}`,{headers:{Authorization:"Bearer "+token}});
    if(!response.ok){let out={};try{out=await response.json();}catch{}throw Error(out.error||response.statusText);}
    const url=URL.createObjectURL(await response.blob());
    if(generation!==reviewBlindGeneration||change!==reviewBlindSwitch||reviewBlind!==trial){URL.revokeObjectURL(url);return null;}
    return url;
}
function reviewBlindMetadata(player){
    return new Promise((resolve,reject)=>{
        const done=()=>{clearTimeout(timer);player.removeEventListener("loadedmetadata",ok);player.removeEventListener("error",bad);reviewBlindAbort=null;};
        const ok=()=>{done();resolve(true);},bad=()=>{done();reject(Error("Browser could not load this blind audition WAV."));};
        const timer=setTimeout(bad,15000);
        reviewBlindAbort=()=>{done();resolve(false);};
        player.addEventListener("loadedmetadata",ok,{once:true});player.addEventListener("error",bad,{once:true});
        if(player.readyState>=1)ok();
    });
}
async function reviewBlindAudition(sample){
    if(!reviewBlind)throw Error("Start or resume a blind trial first.");
    if(!["a","b","x"].includes(sample))throw Error("Choose blind sample A, B or X.");
    reviewPause();
    const trial=reviewBlind,generation=reviewBlindGeneration,change=++reviewBlindSwitch,player=$("review-blind-player");
    const current=()=>generation===reviewBlindGeneration&&change===reviewBlindSwitch&&reviewBlind===trial;
    if(!reviewBlindLoading&&player.readyState>=1)reviewBlindPosition=player.currentTime;
    reviewBlindLoading=true;player.pause();
    try{
        if(!reviewBlindURLs[sample]){
            const url=await reviewBlindBlob(sample,trial,generation,change);if(!url)return;
            reviewBlindURLs[sample]=url;
        }
        if(!current())return;
        player.src=reviewBlindURLs[sample];player.load();
        if(!await reviewBlindMetadata(player)||!current())return;
        player.currentTime=Math.max(0,Math.min(reviewBlindPosition,Math.max(0,player.duration-.001)));
        reviewBlindPosition=player.currentTime;
        document.querySelectorAll("[data-review-blind]").forEach(b=>b.classList.toggle("selected",b.dataset.reviewBlind===sample));
        $("review-blind-now").textContent=sample==="x"?"X · hidden identity":`Reference ${sample.toUpperCase()} · identity hidden`;
        reviewBlindLoading=false;await player.play();
    }catch(error){if(current())throw error;}
    finally{if(current())reviewBlindLoading=false;}
}
async function reviewBlindSubmit(guess){
    if(!reviewBlind||reviewBlind.status!=="open")throw Error("Start or resume an unanswered blind trial first.");
    reviewBlindPause();
    const result=await job("review-blind-submit",{trial_id:reviewBlind.trial_id,guess});
    reviewBlindShow(result);await reviewBlindRefresh(result.review_id);
    notice("Blind answer recorded and revealed. Your saved listening preference was not changed.",true);
}
$("review-blind-player").addEventListener("timeupdate",()=>{
    if(!reviewBlindLoading&&$("review-blind-player").readyState>=1)reviewBlindPosition=$("review-blind-player").currentTime;
});

async function reviewRefresh(){
    await refreshAssets();
    const audio=assets.filter(a=>["input","audio"].includes(a.kind));
    for(const id of ["review-a","review-b"]){
        const previous=$(id).value;
        $(id).innerHTML='<option value="">Choose an imported bounce</option>'+audio.map(a=>`<option value="${a.id}">${esc(a.name)}</option>`).join("");
        if(audio.some(a=>a.id===previous))$(id).value=previous;
    }
    const runs=await api("history"), selected=$("review-run-link").value;
    $("review-run-link").innerHTML='<option value="">No associated run</option>'+runs.filter(r=>r.status==="verified").map(r=>`<option value="${r.id}">${esc(r.plan.title)} · ${esc(r.plan.backend)}</option>`).join("");
    if(runs.some(r=>r.id===selected))$("review-run-link").value=selected;
    const history=await api("reviews");
    $("review-history").innerHTML=history.length?history.map(r=>`<div class="review-history-row"><div><strong>${esc(r.title)}</strong><small>${esc(new Date(r.created*1000).toLocaleString())} · ${esc(r.status)} · ${esc(r.decision.replaceAll("_"," "))}</small></div><button class="quiet review-open" data-id="${r.review_id}">Open review</button></div>`).join(""):'<p>No audio reviews saved yet. Import your before/after exports in Audio lab.</p>';
    document.querySelectorAll(".review-open").forEach(b=>b.onclick=async()=>{
        b.disabled=true;try{reviewShow(await api("review-get",{review_id:b.dataset.id}));}catch(e){notice(e.message);}finally{b.disabled=false;}
    });
}
function reviewShow(result){
    reviewDispose();reviewCurrent=result;
    const report=result.report, ready=report.status==="ready";
    $("review-result").hidden=false;$("review-result-title").textContent=report.title;
    $("review-badge").textContent=ready?"A/B READY · NOT A QUALITY VERDICT":"A/B WITHHELD";
    $("review-readiness").textContent=ready?`Timing evidence: ${report.timing.basis.replaceAll("_"," ")}. Content identity and export provenance remain unverified.`:
        "Re-export or inspect this pair: "+report.blocked_reasons.join(", ").replaceAll("_"," ")+". No A/B audio was rendered.";
    const names={integrated_lufs:"Integrated loudness (LUFS)",oversampled_peak_dbtp_estimate:"4× peak estimate (dBTP)",crest_db:"Crest factor (dB)",stereo_correlation:"Stereo correlation"};
    $("review-metrics").innerHTML=Object.entries(names).map(([key,label])=>`<tr><td>${label}</td><td>${number(report.baseline[key],2)}</td><td>${number(report.candidate[key],2)}</td><td>${number(report.candidate_minus_baseline[key],2)}</td></tr>`).join("");
    $("review-sections").innerHTML=report.sections.map(s=>`<tr><td>${number(s.start_seconds,1)}–${number(s.end_seconds,1)} s</td><td>${number(s.candidate_minus_baseline.integrated_lufs,2)}</td><td>${number(s.candidate_minus_baseline.oversampled_peak_dbtp_estimate,2)}</td><td>${number(s.candidate_minus_baseline.crest_db,2)}</td></tr>`).join("");
    $("review-section-panel").hidden=!report.sections.length;
    $("review-match-note").textContent=ready?`Audition target: ${number(report.level_matched_ab.target_lufs,2)} LUFS. Attenuation only; measured match within 0.1 LU. No EQ, limiting, trimming or time shifting.`:"The JSON report still contains each file’s independent measurements.";
    $("review-audition").hidden=!ready;
    $("review-warnings").innerHTML=[...report.warnings,...report.baseline.warnings.map(x=>"Baseline: "+x),...report.candidate.warnings.map(x=>"Candidate: "+x)].map(w=>`<p class="footnote">${esc(w)}</p>`).join("");
    $("review-detail").textContent=JSON.stringify(report,null,2);
    $("review-choice").value=result.decision;$("review-note").value=result.note;
    $("review-revision").textContent=`Saved decision revision ${result.revision} · human preference only`;
    for(const opt of $("review-choice").options)opt.disabled=!ready&&opt.value.startsWith("prefer_");
    showFiles($("review-files"),result.files,"Review exports · originals preserved");
    if(ready)reviewBlindRefresh(result.review_id).catch(e=>notice(e.message));
    window.dispatchEvent(new Event("flcopilot-review-opened"));
}
function reviewMetadata(player){
    return new Promise((resolve,reject)=>{
        const done=()=>{clearTimeout(timer);player.removeEventListener("loadedmetadata",ok);player.removeEventListener("error",bad);reviewAbortLoad=null;};
        const ok=()=>{done();resolve(true);},bad=()=>{done();reject(Error("Browser could not load this audition WAV."));};
        const timer=setTimeout(bad,15000);
        reviewAbortLoad=()=>{done();resolve(false);};
        player.addEventListener("loadedmetadata",ok,{once:true});player.addEventListener("error",bad,{once:true});
        if(player.readyState>=1)ok();
    });
}
async function reviewAudition(side){
    if(!reviewCurrent||reviewCurrent.report.status!=="ready")throw Error("Open a ready review first.");
    reviewBlindPause();
    if(!["a","b"].includes(side))throw Error("Choose audition side A or B.");
    if(reviewAbortLoad)reviewAbortLoad();
    const generation=reviewGeneration, change=++reviewSwitch, player=$("review-player");
    const current=()=>generation===reviewGeneration&&change===reviewSwitch;
    if(!reviewLoading&&player.readyState>=1)reviewPosition=player.currentTime;
    reviewLoading=true;player.pause();
    try{
        const name=side==="a"?"A_Baseline_Matched.wav":"B_Candidate_Matched.wav";
        const file=reviewCurrent.files.find(f=>f.name===name);
        if(!file)throw Error("Verified audition file is missing.");
        if(!reviewURLs[side]){
            const url=await fileBlob(file);
            if(!current()){URL.revokeObjectURL(url);return;}
            reviewURLs[side]=url;
        }
        if(!current())return;
        if(reviewSide!==side){player.src=reviewURLs[side];player.load();reviewSide=side;}
        if(!await reviewMetadata(player)||!current())return;
        const target={position:reviewPosition};
        window.dispatchEvent(new CustomEvent("flcopilot-review-will-play",{detail:target}));
        player.currentTime=Math.max(0,Math.min(target.position,Math.max(0,player.duration-.001)));
        reviewPosition=player.currentTime;
        document.querySelectorAll("[data-review-side]").forEach(b=>b.classList.toggle("selected",b.dataset.reviewSide===side));
        $("review-now").textContent=side==="a"?"A · baseline · level matched":"B · candidate · level matched";
        reviewLoading=false;
        await player.play();
    }catch(error){if(current())throw error;}
    finally{if(current())reviewLoading=false;}
}
$("review-player").addEventListener("timeupdate",()=>{
    if(!reviewLoading&&$("review-player").readyState>=1)reviewPosition=$("review-player").currentTime;
});
action("review-refresh",reviewRefresh);
action("review-build",async()=>{
    if(!$("review-same-range").checked)throw Error("Confirm the same song, export range and settings before pairing the bounces.");
    const data={baseline:$("review-a").value,candidate:$("review-b").value,confirm_same_range:true,
        title:$("review-title").value,section_seconds:Number($("review-seconds").value)};
    if($("review-run-link").value)data.linked_plan_id=$("review-run-link").value;
    reviewShow(await job("review-audio",data));await reviewRefresh();
});
action("review-play-a",()=>reviewAudition("a"));action("review-play-b",()=>reviewAudition("b"));
action("review-pause",async()=>{reviewPause();});
action("review-blind-start",reviewBlindStart);
action("review-blind-play-a",()=>reviewBlindAudition("a"));action("review-blind-play-b",()=>reviewBlindAudition("b"));action("review-blind-play-x",()=>reviewBlindAudition("x"));
action("review-blind-pause",async()=>{reviewBlindPause();});
action("review-blind-guess-a",()=>reviewBlindSubmit("a"));action("review-blind-guess-b",()=>reviewBlindSubmit("b"));action("review-blind-unsure",()=>reviewBlindSubmit("unsure"));
action("review-save-choice",async()=>{
    if(!reviewCurrent)throw Error("Open a review first.");
    const updated=await api("review-decision",{review_id:reviewCurrent.review_id,expected_revision:reviewCurrent.revision,
        decision:$("review-choice").value,note:$("review-note").value});
    reviewCurrent=updated;$("review-revision").textContent=`Saved decision revision ${updated.revision} · human preference only`;
    notice("Listening preference saved locally. No FL setting or audio file was changed.",true);await reviewRefresh();
});
$("stop").addEventListener("click",()=>{reviewPause();reviewBlindPause();});
document.querySelector('[data-tab="review"]').addEventListener("click",()=>reviewRefresh().catch(e=>notice(e.message)));
window.addEventListener("beforeunload",reviewDispose);

for(const id of ["review-a","review-b"]){$(id).addEventListener("change",()=>{$("review-same-range").checked=false;});}
