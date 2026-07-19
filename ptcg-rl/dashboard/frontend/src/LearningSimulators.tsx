import { useMemo, useState } from "react";

type SimulatorId = "prize" | "damage" | "consistency" | "decision";

type PrizeRaceInput = {
  ourPrizes: number;
  opponentPrizes: number;
  ourPrizeTake: number;
  opponentPrizeTake: number;
  ourAttacksPerKo: number;
  opponentAttacksPerKo: number;
  weAttackFirst: boolean;
};

type PrizeEvent = {
  turn: number;
  actor: "You" | "Opponent";
  prizesTaken: number;
  ourPrizes: number;
  opponentPrizes: number;
};

export function simulatePrizeRace(input: PrizeRaceInput): { winner: "You" | "Opponent" | "Unresolved"; events: PrizeEvent[] } {
  let ourPrizes = clampInteger(input.ourPrizes, 0, 6);
  let opponentPrizes = clampInteger(input.opponentPrizes, 0, 6);
  let ourProgress = 0;
  let opponentProgress = 0;
  const events: PrizeEvent[] = [];

  if (ourPrizes === 0) return { winner: "You", events };
  if (opponentPrizes === 0) return { winner: "Opponent", events };

  for (let turn = 1; turn <= 30; turn += 1) {
    const ourTurn = input.weAttackFirst ? turn % 2 === 1 : turn % 2 === 0;
    if (ourTurn) {
      ourProgress += 1;
      if (ourProgress >= clampInteger(input.ourAttacksPerKo, 1, 6)) {
        ourProgress = 0;
        ourPrizes = Math.max(0, ourPrizes - clampInteger(input.ourPrizeTake, 1, 3));
        events.push({ turn, actor: "You", prizesTaken: input.ourPrizeTake, ourPrizes, opponentPrizes });
        if (ourPrizes === 0) return { winner: "You", events };
      }
    } else {
      opponentProgress += 1;
      if (opponentProgress >= clampInteger(input.opponentAttacksPerKo, 1, 6)) {
        opponentProgress = 0;
        opponentPrizes = Math.max(0, opponentPrizes - clampInteger(input.opponentPrizeTake, 1, 3));
        events.push({ turn, actor: "Opponent", prizesTaken: input.opponentPrizeTake, ourPrizes, opponentPrizes });
        if (opponentPrizes === 0) return { winner: "Opponent", events };
      }
    }
  }
  return { winner: "Unresolved", events };
}

export function calculateDamage(input: {
  hp: number;
  existingDamage: number;
  baseDamage: number;
  modifier: number;
  weakness: boolean;
  resistance: boolean;
}): { finalDamage: number; remainingHp: number; ko: boolean; hitsToKo: number | null } {
  const hp = Math.max(10, input.hp);
  const existingDamage = clampInteger(input.existingDamage, 0, hp);
  let finalDamage = Math.max(0, input.baseDamage + input.modifier);
  if (input.weakness) finalDamage *= 2;
  if (input.resistance) finalDamage = Math.max(0, finalDamage - 30);
  finalDamage = Math.round(finalDamage);
  const remainingHp = Math.max(0, hp - existingDamage - finalDamage);
  const required = Math.max(0, hp - existingDamage);
  const hitsToKo = finalDamage > 0 ? Math.ceil(required / finalDamage) : null;
  return { finalDamage, remainingHp, ko: remainingHp === 0, hitsToKo };
}

function combination(n: number, k: number): number {
  if (k < 0 || k > n) return 0;
  const reduced = Math.min(k, n - k);
  let result = 1;
  for (let i = 1; i <= reduced; i += 1) result = (result * (n - reduced + i)) / i;
  return result;
}

export function hypergeometricDistribution(deckSize: number, targetCopies: number, cardsSeen: number): number[] {
  const n = clampInteger(deckSize, 1, 100);
  const targets = clampInteger(targetCopies, 0, n);
  const draws = clampInteger(cardsSeen, 0, n);
  const denominator = combination(n, draws);
  const maxHits = Math.min(targets, draws);
  return Array.from({ length: maxHits + 1 }, (_, hits) => {
    const ways = combination(targets, hits) * combination(n - targets, draws - hits);
    return denominator ? ways / denominator : 0;
  });
}

