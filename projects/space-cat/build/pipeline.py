#!/usr/bin/env python3
"""Сборка мультфильма «Лум и Звёздочка» из ключевых кадров.

Стадии:
  A. Каждый кадр -> 5.47-сек шот с движением камеры (ffmpeg zoompan). Кэшируется в build/shots/.
  B. Склейка шотов через xfade + титры/субтитры через drawtext -> build/visual.mp4 (один проход).
  C. Закадровый голос (подгонка темпа, расстановка по таймкодам) + музыка с дакингом -> audio/mix.wav
  D. Мукс -> out/<name>.mp4

Пример:  python3 build/pipeline.py --lines 12 --out out/lum_i_zvezdochka_60s.mp4
"""
import argparse, json, os, subprocess, sys, wave
import numpy as np
import imageio_ffmpeg

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRAMES = os.path.join(ROOT, 'frames')
AUDIO = os.path.join(ROOT, 'audio')
BUILD = os.path.join(ROOT, 'build')
SHOTS = '/tmp/wan-cartoon/shots'   # кэш шотов вне репозитория
OUT = os.path.join(ROOT, 'out')
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
FONT_BOLD = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
FONT_REG = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'

FPS = 30
SHOT_FRAMES = 164                 # 164/30 = 5.4667 с
SHOT_DUR = SHOT_FRAMES / FPS
XFADE = 0.5
SLOT = SHOT_DUR - XFADE           # шаг между началами шотов
W, H = 1080, 1920
UPSCALE = 'scale=1728:3096:flags=lanczos'

# --- движение камеры по шотам: (тип, z0/zmax, px0,dpx, py0,dpy, sine) ---
MOTION = {
    1:  ('in',  1.00, 1.14, 0.50, 0.02, 0.55, 0.02, 0.010),
    2:  ('in',  1.02, 1.22, 0.50, 0.00, 0.36, 0.00, 0.012),
    3:  ('out', 1.16, 1.02, 0.50, 0.02, 0.12, 0.30, 0.000),
    4:  ('in',  1.00, 1.14, 0.46, 0.04, 0.52, 0.02, 0.008),
    5:  ('in',  1.00, 1.16, 0.50, 0.00, 0.50, 0.00, 0.010),
    6:  ('out', 1.20, 1.02, 0.50, 0.03, 0.70, -0.25, 0.000),
    7:  ('in',  1.04, 1.14, 0.28, 0.34, 0.50, 0.04, 0.006),
    8:  ('out', 1.18, 1.04, 0.50, 0.05, 0.30, -0.16, 0.000),
    9:  ('in',  1.00, 1.20, 0.50, 0.00, 0.48, 0.02, 0.008),
    10: ('in',  1.02, 1.22, 0.50, 0.00, 0.50, 0.00, 0.006),
    11: ('out', 1.22, 1.02, 0.50, 0.00, 0.66, -0.30, 0.000),
    12: ('out', 1.16, 1.00, 0.50, 0.00, 0.58, -0.10, 0.008),
}
TRANSITION = {8: 'fadeblack', 10: 'fadewhite'}   # кризис и вспышка

# --- титры ---
TITLE = 'ЛУМ И ЗВЁЗДОЧКА'
SUBTITLE_LINE = 'короткометражный мультфильм'
END_TITLE = 'КОНЕЦ'
CREDIT = 'кадры: нейросеть · монтаж: ffmpeg · 2026'


def sh(cmd, quiet=True):
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        sys.stderr.write(r.stderr.decode('utf-8', 'replace')[-4000:] + '\n')
        raise RuntimeError('ffmpeg failed: ' + ' '.join(map(str, cmd[:12])))
    return r


def zoompan_expr(i):
    kind, z0, z1, px0, dpx, py0, dpy, sine = MOTION[i]
    prog = 'on/%d' % (SHOT_FRAMES - 1)
    if kind == 'in':
        z = f'({z0}+({z1}-{z0})*{prog})'
    else:
        z = f'({z0}-({z0}-{z1})*{prog})'
    px = f'({px0}+{dpx}*{prog})'
    py = f'({py0}+{dpy}*{prog})'
    x = f'(iw-iw/zoom)*{px}'
    y = f'(ih-ih/zoom)*{py}'
    if sine:
        x = f'({x}+{sine}*iw/zoom*sin(on/26))'
        y = f'({y}+{sine}*ih/zoom*cos(on/31))'
    return f"z='{z}':x='clip({x},0,iw-iw/zoom)':y='clip({y},0,ih-ih/zoom)'"


