import { describe, expect, it } from "vitest";
import { calculateDamage, hypergeometricDistribution, simulatePrizeRace, softmax } from "./LearningSimulators";

describe("learning simulators", () => {
  it("projects a prize race without taking prizes below zero", () => {
    const result = simulatePrizeRace({
      ourPrizes: 6,
      opponentPrizes: 6,
      ourPrizeTake: 2,
      opponentPrizeTake: 1,
      ourAttacksPerKo: 1,
      opponentAttacksPerKo: 1,
      weAttackFirst: true,
    });
    expect(result.winner).toBe("You");
    expect(result.events.at(-1)?.ourPrizes).toBe(0);
  });

  it("applies the documented simplified damage order", () => {
    expect(calculateDamage({ hp: 220, existingDamage: 40, baseDamage: 100, modifier: 20, weakness: true, resistance: true })).toEqual({
      finalDamage: 210,
      remainingHp: 0,
      ko: true,
      hitsToKo: 1,
    });
  });

  it("produces a normalized hypergeometric distribution", () => {
    const distribution = hypergeometricDistribution(60, 4, 7);
    expect(distribution.reduce((sum, value) => sum + value, 0)).toBeCloseTo(1, 12);
    expect(1 - distribution[0]).toBeCloseTo(0.3994996257, 8);
  });

  it("softmax is normalized and invariant to option reordering", () => {
    const original = softmax([1.4, 0.3, 1.0, -0.8], 0.8);
    const rotated = softmax([0.3, 1.0, -0.8, 1.4], 0.8);
    expect(original.reduce((sum, value) => sum + value, 0)).toBeCloseTo(1, 12);
    expect(original[0]).toBeCloseTo(rotated[3], 12);
  });
});
