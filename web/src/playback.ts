export function pauseEveryOtherPlayer(current: HTMLAudioElement) {
  document.querySelectorAll("audio.history-audio").forEach((node) => {
    const audio = node as HTMLAudioElement;
    if (audio !== current) audio.pause();
  });
}

export function bindExclusivePlayback(audio: HTMLAudioElement) {
  audio.addEventListener("play", () => pauseEveryOtherPlayer(audio));
}

document.addEventListener("click", (event) => {
  const target = event.target;
  if (!(target instanceof Element)) return;
  const waveform = target.closest("[data-waveform]");
  if (!(waveform instanceof HTMLElement)) return;
  const audio = waveform.parentElement?.querySelector("audio.history-audio");
  if (!(audio instanceof HTMLAudioElement) || !Number.isFinite(audio.duration)) return;
  const bounds = waveform.getBoundingClientRect();
  const position = (event.clientX - bounds.left) / bounds.width;
  audio.currentTime = Math.max(0, Math.min(1, position)) * audio.duration;
});
