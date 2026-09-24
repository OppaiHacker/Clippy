import { MixTrackSetting, AudioEffect } from '../types';

interface TrackNodes {
  source: MediaElementAudioSourceNode;
  delay: DelayNode;
  highpass: BiquadFilterNode;
  lowpass: BiquadFilterNode;
  compressor: DynamicsCompressorNode;
  panner: StereoPannerNode;
  gain: GainNode;
  analyser: AnalyserNode;
  trackKey: string;
}

export class AudioGraph {
  private ctx: AudioContext | null = null;
  private sourceCache = new WeakMap<HTMLMediaElement, MediaElementAudioSourceNode>();
  private trackNodesMap = new Map<string, TrackNodes>();
  private masterGainNode: GainNode | null = null;
  private masterLimiterNode: DynamicsCompressorNode | null = null;

  public getContext(): AudioContext {
    if (!this.ctx) {
      const AudioCtx = window.AudioContext || (window as any).webkitAudioContext;
      this.ctx = new AudioCtx();
    }
    if (this.ctx.state === 'suspended') {
      this.ctx.resume().catch(() => {});
    }
    return this.ctx;
  }

  public initMaster() {
    const ctx = this.getContext();
    if (!this.masterGainNode) {
      this.masterGainNode = ctx.createGain();
      this.masterLimiterNode = ctx.createDynamicsCompressor();

      // Master limiter settings
      this.masterLimiterNode.threshold.setValueAtTime(-0.5, ctx.currentTime);
      this.masterLimiterNode.knee.setValueAtTime(0, ctx.currentTime);
      this.masterLimiterNode.ratio.setValueAtTime(20, ctx.currentTime);
      this.masterLimiterNode.attack.setValueAtTime(0.001, ctx.currentTime);
      this.masterLimiterNode.release.setValueAtTime(0.05, ctx.currentTime);

      this.masterGainNode.connect(this.masterLimiterNode);
      this.masterLimiterNode.connect(ctx.destination);
    }
  }

  public registerTrack(trackKey: string, audioElement: HTMLAudioElement): TrackNodes {
    const ctx = this.getContext();
    this.initMaster();

    if (this.trackNodesMap.has(trackKey)) {
      return this.trackNodesMap.get(trackKey)!;
    }

    let source = this.sourceCache.get(audioElement);
    if (!source) {
      source = ctx.createMediaElementSource(audioElement);
      this.sourceCache.set(audioElement, source);
    }

    const delay = ctx.createDelay(10.0);
    const highpass = ctx.createBiquadFilter();
    highpass.type = 'highpass';
    highpass.frequency.setValueAtTime(20, ctx.currentTime);

    const lowpass = ctx.createBiquadFilter();
    lowpass.type = 'lowpass';
    lowpass.frequency.setValueAtTime(20000, ctx.currentTime);

    const compressor = ctx.createDynamicsCompressor();
    compressor.threshold.setValueAtTime(0, ctx.currentTime);
    compressor.ratio.setValueAtTime(1, ctx.currentTime);

    const panner = ctx.createStereoPanner();
    const gain = ctx.createGain();
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 256;
    analyser.smoothingTimeConstant = 0.8;

    // Chain: Source -> Delay -> Highpass -> Lowpass -> Compressor -> Panner -> Gain -> Analyser -> MasterGain
    source.connect(delay);
    delay.connect(highpass);
    highpass.connect(lowpass);
    lowpass.connect(compressor);
    compressor.connect(panner);
    panner.connect(gain);
    gain.connect(analyser);
    analyser.connect(this.masterGainNode!);

    const nodes: TrackNodes = {
      source,
      delay,
      highpass,
      lowpass,
      compressor,
      panner,
      gain,
      analyser,
      trackKey,
    };

    this.trackNodesMap.set(trackKey, nodes);
    return nodes;
  }

  public updateTrackSettings(trackKey: string, setting: MixTrackSetting, anySoloActive: boolean) {
    const nodes = this.trackNodesMap.get(trackKey);
    if (!nodes || !this.ctx) return;

    const ctx = this.ctx;
    const now = ctx.currentTime;

    const offset = Math.max(0, setting.offset || 0);
    nodes.delay.delayTime.setTargetAtTime(offset, now, 0.01);

    const pan = Math.max(-1, Math.min(1, setting.pan || 0));
    nodes.panner.pan.setTargetAtTime(pan, now, 0.01);

    let targetGain = setting.gain !== undefined ? setting.gain : 1.0;
    if (setting.mute) {
      targetGain = 0;
    } else if (anySoloActive && !setting.solo) {
      targetGain = 0;
    }

    nodes.gain.gain.setTargetAtTime(targetGain, now, 0.01);

    for (const eff of setting.effects || []) {
      if (eff.type === 'highpass') {
        nodes.highpass.frequency.setTargetAtTime(eff.freq || 80, now, 0.01);
      } else if (eff.type === 'lowpass') {
        nodes.lowpass.frequency.setTargetAtTime(eff.freq || 12000, now, 0.01);
      } else if (eff.type === 'compressor') {
        nodes.compressor.threshold.setTargetAtTime(eff.threshold || -18, now, 0.01);
        nodes.compressor.ratio.setTargetAtTime(eff.ratio || 3, now, 0.01);
      }
    }
  }

  public setMasterGain(gain: number) {
    if (this.masterGainNode && this.ctx) {
      this.masterGainNode.gain.setTargetAtTime(gain, this.ctx.currentTime, 0.01);
    }
  }

  public getTrackPeak(trackKey: string): number {
    const nodes = this.trackNodesMap.get(trackKey);
    if (!nodes) return 0;

    const buffer = new Uint8Array(nodes.analyser.frequencyBinCount);
    nodes.analyser.getByteTimeDomainData(buffer);

    let maxDiff = 0;
    for (let i = 0; i < buffer.length; i++) {
      const diff = Math.abs(buffer[i] - 128);
      if (diff > maxDiff) maxDiff = diff;
    }
    return maxDiff / 128;
  }

  public destroy() {
    this.trackNodesMap.clear();
    if (this.ctx && this.ctx.state !== 'closed') {
      this.ctx.close().catch(() => {});
    }
    this.ctx = null;
    this.masterGainNode = null;
    this.masterLimiterNode = null;
  }
}