export function softmax(scores: number[], temperature: number): number[] {
  if (!scores.length) return [];
  const safeTemperature = Math.max(0.05, temperature);
  const scaled = scores.map((score) => score / safeTemperature);
  const maximum = Math.max(...scaled);
  const weights = scaled.map((score) => Math.exp(score - maximum));
  const total = weights.reduce((sum, value) => sum + value, 0);
  return weights.map((value) => value / total);
}

function clampInteger(value: number, minimum: number, maximum: number): number {
  return Math.min(maximum, Math.max(minimum, Math.round(value)));
}

function RangeControl({ label, value, minimum, maximum, step = 1, suffix = "", onChange }: {
  label: string;
  value: number;
  minimum: number;
  maximum: number;
  step?: number;
  suffix?: string;
  onChange: (value: number) => void;
}) {
  return (
    <label className="sim-control">
      <span><strong>{label}</strong><output>{value}{suffix}</output></span>
      <input type="range" min={minimum} max={maximum} step={step} value={value} onChange={(event) => onChange(Number(event.target.value))} />
    </label>
  );
}

function PrizeRaceSimulator() {
  const [ourPrizes, setOurPrizes] = useState(6);
  const [opponentPrizes, setOpponentPrizes] = useState(6);
  const [ourPrizeTake, setOurPrizeTake] = useState(2);
  const [opponentPrizeTake, setOpponentPrizeTake] = useState(1);
  const [ourAttacksPerKo, setOurAttacksPerKo] = useState(2);
  const [opponentAttacksPerKo, setOpponentAttacksPerKo] = useState(2);
  const [weAttackFirst, setWeAttackFirst] = useState(true);
  const result = useMemo(() => simulatePrizeRace({ ourPrizes, opponentPrizes, ourPrizeTake, opponentPrizeTake, ourAttacksPerKo, opponentAttacksPerKo, weAttackFirst }), [ourPrizes, opponentPrizes, ourPrizeTake, opponentPrizeTake, ourAttacksPerKo, opponentAttacksPerKo, weAttackFirst]);

  const decisive = result.events.at(-1);
  return (
    <div className="simulator-layout">
      <aside className="sim-controls">
        <RangeControl label="Your prizes remaining" value={ourPrizes} minimum={1} maximum={6} onChange={setOurPrizes} />
        <RangeControl label="Opponent prizes remaining" value={opponentPrizes} minimum={1} maximum={6} onChange={setOpponentPrizes} />
        <RangeControl label="Prizes per your KO" value={ourPrizeTake} minimum={1} maximum={3} onChange={setOurPrizeTake} />
        <RangeControl label="Prizes per opponent KO" value={opponentPrizeTake} minimum={1} maximum={3} onChange={setOpponentPrizeTake} />
        <RangeControl label="Your attacks per KO" value={ourAttacksPerKo} minimum={1} maximum={4} onChange={setOurAttacksPerKo} />
        <RangeControl label="Opponent attacks per KO" value={opponentAttacksPerKo} minimum={1} maximum={4} onChange={setOpponentAttacksPerKo} />
        <label className="sim-check"><input type="checkbox" checked={weAttackFirst} onChange={(event) => setWeAttackFirst(event.target.checked)} />You take the first attack turn</label>
      </aside>
      <div className="sim-output">
        <div className="sim-metrics">
          <div><span>Projected winner</span><strong>{result.winner}</strong></div>
          <div><span>Decisive turn</span><strong>{decisive?.turn ?? "—"}</strong></div>
          <div><span>Knockouts shown</span><strong>{result.events.length}</strong></div>
        </div>
        <div className="prize-track" aria-label="Prize-race timeline">
          {result.events.map((event, index) => (
            <div className={`prize-event ${event.actor === "You" ? "ours" : "theirs"}`} key={`${event.turn}-${index}`}>
              <span>T{event.turn}</span><strong>{event.actor} take {event.prizesTaken}</strong><small>You {event.ourPrizes} · Opponent {event.opponentPrizes}</small>
            </div>
          ))}
        </div>
        <p className="sim-lesson"><strong>Idea prompt:</strong> test whether the agent values a two-prize knockout enough when it changes the race, rather than only maximizing immediate damage.</p>
      </div>
    </div>
  );
}

