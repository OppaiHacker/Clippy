export interface TrackAudioBinding {
  key: string;
  audio: HTMLAudioElement;
  offsetSeconds: number;
}

export class SyncEngine {
  private video: HTMLVideoElement | null = null;
  private audioTracks: TrackAudioBinding[] = [];
  private driftInterval: any = null;
  private inPoint: number = 0;
  private outPoint: number = 0;
  private isLooping: boolean = false;
  private maxObservedDriftMs: number = 0;
  private onTimeUpdateCallback: ((time: number) => void) | null = null;

  public attachVideo(video: HTMLVideoElement) {
    this.video = video;
    this.video.addEventListener('timeupdate', this.handleTimeUpdate);
    this.video.addEventListener('seeking', this.handleSeeking);
    this.video.addEventListener('seeked', this.handleSeeked);
    this.video.addEventListener('ratechange', this.handleRateChange);
  }

  public detachVideo() {
    if (this.video) {
      this.video.removeEventListener('timeupdate', this.handleTimeUpdate);
      this.video.removeEventListener('seeking', this.handleSeeking);
      this.video.removeEventListener('seeked', this.handleSeeked);
      this.video.removeEventListener('ratechange', this.handleRateChange);
      this.video = null;
    }
    this.stopDriftCorrection();
  }

  public setAudioTracks(tracks: TrackAudioBinding[]) {
    this.audioTracks = tracks;
  }

  public setTrimRange(inPoint: number, outPoint: number, isLooping = false) {
    this.inPoint = inPoint;
    this.outPoint = outPoint;
    this.isLooping = isLooping;
  }

  public setOnTimeUpdate(cb: (time: number) => void) {
    this.onTimeUpdateCallback = cb;
  }

  public async play() {
    if (!this.video) return;

    if (this.isLooping && this.outPoint > this.inPoint && this.video.currentTime >= this.outPoint) {
      this.video.currentTime = this.inPoint;
    }

    try {
      await this.video.play();
      this.startDriftCorrection();
      for (const track of this.audioTracks) {
        track.audio.playbackRate = this.video.playbackRate;
        const targetTime = Math.max(0, this.video.currentTime + track.offsetSeconds);
        track.audio.currentTime = targetTime;
        track.audio.play().catch(() => {});
      }
    } catch (e) {
      console.warn('Play interrupted:', e);
    }
  }

  public pause() {
    if (!this.video) return;
    this.video.pause();
    this.stopDriftCorrection();
    for (const track of this.audioTracks) {
      track.audio.pause();
    }
  }

  public seek(seconds: number) {
    if (!this.video) return;
    this.video.currentTime = seconds;
    for (const track of this.audioTracks) {
      track.audio.currentTime = Math.max(0, seconds + track.offsetSeconds);
    }
  }

  public setPlaybackRate(rate: number) {
    if (!this.video) return;
    this.video.playbackRate = rate;
    for (const track of this.audioTracks) {
      track.audio.playbackRate = rate;
    }
  }

  private handleTimeUpdate = () => {
    if (!this.video) return;
    const cur = this.video.currentTime;

    if (this.isLooping && this.outPoint > this.inPoint && cur >= this.outPoint) {
      this.seek(this.inPoint);
      return;
    }

    if (this.onTimeUpdateCallback) {
      this.onTimeUpdateCallback(cur);
    }
  };

  private handleSeeking = () => {
    if (!this.video) return;
    for (const track of this.audioTracks) {
      track.audio.currentTime = Math.max(0, this.video.currentTime + track.offsetSeconds);
    }
  };

  private handleSeeked = () => {
    if (!this.video) return;
    for (const track of this.audioTracks) {
      track.audio.currentTime = Math.max(0, this.video.currentTime + track.offsetSeconds);
    }
  };

  private handleRateChange = () => {
    if (!this.video) return;
    for (const track of this.audioTracks) {
      track.audio.playbackRate = this.video.playbackRate;
    }
  };

  private startDriftCorrection() {
    if (this.driftInterval) return;

    this.driftInterval = setInterval(() => {
      if (!this.video || this.video.paused) return;

      const vTime = this.video.currentTime;

      for (const track of this.audioTracks) {
        const expectedTime = Math.max(0, vTime + track.offsetSeconds);
        const drift = track.audio.currentTime - expectedTime;
        const driftMs = Math.abs(drift) * 1000;

        if (driftMs > this.maxObservedDriftMs) {
          this.maxObservedDriftMs = Math.round(driftMs);
        }

        // Hard threshold: 100ms
        if (Math.abs(drift) > 0.1) {
          track.audio.currentTime = expectedTime;
        }
      }
    }, 500);
  }

  private stopDriftCorrection() {
    if (this.driftInterval) {
      clearInterval(this.driftInterval);
      this.driftInterval = null;
    }
  }

  public getMaxObservedDriftMs(): number {
    return this.maxObservedDriftMs;
  }

  public resetDriftStats() {
    this.maxObservedDriftMs = 0;
  }
}
