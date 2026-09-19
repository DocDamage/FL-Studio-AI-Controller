"use strict";
// Measurements and listening choices are separate; this workspace has no DAW writer.
let reviewCurrent=null, reviewURLs={}, reviewGeneration=0, reviewSide=null, reviewSwitch=0;
function reviewDispose(){
    reviewGeneration++;reviewSwitch++;$("review-player").pause();
    $("review-player").removeAttribute("src");$("review-player").load();
    Object.values(reviewURLs).forEach(url=>URL.revokeObjectURL(url));reviewURLs={};reviewSide=null;
}
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
}
async function reviewAudition(side){
    if(!reviewCurrent||reviewCurrent.report.status!=="ready")throw Error("Open a ready review first.");
    const generation=reviewGeneration, change=++reviewSwitch, player=$("review-player");
    const position=Number.isFinite(player.currentTime)?player.currentTime:0;
    player.pause();
    const name=side==="a"?"A_Baseline_Matched.wav":"B_Candidate_Matched.wav";
    const file=reviewCurrent.files.find(f=>f.name===name);
    if(!file)throw Error("Verified audition file is missing.");
    if(!reviewURLs[side]){
        const url=await fileBlob(file);
        if(generation!==reviewGeneration||change!==reviewSwitch){URL.revokeObjectURL(url);return;}
        reviewURLs[side]=url;
    }
    if(generation!==reviewGeneration||change!==reviewSwitch)return;
    if(reviewSide!==side){
        player.src=reviewURLs[side];player.load();reviewSide=side;
        await new Promise((resolve,reject)=>{
            const done=()=>{clearTimeout(timer);player.removeEventListener("loadedmetadata",ok);player.removeEventListener("error",bad);};
            const ok=()=>{done();resolve();},bad=()=>{done();reject(Error("Browser could not load this audition WAV."));};
            const timer=setTimeout(bad,15000);
            player.addEventListener("loadedmetadata",ok,{once:true});player.addEventListener("error",bad,{once:true});
            if(player.readyState>=1)ok();
        });
        if(generation!==reviewGeneration||change!==reviewSwitch)return;
        player.currentTime=Math.min(position,Math.max(0,player.duration-.01));
    }
    document.querySelectorAll("[data-review-side]").forEach(b=>b.classList.toggle("selected",b.dataset.reviewSide===side));
    $("review-now").textContent=side==="a"?"A · baseline · level matched":"B · candidate · level matched";
    await player.play();
}
action("review-refresh",reviewRefresh);
action("review-build",async()=>{
    if(!$("review-same-range").checked)throw Error("Confirm the same song, export range and settings before pairing the bounces.");
    const data={baseline:$("review-a").value,candidate:$("review-b").value,confirm_same_range:true,
        title:$("review-title").value,section_seconds:Number($("review-seconds").value)};
    if($("review-run-link").value)data.linked_plan_id=$("review-run-link").value;
    reviewShow(await job("review-audio",data));await reviewRefresh();
});
action("review-play-a",()=>reviewAudition("a"));action("review-play-b",()=>reviewAudition("b"));
action("review-pause",async()=>{$("review-player").pause();reviewSwitch++;});
action("review-save-choice",async()=>{
    if(!reviewCurrent)throw Error("Open a review first.");
    const updated=await api("review-decision",{review_id:reviewCurrent.review_id,expected_revision:reviewCurrent.revision,
        decision:$("review-choice").value,note:$("review-note").value});
    reviewCurrent=updated;$("review-revision").textContent=`Saved decision revision ${updated.revision} · human preference only`;
    notice("Listening preference saved locally. No FL setting or audio file was changed.",true);await reviewRefresh();
});
$("stop").addEventListener("click",()=>{$("review-player").pause();reviewSwitch++;});
document.querySelector('[data-tab="review"]').addEventListener("click",()=>reviewRefresh().catch(e=>notice(e.message)));
window.addEventListener("beforeunload",reviewDispose);

for(const id of ["review-a","review-b"]){$(id).addEventListener("change",()=>{$("review-same-range").checked=false;});}