def build_shot(i, force=False):
    os.makedirs(SHOTS, exist_ok=True)
    src = os.path.join(FRAMES, f'shot{i:02d}.png')
    dst = os.path.join(SHOTS, f'shot{i:02d}.mp4')
    if not os.path.exists(src):
        return None
    if os.path.exists(dst) and not force and os.path.getmtime(dst) > os.path.getmtime(src):
        return dst
    vf = (f'{UPSCALE},zoompan={zoompan_expr(i)}:d={SHOT_FRAMES}:s={W}x{H}:fps={FPS},'
          f'format=yuv420p')
    sh([FFMPEG, '-y', '-hide_banner', '-loglevel', 'error', '-i', src, '-vf', vf,
        '-frames:v', str(SHOT_FRAMES), '-c:v', 'libx264', '-preset', 'medium', '-crf', '16', dst])
    return dst


# ---------- звук ----------
def trimmed_seconds(path):
    cmd = [FFMPEG, '-hide_banner', '-i', path, '-af',
           'silenceremove=start_periods=1:start_silence=0.05:start_threshold=-45dB:'
           'stop_periods=-1:stop_silence=0.15:stop_threshold=-45dB', '-f', 'null', '-']
    r = subprocess.run(cmd, capture_output=True)
    txt = r.stderr.decode('utf-8', 'replace')
    times = [l.split('time=')[1].split()[0] for l in txt.splitlines() if 'time=' in l]
    if not times:
        return None
    h, m, s = times[-1].split(':')
    return int(h) * 3600 + int(m) * 60 + float(s)


def decode_voice(path, tempo):
    af = ('silenceremove=start_periods=1:start_silence=0.05:start_threshold=-45dB:'
          'stop_periods=-1:stop_silence=0.15:stop_threshold=-45dB,'
          f'atempo={tempo:.4f},highpass=f=85,acompressor=threshold=-18dB:ratio=2.5:attack=8:release=180')
    r = sh([FFMPEG, '-hide_banner', '-loglevel', 'error', '-i', path, '-af', af,
            '-f', 'f32le', '-ac', '1', '-ar', '44100', '-'])
    return np.frombuffer(r.stdout, dtype='<f4').astype(np.float32)


def plan_lines(n_lines, total, shot_start):
    """Расставляет реплики: подгоняет темп (<=1.28), не даёт репликам накладываться."""
    durs, raws = [], []
    for i in range(1, n_lines + 1):
        p = os.path.join(AUDIO, f'line{i:02d}.mp3')
        if not os.path.exists(p):
            print(f'нет озвучки line{i:02d}.mp3 — реплика будет только текстом')
            raws.append(None); durs.append(None)
            continue
        d = trimmed_seconds(p)
        if not d:
            raws.append(None); durs.append(None)
            continue
        raws.append(d); durs.append(d)
    extra = 1.0
    for _ in range(40):
        plan, prev_end = [], 0.0
        for i, d in enumerate(durs):
            if d is None:                      # нет озвучки — окно по шоту
                t0 = shot_start[i] + 0.55
                plan.append({'i': i + 1, 't0': t0, 'dur': SLOT - 0.95, 'tempo': None, 'raw': 0.0,
                             'voiced': False})
                prev_end = t0 + SLOT - 0.95
                continue
            need = d / max(0.4, (SLOT - 0.45))
            tempo = min(1.28 * extra, max(1.0, need))
            dur = d / tempo
            t0 = max(shot_start[i] + 0.35, prev_end + 0.15)
            plan.append({'i': i + 1, 't0': t0, 'dur': dur, 'tempo': tempo, 'raw': d,
                         'voiced': True})
            prev_end = t0 + dur
        # критерий: озвученные реплики должны укладываться с запасом на финал
        voiced_end = max([q['t0'] + q['dur'] for q in plan if q.get('voiced', True)] or [0])
        if voiced_end <= total - 6.0 or extra >= 1.32:
            break
        extra *= 1.03
    return plan


