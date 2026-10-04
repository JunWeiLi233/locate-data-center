import { ChevronLeft, ChevronRight, Play, X } from 'lucide-react';
import type { StoryStep } from './story';

/** Guided demo controls; each step only changes layers, camera and selection of the loaded result. */
export function StoryBar({ steps, index, onIndex, onExit }: { steps: StoryStep[]; index: number | null; onIndex: (index: number) => void; onExit: () => void }) {
  if (index === null) {
    return <div className="rd-story rd-story--idle"><button type="button" className="button secondary" onClick={() => onIndex(0)}><Play size={14} aria-hidden="true" />Guided demo</button></div>;
  }
  const step = steps[index];
  return <section className="rd-story" aria-label="Guided demo" aria-live="polite">
    <div className="rd-story-progress" aria-hidden="true">{steps.map((item, position) => <span key={item.id} className={position <= index ? 'rd-done' : ''} />)}</div>
    <p className="micro-label">Step {index + 1} of {steps.length}</p>
    <h3>{step.title}</h3>
    <p>{step.body}</p>
    <div className="rd-story-actions">
      <button type="button" className="icon-button" aria-label="Previous step" disabled={index === 0} onClick={() => onIndex(index - 1)}><ChevronLeft size={17} /></button>
      {index < steps.length - 1
        ? <button type="button" className="button primary" onClick={() => onIndex(index + 1)}>Next<ChevronRight size={15} aria-hidden="true" /></button>
        : <button type="button" className="button primary" onClick={onExit}>Explore freely</button>}
      <button type="button" className="icon-button" aria-label="Exit guided demo" onClick={onExit}><X size={16} /></button>
    </div>
  </section>;
}