function DamageSimulator() {
  const [hp, setHp] = useState(220);
  const [existingDamage, setExistingDamage] = useState(40);
  const [baseDamage, setBaseDamage] = useState(120);
  const [modifier, setModifier] = useState(0);
  const [weakness, setWeakness] = useState(false);
  const [resistance, setResistance] = useState(false);
  const result = useMemo(() => calculateDamage({ hp, existingDamage, baseDamage, modifier, weakness, resistance }), [hp, existingDamage, baseDamage, modifier, weakness, resistance]);
  const occupied = Math.min(100, ((existingDamage + result.finalDamage) / hp) * 100);
  return (
    <div className="simulator-layout">
      <aside className="sim-controls">
        <RangeControl label="Defender HP" value={hp} minimum={60} maximum={360} step={10} onChange={(value) => { setHp(value); setExistingDamage((current) => Math.min(current, value)); }} />
        <RangeControl label="Existing damage" value={existingDamage} minimum={0} maximum={hp} step={10} onChange={setExistingDamage} />
        <RangeControl label="Printed attack damage" value={baseDamage} minimum={0} maximum={360} step={10} onChange={setBaseDamage} />
        <RangeControl label="Other modifier" value={modifier} minimum={-100} maximum={150} step={10} onChange={setModifier} />
        <label className="sim-check"><input type="checkbox" checked={weakness} onChange={(event) => setWeakness(event.target.checked)} />Apply simplified ×2 weakness</label>
        <label className="sim-check"><input type="checkbox" checked={resistance} onChange={(event) => setResistance(event.target.checked)} />Apply simplified −30 resistance</label>
      </aside>
      <div className="sim-output">
        <div className="pokemon-card-visual">
          <div><span>Defending Pokémon</span><strong>{Math.max(0, hp - existingDamage)} / {hp} HP before attack</strong></div>
          <div className="hp-track"><span style={{ width: `${occupied}%` }} /></div>
          <div className="damage-burst">{result.finalDamage}<small>damage</small></div>
        </div>
        <div className="sim-metrics">
          <div><span>Remaining HP</span><strong>{result.remainingHp}</strong></div>
          <div><span>Knockout</span><strong>{result.ko ? "YES" : "NO"}</strong></div>
          <div><span>Hits to KO</span><strong>{result.hitsToKo ?? "∞"}</strong></div>
        </div>
        <p className="sim-lesson"><strong>Boundary:</strong> this is a simplified arithmetic sandbox. Card effects and engine ordering remain authoritative.</p>
      </div>
    </div>
  );
}

function ConsistencySimulator() {
  const [copies, setCopies] = useState(4);
  const [cardsSeen, setCardsSeen] = useState(7);
  const distribution = useMemo(() => hypergeometricDistribution(60, copies, cardsSeen), [copies, cardsSeen]);
  const atLeastOne = 1 - (distribution[0] ?? 0);
  const expected = (copies * cardsSeen) / 60;
  return (
    <div className="simulator-layout">
      <aside className="sim-controls">
        <RangeControl label="Copies of a key card" value={copies} minimum={1} maximum={4} onChange={setCopies} />
        <RangeControl label="Cards seen" value={cardsSeen} minimum={1} maximum={20} onChange={setCardsSeen} />
        <div className="sim-note">Exact sampling without replacement from a 60-card deck. This does not model mulligans, search cards, prizes, or sequencing.</div>
      </aside>
      <div className="sim-output">
        <div className="sim-metrics">
          <div><span>See at least one</span><strong>{(atLeastOne * 100).toFixed(1)}%</strong></div>
          <div><span>Miss all copies</span><strong>{((distribution[0] ?? 0) * 100).toFixed(1)}%</strong></div>
          <div><span>Expected copies</span><strong>{expected.toFixed(2)}</strong></div>
        </div>
        <div className="probability-bars" aria-label="Probability distribution">
          {distribution.map((probability, hits) => (
            <div key={hits}><span>{hits} drawn</span><div><i style={{ width: `${probability * 100}%` }} /></div><strong>{(probability * 100).toFixed(1)}%</strong></div>
          ))}
        </div>
        <p className="sim-lesson"><strong>Idea prompt:</strong> compare raw consistency against the opportunity cost of each extra copy, then validate the complete deck in matchup tests.</p>
      </div>
    </div>
  );
}

const defaultOptions = [
  { id: "attack", label: "Attack active", score: 1.4 },
  { id: "retreat", label: "Retreat", score: 0.3 },
  { id: "supporter", label: "Play supporter", score: 1.0 },
  { id: "pass", label: "End turn", score: -0.8 },
];