def make_mix(n_lines, total, shot_start):
    plan = plan_lines(n_lines, total, shot_start)
    N = int(total * 44100)
    voice = np.zeros(N, dtype=np.float32)
    for p in plan:
        if not p.get('voiced', True):
            continue
        x = decode_voice(os.path.join(AUDIO, f'line{p["i"]:02d}.mp3'), p['tempo'])
        # лёгкая «космическая» реверберация голоса
        y = x.copy()
        for dly, g in ((0.055, 0.20), (0.115, 0.12), (0.19, 0.07)):
            k = int(dly * 44100)
            y[k:] += x[:len(y) - k] * g
        j = int(p['t0'] * 44100)
        e = min(j + len(y), N)
        voice[j:e] += y[:e - j]
    # музыка
    with wave.open(os.path.join(AUDIO, 'music.wav'), 'rb') as w:
        music = np.frombuffer(w.readframes(w.getnframes()), dtype='<i2').astype(np.float32) / 32768.0
    music = music.reshape(-1, 2)
    if len(music) < N:
        music = np.pad(music, ((0, N - len(music)), (0, 0)))
    music = music[:N]
    # дакинг музыки под голосом
    env = np.abs(voice)
    k = int(0.25 * 44100)
    ker = np.ones(k, dtype=np.float32) / k
    env = np.convolve(env, ker, mode='same')
    env = env / (env.max() + 1e-6)
    duck = 1.0 - 0.45 * env
    music *= duck[:, None]
    voice_n = voice / (np.abs(voice).max() + 1e-6) * 0.92
    mix = music * 0.62 + voice_n[:, None]
    peak = np.abs(mix).max()
    mix = mix / peak * 0.95
    mix = np.tanh(mix * 1.05) * 0.96
    out = os.path.join(AUDIO, 'mix.wav')
    with wave.open(out, 'wb') as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(44100)
        w.writeframes((np.clip(mix, -1, 1) * 32767).astype('<i2').tobytes())
    json.dump(plan, open(os.path.join(BUILD, 'voice_plan.json'), 'w'), ensure_ascii=False, indent=1)
    return out, plan


# ---------- текст на кадре (libass) ----------
def wrap(text, width=30):
    words, lines, cur = text.split(), [], ''
    for wd in words:
        if len(cur) + len(wd) + 1 <= width:
            cur = (cur + ' ' + wd).strip()
        else:
            lines.append(cur); cur = wd
    if cur: lines.append(cur)
    return '\\N'.join(lines)          # мягкий перенос строки в ASS


