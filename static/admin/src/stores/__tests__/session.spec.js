import { describe, it, expect } from 'vitest';
import { MAX_TURNS, trimTurns } from '../session.js';

describe('MAX_TURNS', () => {
  it('is 50', () => {
    expect(MAX_TURNS).toBe(50);
  });
});

describe('trimTurns', () => {
  const makeTurns = (n) =>
    Array.from({ length: n }, (_, i) => ({ role: 'user', text: `turn ${i}`, t: i }));

  it('returns 0 and leaves the array unchanged when length < max', () => {
    const arr = makeTurns(10);
    const before = arr.slice();
    expect(trimTurns(arr)).toBe(0);
    expect(arr).toEqual(before);
    expect(arr.length).toBe(10);
  });

  it('returns 0 and leaves the array unchanged when length === max (50)', () => {
    const arr = makeTurns(MAX_TURNS);
    const before = arr.slice();
    expect(trimTurns(arr)).toBe(0);
    expect(arr).toEqual(before);
    expect(arr.length).toBe(MAX_TURNS);
  });

  it('trims to max and returns the correct drop count when length > max', () => {
    const arr = makeTurns(MAX_TURNS + 7); // 57
    const dropped = trimTurns(arr);
    expect(dropped).toBe(7);
    expect(arr.length).toBe(MAX_TURNS);
  });

  it('drops only from the head, keeping the most recent turns in order', () => {
    const arr = makeTurns(MAX_TURNS + 10); // 60, texts "turn 0".."turn 59"
    trimTurns(arr);
    expect(arr.length).toBe(MAX_TURNS);
    // The first 10 (oldest) were dropped; the kept window is turns 10..59.
    expect(arr[0].text).toBe('turn 10');
    expect(arr[arr.length - 1].text).toBe('turn 59');
    // Order preserved within the kept window.
    expect(arr.map((x) => x.text)).toEqual(
      Array.from({ length: MAX_TURNS }, (_, i) => `turn ${i + 10}`),
    );
  });

  it('honors a custom max argument', () => {
    const arr = makeTurns(20);
    expect(trimTurns(arr, 5)).toBe(15);
    expect(arr.length).toBe(5);
    expect(arr[0].text).toBe('turn 15');
    expect(arr[4].text).toBe('turn 19');
  });

  it('massive over-push: trimming on every push keeps exactly the last MAX_TURNS', () => {
    // Simulate pushTurn's new-bubble branch 200 times: push then trim each time.
    const arr = [];
    for (let i = 0; i < 200; i++) {
      arr.push({ role: i % 2 ? 'bot' : 'user', text: `turn ${i}`, t: i });
      trimTurns(arr);
    }
    expect(arr.length).toBe(MAX_TURNS);
    expect(arr[0].text).toBe('turn 150');
    expect(arr[MAX_TURNS - 1].text).toBe('turn 199');
  });
});
