#!/usr/bin/env python3
"""Процедурная музыкальная дорожка 60 сек для мультфильма «Лум и Звёздочка».
Синтез: мягкий пэд, бас, колокольчики, шумовые свеллы, псевдо-реверберация.
Ключ: A minor -> C major (Am F C G), финал — тёплый мажор.
"""
import numpy as np, wave, json, os

SR = 44100
DUR = 60.0
N = int(SR * DUR)

def note(name):
    """Название ноты -> частота (A4=440)."""
    base = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}
    p = name[0].upper(); i = 1
    acc = 0
    while i < len(name) and name[i] in '#b':
        acc += 1 if name[i] == '#' else -1; i += 1
    octv = int(name[i:])
    midi = base[p] + acc + (octv + 1) * 12
    return 440.0 * 2 ** ((midi - 69) / 12)

# --- партитура ---
CHORDS = [
    (0.0,  5.0,  ['A3', 'C4', 'E4'],   'A2'),
    (5.0,  5.0,  ['F3', 'A3', 'C4'],   'F2'),
    (10.0, 5.0,  ['A3', 'C4', 'E4'],   'A2'),
    (15.0, 5.0,  ['F3', 'A3', 'C4'],   'F2'),
    (20.0, 5.0,  ['C4', 'E4', 'G4'],   'C3'),
    (25.0, 5.0,  ['G3', 'B3', 'D4'],   'G2'),
    (30.0, 5.0,  ['A3', 'C4', 'E4'],   'A2'),
    (35.0, 5.0,  ['F3', 'A3', 'C4'],   'F2'),
    (40.0, 5.0,  ['A3', 'C4', 'E4'],   'A2'),
    (45.0, 5.0,  ['G3', 'B3', 'D4'],   'G2'),
    (50.0, 5.0,  ['C4', 'E4', 'G4'],   'C3'),
    (55.0, 5.0,  ['F3', 'A3', 'C4', 'E4'], 'C3'),
]

def env_ar(n, atk, rel, sr=SR):
    e = np.ones(n)
    a = min(int(atk * sr), n); r = min(int(rel * sr), n)
    if a > 0: e[:a] = np.linspace(0, 1, a) ** 1.5
    if r > 0: e[-r:] = np.linspace(1, 0, r) ** 1.5
    return e

def add(buf, sig, t0):
    i = int(t0 * SR)
    j = min(i + len(sig), len(buf))
    if i >= len(buf): return
    buf[i:j] += sig[:j - i]

def pad_voice(f, dur, detune=0.004):
    n = int(dur * SR)
    t = np.arange(n) / SR
    out = np.zeros(n)
    for k, amp in [(1, 1.0), (2, 0.28), (3, 0.12), (4, 0.05)]:
        out += amp * np.sin(2 * np.pi * f * k * t) * np.exp(-t * (0.05 * k))
    out += 0.5 * np.sin(2 * np.pi * f * (1 + detune) * t) * np.exp(-t * 0.06)
    lfo = 1 + 0.06 * np.sin(2 * np.pi * 0.13 * t)
    return out * lfo * env_ar(n, 1.3, 1.6)

def bell(f, dur=2.2, amp=1.0):
    n = int(dur * SR)
    t = np.arange(n) / SR
    out = (np.sin(2 * np.pi * f * t) + 0.5 * np.sin(2 * np.pi * f * 2.01 * t)
           + 0.25 * np.sin(2 * np.pi * f * 3.02 * t))
    return amp * out * np.exp(-t * 2.4)

def thump(f=58.0, dur=0.45, amp=1.0):
    n = int(dur * SR)
    t = np.arange(n) / SR
    fdraw = f * (1 + 1.2 * np.exp(-t * 22))
    return amp * np.sin(2 * np.pi * fdraw * t) * np.exp(-t * 7.0)

def noise_sweep(dur=2.0, amp=0.5, seed=7, center=0.5):
    n = int(dur * SR)
    rng = np.random.default_rng(seed)
    x = rng.standard_normal(n)
    # однополюсный ФНЧ с меняющейся частотой
    a = np.linspace(0.02, 0.32, n)
    y = np.zeros(n); acc = 0.0
    for i in range(n):
        acc += a[i] * (x[i] - acc); y[i] = acc
    e = np.exp(-((np.arange(n) / SR - dur * center) ** 2) / (2 * (dur * 0.28) ** 2))
    return amp * y / (np.max(np.abs(y)) + 1e-9) * e

L = np.zeros(N); R = np.zeros(N)   # сухой стерео-сигнал

# 1. Пэд — основа
for t0, d, chord, root in CHORDS:
    for k, nm in enumerate(chord):
        f = note(nm)
        pan = 0.5 + 0.30 * np.sin(k * 2.1)          # разводим голоса по панораме
        g = 0.20 if k < 2 else 0.15
        v = g * pad_voice(f, d + 1.6)
        add(L, v * (1 - pan), t0)
        add(R, v * pan, t0)

