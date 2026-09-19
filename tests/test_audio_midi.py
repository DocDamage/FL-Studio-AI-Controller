import json
import math
import struct
import threading
from pathlib import Path
import numpy as np
import pytest
import soundfile as sf
from flcopilot.audio import analyze,master,measure_array,peak4,_stats
from flcopilot.assets import file_hash
from flcopilot.contracts import MasterRequest,PlanError,Stopped
from flcopilot.creative import export_sketch,vlq
from flcopilot.process import ffmpeg_path,run_owned

@pytest.fixture
def audio(tmp_path):
    sr=44100;t=np.arange(sr*6)/sr
    env=.35+.3*np.sin(2*np.pi*.7*t)**2
    signal=.3*env*np.sin(2*np.pi*440*t)+.08*np.sin(2*np.pi*70*t)
    y=np.column_stack([signal,signal*.92+.015*np.sin(2*np.pi*997*t)])
    f=tmp_path/"mix.wav";sf.write(f,y,sr,subtype="FLOAT");return f,y,sr

def test_sine_rms_peak_lufs():
    sr=48000;t=np.arange(sr*3)/sr;y=(.5*np.sin(2*np.pi*1000*t))[:,None]
    m=measure_array(y,sr)
    assert abs(m["sample_peak_dbfs"]+6.0206)<.001
    assert abs(m["rms_dbfs"]+9.0309)<.001
    assert -10<m["integrated_lufs"]<-8
    assert m["oversampled_peak_dbtp_estimate"]>=m["sample_peak_dbfs"]

def test_lufs_agrees_with_ffmpeg(audio):
    f,y,sr=audio;m=analyze(f)
    _,log=run_owned([ffmpeg_path(),"-hide_banner","-nostdin","-i",str(f),"-af","loudnorm=print_format=json","-f","null","-"])
    ff=_stats(log)
    assert abs(m["integrated_lufs"]-float(ff["input_i"]))<.25

def test_analysis_hash_metadata(audio):
    f,y,sr=audio;m=analyze(f)
    assert m["frames"]==len(y) and m["sample_rate"]==sr and m["channels"]==2
    assert m["source_sha256"]==file_hash(f)
    assert sum(m["band_energy_fractions"].values())<=1.000001

def test_silence_is_not_finite_loudness(tmp_path):
    f=tmp_path/"silence.wav";sf.write(f,np.zeros((48000,2)),48000)
    assert analyze(f)["integrated_lufs"] is None
    with pytest.raises(PlanError,match="silence"):master(f,tmp_path/"exports",MasterRequest(asset="a"*32))
    assert not list((tmp_path/"exports").iterdir())

def test_antiphase_has_energy_warning():
    sr=48000;t=np.arange(sr*2)/sr;s=.2*np.sin(2*np.pi*100*t)
    m=measure_array(np.column_stack([s,-s]),sr)
    assert m["stereo_correlation"]<-.999 and m["band_energy_fractions"]["bass"]>.5 and m["warnings"]

def test_true_peak_estimate_detects_intersample_peak():
    sr=48000;t=np.arange(sr)/sr;y=(.8*np.sin(2*np.pi*12000*t+np.pi/4))[:,None]
    assert peak4(y)>np.max(np.abs(y))*1.2

@pytest.mark.parametrize("preserve",[True,False])
def test_master_writes_real_files_keeps_source(audio,tmp_path,preserve):
    f,y,sr=audio;original=f.read_bytes();r,files=master(f,tmp_path/"exports",MasterRequest(asset="a"*32,target_lufs=-14.,preserve_dynamics=preserve))
    assert len(files)==4 and all(p.exists() and p.stat().st_size>100 for p in files)
    assert f.read_bytes()==original
    out,osr=sf.read(files[0],always_2d=True)
    assert out.shape==y.shape and osr==sr and sf.info(files[0]).subtype=="PCM_24"
    assert r["after"]["oversampled_peak_dbtp_estimate"]<=-.95
    assert not r["subjective_quality_validated"] and not r["tonal_eq_applied"]
    assert abs(analyze(files[1])["integrated_lufs"]-analyze(files[2])["integrated_lufs"])<.02
    assert json.loads(files[3].read_text())["master_sha256"]==file_hash(files[0])

def test_preserve_mode_reports_unmet_target(tmp_path):
    sr=48000;t=np.arange(sr*3)/sr;y=.02*np.sin(2*np.pi*1000*t);y[10000]=.92
    f=tmp_path/"transient.wav";sf.write(f,y,sr,subtype="FLOAT")
    # Keep target within the explicit 18 dB maximum boost guard.
    r,files=master(f,tmp_path/"exports",MasterRequest(asset="a"*32,target_lufs=-24.))
    assert r["after"]["integrated_lufs"]<-24.5
    assert any("not met" in w for w in r["warnings"])

def test_cancel_master_no_leftover(audio,tmp_path):
    stop=threading.Event();stop.set();f,y,sr=audio
    with pytest.raises(Stopped):master(f,tmp_path/"exports",MasterRequest(asset="a"*32),stop)
    assert not list((tmp_path/"exports").iterdir())

@pytest.mark.parametrize("kind",["short","multichannel","nan","invalid"])
def test_reject_invalid_audio(tmp_path,kind):
    f=tmp_path/"input.wav"
    if kind=="short":sf.write(f,np.zeros(100),48000)
    elif kind=="multichannel":sf.write(f,np.zeros((48000,6)),48000)
    elif kind=="nan":sf.write(f,np.full(48000,float("nan")),48000,subtype="FLOAT")
    else:f.write_bytes(b"not wave")
    with pytest.raises((PlanError,RuntimeError)):analyze(f)

def parse_midi(path):
    data=path.read_bytes();assert data[:4]==b"MThd"
    size,fmt,count,ppq=struct.unpack(">IHHH",data[4:14]);assert (size,fmt,ppq)==(6,1,480)
    pos=14;events=[]
    for _ in range(count):
        assert data[pos:pos+4]==b"MTrk";n=int.from_bytes(data[pos+4:pos+8],"big");chunk=data[pos+8:pos+8+n]
        assert chunk.endswith(b"\xff\x2f\x00");assert len(chunk)==n
        pos+=8+n;events.append(chunk)
    assert pos==len(data);return events

def test_midi_is_valid_repeatable_file(tmp_path):
    a,report=export_sketch(tmp_path);b,_=export_sketch(tmp_path)
    assert a!=b and a.read_bytes()==b.read_bytes()
    assert len(parse_midi(a))==3 and report["bpm"]==88 and not report["fl_playlist_modified"]

def test_midi_seed_changes_content(tmp_path):
    a,_=export_sketch(tmp_path,seed=1);b,_=export_sketch(tmp_path,seed=2);assert a.read_bytes()!=b.read_bytes()

@pytest.mark.parametrize("args",[{"bpm":True},{"bpm":float("nan")},{"bars":0},{"bars":True},{"key":"H"},{"swing":.8},{"seed":-1}])
def test_bad_midi(args,tmp_path):
    with pytest.raises(PlanError):export_sketch(tmp_path,**args)

@pytest.mark.parametrize("value,expected",[(0,b"\0"),(127,b"\x7f"),(128,b"\x81\0"),(16383,b"\xff\x7f")])
def test_midi_vlq(value,expected):assert vlq(value)==expected