function DecisionSimulator() {
  const [options, setOptions] = useState(defaultOptions);
  const [temperature, setTemperature] = useState(0.8);
  const [selectedTargets, setSelectedTargets] = useState<string[]>([]);
  const probabilities = softmax(options.map((option) => option.score), temperature);
  const best = options.reduce((current, option) => option.score > current.score ? option : current, options[0]);
  const targets = ["Bench slot A", "Bench slot B", "Bench slot C", "Bench slot D"];
  const stopLegal = selectedTargets.length >= 1;
  const toggleTarget = (target: string) => {
    setSelectedTargets((current) => current.includes(target) ? current.filter((item) => item !== target) : current.length < 3 ? [...current, target] : current);
  };
  const reorder = () => setOptions((current) => [...current.slice(1), current[0]]);
  return (
    <div className="decision-lab">
      <div className="decision-panel">
        <div className="decision-toolbar"><RangeControl label="Policy temperature" value={temperature} minimum={0.1} maximum={2} step={0.1} suffix="×" onChange={setTemperature} /><button type="button" onClick={reorder}>Rotate engine option order</button></div>
        <div className="option-stack">
          {options.map((option, index) => (
            <article className={option.id === best.id ? "best" : ""} key={option.id}>
              <div><span>Engine index {index}</span><strong>{option.label}</strong></div>
              <label>Score <input aria-label={`${option.label} score`} type="range" min={-2} max={2} step={0.1} value={option.score} onChange={(event) => setOptions((current) => current.map((item) => item.id === option.id ? { ...item, score: Number(event.target.value) } : item))} /></label>
              <b>{(probabilities[index] * 100).toFixed(1)}%</b>
            </article>
          ))}
        </div>
        <p className="sim-lesson"><strong>Semantic invariance:</strong> rotating the engine list changes indices but not which named action has the highest score.</p>
      </div>
      <div className="decision-panel">
        <h3>STOP-aware multi-select</h3>
        <p>Select one to three targets. STOP is masked until the minimum selection is satisfied.</p>
        <div className="target-grid">
          {targets.map((target) => <button type="button" className={selectedTargets.includes(target) ? "selected" : ""} onClick={() => toggleTarget(target)} key={target}>{target}</button>)}
        </div>
        <button type="button" className="stop-action" disabled={!stopLegal} onClick={() => setSelectedTargets([])}>STOP · commit {selectedTargets.length} target{selectedTargets.length === 1 ? "" : "s"}</button>
        <div className="selection-sequence">Sequence: {selectedTargets.length ? `${selectedTargets.join(" → ")} → STOP` : "choose a legal target"}</div>
        <p className="sim-lesson"><strong>Idea prompt:</strong> test whether ordered target selection needs additional context features when two individually good targets interact badly.</p>
      </div>
    </div>
  );
}

export function LearningSimulators() {
  const [active, setActive] = useState<SimulatorId>("prize");
  const tabs: Array<{ id: SimulatorId; label: string; title: string; summary: string }> = [
    { id: "prize", label: "Prize race", title: "Turn and prize-race planner", summary: "See how knockout speed, prize value, and initiative change the shortest route to victory." },
    { id: "damage", label: "Damage math", title: "Damage and knockout sandbox", summary: "Build intuition for thresholds, existing damage, weakness, resistance, and two-hit knockouts." },
    { id: "consistency", label: "Deck odds", title: "Opening consistency calculator", summary: "Measure the exact chance of seeing key copies in a fixed number of cards from a 60-card deck." },
    { id: "decision", label: "Agent choices", title: "Legal-option and multi-select lab", summary: "Understand semantic option scoring, list-order invariance, temperature, masks, and STOP." },
  ];
  const current = tabs.find((tab) => tab.id === active) ?? tabs[0];
  return (
    <section className="learning-simulators">
      <div className="sim-heading">
        <div><p className="eyebrow">Interactive visual playgrounds</p><h2>{current.title}</h2><p>{current.summary}</p></div>
        <span className="sim-disclaimer">Educational approximations · not engine validation</span>
      </div>
      <div className="sim-tabs" role="tablist" aria-label="Learning simulators">
        {tabs.map((tab) => <button type="button" role="tab" aria-selected={active === tab.id} className={active === tab.id ? "active" : ""} onClick={() => setActive(tab.id)} key={tab.id}>{tab.label}</button>)}
      </div>
      <div className="panel simulator-shell">
        {active === "prize" && <PrizeRaceSimulator />}
        {active === "damage" && <DamageSimulator />}
        {active === "consistency" && <ConsistencySimulator />}
        {active === "decision" && <DecisionSimulator />}
      </div>
    </section>
  );
}