# 2. Бас — с 18-й секунды, по 2.5 с
for t0, d, chord, root in CHORDS:
    if t0 < 18: continue
    f = note(root)
    n = int(2.4 * SR); t = np.arange(n) / SR
    b = 0.30 * np.sin(2 * np.pi * f * t) * env_ar(n, 0.05, 1.4) * np.exp(-t * 0.9)
    add(L, b, t0); add(R, b, t0 + 0.04)
# 3. Пульс (сердцебиение) в средней части и в кризисе
for t0 in np.arange(24.5, 40.0, 1.25):
    add(L, thump(amp=0.22), t0); add(R, thump(amp=0.22), t0 + 0.012)
for t0 in np.arange(40.0, 49.0, 1.25):
    add(L, thump(amp=0.13, f=52), t0); add(R, thump(amp=0.13, f=52), t0 + 0.012)
# 4. Колокольчики: искры звёзд
sparkle = [1.2, 3.4, 6.1, 8.7, 12.3, 16.8, 21.5, 26.2, 27.9, 29.5, 31.2, 33.8,
           36.5, 38.2, 41.3, 43.0, 50.6, 51.8, 52.7, 53.6, 55.2, 56.4, 57.5, 58.6]
sc_notes = ['E5', 'A4', 'C5', 'G5', 'E5', 'D5', 'C5', 'E5', 'G5', 'A5', 'G5', 'E5',
            'D5', 'C5', 'E5', 'G5', 'C6', 'E5', 'G5', 'C6', 'A5', 'G5', 'E5', 'C6']
for i, t0 in enumerate(sparkle):
    f = note(sc_notes[i % len(sc_notes)])
    amp = 0.20 if t0 < 24 else (0.13 if t0 < 49 else 0.24)
    v = bell(f, dur=2.6, amp=amp)
    add(L, v * 0.85, t0); add(R, v, t0 + 0.03)
# 5. Шумовые свеллы: взлёт (24.5) и вспышка (49.5)
s1 = noise_sweep(2.4, amp=0.30, seed=11)
add(L, s1 * 0.9, 24.0); add(R, s1, 24.12)
s2 = noise_sweep(2.2, amp=0.34, seed=23)
add(L, s2, 49.3); add(R, s2 * 0.9, 49.42)
# 6. Финальный тёплый аккорд (55-60) — усиливаем мажор
for k, nm in enumerate(['C4', 'E4', 'G4', 'C5']):
    v = 0.16 * pad_voice(note(nm), 6.0, detune=0.002)
    add(L, v * (0.7 + 0.3 * k / 3), 54.6); add(R, v, 54.72)

# 7. Псевдо-реверберация: несколько затухающих копий
taps = [(0.031, 0.34), (0.053, 0.26), (0.079, 0.19), (0.113, 0.13), (0.191, 0.08)]
wetL = np.zeros(N); wetR = np.zeros(N)
for delay, g in taps:
    d = int(delay * SR)
    wetL[d:] += L[:N - d] * g
    wetR[d:] += R[:N - d] * g
mixL = 0.78 * L + 0.42 * wetL
mixR = 0.78 * R + 0.42 * wetR

# 8. Общая огибающая громкости по секциям (партитура из раскадровки)
t = np.arange(N) / SR
curve = np.interp(t, [0, 9, 10, 24, 25, 39, 40, 49, 50, 54, 55, 59.5, 60],
                     [0.62, 0.72, 0.55, 0.60, 0.95, 1.00, 0.42, 0.38, 1.05, 1.10, 0.95, 0.80, 0.0])
mixL *= curve; mixR *= curve

# 9. Финальная нормализация
peak = max(np.max(np.abs(mixL)), np.max(np.abs(mixR)))
mixL = mixL / peak * 0.72; mixR = mixR / peak * 0.72
# фейды входа/выхода
f_in = int(0.4 * SR); f_out = int(1.2 * SR)
for ch in (mixL, mixR):
    ch[:f_in] *= np.linspace(0, 1, f_in)
    ch[-f_out:] *= np.linspace(1, 0, f_out)

stereo = np.stack([mixL, mixR], axis=1)
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'audio', 'music.wav')
out = os.path.abspath(out)
with wave.open(out, 'wb') as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes((np.clip(stereo, -1, 1) * 32767).astype('<i2').tobytes())
print(json.dumps({'file': out, 'seconds': DUR, 'peak': float(peak),
                  'rms_db': float(20 * np.log10(np.sqrt(np.mean(stereo ** 2)) + 1e-9))}, ensure_ascii=False))