def ts(t):
    h = int(t // 3600); m = int(t % 3600 // 60); s = t % 60
    return f'{h}:{m:02d}:{s:05.2f}'


ASS_HEAD = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sub,DejaVu Sans,52,&H00FFFFFF,&H000000FF,&HB4000000,&HB4000000,-1,0,0,0,100,100,0.5,0,1,3.6,3,2,70,70,250,204
Style: Title,DejaVu Sans,100,&H008AD9FF,&H000000FF,&H90000000,&H90000000,-1,0,0,0,100,100,1.2,0,1,4,5,8,40,40,215,204
Style: Tag,DejaVu Sans,40,&H00F3ECFF,&H000000FF,&HB4000000,&HB4000000,0,0,0,0,100,100,1,0,1,3,2,8,40,40,375,204
Style: End,DejaVu Sans,92,&H00A0E2FF,&H000000FF,&H90000000,&H90000000,-1,0,0,0,100,100,2,0,1,4,5,8,40,40,240,204

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def write_ass(plan, total, path, title=True, endcard=True):
    ev = []
    if title:
        ev.append(f'Dialogue: 0,{ts(0.45)},{ts(4.45)},Title,,0,0,0,,'
                  f'{{\\fad(500,500)\\fscx96\\fscy96\\t(0,700,\\fscx100\\fscy100)}}{wrap(TITLE, 26)}')
        ev.append(f'Dialogue: 0,{ts(0.95)},{ts(4.45)},Tag,,0,0,0,,'
                  f'{{\\fad(600,500)}}{wrap(SUBTITLE_LINE, 40)}')
    for p in plan:
        t0 = max(p['t0'], 0.2)
        t1 = min(p['t0'] + p['dur'] - 0.05, total - 0.2)
        ev.append(f'Dialogue: 0,{ts(t0)},{ts(t1)},Sub,,0,0,0,,'
                  f'{{\\fad(340,380)}}{wrap(TEXT[p["i"] - 1], 30)}')
    if endcard:
        ev.append(f'Dialogue: 0,{ts(total - 4.1)},{ts(total - 0.3)},End,,0,0,0,,'
                  f'{{\\fad(600,500)\\fscx95\\fscy95\\t(0,800,\\fscx103\\fscy103)}}{wrap(END_TITLE, 26)}')
        ev.append(f'Dialogue: 0,{ts(total - 3.7)},{ts(total - 0.3)},Tag,,0,0,0,,'
                  f'{{\\fad(700,500)}}{wrap(CREDIT, 38)}')
    open(path, 'w', encoding='utf-8').write(ASS_HEAD + '\n'.join(ev) + '\n')
    return path


def build_visual(shots, out_path, force=False):
    """Тяжёлый проход: склейка шотов через xfade. Кэшируется."""
    if os.path.exists(out_path) and not force:
        print('склейка уже готова, беру из кэша:', out_path)
        return out_path
    inputs, filters, cur = [], [], '[0:v]'
    for p in shots:
        inputs += ['-i', p]
    for k in range(1, len(shots)):
        off = k * SLOT
        tr = TRANSITION.get(k, 'fade')
        lbl = f'[x{k}]'
        filters.append(f'{cur}[{k}:v]xfade=transition={tr}:duration={XFADE}:offset={off:.4f}{lbl}')
        cur = lbl
    filters.append(f'{cur}format=yuv420p[v]')
    sh([FFMPEG, '-y', '-hide_banner', '-loglevel', 'error'] + inputs + [
        '-filter_complex', ';'.join(filters), '-map', '[v]',
        '-c:v', 'libx264', '-preset', 'slow', '-crf', '17', '-pix_fmt', 'yuv420p',
        '-r', str(FPS), out_path])
    return out_path


TEXT = [
    'Высоко в звёздном небе жил котёнок Лум — самый маленький хранитель звёзд.',
    'Каждую ночь он зажигал огоньки и следил, чтобы ни одна звёздочка не погасла.',
    'Но однажды маленькая звезда вздрогнула и сорвалась вниз.',
    'Лум нашёл её в траве — тёплую, но совсем потухшую.',
    '«Не бойся, — прошептал он. — Я верну тебя домой.»',
    'Он взял свою ракету и полетел сквозь синюю туманность.',
    'Мимо пронеслась комета и осветила ему дорогу.',
    'Дорога была длинной, и впереди ждала темнота.',
    'Путь был долгим, и звёздочка почти погасла в его лапах.',
    'Тогда Лум обнял её и отдал своё тепло.',
    'И звезда вспыхнула — ярко, как тысяча маяков!',
    'С тех пор он знал: даже самый маленький свет может зажечь целое небо.',
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--lines', type=int, default=12)
    ap.add_argument('--max-shots', type=int, default=12)
    ap.add_argument('--out', default=os.path.join(OUT, 'lum_i_zvezdochka_60s.mp4'))
    ap.add_argument('--no-title', action='store_true')
    ap.add_argument('--force-shots', action='store_true')
    ap.add_argument('--force-visual', action='store_true')
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    work = '/tmp/wan-cartoon'; os.makedirs(work, exist_ok=True)
    shots = []
    for i in range(1, a.max_shots + 1):
        p = build_shot(i, force=a.force_shots)
        if p is None:
            print(f'нет кадра shot{i:02d}.png — пропускаю')
            continue
        shots.append(p)
    total = len(shots) * SHOT_DUR - (len(shots) - 1) * XFADE
    print(f'шотов: {len(shots)} · реплик: {a.lines} · длительность: {total:.2f} с')

    silent = build_visual(shots, os.path.join(work, 'visual.mp4'), force=a.force_visual)
    shot_start = [k * SLOT for k in range(len(shots))]
    mix, plan = make_mix(a.lines, total, shot_start)
    assfile = write_ass(plan, total, os.path.join(BUILD, 'subs.ass'), title=not a.no_title)

    # финальный проход: титры + звук + нормализация
    sh([FFMPEG, '-y', '-hide_banner', '-loglevel', 'error', '-i', silent, '-i', mix,
        '-vf', f"ass='{assfile}'",
        '-map', '0:v', '-map', '1:a',
        '-c:v', 'libx264', '-preset', 'slow', '-crf', '19', '-pix_fmt', 'yuv420p',
        '-c:a', 'aac', '-b:a', '192k', '-ar', '48000',
        '-af', 'loudnorm=I=-16:TP=-1.5:LRA=11', '-t', f'{total:.3f}',
        '-movflags', '+faststart', a.out])
    print('готово:', a.out)
    for p in plan:
        mark = f"темп {p['tempo']:.2f}×" if p.get('voiced', True) else 'только текст'
        print(f"  реплика {p['i']:02d}: {p['t0']:5.2f}–{p['t0'] + p['dur']:5.2f} с  ({mark})")


if __name__ == '__main__':
    main()
