"""졸라맨(스틱 피겨) 애니메이션: 교사를 꿈꾸는 대학생의 1~4학년 성장기 GIF 생성기 (영문판).

실행:  python make_gif.py   ->  teacher_dream_en.gif 생성
"""
import math
import os
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 640, 400
GROUND = 300
FRAMES_PER_SCENE = 30
DURATION_MS = 80

INK = (30, 30, 40)
ME = (40, 90, 200)        # 주인공 색
PAPER = (252, 250, 245)
BOARD = (40, 80, 60)
ACCENT = (230, 90, 70)
GOLD = (240, 180, 40)
GRAY = (150, 150, 160)

FONT_CANDIDATES = [
    "C:/Windows/Fonts/arialbd.ttf",                              # Windows
    "C:/Windows/Fonts/arial.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",         # macOS
    "/Library/Fonts/Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",      # Linux / Streamlit Cloud
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]


def load_font(size):
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    try:
        return ImageFont.load_default(size=size)  # Pillow 10.1+ : 크기 조절 가능한 기본 폰트
    except TypeError:
        return ImageFont.load_default()


F_BIG = load_font(30)
F_MID = load_font(20)
F_SMALL = load_font(14)


# ---------------------------------------------------------------- 그리기 도구
def limb(d, x, y, length, angle_deg, color, width=4):
    """(x, y)에서 angle 방향으로 선을 그리고 끝점을 반환. 0도=아래, +는 앞(오른쪽)."""
    a = math.radians(angle_deg)
    x2 = x + length * math.sin(a)
    y2 = y + length * math.cos(a)
    d.line([(x, y), (x2, y2)], fill=color, width=width)
    return x2, y2


def stick(d, x, foot_y, s=1.0, color=INK, arm_l=20, arm_r=-20,
          leg_l=15, leg_r=-15, face="smile", glasses=False, cap=False,
          sitting=False):
    """졸라맨 그리기. x=몸 중심, foot_y=발 위치, s=크기 배율."""
    w = max(2, int(4 * s))
    head_r = 14 * s
    body = 40 * s
    leg = 34 * s
    arm = 30 * s

    hip_y = foot_y - (leg * 0.75 if sitting else leg)
    neck_y = hip_y - body
    head_cy = neck_y - head_r

    # 다리
    if sitting:
        kx, ky = x + 22 * s, hip_y
        d.line([(x, hip_y), (kx, ky)], fill=color, width=w)
        d.line([(kx, ky), (kx, foot_y)], fill=color, width=w)
    else:
        limb(d, x, hip_y, leg, leg_l, color, w)
        limb(d, x, hip_y, leg, leg_r, color, w)
    # 몸통
    d.line([(x, neck_y), (x, hip_y)], fill=color, width=w)
    # 머리
    d.ellipse([x - head_r, head_cy - head_r, x + head_r, head_cy + head_r],
              fill=PAPER, outline=color, width=w)
    # 얼굴
    ex = 5 * s
    ey = head_cy - 3 * s
    if face == "focus":
        d.line([(x - ex - 2 * s, ey), (x - ex + 2 * s, ey)], fill=color, width=max(1, w - 1))
        d.line([(x + ex - 2 * s, ey), (x + ex + 2 * s, ey)], fill=color, width=max(1, w - 1))
    else:
        r = 1.6 * s
        d.ellipse([x - ex - r, ey - r, x - ex + r, ey + r], fill=color)
        d.ellipse([x + ex - r, ey - r, x + ex + r, ey + r], fill=color)
    if face in ("smile", "happy"):
        span = 7 * s if face == "smile" else 8 * s
        d.arc([x - span, head_cy - 2 * s, x + span, head_cy + 8 * s],
              start=20, end=160, fill=color, width=max(1, w - 1))
    elif face in ("focus", "neutral"):
        d.line([(x - 4 * s, head_cy + 6 * s), (x + 4 * s, head_cy + 6 * s)],
               fill=color, width=max(1, w - 1))
    elif face == "wow":
        d.ellipse([x - 3 * s, head_cy + 3 * s, x + 3 * s, head_cy + 9 * s],
                  outline=color, width=max(1, w - 1))
    if glasses:
        gr = 4.5 * s
        for gx in (x - ex, x + ex):
            d.ellipse([gx - gr, ey - gr, gx + gr, ey + gr], outline=color, width=max(1, w - 2))
        d.line([(x - ex + gr, ey), (x + ex - gr, ey)], fill=color, width=max(1, w - 2))
    # 팔 (머리 위에 그려서 손든 모습이 가려지지 않게)
    sh_y = neck_y + 8 * s
    hl = limb(d, x, sh_y, arm, arm_l, color, w)
    hr = limb(d, x, sh_y, arm, arm_r, color, w)
    if cap:  # 학사모
        top = head_cy - head_r
        d.polygon([(x - 20 * s, top), (x, top - 8 * s), (x + 20 * s, top), (x, top + 6 * s)],
                  fill=INK)
        d.line([(x + 16 * s, top), (x + 18 * s, top + 16 * s)], fill=GOLD, width=max(1, w - 2))
    return {"head": (x, head_cy), "head_r": head_r, "hand_l": hl, "hand_r": hr}


