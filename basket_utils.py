import math
import numpy as np
import torch

def get_device():
    """Automatically select device -> cuda > mps > cpu"""
    if torch.cuda.is_available():
        return 'cuda'
    elif torch.backends.mps.is_available():
        return 'mps'
    return 'cpu'


def score(ball_pos, hoop_pos):
    """Check if the ball's trajectory intersects the hoop region (more accurate version)."""
    if len(ball_pos) < 2 or len(hoop_pos) < 1:
        return False

    rim_center = hoop_pos[-1][0]
    rim_w = hoop_pos[-1][2]
    rim_h = hoop_pos[-1][3]
    rim_x1 = rim_center[0] - 0.4 * rim_w
    rim_x2 = rim_center[0] + 0.4 * rim_w
    rim_y1 = rim_center[1] - 0.3 * rim_h  # upper part of the hoop
    rim_y2 = rim_center[1] + 0.2 * rim_h  # lower part

    above = None
    below = None
    for i in reversed(range(len(ball_pos))):
        y = ball_pos[i][0][1]
        if y < rim_y1:
            above = ball_pos[i][0]
        elif y > rim_y2 and above:
            below = ball_pos[i][0]
            break

    if above and below:
        x = [above[0], below[0]]
        y = [above[1], below[1]]

        try:
            m, b = np.polyfit(x, y, 1)
            for check_x in np.linspace(rim_x1, rim_x2, 5):
                pred_y = m * check_x + b
                if rim_y1 <= pred_y <= rim_y2:
                    return True
        except:
            pass

    return False


def detect_down(ball_pos, hoop_pos):
    """Detect if the ball has dropped significantly below the hoop."""
    if not hoop_pos or not ball_pos:
        return False
    hoop_y = hoop_pos[-1][0][1]
    hoop_h = hoop_pos[-1][3]
    ball_y = ball_pos[-1][0][1]

    return ball_y > hoop_y + 0.5 * hoop_h + 5  # small buffer


def detect_up(ball_pos, hoop_pos):
    """Detect if the ball has entered the area above the hoop (for shot detection)."""
    if not hoop_pos or not ball_pos:
        return False

    hoop_x, hoop_y = hoop_pos[-1][0]
    hoop_w, hoop_h = hoop_pos[-1][2], hoop_pos[-1][3]
    bx, by = ball_pos[-1][0]

    x1 = hoop_x - 2.5 * hoop_w
    x2 = hoop_x + 2.5 * hoop_w
    y1 = hoop_y - 2.2 * hoop_h
    y2 = hoop_y

    return x1 < bx < x2 and y1 < by < y2


def in_hoop_region(center, hoop_pos):
    """Check if ball center is within hoop region."""
    if not hoop_pos:
        return False

    hx, hy = hoop_pos[-1][0]
    hw, hh = hoop_pos[-1][2], hoop_pos[-1][3]

    x1 = hx - 0.5 * hw
    x2 = hx + 0.5 * hw
    y1 = hy - 0.2 * hh
    y2 = hy + 0.3 * hh

    return x1 <= center[0] <= x2 and y1 <= center[1] <= y2


def clean_ball_pos(ball_pos, frame_count):
    """Remove outlier or inaccurate ball detections."""
    if len(ball_pos) > 1:
        w1, h1 = ball_pos[-2][2], ball_pos[-2][3]
        w2, h2 = ball_pos[-1][2], ball_pos[-1][3]

        x1, y1 = ball_pos[-2][0]
        x2, y2 = ball_pos[-1][0]

        f1, f2 = ball_pos[-2][1], ball_pos[-1][1]
        f_dif = f2 - f1

        dist = math.sqrt((x2 - x1)**2 + (y2 - y1)**2)
        max_dist = 4 * math.sqrt(w1**2 + h1**2)

        if dist > max_dist and f_dif < 5:
            ball_pos.pop()

        elif (w2 * 1.4 < h2) or (h2 * 1.4 < w2):
            ball_pos.pop()

    if len(ball_pos) > 0 and frame_count - ball_pos[0][1] > 30:
        ball_pos.pop(0)

    return ball_pos


def clean_hoop_pos(hoop_pos):
    """Remove inconsistent or jumping hoop data."""
    if len(hoop_pos) > 1:
        x1, y1 = hoop_pos[-2][0]
        x2, y2 = hoop_pos[-1][0]

        w1, h1 = hoop_pos[-2][2], hoop_pos[-2][3]
        w2, h2 = hoop_pos[-1][2], hoop_pos[-1][3]

        f1, f2 = hoop_pos[-2][1], hoop_pos[-1][1]
        f_dif = f2 - f1

        dist = math.sqrt((x2 - x1)**2 + (y2 - y1)**2)
        max_dist = 0.5 * math.sqrt(w1**2 + h1**2)

        if dist > max_dist and f_dif < 5:
            hoop_pos.pop()

        if (w2 * 1.3 < h2) or (h2 * 1.3 < w2):
            hoop_pos.pop()

    if len(hoop_pos) > 25:
        hoop_pos.pop(0)

    return hoop_pos