def text_c(d, xy, msg, font, fill=INK):
    d.text(xy, msg, font=font, fill=fill, anchor="mm")


def ground(d):
    d.line([(0, GROUND), (W, GROUND)], fill=INK, width=3)


def progress(d, year):
    """하단 1~4학년 진행 표시."""
    labels = ["Year 1", "Year 2", "Year 3", "Year 4", "Teacher"]
    y = 360
    xs = [100 + i * 110 for i in range(5)]
    d.line([(xs[0], y), (xs[-1], y)], fill=GRAY, width=3)
    if year > 1:
        d.line([(xs[0], y), (xs[min(year, 5) - 1], y)], fill=ME, width=5)
    for i, (px, lab) in enumerate(zip(xs, labels), start=1):
        done = i <= year
        col = GOLD if (i == 5 and done) else (ME if done else PAPER)
        d.ellipse([px - 9, y - 9, px + 9, y + 9], fill=col, outline=INK, width=2)
        text_c(d, (px, y + 22), lab, F_SMALL, INK if done else GRAY)


def caption(d, msg, sub=None):
    text_c(d, (W // 2, 34), msg, F_BIG)
    if sub:
        text_c(d, (W // 2, 68), sub, F_SMALL, (90, 90, 100))


def new_frame():
    img = Image.new("RGB", (W, H), PAPER)
    return img, ImageDraw.Draw(img)


def book(d, x, y, w=26, h=20, color=ACCENT):
    d.rectangle([x, y, x + w, y + h], fill=color, outline=INK, width=2)
    d.line([(x + 4, y), (x + 4, y + h)], fill=INK, width=1)


def desk(d, x, y=GROUND, w=110):
    top = y - 50
    d.rectangle([x, top, x + w, top + 8], fill=(180, 130, 80), outline=INK, width=2)
    d.line([(x + 8, top + 8), (x + 8, y)], fill=INK, width=4)
    d.line([(x + w - 8, top + 8), (x + w - 8, y)], fill=INK, width=4)
    return top


def blackboard(d, x, y, w, h, lines=()):
    d.rectangle([x, y, x + w, y + h], fill=BOARD, outline=(120, 80, 40), width=6)
    for i, t in enumerate(lines):
        d.text((x + 14, y + 12 + i * 26), t, font=F_MID, fill=(240, 240, 230))


def walk_angles(t, speed=0.6):
    a = math.sin(t * speed) * 28
    return dict(leg_l=a, leg_r=-a, arm_l=-a * 0.8, arm_r=a * 0.8)


# ---------------------------------------------------------------- 장면
def scene_intro(f):
    img, d = new_frame()
    ground(d)
    caption(d, "My dream: Teacher!", "A stick-figure student's 4-year journey")
    x = 120 + f * 4
    stick(d, x, GROUND, **walk_angles(f), face="smile")
    # 생각 풍선 + 작은 칠판
    if f > 8:
        bx, by = x + 60, 120
        for i, r in enumerate((4, 7)):
            d.ellipse([x + 20 + i * 16 - r, 185 - i * 18 - r, x + 20 + i * 16 + r, 185 - i * 18 + r],
                      outline=INK, width=2, fill=PAPER)
        d.ellipse([bx - 10, by - 45, bx + 130, by + 40], outline=INK, width=2, fill=PAPER)
        d.rectangle([bx + 18, by - 22, bx + 102, by + 18], fill=BOARD)
        d.text((bx + 28, by - 16), "1+1=2", font=F_SMALL, fill=(240, 240, 230))
    progress(d, 0)
    return img


def scene_year1(f):
    img, d = new_frame()
    ground(d)
    caption(d, "Year 1 - Welcome to College!", "Starting with Intro to Education")
    # 건물
    bx = 400
    d.rectangle([bx, 140, bx + 190, GROUND], fill=(235, 228, 215), outline=INK, width=3)
    d.polygon([(bx - 10, 140), (bx + 95, 95), (bx + 200, 140)], fill=(200, 90, 70), outline=INK)
    text_c(d, (bx + 95, 160), "College of Ed.", F_MID)
    for wx in (bx + 20, bx + 75, bx + 130):
        d.rectangle([wx, 185, wx + 40, 215], fill=(190, 220, 240), outline=INK, width=2)
    d.rectangle([bx + 75, 240, bx + 115, GROUND], fill=(150, 100, 60), outline=INK, width=2)
    x = 60 + f * 9
    p = stick(d, x, GROUND, **walk_angles(f, 0.7), face="smile")
    hx, hy = p["hand_r"]
    book(d, hx - 4, hy - 10)
    progress(d, 1)
    return img


def scene_year2(f):
    img, d = new_frame()
    ground(d)
    caption(d, "Year 2 - Deep in Study", "Late nights at the library")
    # 창밖 달
    d.rectangle([60, 100, 180, 200], fill=(40, 50, 90), outline=INK, width=3)
    d.ellipse([110, 115, 145, 150], fill=(250, 240, 180))
    d.ellipse([122, 112, 152, 142], fill=(40, 50, 90))
    for sx, sy in ((80, 170), (160, 180), (90, 120)):
        d.ellipse([sx - 2, sy - 2, sx + 2, sy + 2], fill=(250, 250, 220))
    top = desk(d, 300)
    # 쌓이는 책
    n = 1 + f // 5
    for i in range(min(n, 7)):
        book(d, 370, top - 16 - i * 16, 34, 14, [ACCENT, ME, GOLD, (90, 160, 90)][i % 4])
    # 공부하는 사람 (앉아서 필기)
    writing = math.sin(f * 1.3) * 10
    stick(d, 270, GROUND, sitting=True, face="focus", glasses=True,
          arm_r=95 + writing, arm_l=80)
    d.line([(318, top - 2), (345, top - 2)], fill=GRAY, width=2)  # 노트
    # 땀방울/열정
    if f % 10 < 6:
        d.text((240, 150), "!", font=F_BIG, fill=ACCENT)
    text_c(d, (520, 230), f"Studying: {f * 4 + 10} hrs...", F_SMALL, GRAY)
    progress(d, 2)
    return img


def scene_year3(f):
    img, d = new_frame()
    ground(d)
    caption(d, "Year 3 - Practice Teaching", "Nervous, but one more time!")
    blackboard(d, 60, 110, 240, 120, ["Lesson Plan", "1. Warm-up", "2. Activity"][: 1 + f // 8])
    point = -125 + math.sin(f * 0.5) * 15
    stick(d, 340, GROUND, arm_r=point, arm_l=25, face="smile")
    # 친구들(작게)
    for i, fx in enumerate((470, 530, 590)):
        up = (f // 6 + i) % 3 == 0
        stick(d, fx, GROUND, s=0.75, color=GRAY,
              arm_r=-210 if up else -15, arm_l=15, face="smile")
    if f > 15:
        text_c(d, (530, 150), "Clap clap!", F_MID, ACCENT)
    progress(d, 3)
    return img


def scene_year4(f):
    img, d = new_frame()
    ground(d)
    if f < 14:
        caption(d, "Year 4 - Student Teaching", "Meeting real students for the first time")
        blackboard(d, 60, 110, 200, 110, ["Hello, class!"])
        stick(d, 300, GROUND, arm_r=-125 + math.sin(f) * 20, face="happy")
        for i, kx in enumerate((420, 480, 540, 600)):
            stick(d, kx, GROUND, s=0.6, color=GRAY, face="smile",
                  arm_r=-210 if (f + i) % 4 == 0 else -10)
    else:
        caption(d, "Year 4 - Teacher Exam", "Four years of effort, all in one day")
        top = desk(d, 250)
        d.rectangle([300, top - 6, 345, top], fill=(255, 255, 255), outline=INK, width=1)
        text_c(d, (322, top - 25), "EXAM", F_SMALL)
        stick(d, 220, GROUND, sitting=True, face="focus", glasses=True,
              arm_r=95 + math.sin(f * 1.5) * 8, arm_l=80)
        if f >= 22:
            # 합격 도장
            s = min(1.0, (f - 21) / 3)
            cx, cy, r = 490, 190, int(60 * s)
            d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=ACCENT, width=6)
            if s >= 1:
                text_c(d, (cx, cy), "PASS!", load_font(30), ACCENT)
    progress(d, 4)
    return img


rng = random.Random(7)
CONFETTI = [(rng.randint(0, W), rng.randint(-300, 0), rng.choice([ACCENT, GOLD, ME, (90, 170, 90)]),
             rng.uniform(4, 8)) for _ in range(60)]


def scene_teacher(f):
    img, d = new_frame()
    ground(d)
    caption(d, "I Became a Teacher!", "4 years of hard work - a new beginning")
    blackboard(d, 40, 100, 250, 130, ["Dreams", "come true!"])
    stick(d, 330, GROUND, arm_r=-125 + math.sin(f * 0.6) * 15, arm_l=40,
          face="happy", cap=f < 10)
    # 교사 명찰
    d.rectangle([334, 240, 352, 252], fill=GOLD, outline=INK)
    for i, kx in enumerate((440, 500, 560, 620)):
        stick(d, kx, GROUND, s=0.6, color=GRAY, face="happy",
              arm_r=-210 if (f // 4 + i) % 2 == 0 else -20)
    for cx, cy, col, sp in CONFETTI:
        y = cy + f * sp * 3
        if 0 < y < GROUND:
            d.rectangle([cx, y, cx + 6, y + 4], fill=col)
    progress(d, 5)
    return img


SCENES = [scene_intro, scene_year1, scene_year2, scene_year3, scene_year4, scene_teacher]


def generate(path="teacher_dream_en.gif"):
    frames, durations = [], []
    for scene in SCENES:
        for f in range(FRAMES_PER_SCENE):
            frames.append(scene(f))
            durations.append(DURATION_MS)
        durations[-1] = 900  # 장면 끝에서 잠깐 멈춤
    durations[-1] = 2500     # 마지막 장면은 길게
    pal = [fr.convert("P", palette=Image.ADAPTIVE, colors=64) for fr in frames]
    pal[0].save(path, save_all=True, append_images=pal[1:], duration=durations,
                loop=0, optimize=True, disposal=2)
    return Path(path)


if __name__ == "__main__":
    out = generate(str(Path(__file__).with_name("teacher_dream_en.gif")))
    print(f"Saved: {out} ({out.stat().st_size / 1024:.0f} KB)")
